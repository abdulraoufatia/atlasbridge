"""Safety tests for streaming output, secret redaction, and plan detection.

These tests verify correctness invariants:
  - Secret tokens are NEVER sent to channels unredacted
  - Plan detection NEVER triggers PTY injection
  - Plan Execute does NOT inject into PTY
  - STREAMING state queues messages, does not inject
  - Queued messages are delivered on STREAMING → RUNNING transition
  - StreamingManager accumulator is bounded
  - Conversation state transitions are validated
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.conversation.session_binding import (
    VALID_CONVERSATION_TRANSITIONS,
    ConversationRegistry,
    ConversationState,
)
from atlasbridge.core.interaction.output_forwarder import OutputForwarder
from atlasbridge.core.interaction.plan_detector import DetectedPlan, detect_plan
from atlasbridge.core.interaction.streaming import _MAX_ACCUMULATOR_CHARS, StreamingManager
from atlasbridge.core.prompt.models import Reply
from atlasbridge.core.routing.router import PromptRouter
from atlasbridge.core.session.manager import SessionManager
from atlasbridge.core.session.models import Session


def _make_channel() -> MagicMock:
    ch = MagicMock()
    ch.send_output = AsyncMock()
    ch.send_output_editable = AsyncMock(return_value="")
    ch.send_agent_message = AsyncMock()
    ch.edit_prompt_message = AsyncMock()
    ch.notify = AsyncMock()
    ch.send_plan = AsyncMock(return_value="")
    ch.is_allowed = MagicMock(return_value=True)
    ch.send_prompt = AsyncMock(return_value="msg-100")
    return ch


class TestSecretRedaction:
    """Secrets MUST be redacted before reaching the channel."""

    def test_telegram_token_redacted_in_stream(self) -> None:
        token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ_1234567890ab"
        result = OutputForwarder._redact(f"Token: {token}")
        assert token not in result
        assert "[REDACTED]" in result

    def test_slack_token_redacted_in_stream(self) -> None:
        token = "xoxb-FAKE000-FAKE000-FAKETOKEN0000"
        result = OutputForwarder._redact(f"Bot: {token}")
        assert token not in result
        assert "[REDACTED]" in result

    def test_github_pat_redacted_in_stream(self) -> None:
        token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        result = OutputForwarder._redact(f"PAT: {token}")
        assert token not in result

    def test_aws_key_redacted_in_stream(self) -> None:
        key = "AKIAIOSFODNN7EXAMPLE"
        result = OutputForwarder._redact(f"Key: {key}")
        assert key not in result

    @pytest.mark.asyncio
    async def test_redaction_in_flush_pipeline(self) -> None:
        """End-to-end: secrets in PTY output never reach the channel."""
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"Found key: sk-ABCDEFGHIJKLMNOPQRSTuvwxyz1234567890xx\n")
        await fwd._flush()
        sent = ch.send_output_editable.call_args[0][0]
        assert "sk-ABCD" not in sent
        assert "[REDACTED]" in sent


class TestPlanDetectionSafety:
    """Plan detection MUST NOT trigger any injection."""

    def test_plan_detection_never_injects(self) -> None:
        """DetectedPlan is a pure data class — no adapter calls."""
        plan = detect_plan("Plan:\n1. Create module\n2. Add tests\n")
        assert plan is not None
        assert isinstance(plan, DetectedPlan)
        # DetectedPlan is a frozen dataclass — no methods that inject
        assert hasattr(plan, "title")
        assert hasattr(plan, "steps")
        assert not hasattr(plan, "inject")
        assert not hasattr(plan, "execute")

    @pytest.mark.asyncio
    async def test_plan_execute_does_not_inject(self) -> None:
        """Execute decision does NOT call any adapter injection."""
        ch = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-safe-1", tool="claude")
        sm.register(session)

        adapter = AsyncMock()
        router = PromptRouter(
            session_manager=sm,
            channel=ch,
            adapter_map={"sess-safe-1": adapter},
            store=MagicMock(),
        )

        from datetime import UTC, datetime

        reply = Reply(
            prompt_id="__plan__",
            session_id="sess-safe-1",
            value="execute",
            nonce="",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )
        await router.handle_reply(reply)

        # CRITICAL: execute must NOT inject
        adapter.inject_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_plan_cancel_uses_cr_not_lf(self) -> None:
        """Cancel injection goes through chat handler (which uses CR)."""
        ch = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-safe-2", tool="claude")
        sm.register(session)

        chat_handler = AsyncMock()
        router = PromptRouter(
            session_manager=sm,
            channel=ch,
            adapter_map={},
            store=MagicMock(),
            chat_mode_handler=chat_handler,
        )

        from datetime import UTC, datetime

        reply = Reply(
            prompt_id="__plan__",
            session_id="sess-safe-2",
            value="cancel",
            nonce="",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )
        await router.handle_reply(reply)

        # Cancel goes through chat handler (which uses execute_chat_input → \r)
        chat_handler.assert_called_once()


class TestStreamingStateSafety:
    """STREAMING state MUST queue messages, not inject."""

    @pytest.mark.asyncio
    async def test_streaming_state_blocks_chat_input(self) -> None:
        """When conversation is STREAMING, messages are queued, not injected."""
        ch = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-stream-1", tool="claude")
        sm.register(session)

        registry = ConversationRegistry()
        binding = registry.bind("telegram", "chat-123", "sess-stream-1")
        registry.transition_state("telegram", "chat-123", ConversationState.STREAMING)
        assert binding.state == ConversationState.STREAMING

        chat_handler = AsyncMock()
        router = PromptRouter(
            session_manager=sm,
            channel=ch,
            adapter_map={},
            store=MagicMock(),
            chat_mode_handler=chat_handler,
            conversation_registry=registry,
        )

        from datetime import UTC, datetime

        reply = Reply(
            prompt_id="",
            session_id="",
            value="user message during streaming",
            nonce="",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
            thread_id="chat-123",
        )
        await router.handle_reply(reply)

        # MUST NOT go to chat handler during STREAMING
        chat_handler.assert_not_called()
        # MUST be queued
        assert len(binding.queued_messages) == 1

    def test_queued_messages_delivered_on_running(self) -> None:
        """Queued messages are drained when transitioning to RUNNING."""
        registry = ConversationRegistry()
        binding = registry.bind("telegram", "chat-123", "sess-drain-1")
        registry.transition_state("telegram", "chat-123", ConversationState.STREAMING)
        binding.queued_messages.append("msg1")
        binding.queued_messages.append("msg2")

        # Transition to RUNNING
        registry.transition_state("telegram", "chat-123", ConversationState.RUNNING)

        # Drain messages
        messages = registry.drain_queued_messages("sess-drain-1")
        assert messages == ["msg1", "msg2"]
        assert len(binding.queued_messages) == 0


class TestAccumulatorBounded:
    """StreamingManager accumulator MUST NOT exceed 8192 chars."""

    def test_accumulator_bounded(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        # Feed 20000 chars
        mgr.accumulate("x" * 20000)
        assert len(mgr._accumulator) <= _MAX_ACCUMULATOR_CHARS


class TestConversationStateTransitions:
    """State transitions MUST follow the validated transition graph."""

    def test_all_states_have_transitions(self) -> None:
        for state in ConversationState:
            assert state in VALID_CONVERSATION_TRANSITIONS

    def test_stopped_is_terminal(self) -> None:
        valid = VALID_CONVERSATION_TRANSITIONS[ConversationState.STOPPED]
        assert len(valid) == 0

    def test_invalid_transition_rejected(self) -> None:
        registry = ConversationRegistry()
        registry.bind("telegram", "chat-1", "sess-1")
        # Transition to STOPPED (terminal)
        registry.transition_state("telegram", "chat-1", ConversationState.STOPPED)
        # STOPPED → RUNNING is invalid (STOPPED is terminal)
        result = registry.transition_state("telegram", "chat-1", ConversationState.RUNNING)
        assert result is False

    def test_valid_transition_accepted(self) -> None:
        registry = ConversationRegistry()
        registry.bind("telegram", "chat-1", "sess-1")
        # bind() sets state to RUNNING, RUNNING → STREAMING is valid
        result = registry.transition_state("telegram", "chat-1", ConversationState.STREAMING)
        assert result is True
