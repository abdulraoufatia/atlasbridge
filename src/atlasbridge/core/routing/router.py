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

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptStatus, Reply
from atlasbridge.core.prompt.state import PromptStateMachine
from atlasbridge.core.session.manager import SessionManager

logger = structlog.get_logger()


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
        interaction_engine: Any = None,  # InteractionEngine — optional
        chat_mode_handler: Callable[[Reply], Awaitable[Any]] | None = None,
        conversation_registry: Any = None,  # ConversationRegistry — optional
    ) -> None:
        self._sessions = session_manager
        self._channel = channel
        self._adapter_map = adapter_map
        self._store = store
        self._interaction_engine = interaction_engine
        self._chat_mode_handler = chat_mode_handler
        self._conversation_registry = conversation_registry

        # Active state machines: prompt_id → PromptStateMachine
        self._machines: dict[str, PromptStateMachine] = {}
        # Per-session pending queue: session_id → [PromptEvent, ...]
        self._pending: dict[str, list[PromptEvent]] = {}

    # ------------------------------------------------------------------
    # Forward path
    # ------------------------------------------------------------------

    async def route_event(self, event: PromptEvent) -> None:
        """Route a PromptEvent to the channel, respecting confidence rules."""
        log = logger.bind(
            session_id=event.session_id[:8],
            prompt_id=event.prompt_id,
            prompt_type=event.prompt_type,
            confidence=event.confidence,
        )

        session = self._sessions.get_or_none(event.session_id)
        if session is None:
            log.warning("event_dropped_unknown_session")
            return

        # Queue if another prompt is already active for this session
        if session.active_prompt_id:
            self._pending.setdefault(event.session_id, []).append(event)
            log.debug("event_queued", active_prompt=session.active_prompt_id)
            return

        # Confidence gate: LOW is routed to the channel so the user can decide.
        # The channel message labels it as "low (ambiguous)" so the user knows.
        if event.confidence == Confidence.LOW:
            log.info("routing_low_confidence", trigger="silence_fallback")

        await self._dispatch(event)

    async def _dispatch(self, event: PromptEvent) -> None:
        """Send event to channel and register state machine."""
        log = logger.bind(
            session_id=event.session_id[:8],
            prompt_id=event.prompt_id,
            prompt_type=event.prompt_type,
            confidence=event.confidence,
        )

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

            log.info("prompt_routed", message_id=message_id)
        except Exception as exc:  # noqa: BLE001
            sm.transition(PromptStatus.FAILED, f"channel error: {exc}")
            log.error("prompt_route_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Return path
    # ------------------------------------------------------------------

    async def handle_reply(self, reply: Reply) -> None:
        """Process an incoming Reply from the channel."""
        # Free-text replies have empty prompt_id — resolve to active prompt
        if not reply.prompt_id:
            resolved = self._resolve_free_text_reply(reply)
            if resolved is None:
                # No active prompt — route to chat mode if handler is set
                if self._chat_mode_handler is not None:
                    logger.info(
                        "chat_mode_input",
                        channel_identity=reply.channel_identity,
                        value_length=len(reply.value),
                    )
                    await self._chat_mode_handler(reply)
                    return
                logger.debug("free_text_reply_dropped", reason="no_active_prompt")
                return
            reply = resolved

        log = logger.bind(
            prompt_id=reply.prompt_id,
            session_id=reply.session_id[:8] if reply.session_id else "",
            channel_identity=reply.channel_identity,
        )

        sm = self._machines.get(reply.prompt_id)
        if sm is None:
            log.debug("reply_ignored", reason="unknown_prompt")
            return

        # Already resolved — silently discard duplicate callbacks
        if sm.is_terminal:
            log.debug("reply_ignored", reason="already_resolved")
            return

        # TTL check
        if sm.expire_if_due():
            log.info("reply_rejected", reason="expired")
            await self._channel.notify(
                "This prompt has expired. The safe default was used.",
                session_id=reply.session_id,
            )
            await self._resolve_next(reply.session_id)
            return

        # Validate session binding
        if sm.event.session_id != reply.session_id and reply.session_id:
            log.warning(
                "reply_rejected",
                reason="session_mismatch",
                expected_session=sm.event.session_id[:8],
            )
            return

        # Identity allowlist (channel enforces; double-check here)
        if not self._channel.is_allowed(reply.channel_identity):
            log.warning("reply_rejected", reason="identity_not_allowed")
            return

        try:
            sm.transition(PromptStatus.REPLY_RECEIVED, f"reply from {reply.channel_identity}")

            if self._interaction_engine is not None:
                # Use the interaction engine (classify → plan → execute → feedback)
                result = await self._interaction_engine.handle_prompt_reply(sm.event, reply)

                if result.success:
                    sm.transition(PromptStatus.INJECTED, "injected via interaction engine")
                    sm.transition(PromptStatus.RESOLVED, "interaction engine confirmed")
                elif result.escalated:
                    sm.transition(PromptStatus.FAILED, "escalated: retries exhausted")
                else:
                    sm.transition(PromptStatus.INJECTED, "injected via interaction engine")
                    sm.transition(PromptStatus.RESOLVED, "injection completed (stalled)")

                self._sessions.mark_reply_received(sm.event.session_id)

                # Edit the channel message with structured feedback
                feedback = result.feedback_message or f"✓ Answered: {result.injected_value!r}"
                session = self._sessions.get_or_none(sm.event.session_id)
                if session:
                    msg_id = session.channel_message_ids.get(reply.prompt_id, "")
                    if msg_id:
                        await self._channel.edit_prompt_message(
                            msg_id,
                            feedback,
                            session_id=sm.event.session_id,
                        )
            else:
                # Direct injection path (no interaction engine)
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

                # Edit the channel message to show resolution
                session = self._sessions.get_or_none(sm.event.session_id)
                if session:
                    msg_id = session.channel_message_ids.get(reply.prompt_id, "")
                    if msg_id:
                        await self._channel.edit_prompt_message(
                            msg_id,
                            f"✓ Answered: {reply.value!r}",
                            session_id=sm.event.session_id,
                        )

            latency = sm.latency_ms
            log.info(
                "reply_injected",
                value_length=len(reply.value),
                latency_ms=round(latency, 1) if latency else None,
            )

            # Bind thread→session in conversation registry
            if self._conversation_registry is not None and reply.thread_id and sm.event.session_id:
                ch_name = reply.channel_identity.split(":")[0]
                self._conversation_registry.bind(ch_name, reply.thread_id, sm.event.session_id)

            await self._resolve_next(sm.event.session_id)

        except Exception as exc:  # noqa: BLE001
            sm.transition(PromptStatus.FAILED, str(exc))
            log.error("reply_injection_failed", error=str(exc))

    def _resolve_free_text_reply(self, reply: Reply) -> Reply | None:
        """Resolve a free-text reply (empty prompt_id) to the active prompt.

        When a ConversationRegistry is available and the reply has a
        thread_id, the registry is consulted first for deterministic
        session resolution.  Falls back to first-match scan.
        """
        target_session: str | None = None

        # Try conversation registry first (thread→session binding)
        if self._conversation_registry is not None and reply.thread_id:
            channel_name = reply.channel_identity.split(":")[0]
            target_session = self._conversation_registry.resolve(channel_name, reply.thread_id)

        for prompt_id, sm in self._machines.items():
            if sm.is_terminal:
                continue
            sid = sm.event.session_id
            if not sid:
                continue
            # If registry resolved a session, match only that session
            if target_session is not None and sid != target_session:
                continue
            return Reply(
                prompt_id=prompt_id,
                session_id=sid,
                value=reply.value,
                nonce=reply.nonce,
                channel_identity=reply.channel_identity,
                timestamp=reply.timestamp,
                newline_policy=reply.newline_policy,
                thread_id=reply.thread_id,
            )
        return None

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
                logger.info(
                    "prompt_expired",
                    prompt_id=sm.event.prompt_id,
                    session_id=sm.event.session_id[:8],
                )
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
