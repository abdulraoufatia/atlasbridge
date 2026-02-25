"""
Prompt router.

The PromptRouter sits between the PromptDetector and the Channel.

Forward path:
  PromptEvent → validate → route to channel → update session state

Return path:
  Reply → gate evaluation → validate nonce/TTL/session → inject via adapter → update state

Routing rules:
  HIGH confidence  → route immediately
  MED confidence   → route if tty_blocked is True; else buffer for 1s
  LOW confidence   → ambiguity protocol (send SHOW_LAST_OUTPUT; wait for reply)
  No signal        → discard

Channel message gating:
  Every incoming reply is evaluated by the ChannelMessageGate before any
  state mutation or injection. Rejected messages are never queued — the
  gate returns an immediate verdict and the caller receives feedback.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog

from atlasbridge.core.audit.writer import AuditWriter
from atlasbridge.core.conversation.session_binding import ConversationState
from atlasbridge.core.gate.engine import GateContext, GateDecision, GateRejectReason, evaluate_gate
from atlasbridge.core.gate.messages import format_gate_decision
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptStatus, Reply
from atlasbridge.core.prompt.state import PromptStateMachine
from atlasbridge.core.session.manager import SessionManager
from atlasbridge.core.session.models import SessionStatus

logger = structlog.get_logger()

# Spam prevention constants
_FAILSAFE_WINDOW_S = 60.0  # Rolling window for failsafe counter
_FAILSAFE_MAX_DISPATCHES = 5  # Max dispatches per session in the window


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
        audit_writer: AuditWriter | None = None,
        dry_run: bool = False,
    ) -> None:
        self._sessions = session_manager
        self._channel = channel
        self._adapter_map = adapter_map
        self._store = store
        self._interaction_engine = interaction_engine
        self._chat_mode_handler = chat_mode_handler
        self._conversation_registry = conversation_registry
        self._audit_writer = audit_writer
        self._dry_run = dry_run

        # Active state machines: prompt_id → PromptStateMachine
        self._machines: dict[str, PromptStateMachine] = {}

        # Spam prevention: session_id → (window_start, dispatch_count)
        self._session_dispatch_counts: dict[str, list[float]] = {}

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

        # --- Content-based dedup: skip if same content already awaiting reply ---
        content_hash = hashlib.sha256(event.excerpt.encode()).hexdigest()[:16]
        if session.active_prompt_id:
            active_sm = self._machines.get(session.active_prompt_id)
            if active_sm and not active_sm.is_terminal:
                active_hash = hashlib.sha256(active_sm.event.excerpt.encode()).hexdigest()[:16]
                if active_hash == content_hash:
                    log.debug("prompt_deduplicated", active_prompt=session.active_prompt_id[:8])
                    return

        # --- Failsafe: pause routing if too many dispatches in window ---
        now = time.monotonic()
        timestamps = self._session_dispatch_counts.get(event.session_id, [])
        # Prune old entries outside the failsafe window
        timestamps = [t for t in timestamps if (now - t) < _FAILSAFE_WINDOW_S]
        if len(timestamps) >= _FAILSAFE_MAX_DISPATCHES:
            log.warning("failsafe_routing_paused", dispatches_in_window=len(timestamps))
            self._session_dispatch_counts[event.session_id] = timestamps
            if self._channel is not None:
                await self._channel.notify(
                    f"Rate limit: {len(timestamps)} prompts in 60s. Check console.",
                    session_id=event.session_id,
                )
            return
        timestamps.append(now)
        self._session_dispatch_counts[event.session_id] = timestamps

        # New prompts supersede old ones — no queueing
        if session.active_prompt_id:
            log.debug("prompt_superseded", old_prompt=session.active_prompt_id)

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

        if self._dry_run:
            sm.transition(PromptStatus.ROUTED, "dry run — channel suppressed")
            log.info(
                "dry_run_prompt_detected",
                prompt_type=event.prompt_type,
                confidence=event.confidence,
                excerpt=event.excerpt[:80],
            )
            return

        try:
            sm.transition(PromptStatus.ROUTED, "dispatching to channel")

            # Delivery dedup: skip if already delivered (survives daemon restarts)
            if self._store is not None and hasattr(self._store, "was_delivered"):
                ch_name = getattr(self._channel, "channel_name", "unknown")
                identities = (
                    list(self._channel.get_allowed_identities())
                    if hasattr(self._channel, "get_allowed_identities")
                    else []
                )
                if identities and all(
                    self._store.was_delivered(event.prompt_id, ch_name, ident)
                    for ident in identities
                ):
                    log.info("prompt_already_delivered", prompt_id=event.prompt_id)
                    sm.transition(PromptStatus.AWAITING_REPLY, "already delivered")
                    self._sessions.mark_awaiting_reply(event.session_id, event.prompt_id)
                    return

            message_id = await self._channel.send_prompt(event)

            sm.transition(PromptStatus.AWAITING_REPLY, "channel delivered prompt")
            self._sessions.mark_awaiting_reply(event.session_id, event.prompt_id)

            # Record delivery for idempotent resend protection
            if self._store is not None and hasattr(self._store, "record_delivery"):
                ch_name = getattr(self._channel, "channel_name", "unknown")
                identities = (
                    list(self._channel.get_allowed_identities())
                    if hasattr(self._channel, "get_allowed_identities")
                    else []
                )
                for ident in identities:
                    self._store.record_delivery(
                        event.prompt_id, event.session_id, ch_name, ident, message_id or ""
                    )

            # Bind conversation threads so the gate can resolve session on first reply.
            # Without this, the first reply to a freshly-dispatched prompt has no
            # conversation binding and the gate rejects with "No active session".
            if self._conversation_registry is not None and hasattr(
                self._channel, "get_allowed_identities"
            ):
                for ident in self._channel.get_allowed_identities():
                    parts = ident.split(":", 1)
                    if len(parts) == 2:
                        ch_name_bind, thread_id = parts
                        self._conversation_registry.bind(ch_name_bind, thread_id, event.session_id)
                        self._conversation_registry.update_state(
                            ch_name_bind,
                            thread_id,
                            ConversationState.AWAITING_INPUT,
                        )

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
        # Plan response handling (sentinel prompt_id)
        if reply.prompt_id == "__plan__":
            await self.handle_plan_response(
                session_id=reply.session_id,
                decision=reply.value,
            )
            return

        # For free-text replies (no prompt_id), try to bind to the active prompt
        # before running the gate so that session/prompt context is available.
        effective_reply = reply
        if not reply.prompt_id:
            resolved = self._resolve_free_text_reply(reply)
            if resolved is not None:
                effective_reply = resolved

        # Gate evaluation — rejected messages are never injected.
        decision = self._evaluate_gate(effective_reply)
        if decision is not None and decision.action == "reject":
            session_id = (
                effective_reply.session_id or self._resolve_session_for_reply(effective_reply) or ""
            )
            feedback = format_gate_decision(decision)
            logger.info(
                "channel_message_rejected",
                reason_code=decision.reason_code,
                session_id=session_id[:8] if session_id else "",
            )
            self._audit_gate_decision(effective_reply, decision, session_id)
            if self._channel is not None:
                await self._channel.notify(feedback, session_id=session_id)
            return

        # Audit accepted gate decision
        if decision is not None and decision.action == "accept":
            session_id = (
                effective_reply.session_id or self._resolve_session_for_reply(effective_reply) or ""
            )
            self._audit_gate_decision(effective_reply, decision, session_id)

        # If, after attempted binding and gate evaluation, there is still no
        # prompt_id, treat this as Chat Mode (free-text turn) or drop it.
        if not effective_reply.prompt_id:
            # No active prompt — check conversation state for chat mode
            if self._chat_mode_handler is not None:
                logger.info(
                    "chat_mode_input",
                    channel_identity=effective_reply.channel_identity,
                    value_length=len(effective_reply.value),
                )
                await self._chat_mode_handler(effective_reply)
                return
            logger.debug("free_text_reply_dropped", reason="no_active_prompt")
            return

        log = logger.bind(
            prompt_id=effective_reply.prompt_id,
            session_id=effective_reply.session_id[:8] if effective_reply.session_id else "",
            channel_identity=effective_reply.channel_identity,
        )

        sm = self._machines.get(effective_reply.prompt_id)
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
            if self._channel is not None:
                await self._channel.notify(
                    "This prompt has expired. The safe default was used.",
                    session_id=effective_reply.session_id,
                )
            return

        # Validate session binding
        if sm.event.session_id != effective_reply.session_id and effective_reply.session_id:
            log.warning(
                "reply_rejected",
                reason="session_mismatch",
                expected_session=sm.event.session_id[:8],
            )
            return

        # Identity allowlist (channel enforces; double-check here)
        if not self._channel.is_allowed(effective_reply.channel_identity):
            log.warning("reply_rejected", reason="identity_not_allowed")
            return

        try:
            sm.transition(
                PromptStatus.REPLY_RECEIVED,
                f"reply from {effective_reply.channel_identity}",
            )

            if self._interaction_engine is not None:
                # Use the interaction engine (classify → plan → execute → feedback)
                result = await self._interaction_engine.handle_prompt_reply(
                    sm.event, effective_reply
                )

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
                feedback = result.feedback_message or f"\u2713 Answered: {result.injected_value!r}"
                session = self._sessions.get_or_none(sm.event.session_id)
                if session:
                    msg_id = session.channel_message_ids.get(effective_reply.prompt_id, "")
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
                    value=effective_reply.value,
                    prompt_type=sm.event.prompt_type,
                )

                sm.transition(PromptStatus.INJECTED, "injected into PTY")
                sm.transition(PromptStatus.RESOLVED, "injection confirmed")

                self._sessions.mark_reply_received(sm.event.session_id)

                # Edit the channel message to show resolution
                session = self._sessions.get_or_none(sm.event.session_id)
                if session:
                    msg_id = session.channel_message_ids.get(effective_reply.prompt_id, "")
                    if msg_id:
                        await self._channel.edit_prompt_message(
                            msg_id,
                            f"\u2713 Answered: {effective_reply.value!r}",
                            session_id=sm.event.session_id,
                        )

            # Send acknowledgement to channel
            if self._channel is not None:
                val_display = effective_reply.value[:40]
                ack = f'Sent: "{val_display}"\nSession: {sm.event.session_id[:8]}'
                await self._channel.notify(ack, session_id=sm.event.session_id)

            # Reset failsafe counter — successful reply means the prompt cycle completed
            self._session_dispatch_counts.pop(sm.event.session_id, None)

            latency = sm.latency_ms
            log.info(
                "reply_injected",
                value_length=len(reply.value),
                latency_ms=round(latency, 1) if latency else None,
            )

            # Bind thread→session in conversation registry
            if (
                self._conversation_registry is not None
                and effective_reply.thread_id
                and sm.event.session_id
            ):
                ch_name = effective_reply.channel_identity.split(":")[0]
                self._conversation_registry.bind(
                    ch_name, effective_reply.thread_id, sm.event.session_id
                )

        except Exception as exc:  # noqa: BLE001
            sm.transition(PromptStatus.FAILED, str(exc))
            log.error("reply_injection_failed", error=str(exc))
            if self._channel is not None:
                await self._channel.notify(
                    "Reply failed. Try again.",
                    session_id=sm.event.session_id,
                )

    def _evaluate_gate(self, reply: Reply) -> GateDecision | None:
        """Build a GateContext and evaluate the channel message gate.

        Returns None if no conversation registry is available (gate cannot
        evaluate without session state).
        """
        if self._conversation_registry is None:
            return None

        # Resolve session and state from thread context
        session_id: str | None = reply.session_id or None
        state = None
        active_prompt_id: str | None = None

        if reply.thread_id:
            channel_name = reply.channel_identity.split(":")[0]
            binding = self._conversation_registry.get_binding(channel_name, reply.thread_id)
            if binding is not None:
                session_id = binding.session_id
                state = binding.state
            if session_id is None:
                session_id = self._conversation_registry.resolve(channel_name, reply.thread_id)

        # Look up active prompt
        if session_id:
            session = self._sessions.get_or_none(session_id)
            if session:
                active_prompt_id = session.active_prompt_id
                # Fallback: derive a conversation state from the session status when
                # no explicit ConversationBinding exists yet. This allows first
                # replies to freshly-routed prompts (e.g. trust prompts) to pass
                # the gate without reporting "No active session" while still
                # respecting STOPPED/terminal invariants.
                # Session status is the authoritative source of truth.
                # The binding state can be stale (e.g. OutputForwarder
                # transitioned to RUNNING before the prompt was detected),
                # so override whenever session status says AWAITING_REPLY.
                if session.status == SessionStatus.AWAITING_REPLY:
                    state = ConversationState.AWAITING_INPUT
                elif state is None:
                    if session.status in (SessionStatus.STARTING, SessionStatus.RUNNING):
                        state = ConversationState.RUNNING
                    elif session.is_terminal:
                        state = ConversationState.STOPPED

        # Build identity allowlist from channel
        allowlist: frozenset[str] = frozenset()
        if hasattr(self._channel, "get_allowed_identities"):
            allowlist = frozenset(self._channel.get_allowed_identities())
        elif hasattr(self._channel, "is_allowed"):
            # Fallback: can't enumerate, just mark the user as allowed if they pass
            if self._channel.is_allowed(reply.channel_identity):
                allowlist = frozenset({reply.channel_identity})

        # Build channel name from identity
        channel_name = reply.channel_identity.split(":")[0] if reply.channel_identity else ""
        user_id = reply.channel_identity

        now = datetime.now(UTC).isoformat()

        ctx = GateContext(
            session_id=session_id,
            conversation_state=state,
            active_prompt_id=active_prompt_id,
            interaction_class=None,
            prompt_expires_at=None,
            channel_user_id=user_id,
            channel_name=channel_name,
            message_body=reply.value,
            message_hash=hashlib.sha256(reply.value.encode()).hexdigest(),
            identity_allowlist=allowlist,
            timestamp=now,
        )

        return evaluate_gate(ctx)

    def _audit_gate_decision(self, reply: Reply, decision: GateDecision, session_id: str) -> None:
        """Write an audit event for a gate decision."""
        if self._audit_writer is None:
            return

        channel = reply.channel_identity.split(":")[0] if reply.channel_identity else ""
        user_id = reply.channel_identity
        # Determine conversation state from gate context (best effort)
        state = ""
        if self._conversation_registry is not None and reply.thread_id:
            binding = self._conversation_registry.get_binding(channel, reply.thread_id)
            if binding is not None:
                state = binding.state.value

        is_password = decision.reason_code == GateRejectReason.REJECT_UNSAFE_INPUT_TYPE
        is_rate_limited = decision.reason_code == GateRejectReason.REJECT_RATE_LIMITED

        if decision.action == "accept":
            self._audit_writer.channel_message_accepted(
                session_id=session_id,
                prompt_id=None,
                channel=channel,
                user_id=user_id,
                body=reply.value,
                conversation_state=state,
                accept_type=decision.accept_type.value if decision.accept_type else "reply",
                is_password=is_password,
            )
        else:
            self._audit_writer.channel_message_rejected(
                session_id=session_id,
                prompt_id=None,
                channel=channel,
                user_id=user_id,
                body=reply.value,
                conversation_state=state,
                reason_code=decision.reason_code.value if decision.reason_code else "unknown",
                is_password=is_password,
                is_rate_limited=is_rate_limited,
            )

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_session_for_reply(self, reply: Reply) -> str | None:
        """Resolve session_id from reply's thread context."""
        if self._conversation_registry is None:
            return None
        if reply.thread_id:
            channel_name = reply.channel_identity.split(":")[0]
            return self._conversation_registry.resolve(channel_name, reply.thread_id)
        return None

    async def handle_plan_response(self, session_id: str, decision: str) -> None:
        """Handle a plan button response (execute/modify/cancel)."""
        log = logger.bind(session_id=session_id[:8], decision=decision)

        if decision == "execute":
            log.info("plan_execute")
            if self._channel is not None:
                await self._channel.notify(
                    "Plan accepted. Agent continuing.",
                    session_id=session_id,
                )

        elif decision == "modify":
            log.info("plan_modify")
            if self._channel is not None:
                await self._channel.notify(
                    "Send your modifications as a message.",
                    session_id=session_id,
                )

        elif decision == "cancel":
            log.info("plan_cancel")
            if self._chat_mode_handler is not None:
                cancel_reply = Reply(
                    prompt_id="",
                    session_id=session_id,
                    value="Cancel the current plan. Do not proceed with these steps.",
                    nonce="",
                    channel_identity="system:plan_cancel",
                    timestamp="",
                )
                await self._chat_mode_handler(cancel_reply)
            if self._channel is not None:
                await self._channel.notify(
                    "Plan cancelled. Cancellation sent to agent.",
                    session_id=session_id,
                )

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
                            "\u23f0 Prompt expired. Safe default applied.",
                            session_id=sm.event.session_id,
                        )
