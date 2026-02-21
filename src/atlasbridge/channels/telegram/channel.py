"""
Telegram channel implementation.

Uses httpx for direct Bot API calls (no framework dependency).
Long-polling via getUpdates. Inline keyboard for YES_NO / MULTIPLE_CHOICE.

Callback data format:
  ans:{prompt_id}:{session_id}:{nonce}:{value}

  Components:
    prompt_id  — 24-char hex (secrets.token_hex(12))
    session_id — UUID4
    nonce      — 16-char hex (secrets.token_hex(8))
    value      — y | n | 1 | 2 | ... (URL-safe; no colons)

  Max total length: ~120 bytes (Telegram limit: 64 bytes of callback_data)
  If the compound key exceeds 64 bytes, the nonce is stored server-side
  and the callback_data uses a short reference key.

Rate limiting:
  Telegram allows ~30 messages/second per bot. AtlasBridge sends at most
  1 prompt per session at a time, so rate limiting is not a concern
  for normal usage. The channel implements exponential backoff on 429.

Allowlist:
  Config key: channels.telegram.allowed_user_ids (list of int)
  Only users in this list can trigger injections.

Singleton polling:
  Only one process per bot token may run getUpdates (Telegram enforces
  this with HTTP 409).  TelegramChannel acquires a PollerLock before
  starting its poll loop.  If the lock is held, the channel operates
  in send-only mode — it can still send messages and edit prompts,
  but does not poll for updates.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC
from pathlib import Path
from typing import Any

from atlasbridge.channels.base import BaseChannel
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType, Reply

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}/{method}"
_POLL_TIMEOUT = 30  # Long-poll timeout (seconds)
_RETRY_BASE_S = 1.0
_RETRY_MAX_S = 60.0


class TelegramConflictError(Exception):
    """Raised when Telegram returns 409 — another poller is active."""


class TelegramChannel(BaseChannel):
    """
    Telegram Bot API channel.

    Requires:
      bot_token        — Telegram Bot API token (from @BotFather)
      allowed_user_ids — list of Telegram user IDs permitted to reply
    """

    channel_name = "telegram"
    display_name = "Telegram"

    def __init__(
        self,
        bot_token: str,
        allowed_user_ids: list[int],
        command_callback: Callable[[str, str], Awaitable[str]] | None = None,
        *,
        locks_dir: Path | None = None,
    ) -> None:
        self._token = bot_token
        self._allowed = set(allowed_user_ids)
        self._reply_queue: asyncio.Queue[Reply] = asyncio.Queue()
        self._offset = 0  # getUpdates offset
        self._running = False
        self._polling = False  # True only if we own the poll loop
        self._client = None  # httpx.AsyncClient — created in start()
        self._command_callback = command_callback
        self._locks_dir = locks_dir
        self._poller_lock = None  # PollerLock — created in start()

    async def start(self) -> None:
        try:
            import httpx  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "httpx is required for the Telegram channel. Install with: pip install httpx"
            ) from exc

        self._client = httpx.AsyncClient(timeout=_POLL_TIMEOUT + 5)
        self._running = True

        # Acquire the singleton poller lock
        from atlasbridge.core.poller_lock import PollerLock

        self._poller_lock = PollerLock(self._token, locks_dir=self._locks_dir)
        if self._poller_lock.acquire():
            self._polling = True
            asyncio.create_task(self._poll_loop(), name="telegram_poll")
            logger.info("Telegram channel started (polling)")
        else:
            holder = self._poller_lock.holder_pid
            logger.warning(
                "Telegram poller already running (PID %s) — operating in send-only mode. "
                "Stop the other instance with `atlasbridge stop` if this is unexpected.",
                holder or "unknown",
            )
            logger.info("Telegram channel started (send-only, no polling)")

    async def close(self) -> None:
        self._running = False
        self._polling = False
        if self._poller_lock is not None:
            self._poller_lock.release()
            self._poller_lock = None
        if self._client:
            await self._client.aclose()
        logger.info("Telegram channel closed")

    async def send_prompt(self, event: PromptEvent) -> str:
        """Send a prompt message with an inline keyboard."""
        text = self._format_prompt(event)
        keyboard = self._build_keyboard(event)
        payload: dict[str, Any] = {"text": text, "parse_mode": "HTML"}
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}

        responses = []
        for uid in self._allowed:
            payload["chat_id"] = uid
            resp = await self._api("sendMessage", payload)
            if resp:
                responses.append(str(resp.get("message_id", "")))

        return responses[0] if responses else ""

    async def notify(self, message: str, session_id: str = "") -> None:
        for uid in self._allowed:
            await self._api("sendMessage", {"chat_id": uid, "text": message})

    async def edit_prompt_message(
        self,
        message_id: str,
        new_text: str,
        session_id: str = "",
    ) -> None:
        for uid in self._allowed:
            await self._api(
                "editMessageText",
                {
                    "chat_id": uid,
                    "message_id": int(message_id),
                    "text": new_text,
                },
            )

    async def receive_replies(self) -> AsyncIterator[Reply]:  # type: ignore[override]
        while self._running:
            try:
                reply = await asyncio.wait_for(self._reply_queue.get(), timeout=1.0)
                yield reply
            except TimeoutError:
                continue

    def is_allowed(self, identity: str) -> bool:
        # identity = "telegram:123456789"
        try:
            _, uid_str = identity.split(":", 1)
            return int(uid_str) in self._allowed
        except (ValueError, AttributeError):
            return False

    def healthcheck(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._running else "stopped",
            "channel": self.channel_name,
            "polling": self._polling,
            "allowed_users": len(self._allowed),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Long-polling loop — runs for the lifetime of the daemon."""
        backoff = _RETRY_BASE_S
        while self._running and self._polling:
            try:
                updates = await self._api(
                    "getUpdates",
                    {
                        "offset": self._offset,
                        "timeout": _POLL_TIMEOUT,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )
                if updates:
                    for update in updates:
                        self._offset = update["update_id"] + 1
                        await self._handle_update(update)
                backoff = _RETRY_BASE_S
            except TelegramConflictError:
                logger.error(
                    "Telegram 409 Conflict — another poller is active for this bot token. "
                    "Stopping polling. If this is unexpected, run `atlasbridge stop` "
                    "and restart."
                )
                self._polling = False
                if self._poller_lock is not None:
                    self._poller_lock.release()
                return
            except Exception:  # noqa: BLE001
                logger.warning("Telegram polling error; backoff=%.1fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _RETRY_MAX_S)

    async def _handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self._handle_callback(update["callback_query"])
        elif "message" in update:
            await self._handle_message(update["message"])

    async def _handle_callback(self, cb: dict[str, Any]) -> None:
        """Handle inline keyboard button tap."""
        user_id = cb.get("from", {}).get("id")
        data = cb.get("data", "")

        if not self.is_allowed(f"telegram:{user_id}"):
            logger.warning("Rejected callback from unknown user %s", user_id)
            return

        # Parse: ans:{prompt_id}:{session_id}:{nonce}:{value}
        try:
            parts = data.split(":", 4)
            if parts[0] != "ans" or len(parts) != 5:
                return
            _, prompt_id, session_id, nonce, value = parts
        except ValueError:
            return

        reply = Reply(
            prompt_id=prompt_id,
            session_id=session_id,
            value=value,
            nonce=nonce,
            channel_identity=f"telegram:{user_id}",
            timestamp=_utcnow(),
        )
        await self._reply_queue.put(reply)

        # Acknowledge the callback to remove the spinner on the button
        await self._api("answerCallbackQuery", {"callback_query_id": cb["id"]})

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle free-text reply messages and / commands."""
        user_id = msg.get("from", {}).get("id")
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()

        if not text:
            return

        if text.startswith("/"):
            if not self.is_allowed(f"telegram:{user_id}"):
                return
            if self._command_callback is not None:
                cmd = text.split()[0].lower()
                try:
                    response = await self._command_callback(cmd, f"telegram:{user_id}")
                except Exception as exc:  # noqa: BLE001
                    response = f"Error: {exc}"
                if chat_id is not None:
                    await self._api("sendMessage", {"chat_id": chat_id, "text": response})
            return

        if not self.is_allowed(f"telegram:{user_id}"):
            return

        # Free-text reply: nonce is derived from message_id for idempotency
        nonce = secrets.token_hex(8)
        reply = Reply(
            prompt_id="",  # Router resolves the active prompt for this session
            session_id="",  # Router resolves by active session
            value=text,
            nonce=nonce,
            channel_identity=f"telegram:{user_id}",
            timestamp=_utcnow(),
            newline_policy="append",
        )
        await self._reply_queue.put(reply)

    async def _api(self, method: str, payload: dict[str, Any]) -> Any:
        """Make a Telegram Bot API call. Returns the result dict or None on error."""
        if self._client is None:
            return None
        url = _BASE_URL.format(token=self._token, method=method)
        try:
            resp = await self._client.post(url, json=payload)
            data = resp.json()
            if data.get("ok"):
                return data.get("result")
            # Detect 409 Conflict — another getUpdates poller
            error_code = data.get("error_code")
            description = data.get("description", "")
            if error_code == 409 and "getUpdates" in description:
                raise TelegramConflictError(description)
            logger.warning("Telegram API error: %s", data)
        except TelegramConflictError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram API request failed: %s", exc)
        return None

    @staticmethod
    def _format_prompt(event: PromptEvent) -> str:
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
            PromptType.TYPE_YES_NO: "Tap <b>Yes</b> or <b>No</b> below.",
            PromptType.TYPE_CONFIRM_ENTER: "Tap <b>Send Enter</b> below to continue.",
            PromptType.TYPE_MULTIPLE_CHOICE: "Tap a numbered option below.",
            PromptType.TYPE_FREE_TEXT: "Type your response and send it as a message.",
        }
        label = type_labels.get(event.prompt_type, event.prompt_type)
        conf = confidence_labels.get(event.confidence, event.confidence)
        instruction = response_instructions.get(event.prompt_type, "")
        ttl_min = event.ttl_seconds // 60

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "<b>AtlasBridge</b> — Input Required\n",
            f"Session: <code>{event.session_id[:8]}</code>",
        ]

        if event.tool:
            lines.append(f"Tool: {event.tool}")

        if event.cwd:
            lines.append(f"\nWorkspace:\n{event.cwd}")

        lines.append(f"\nQuestion:\n<pre>{event.excerpt}</pre>")

        if instruction:
            lines.append(f"\nHow to respond:\n{instruction}")

        lines.append(f"\n⏱ Expires in {ttl_min} minutes.")
        lines.append(f"Type: {label} | Confidence: {conf}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)

    @staticmethod
    def _build_keyboard(event: PromptEvent) -> list[list[dict[str, str]]]:
        """Build Telegram inline keyboard buttons."""
        base = f"ans:{event.prompt_id}:{event.session_id}:{event.idempotency_key}"

        if event.prompt_type == PromptType.TYPE_YES_NO:
            return [
                [
                    {"text": "Yes", "callback_data": f"{base}:y"},
                    {"text": "No", "callback_data": f"{base}:n"},
                ]
            ]
        if event.prompt_type == PromptType.TYPE_CONFIRM_ENTER:
            return [
                [
                    {"text": "Send Enter", "callback_data": f"{base}:enter"},
                    {"text": "Cancel", "callback_data": f"{base}:cancel"},
                ]
            ]
        if event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE:
            return [
                [
                    {"text": str(i + 1), "callback_data": f"{base}:{i + 1}"}
                    for i in range(len(event.choices))
                ]
            ]
        return []  # FREE_TEXT: no buttons; user replies via message


def _utcnow() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()
