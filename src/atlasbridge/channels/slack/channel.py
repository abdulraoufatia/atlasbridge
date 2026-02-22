"""
Slack channel implementation.

Uses httpx for Slack Web API calls (chat.postMessage, chat.update, conversations.open).
Uses Slack Socket Mode for receiving interactive component callbacks — requires the
optional ``atlasbridge[slack]`` extra (slack-sdk + websockets).

Block Kit message structure:
  section block — formatted prompt text (mrkdwn)
  actions block — interactive buttons (YES_NO, MULTIPLE_CHOICE, CONFIRM_ENTER)

Callback value format (same as Telegram for consistency):
  ans:{prompt_id}:{session_id}:{nonce}:{value}

Socket Mode:
  Requires a Slack App with Socket Mode enabled and an app-level token (xapp-*).
  If slack_sdk is not installed, interactive replies are unavailable but
  AtlasBridge can still SEND prompts to Slack.

Allowlist:
  Config key: channels.slack.allowed_users (list of Slack user IDs, e.g. "U1234567890")
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog

from atlasbridge.channels.base import BaseChannel
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType, Reply

logger = structlog.get_logger()

_SLACK_API_BASE = "https://slack.com/api/{method}"


class SlackChannel(BaseChannel):
    """
    Slack channel using the Slack Web API + Socket Mode.

    Requires:
      bot_token        — Slack Bot User OAuth Token (xoxb-*)
      app_token        — Slack App-Level Token for Socket Mode (xapp-*)
      allowed_user_ids — Slack user IDs permitted to reply (e.g. "U1234567890")
    """

    channel_name = "slack"
    display_name = "Slack"

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        allowed_user_ids: list[str],
        command_callback: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._app_token = app_token
        self._allowed: set[str] = set(allowed_user_ids)
        self._reply_queue: asyncio.Queue[Reply] = asyncio.Queue()
        self._running = False
        self._client: Any = None  # httpx.AsyncClient — created in start()
        self._dm_cache: dict[str, str] = {}  # user_id → DM channel_id
        self._command_callback = command_callback

    async def start(self) -> None:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx is required for the Slack channel. Install with: pip install httpx"
            ) from exc

        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self._bot_token}"},
            timeout=30.0,
        )
        self._running = True
        asyncio.create_task(self._socket_mode_loop(), name="slack_socket_mode")
        logger.info("slack_started")

    async def close(self) -> None:
        self._running = False
        if self._client:
            await self._client.aclose()
        logger.info("slack_closed")

    async def send_prompt(self, event: PromptEvent) -> str:
        """Send a Block Kit prompt to all allowlisted users via DM."""
        text = self._format_prompt(event)
        blocks = self._build_blocks(event)
        message_ids: list[str] = []

        for uid in self._allowed:
            ch_id = await self._get_dm_channel(uid)
            if not ch_id:
                continue
            result = await self._api(
                "chat.postMessage",
                {"channel": ch_id, "text": text, "blocks": blocks},
            )
            if result:
                ts = result.get("ts", "")
                if ts:
                    message_ids.append(f"{ch_id}:{ts}")

        return message_ids[0] if message_ids else ""

    async def notify(self, message: str, session_id: str = "") -> None:
        for uid in self._allowed:
            ch_id = await self._get_dm_channel(uid)
            if ch_id:
                await self._api("chat.postMessage", {"channel": ch_id, "text": message})

    async def send_output(self, text: str, session_id: str = "") -> None:
        if len(text) > 3000:
            text = text[:3000] + "\n...(truncated)"
        formatted = f"```\n{text}\n```"
        for uid in self._allowed:
            ch_id = await self._get_dm_channel(uid)
            if ch_id:
                await self._api(
                    "chat.postMessage",
                    {"channel": ch_id, "text": formatted},
                )

    async def send_agent_message(self, text: str, session_id: str = "") -> None:
        """Send agent prose with mrkdwn formatting (not code block)."""
        if len(text) > 3500:
            text = text[:3500] + "\n...(truncated)"
        for uid in self._allowed:
            ch_id = await self._get_dm_channel(uid)
            if ch_id:
                await self._api(
                    "chat.postMessage",
                    {"channel": ch_id, "text": text, "mrkdwn": True},
                )

    async def edit_prompt_message(
        self,
        message_id: str,
        new_text: str,
        session_id: str = "",
    ) -> None:
        # message_id = "{channel_id}:{ts}", e.g. "D12345:1234567890.123456"
        try:
            ch_id, ts = message_id.rsplit(":", 1)
        except ValueError:
            return
        await self._api(
            "chat.update",
            {"channel": ch_id, "ts": ts, "text": new_text, "blocks": []},
        )

    async def receive_replies(self) -> AsyncIterator[Reply]:
        while self._running:
            try:
                reply = await asyncio.wait_for(self._reply_queue.get(), timeout=1.0)
                yield reply
            except TimeoutError:
                continue

    def is_allowed(self, identity: str) -> bool:
        # identity = "slack:U1234567890"
        try:
            _, uid = identity.split(":", 1)
            return uid in self._allowed
        except (ValueError, AttributeError):
            return False

    def healthcheck(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._running else "stopped",
            "channel": self.channel_name,
            "allowed_users": len(self._allowed),
        }

    # ------------------------------------------------------------------
    # Socket Mode (receive interactive component callbacks)
    # ------------------------------------------------------------------

    async def _socket_mode_loop(self) -> None:
        """
        Listen for Slack interactive component callbacks via Socket Mode.

        Requires ``slack_sdk[socket-mode]`` and ``websockets``.
        Installs with: pip install "atlasbridge[slack]"

        If slack_sdk is not installed, this coroutine exits immediately
        with a warning — outgoing prompts still work, but interactive
        button replies will not be received.
        """
        try:
            from slack_sdk.socket_mode.websockets import SocketModeClient
        except ImportError:
            logger.warning(
                "slack_sdk_missing",
                hint="Install with: pip install 'atlasbridge[slack]'",
            )
            return

        from slack_sdk.socket_mode.response import SocketModeResponse

        client = SocketModeClient(
            app_token=self._app_token,
            web_client=None,  # We use httpx for API calls
        )

        async def _handle(client: Any, req: Any) -> None:
            try:
                if req.type == "interactive":
                    raw = req.payload.get("payload", "{}")
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                    if payload.get("type") == "block_actions":
                        user_id = payload.get("user", {}).get("id", "")
                        # Extract thread context for conversation binding
                        ch_info = payload.get("channel", {})
                        ch_id = ch_info.get("id", "") if isinstance(ch_info, dict) else ""
                        msg_ts = payload.get("message", {}).get("ts", "")
                        thread_id = f"{ch_id}:{msg_ts}" if ch_id and msg_ts else ""
                        for action in payload.get("actions", []):
                            value = action.get("value", "")
                            if value:
                                await self._handle_action(value, user_id, thread_id=thread_id)
                elif req.type == "slash_commands":
                    payload = req.payload or {}
                    cmd = payload.get("command", "").lower()
                    user_id = payload.get("user_id", "")
                    identity = f"slack:{user_id}"
                    if self.is_allowed(identity) and self._command_callback is not None and cmd:
                        try:
                            response_text = await self._command_callback(cmd, identity)
                        except Exception as exc:  # noqa: BLE001
                            response_text = f"Error: {exc}"
                        await client.send_socket_mode_response(
                            SocketModeResponse(
                                envelope_id=req.envelope_id,
                                payload={"text": response_text},
                            )
                        )
                        return
            except Exception as exc:  # noqa: BLE001
                logger.warning("slack_socket_handler_error", error=str(exc))
            finally:
                await client.send_socket_mode_response(
                    SocketModeResponse(envelope_id=req.envelope_id)
                )

        client.socket_mode_request_listeners.append(_handle)
        try:
            await client.connect()
            logger.info("slack_socket_connected")
            while self._running:
                await asyncio.sleep(1.0)
        except Exception as exc:  # noqa: BLE001
            logger.error("slack_socket_connection_error", error=str(exc))
        finally:
            await client.close()

    async def _handle_action(self, value: str, user_id: str, *, thread_id: str = "") -> None:
        """Parse callback value and enqueue Reply."""
        if not self.is_allowed(f"slack:{user_id}"):
            logger.warning("slack_action_rejected", user_id=user_id, reason="not_allowed")
            return
        try:
            parts = value.split(":", 4)
            if parts[0] != "ans" or len(parts) != 5:
                return
            _, prompt_id, session_id, nonce, val = parts
        except ValueError:
            return

        reply = Reply(
            prompt_id=prompt_id,
            session_id=session_id,
            value=val,
            nonce=nonce,
            channel_identity=f"slack:{user_id}",
            timestamp=datetime.now(UTC).isoformat(),
            thread_id=thread_id,
        )
        await self._reply_queue.put(reply)

    # ------------------------------------------------------------------
    # Slack API helpers
    # ------------------------------------------------------------------

    async def _get_dm_channel(self, user_id: str) -> str:
        """Open or retrieve an existing DM channel with *user_id*."""
        if user_id in self._dm_cache:
            return self._dm_cache[user_id]
        result = await self._api("conversations.open", {"users": user_id})
        if result:
            ch_id: str = result["channel"]["id"]
            self._dm_cache[user_id] = ch_id
            return ch_id
        return ""

    async def _api(self, method: str, payload: dict[str, Any]) -> Any:
        """Call a Slack Web API method. Returns the result dict or None on error."""
        if self._client is None:
            return None
        url = _SLACK_API_BASE.format(method=method)
        try:
            resp = await self._client.post(url, json=payload)
            data = resp.json()
            if data.get("ok"):
                return data
            logger.warning("slack_api_error", method=method, error=data.get("error"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("slack_api_request_failed", method=method, error=str(exc))
        return None

    # ------------------------------------------------------------------
    # Message formatting (static — testable without a live Slack connection)
    # ------------------------------------------------------------------

    @staticmethod
    def _format_prompt(event: PromptEvent) -> str:
        """Plain-text fallback for notifications and accessibility."""
        type_labels = {
            PromptType.TYPE_YES_NO: "Yes / No",
            PromptType.TYPE_CONFIRM_ENTER: "Press Enter",
            PromptType.TYPE_MULTIPLE_CHOICE: "Multiple Choice",
            PromptType.TYPE_FREE_TEXT: "Free Text",
        }
        label = type_labels.get(event.prompt_type, event.prompt_type)
        ttl_min = event.ttl_seconds // 60

        parts = [f"AtlasBridge — Input Required | Session: {event.session_id[:8]}"]
        if event.tool:
            parts.append(f"Tool: {event.tool}")
        if event.cwd:
            parts.append(f"Workspace: {event.cwd}")
        parts.append(f"Question: {event.excerpt[:120]}")
        parts.append(f"Expires in {ttl_min} min | Type: {label}")
        return " | ".join(parts)

    @staticmethod
    def _build_blocks(event: PromptEvent) -> list[dict[str, Any]]:
        """Build Slack Block Kit blocks for the prompt message."""
        type_labels = {
            PromptType.TYPE_YES_NO: "Yes / No",
            PromptType.TYPE_CONFIRM_ENTER: "Press Enter",
            PromptType.TYPE_MULTIPLE_CHOICE: "Multiple Choice",
            PromptType.TYPE_FREE_TEXT: "Free Text",
        }
        confidence_labels = {
            Confidence.HIGH: "high",
            Confidence.MED: "medium",
            Confidence.LOW: "low (ambiguous)",
        }
        response_instructions = {
            PromptType.TYPE_YES_NO: "Tap *Yes* or *No* below.",
            PromptType.TYPE_CONFIRM_ENTER: "Tap *Send Enter* below to continue.",
            PromptType.TYPE_MULTIPLE_CHOICE: "Tap a numbered option below.",
            PromptType.TYPE_FREE_TEXT: "Type your response and send it as a message.",
        }
        label = type_labels.get(event.prompt_type, event.prompt_type)
        conf = confidence_labels.get(event.confidence, event.confidence)
        instruction = response_instructions.get(event.prompt_type, "")
        ttl_min = event.ttl_seconds // 60

        # Header section
        header_text = f"*AtlasBridge* — Input Required\n\nSession: `{event.session_id[:8]}`"
        if event.tool:
            header_text += f"\nTool: {event.tool}"
        if event.cwd:
            header_text += f"\n\nWorkspace:\n{event.cwd}"

        blocks: list[dict[str, Any]] = [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": header_text},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Question:\n```{event.excerpt}```",
                },
            },
        ]

        if instruction:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"How to respond:\n{instruction}",
                    },
                }
            )

        # Footer context
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f":timer_clock: Expires in {ttl_min} minutes. "
                            f"Type: {label} | Confidence: {conf}"
                        ),
                    }
                ],
            }
        )

        # Action buttons
        base = f"ans:{event.prompt_id}:{event.session_id}:{event.idempotency_key}"

        if event.prompt_type == PromptType.TYPE_YES_NO:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Yes"},
                            "value": f"{base}:y",
                            "action_id": "atlasbridge_yes",
                            "style": "primary",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "No"},
                            "value": f"{base}:n",
                            "action_id": "atlasbridge_no",
                            "style": "danger",
                        },
                    ],
                }
            )
        elif event.prompt_type == PromptType.TYPE_CONFIRM_ENTER:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Send Enter"},
                            "value": f"{base}:enter",
                            "action_id": "atlasbridge_enter",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Cancel"},
                            "value": f"{base}:cancel",
                            "action_id": "atlasbridge_cancel",
                            "style": "danger",
                        },
                    ],
                }
            )
        elif event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE:
            elements = [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"{i + 1}. {c[:40]}" if c else str(i + 1),
                    },
                    "value": f"{base}:{i + 1}",
                    "action_id": f"atlasbridge_choice_{i + 1}",
                }
                for i, c in enumerate(event.choices)
            ]
            blocks.append({"type": "actions", "elements": elements})

        blocks.append({"type": "divider"})

        return blocks
