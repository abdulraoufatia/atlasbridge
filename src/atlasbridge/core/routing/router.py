"""
Prompt router.

The PromptRouter sits between the PromptDetector and the Channel.

Forward path:
  PromptEvent → validate → route to channel → update session state

Return path:
  Reply → validate nonce/TTL/session → inject via adapter → update state

Routing rules:
  HIGH confidence  → route immediately
  MED confidence   → route if tty_blocked is True; else buffer for 1s
  LOW confidence   → ambiguity protocol (send SHOW_LAST_OUTPUT; wait for reply)
  No signal        → discard

One active prompt per session:
  If a new PromptEvent arrives while a prompt is AWAITING_REPLY, it is
  held in the session's pending queue until the active prompt is resolved.
"""

from __future__ import annotations

import logging
from typing import Any

from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptStatus, Reply
from atlasbridge.core.prompt.state import PromptStateMachine
from atlasbridge.core.session.manager import SessionManager

logger = logging.getLogger(__name__)


class PromptRouter:
    """
    Routes PromptEvents to the channel and routes Replies to the PTY.

    Dependencies are injected at construction time to keep the router
    testable without a live PTY or Telegram connection.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        channel: Any,  # BaseChannel — avoid circular import
        adapter_map: dict[str, Any],  # session_id → BaseAdapter
        store: Any,  # Database — for audit/idempotency
    ) -> None:
        self._sessions = session_manager
        self._channel = channel
        self._adapter_map = adapter_map
        self._store = store

        # Active state machines: prompt_id → PromptStateMachine
        self._machines: dict[str, PromptStateMachine] = {}
        # Per-session pending queue: session_id → [PromptEvent, ...]
        self._pending: dict[str, list[PromptEvent]] = {}

    # ------------------------------------------------------------------
    # Forward path
    # ------------------------------------------------------------------

    async def route_event(self, event: PromptEvent) -> None:
        """Route a PromptEvent to the channel, respecting confidence rules."""
        session = self._sessions.get_or_none(event.session_id)
        if session is None:
            logger.warning("Dropped event for unknown session %s", event.session_id)
            return

        # Queue if another prompt is already active for this session
        if session.active_prompt_id:
            self._pending.setdefault(event.session_id, []).append(event)
            logger.debug(
                "Queued prompt %s (session %s already has active prompt %s)",
                event.prompt_id,
                event.session_id[:8],
                session.active_prompt_id,
            )
            return

        # Confidence gate: LOW is routed to the channel so the user can decide.
        # The channel message labels it as "low (ambiguous)" so the user knows.
        if event.confidence == Confidence.LOW:
            logger.info(
                "LOW confidence prompt %s — routing as ambiguous (silence fallback)",
                event.prompt_id,
            )

        await self._dispatch(event)

    async def _dispatch(self, event: PromptEvent) -> None:
        """Send event to channel and register state machine."""
        # Enrich event with session context before dispatch
        session = self._sessions.get_or_none(event.session_id)
        if session:
            event.tool = session.tool
            event.cwd = session.cwd
            event.session_label = session.label

        sm = PromptStateMachine(event=event)
        self._machines[event.prompt_id] = sm

        try:
            sm.transition(PromptStatus.ROUTED, "dispatching to channel")
            message_id = await self._channel.send_prompt(event)

            sm.transition(PromptStatus.AWAITING_REPLY, "channel delivered prompt")
            self._sessions.mark_awaiting_reply(event.session_id, event.prompt_id)

            # Store message_id for later editing (e.g. resolved, expired)
            session = self._sessions.get_or_none(event.session_id)
            if session:
                session.channel_message_ids[event.prompt_id] = message_id

            logger.info(
                "Prompt %s routed to channel (session %s, type=%s, confidence=%s)",
                event.prompt_id,
                event.session_id[:8],
                event.prompt_type,
                event.confidence,
            )
        except Exception as exc:  # noqa: BLE001
            sm.transition(PromptStatus.FAILED, f"channel error: {exc}")
            logger.error("Failed to route prompt %s: %s", event.prompt_id, exc)

    # ------------------------------------------------------------------
    # Return path
    # ------------------------------------------------------------------

    async def handle_reply(self, reply: Reply) -> None:
        """Process an incoming Reply from the channel."""
        sm = self._machines.get(reply.prompt_id)
        if sm is None:
            logger.warning("Reply for unknown prompt %s", reply.prompt_id)
            await self._channel.notify(
                "Unknown prompt ID. This may be an old or invalid request.",
                session_id=reply.session_id,
            )
            return

        # TTL check
        if sm.expire_if_due():
            logger.info("Reply for expired prompt %s rejected", reply.prompt_id)
            await self._channel.notify(
                "This prompt has expired. The safe default was used.",
                session_id=reply.session_id,
            )
            await self._resolve_next(reply.session_id)
            return

        # Validate session binding
        if sm.event.session_id != reply.session_id and reply.session_id:
            logger.warning(
                "Reply session_id mismatch: prompt=%s reply=%s",
                sm.event.session_id,
                reply.session_id,
            )
            return

        # Identity allowlist (channel enforces; double-check here)
        if not self._channel.is_allowed(reply.channel_identity):
            logger.warning(
                "Reply from non-allowlisted identity %s rejected",
                reply.channel_identity,
            )
            return

        try:
            sm.transition(PromptStatus.REPLY_RECEIVED, f"reply from {reply.channel_identity}")

            adapter = self._adapter_map.get(sm.event.session_id)
            if adapter is None:
                raise RuntimeError(f"No adapter for session {sm.event.session_id}")

            await adapter.inject_reply(
                session_id=sm.event.session_id,
                value=reply.value,
                prompt_type=sm.event.prompt_type,
            )

            sm.transition(PromptStatus.INJECTED, "injected into PTY")
            sm.transition(PromptStatus.RESOLVED, "injection confirmed")

            self._sessions.mark_reply_received(sm.event.session_id)

            # Edit the Telegram message to show resolution
            session = self._sessions.get_or_none(sm.event.session_id)
            if session:
                msg_id = session.channel_message_ids.get(reply.prompt_id, "")
                if msg_id:
                    await self._channel.edit_prompt_message(
                        msg_id,
                        f"✓ Answered: {reply.value!r}",
                        session_id=sm.event.session_id,
                    )

            await self._resolve_next(sm.event.session_id)

        except Exception as exc:  # noqa: BLE001
            sm.transition(PromptStatus.FAILED, str(exc))
            logger.error("Injection failed for prompt %s: %s", reply.prompt_id, exc)

    async def _resolve_next(self, session_id: str) -> None:
        """After a prompt resolves, dispatch the next queued prompt if any."""
        queue = self._pending.get(session_id, [])
        if queue:
            next_event = queue.pop(0)
            await self._dispatch(next_event)

    # ------------------------------------------------------------------
    # TTL expiry sweep (called by scheduler)
    # ------------------------------------------------------------------

    async def expire_overdue(self) -> None:
        """Expire all overdue prompts. Called periodically by the scheduler."""
        for sm in list(self._machines.values()):
            if sm.expire_if_due():
                logger.info("Prompt %s expired (TTL elapsed)", sm.event.prompt_id)
                session = self._sessions.get_or_none(sm.event.session_id)
                if session:
                    msg_id = session.channel_message_ids.get(sm.event.prompt_id, "")
                    if msg_id:
                        await self._channel.edit_prompt_message(
                            msg_id,
                            "⏰ Prompt expired. Safe default applied.",
                            session_id=sm.event.session_id,
                        )
                await self._resolve_next(sm.event.session_id)
