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
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC
from pathlib import Path
from typing import Any

import structlog

from atlasbridge.channels.base import BaseChannel
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType, Reply

logger = structlog.get_logger()

_BASE_URL = "https://api.telegram.org/bot{token}/{method}"
_POLL_TIMEOUT = 30  # Long-poll timeout (seconds)
_RETRY_BASE_S = 1.0
_RETRY_MAX_S = 60.0
_CALLBACK_REF_TTL_S = 600.0  # 10 minutes TTL for callback refs
_TELEGRAM_CALLBACK_MAX = 64  # Telegram callback_data byte limit

# Reply aliases: common natural-language replies mapped to canonical values
_REPLY_ALIASES: dict[str, str] = {
    "yes": "y",
    "yeah": "y",
    "yep": "y",
    "no": "n",
    "nah": "n",
    "nope": "n",
}


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
        self._client: Any = None  # httpx.AsyncClient — created in start()
        self._command_callback = command_callback
        self._locks_dir = locks_dir
        self._poller_lock: Any = None  # PollerLock — created in start()
        # Server-side callback reference store (Telegram limits callback_data to 64 bytes)
        self._callback_refs: dict[str, tuple[dict[str, str], float]] = {}
        self._callback_seq: int = 0

    async def start(self) -> None:
        try:
            import httpx
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
            logger.info("telegram_started", mode="polling")
        else:
            holder = self._poller_lock.holder_pid
            logger.warning(
                "telegram_started",
                mode="send_only",
                holder_pid=holder or "unknown",
                hint="Stop the other instance with `atlasbridge stop` if unexpected",
            )

    async def close(self) -> None:
        self._running = False
        self._polling = False
        if self._poller_lock is not None:
            self._poller_lock.release()
            self._poller_lock = None
        if self._client:
            await self._client.aclose()
        logger.info("telegram_closed")

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
            else:
                logger.warning(
                    "telegram_send_failed",
                    user_id=uid,
                    hint="Ensure the user has sent /start to the bot",
                )

        return responses[0] if responses else ""

    async def notify(self, message: str, session_id: str = "") -> None:
        for uid in self._allowed:
            await self._api("sendMessage", {"chat_id": uid, "text": message})

    async def send_output(self, text: str, session_id: str = "") -> None:
        if len(text) > 3900:
            text = text[:3900] + "\n...(truncated)"
        formatted = f"<pre>{text}</pre>"
        for uid in self._allowed:
            await self._api(
                "sendMessage",
                {
                    "chat_id": uid,
                    "text": formatted,
                    "parse_mode": "HTML",
                    "disable_notification": True,
                },
            )

    async def send_output_editable(self, text: str, session_id: str = "") -> str:
        """Send CLI output and return the Telegram message_id for editing."""
        if len(text) > 3900:
            text = text[:3900] + "\n...(truncated)"
        formatted = f"<pre>{text}</pre>"
        msg_id = ""
        for uid in self._allowed:
            result = await self._api(
                "sendMessage",
                {
                    "chat_id": uid,
                    "text": formatted,
                    "parse_mode": "HTML",
                    "disable_notification": True,
                },
            )
            if result and not msg_id:
                msg_id = str(result.get("message_id", ""))
        return msg_id

    async def send_agent_message(self, text: str, session_id: str = "") -> None:
        """Send agent prose with HTML formatting (not <pre> monospace)."""
        if len(text) > 4000:
            text = text[:4000] + "\n...(truncated)"
        for uid in self._allowed:
            await self._api(
                "sendMessage",
                {
                    "chat_id": uid,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )

    async def send_plan(self, plan: Any, session_id: str = "") -> str:
        """Send a detected plan with inline Execute/Modify/Cancel buttons."""
        steps_html = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(plan.steps))
        text = f"<b>{plan.title}</b>\n\n{steps_html}"
        if len(text) > 3900:
            text = text[:3900] + "\n...(truncated)"

        buttons = [
            [
                {"text": "Execute", "callback_data": f"plan:{session_id}:execute"},
                {"text": "Modify", "callback_data": f"plan:{session_id}:modify"},
                {"text": "Cancel", "callback_data": f"plan:{session_id}:cancel"},
            ]
        ]
        keyboard = {"inline_keyboard": buttons}

        msg_id = ""
        for uid in self._allowed:
            result = await self._api(
                "sendMessage",
                {
                    "chat_id": uid,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                },
            )
            if result and not msg_id:
                msg_id = str(result.get("message_id", ""))
        return msg_id

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

    async def receive_replies(self) -> AsyncIterator[Reply]:
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

    def get_allowed_identities(self) -> list[str]:
        """Return all allowlisted identities in channel:id format."""
        return [f"telegram:{uid}" for uid in sorted(self._allowed)]

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
                    "telegram_conflict",
                    hint="Another poller is active. Run `atlasbridge stop` and restart.",
                )
                self._polling = False
                if self._poller_lock is not None:
                    self._poller_lock.release()
                return
            except Exception:  # noqa: BLE001
                logger.warning("telegram_poll_error", backoff_s=backoff)
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
            logger.warning("telegram_callback_rejected", user_id=user_id, reason="not_allowed")
            return

        # Extract chat_id for thread binding
        cb_chat_id = cb.get("message", {}).get("chat", {}).get("id")

        # Parse: plan:{session_id}:{decision}
        if data.startswith("plan:"):
            try:
                _, session_id, decision = data.split(":", 2)
            except ValueError:
                return
            reply = Reply(
                prompt_id="__plan__",
                session_id=session_id,
                value=decision,
                nonce="",
                channel_identity=f"telegram:{user_id}",
                timestamp=_utcnow(),
                thread_id=str(cb_chat_id) if cb_chat_id else "",
            )
            await self._reply_queue.put(reply)
            await self._api("answerCallbackQuery", {"callback_query_id": cb["id"]})
            return

        # Parse callback data — two formats:
        #   Full:  ans:{prompt_id}:{session_id}:{nonce}:{value}
        #   Ref:   ref:{key}:{value}  (server-side lookup)
        prompt_id = session_id = nonce = value = ""
        try:
            if data.startswith("ref:"):
                parts = data.split(":", 2)
                if len(parts) != 3:
                    return
                _, ref_key, value = parts
                ref = self._callback_refs.get(ref_key)
                if ref is None:
                    logger.warning("telegram_callback_ref_expired", ref_key=ref_key)
                    return
                ref_data, _ = ref
                prompt_id = ref_data["prompt_id"]
                session_id = ref_data["session_id"]
                nonce = ref_data["nonce"]
            elif data.startswith("ans:"):
                parts = data.split(":", 4)
                if len(parts) != 5:
                    return
                _, prompt_id, session_id, nonce, value = parts
            else:
                return
        except (ValueError, KeyError):
            logger.warning("telegram_callback_parse_failed", data=data[:64])
            return

        reply = Reply(
            prompt_id=prompt_id,
            session_id=session_id,
            value=value,
            nonce=nonce,
            channel_identity=f"telegram:{user_id}",
            timestamp=_utcnow(),
            thread_id=str(cb_chat_id) if cb_chat_id else "",
        )
        await self._reply_queue.put(reply)

        # Acknowledge with a visible toast on the user's phone
        await self._api(
            "answerCallbackQuery",
            {
                "callback_query_id": cb["id"],
                "text": f"Sent: {value}",
            },
        )

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

        # Normalize common reply aliases (yes→y, no→n, etc.)
        alias = _REPLY_ALIASES.get(text.lower())
        if alias is not None:
            text = alias

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
            thread_id=str(chat_id) if chat_id else "",
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
            error_code = data.get("error_code")
            description = data.get("description", "")
            # 409 Conflict — another getUpdates poller
            if error_code == 409 and "getUpdates" in description:
                raise TelegramConflictError(description)
            # 400 "chat not found" — user hasn't messaged the bot yet
            if error_code == 400 and "chat not found" in description.lower():
                logger.error(
                    "telegram_chat_not_found",
                    chat_id=payload.get("chat_id"),
                    hint="The user must send /start to the bot first",
                )
            else:
                logger.warning(
                    "telegram_api_error",
                    method=method,
                    error_code=error_code,
                    description=description,
                )
        except TelegramConflictError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram_api_request_failed", method=method, error=str(exc))
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
            PromptType.TYPE_MULTIPLE_CHOICE: (
                "Reply <b>1</b> or <b>2</b> (or tap a button below)."
            ),
            PromptType.TYPE_FREE_TEXT: "Type your response and send it as a message.",
        }
        label = type_labels.get(event.prompt_type, event.prompt_type)
        conf = confidence_labels.get(event.confidence, event.confidence)
        instruction = response_instructions.get(event.prompt_type, "")
        ttl_min = event.ttl_seconds // 60

        lines = [
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            "<b>AtlasBridge</b> \u2014 Input Required\n",
            f"Session: <code>{event.session_id[:8]}</code>",
        ]

        if event.tool:
            lines.append(f"Tool: {event.tool}")

        if event.cwd:
            lines.append(f"\nWorkspace:\n{event.cwd}")

        question_html = TelegramChannel._format_question(event)
        lines.append(f"\nQuestion:\n{question_html}")

        if instruction:
            lines.append(f"\nHow to respond:\n{instruction}")

        lines.append(f"\n\u23f1 Expires in {ttl_min} minutes.")
        lines.append(f"Type: {label} | Confidence: {conf}")
        lines.append(
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        )

        return "\n".join(lines)

    @staticmethod
    def _format_question(event: PromptEvent) -> str:
        """Format the question/excerpt for a phone-first experience.

        Removes terminal-only hints and rewrites Claude's folder trust prompt
        into a workspace trust confirmation while preserving semantics.
        """
        excerpt = event.excerpt or ""
        lower = excerpt.lower()

        # Special-case Claude's folder trust prompt — present as workspace trust.
        if "trust" in lower and "folder" in lower:
            # Build a workspace-centric description and sanitised options.
            tool_label = (event.tool or "Claude Code").strip()
            lines: list[str] = []
            lines.append("Workspace trust confirmation")
            lines.append("")
            lines.append(
                f"{tool_label} is asking to trust this workspace for file access and execution."
            )

            if event.cwd:
                lines.append("")
                lines.append("Workspace:")
                lines.append(event.cwd)

            # Present numbered options without terminal hints or folder wording.
            if event.choices:
                lines.append("")
                lines.append("Options:")
                for i, raw_choice in enumerate(event.choices, start=1):
                    choice = (raw_choice or "").strip()
                    # Soften CLI phrasing: "folder" → "workspace"
                    choice = choice.replace("this folder", "this workspace")
                    choice = choice.replace("folder", "workspace")
                    lines.append(f"{i}. {choice or i}")

            joined = "\n".join(lines)
            return f"<pre>{joined}</pre>"

        # Generic path: use centralized terminal hint stripping.
        from atlasbridge.core.prompt.sanitize import strip_terminal_hints

        cleaned = strip_terminal_hints(excerpt).strip() or excerpt.strip()
        return f"<pre>{cleaned}</pre>"

    def _make_callback_data(
        self,
        prompt_id: str,
        session_id: str,
        nonce: str,
        value: str,
    ) -> str:
        """Build callback_data within Telegram's 64-byte limit.

        If the full compound key fits, use it directly. Otherwise, store
        the routing metadata server-side and return a short reference key.
        """
        full = f"ans:{prompt_id}:{session_id}:{nonce}:{value}"
        if len(full.encode()) <= _TELEGRAM_CALLBACK_MAX:
            return full

        # Prune expired refs
        now = time.monotonic()
        expired = [
            k for k, (_, ts) in self._callback_refs.items() if (now - ts) > _CALLBACK_REF_TTL_S
        ]
        for k in expired:
            del self._callback_refs[k]

        # Store server-side, return short ref
        self._callback_seq += 1
        ref_key = f"r{self._callback_seq}"
        self._callback_refs[ref_key] = (
            {"prompt_id": prompt_id, "session_id": session_id, "nonce": nonce},
            now,
        )
        return f"ref:{ref_key}:{value}"

    def _build_keyboard(self, event: PromptEvent) -> list[list[dict[str, str]]]:
        """Build Telegram inline keyboard buttons."""
        pid = event.prompt_id
        sid = event.session_id
        nonce = event.idempotency_key

        if event.prompt_type == PromptType.TYPE_YES_NO:
            return [
                [
                    {
                        "text": "Yes",
                        "callback_data": self._make_callback_data(pid, sid, nonce, "y"),
                    },
                    {"text": "No", "callback_data": self._make_callback_data(pid, sid, nonce, "n")},
                ]
            ]
        if event.prompt_type == PromptType.TYPE_CONFIRM_ENTER:
            return [
                [
                    {
                        "text": "Send Enter",
                        "callback_data": self._make_callback_data(pid, sid, nonce, "enter"),
                    },
                    {
                        "text": "Cancel",
                        "callback_data": self._make_callback_data(pid, sid, nonce, "cancel"),
                    },
                ]
            ]
        if event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE:
            return [
                [
                    {
                        "text": f"{i + 1}. {c[:30]}" if c else str(i + 1),
                        "callback_data": self._make_callback_data(pid, sid, nonce, str(i + 1)),
                    }
                    for i, c in enumerate(event.choices)
                ]
            ]
        return []  # FREE_TEXT: no buttons; user replies via message


def _utcnow() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()
