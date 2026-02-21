"""
Aegis Telegram bot — long-polling client with inline keyboard callbacks.

Architecture
------------
TelegramBot runs two async tasks:

1. _poll_loop: long-polls getUpdates, dispatches callback_query and
   message events to the response queue.
2. (caller-driven) send_prompt / send_message: outbound API calls.

The PTY supervisor owns the asyncio.Queue[str] that connects the bot
response to the injection side. The bot puts normalized response strings
into that queue; the supervisor dequeues and injects.

Security
--------
- Every incoming update is checked against allowed_users before processing.
- Callback data is validated: "ans:<prompt_id>:<nonce>:<value>" — the
  nonce is a one-time token stored in the DB; the DB decide_prompt()
  guard rejects replays and expired prompts.
- Free-text replies are length-capped at free_text_max_chars.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from aegis.channels.base import BaseChannel
from aegis.channels.telegram.templates import (
    format_already_decided,
    format_expired,
    format_prompt,
    format_response_accepted,
    format_session_ended,
    format_session_started,
    format_timeout_notice,
    parse_callback_data,
)
from aegis.core.constants import PromptStatus, PromptType
from aegis.store.database import Database
from aegis.store.models import PromptRecord

log = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_PARSE_MODE = "Markdown"


class TelegramBot(BaseChannel):
    """
    Telegram long-polling bot for the Aegis interactive bridge.

    Parameters
    ----------
    token: Telegram bot token (secret).
    allowed_users: Whitelist of Telegram user IDs.
    db: Database instance for prompt lookups and decisions.
    response_queue: asyncio.Queue to put normalised responses into.
    poll_timeout: Long-poll timeout in seconds (default 30).
    free_text_max_chars: Max chars for free-text replies (default 200).
    tool_name: Display name of the supervised tool.
    """

    def __init__(
        self,
        token: str,
        allowed_users: list[int],
        db: Database,
        response_queue: asyncio.Queue[tuple[str, str]],
        poll_timeout: int = 30,
        free_text_max_chars: int = 200,
        tool_name: str = "Claude Code",
    ) -> None:
        self._token = token
        self._allowed_users = set(allowed_users)
        self._db = db
        self._response_queue = response_queue
        self._poll_timeout = poll_timeout
        self._free_text_max_chars = free_text_max_chars
        self._tool_name = tool_name

        self._client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._offset: int = 0
        self._running = False

        # prompt_id → message_id for editing sent messages
        self._sent_messages: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open HTTP client and begin long-polling in background."""
        self._client = httpx.AsyncClient(timeout=self._poll_timeout + 10)
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop(), name="telegram-poll")
        log.info("Telegram bot started (long-poll timeout=%ds)", self._poll_timeout)

    async def close(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
            self._client = None
        log.info("Telegram bot stopped")

    # ------------------------------------------------------------------
    # BaseChannel implementation
    # ------------------------------------------------------------------

    async def send_prompt(self, prompt: PromptRecord) -> int | None:
        """Send a prompt message with inline keyboard. Returns message_id."""
        text, keyboard = format_prompt(prompt, tool=self._tool_name)
        payload: dict[str, Any] = {
            "text": text,
            "parse_mode": _PARSE_MODE,
        }
        if keyboard:
            payload["reply_markup"] = keyboard

        for uid in self._allowed_users:
            msg_id = await self._send_message_to(uid, **payload)
            if msg_id:
                self._sent_messages[prompt.id] = msg_id
                return msg_id
        return None

    async def send_message(self, text: str) -> None:
        for uid in self._allowed_users:
            await self._send_message_to(uid, text=text, parse_mode=_PARSE_MODE)

    async def send_timeout_notice(self, prompt: PromptRecord, injected: str) -> None:
        text = format_timeout_notice(prompt, injected, tool=self._tool_name)
        for uid in self._allowed_users:
            # Edit original message if we have its id, otherwise send new
            msg_id = self._sent_messages.get(prompt.id)
            if msg_id:
                await self._edit_message(uid, msg_id, text)
            else:
                await self._send_message_to(uid, text=text, parse_mode=_PARSE_MODE)

    async def notify_session_started(self, session_id: str, cwd: str) -> None:
        text = format_session_started(session_id, self._tool_name, cwd)
        await self.send_message(text)

    async def notify_session_ended(self, session_id: str, exit_code: int | None) -> None:
        text = format_session_ended(session_id, self._tool_name, exit_code)
        await self.send_message(text)

    # ------------------------------------------------------------------
    # Long-poll loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        log.debug("Telegram poll loop starting")
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    self._offset = max(self._offset, update["update_id"] + 1)
                    await self._dispatch(update)
            except asyncio.CancelledError:
                break
            except httpx.TimeoutException:
                # Normal during long-poll; just retry
                continue
            except Exception as exc:
                log.warning("Telegram poll error: %s", exc)
                await asyncio.sleep(5)

    async def _get_updates(self) -> list[dict[str, Any]]:
        assert self._client is not None
        resp = await self._call(
            "getUpdates",
            offset=self._offset,
            timeout=self._poll_timeout,
            allowed_updates=["callback_query", "message"],
        )
        return resp.get("result", [])

    async def _dispatch(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self._handle_callback(update["callback_query"])
        elif "message" in update:
            await self._handle_message(update["message"])

    # ------------------------------------------------------------------
    # Callback handler (button press)
    # ------------------------------------------------------------------

    async def _handle_callback(self, cq: dict[str, Any]) -> None:
        cq_id = cq.get("id", "")
        user = cq.get("from", {})
        user_id = user.get("id")

        if not self._is_allowed(user_id):
            await self._answer_callback(cq_id, "⛔ Unauthorized")
            log.warning("Rejected callback from user_id=%s", user_id)
            return

        data = cq.get("data", "")
        parsed = parse_callback_data(data)
        if not parsed:
            await self._answer_callback(cq_id, "⚠️ Invalid callback data")
            return

        prompt_id, nonce, value = parsed
        await self._process_response(
            prompt_id=prompt_id,
            nonce=nonce,
            raw_value=value,
            user_id=user_id,
            cq_id=cq_id,
            chat_id=cq.get("message", {}).get("chat", {}).get("id"),
            msg_id=cq.get("message", {}).get("message_id"),
        )

    async def _process_response(
        self,
        prompt_id: str,
        nonce: str,
        raw_value: str,
        user_id: int,
        cq_id: str | None,
        chat_id: int | None,
        msg_id: int | None,
    ) -> None:
        prompt = self._db.get_prompt(prompt_id)
        if not prompt:
            await self._answer_callback(cq_id, "⚠️ Prompt not found")
            return

        if prompt.is_expired:
            await self._answer_callback(cq_id, "⏰ Prompt expired")
            if chat_id and msg_id:
                await self._edit_message(chat_id, msg_id, format_expired(prompt))
            return

        # Normalise value
        normalized = _normalize_value(raw_value, prompt)
        decided_by = f"telegram:{user_id}"

        rows = self._db.decide_prompt(
            prompt_id=prompt_id,
            status=PromptStatus.RESPONSE_RECEIVED,
            decided_by=decided_by,
            response_normalized=normalized,
            nonce=nonce,
        )

        if rows == 0:
            # Already decided or nonce mismatch
            await self._answer_callback(cq_id, "⚠️ Already answered or expired")
            if chat_id and msg_id:
                updated = self._db.get_prompt(prompt_id)
                if updated:
                    await self._edit_message(chat_id, msg_id, format_already_decided(updated))
            return

        # Acknowledge and update message
        await self._answer_callback(cq_id, f"✅ Recorded: {normalized!r}")
        if chat_id and msg_id:
            await self._edit_message(chat_id, msg_id, format_response_accepted(prompt, normalized))

        # Signal the supervisor
        await self._response_queue.put((prompt_id, normalized))
        log.info(
            "Response accepted: prompt_id=%s value=%r by=%s", prompt_id, normalized, decided_by
        )

    # ------------------------------------------------------------------
    # Message handler (free-text reply)
    # ------------------------------------------------------------------

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        user = msg.get("from", {})
        user_id = user.get("id")
        if not self._is_allowed(user_id):
            return

        text = (msg.get("text") or "").strip()
        if not text:
            return

        # Reply-to-message handling: find which prompt this replies to
        reply_to = msg.get("reply_to_message")
        prompt = None
        if reply_to:
            reply_msg_id = reply_to.get("message_id")
            # Look up which prompt owned that message
            prompt = self._find_prompt_by_msg_id(reply_msg_id)

        if prompt is None:
            # No active free-text context — ignore
            return

        if prompt.input_type != PromptType.FREE_TEXT:
            # Not expecting free text for this prompt
            return

        if len(text) > self._free_text_max_chars:
            text = text[: self._free_text_max_chars]

        await self._process_response(
            prompt_id=prompt.id,
            nonce=prompt.nonce,
            raw_value=text,
            user_id=user_id,
            cq_id=None,
            chat_id=msg.get("chat", {}).get("id"),
            msg_id=None,
        )

    def _find_prompt_by_msg_id(self, msg_id: int | None) -> PromptRecord | None:
        if msg_id is None:
            return None
        for prompt_id, sent_id in self._sent_messages.items():
            if sent_id == msg_id:
                return self._db.get_prompt(prompt_id)
        return None

    # ------------------------------------------------------------------
    # Telegram API helpers
    # ------------------------------------------------------------------

    async def _call(self, method: str, **params: Any) -> dict[str, Any]:
        assert self._client is not None
        url = _API_BASE.format(token=self._token, method=method)
        resp = await self._client.post(url, json=params)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            log.error("Telegram API error (%s): %s", method, data)
        return data

    async def _send_message_to(self, chat_id: int, **kwargs: Any) -> int | None:
        try:
            data = await self._call("sendMessage", chat_id=chat_id, **kwargs)
            return data.get("result", {}).get("message_id")
        except Exception as exc:
            log.error("sendMessage to %s failed: %s", chat_id, exc)
            return None

    async def _edit_message(self, chat_id: int, msg_id: int, text: str) -> None:
        try:
            await self._call(
                "editMessageText",
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                parse_mode=_PARSE_MODE,
            )
        except Exception as exc:
            log.debug("editMessageText failed (ok if already edited): %s", exc)

    async def _answer_callback(self, cq_id: str | None, text: str) -> None:
        if not cq_id:
            return
        try:
            await self._call("answerCallbackQuery", callback_query_id=cq_id, text=text)
        except Exception as exc:
            log.debug("answerCallbackQuery failed: %s", exc)

    def _is_allowed(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self._allowed_users


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------


def _normalize_value(raw: str, prompt: PromptRecord) -> str:
    """
    Translate a raw callback value into the string that will be injected.

    "default" → the prompt's safe_default
    "y"/"n"   → kept as-is
    "enter"   → newline
    digit     → kept as-is (multiple choice option number)
    free text → passed through (already length-capped by caller)
    """
    if raw == "default":
        return prompt.safe_default
    if raw == "enter":
        return "\n"
    return raw
