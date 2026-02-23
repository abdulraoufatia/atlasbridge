"""Unit tests for InteractionEngine."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.interaction.classifier import InteractionClass
from atlasbridge.core.interaction.engine import InteractionEngine
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType, Reply


@pytest.fixture
def mock_adapter() -> AsyncMock:
    adapter = AsyncMock()
    adapter.inject_reply = AsyncMock()
    adapter._supervisors = {}
    return adapter


@pytest.fixture
def mock_detector() -> MagicMock:
    detector = MagicMock()
    # Start with a baseline time, advance on inject to simulate CLI advancing
    initial = time.monotonic()
    detector.last_output_time = initial
    detector.mark_injected = MagicMock()
    return detector


@pytest.fixture
def mock_channel() -> AsyncMock:
    channel = AsyncMock()
    channel.notify = AsyncMock()
    return channel


@pytest.fixture
def mock_session_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def engine(
    mock_adapter: AsyncMock,
    mock_detector: MagicMock,
    mock_channel: AsyncMock,
    mock_session_manager: MagicMock,
) -> InteractionEngine:
    return InteractionEngine(
        adapter=mock_adapter,
        session_id="test-session-abc123",
        detector=mock_detector,
        channel=mock_channel,
        session_manager=mock_session_manager,
    )


def _event(
    prompt_type: PromptType = PromptType.TYPE_YES_NO,
    excerpt: str = "Continue? [y/n]",
) -> PromptEvent:
    return PromptEvent.create(
        session_id="test-session-abc123",
        prompt_type=prompt_type,
        confidence=Confidence.HIGH,
        excerpt=excerpt,
    )


def _reply(value: str = "y") -> Reply:
    return Reply(
        prompt_id="prompt-123",
        session_id="test-session-abc123",
        value=value,
        nonce="nonce-abc",
        channel_identity="telegram:12345",
        timestamp="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# handle_prompt_reply
# ---------------------------------------------------------------------------


class TestHandlePromptReply:
    @pytest.mark.asyncio
    async def test_classifies_and_executes(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        event = _event(prompt_type=PromptType.TYPE_YES_NO)
        reply = _reply("y")

        # Simulate advance
        initial = mock_detector.last_output_time

        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await engine.handle_prompt_reply(event, reply)

        assert result.success is True
        mock_adapter.inject_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_password_prompt_redacted(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Password:",
        )
        reply = _reply("secret123")

        initial = mock_detector.last_output_time

        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await engine.handle_prompt_reply(event, reply)

        assert result.injected_value == "[REDACTED]"
        assert "secret123" not in result.feedback_message

    @pytest.mark.asyncio
    async def test_confirm_enter_classified(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_CONFIRM_ENTER,
            excerpt="Press Enter to continue",
        )
        reply = _reply("enter")

        initial = mock_detector.last_output_time

        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await engine.handle_prompt_reply(event, reply)
        assert result.success is True
        assert "Enter" in result.feedback_message

    @pytest.mark.asyncio
    async def test_numbered_choice_classified(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt="1) Fast\n2) Balanced\n3) Thorough",
        )
        reply = _reply("2")

        initial = mock_detector.last_output_time

        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await engine.handle_prompt_reply(event, reply)
        assert result.success is True
        assert "option" in result.feedback_message or "2" in result.feedback_message


# ---------------------------------------------------------------------------
# handle_chat_input
# ---------------------------------------------------------------------------


class TestHandleChatInput:
    @pytest.mark.asyncio
    async def test_injects_to_stdin(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        tty = AsyncMock()
        mock_adapter._supervisors["test-session-abc123"] = tty

        reply = _reply("refactor this function")

        result = await engine.handle_chat_input(reply)

        assert result.success is True
        tty.inject_reply.assert_called_once_with(b"refactor this function\r")

    @pytest.mark.asyncio
    async def test_no_tty_returns_failure(self, engine: InteractionEngine) -> None:
        reply = _reply("hello")
        result = await engine.handle_chat_input(reply)
        assert result.success is False


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


class TestFeedback:
    @pytest.mark.asyncio
    async def test_notification_sent_on_stall(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
        mock_channel: AsyncMock,
    ) -> None:
        """When CLI stalls during retry, engine sends stall notification."""
        event = _event(prompt_type=PromptType.TYPE_YES_NO)
        reply = _reply("y")

        # Detector never advances — triggers retry + escalation
        mock_detector.last_output_time = time.monotonic()

        # Patch plan to fast timeouts
        from atlasbridge.core.interaction.classifier import InteractionClass
        from atlasbridge.core.interaction.plan import InteractionPlan

        fast_plan = InteractionPlan(
            interaction_class=InteractionClass.YES_NO,
            advance_timeout_s=0.2,
            retry_delay_s=0.1,
            max_retries=1,
            display_template="Sent: {value} + Enter",
            feedback_on_advance="CLI advanced",
            feedback_on_stall='CLI stalled on "{value}"',
        )

        # Monkey-patch build_plan for this test
        import atlasbridge.core.interaction.engine as engine_mod

        original_build = engine_mod.build_plan

        def _fast_build(ic: InteractionClass) -> InteractionPlan:
            if ic == InteractionClass.YES_NO:
                return fast_plan
            return original_build(ic)

        engine_mod.build_plan = _fast_build
        try:
            await engine.handle_prompt_reply(event, reply)
        finally:
            engine_mod.build_plan = original_build

        # Stall notification + escalation notification
        assert mock_channel.notify.call_count >= 1


class TestTrustFolderPromptFlow:
    """End-to-end: trust folder prompt → normalize → inject → advance."""

    TRUST_PROMPT = (
        "Do you trust the files in this folder?\n"
        "1. Yes, I trust this folder\n"
        "2. No, exit\n"
        "Enter to confirm"
    )

    @pytest.mark.asyncio
    async def test_yes_reply_normalizes_and_injects(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt=self.TRUST_PROMPT,
        )
        reply = _reply("yes")

        initial = mock_detector.last_output_time

        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await engine.handle_prompt_reply(event, reply)

        assert result.success is True
        # Adapter should have received "1" (normalized), not "yes"
        call_kwargs = mock_adapter.inject_reply.call_args
        assert call_kwargs.kwargs.get("value") == "1" or call_kwargs[1].get("value") == "1"

    @pytest.mark.asyncio
    async def test_trust_reply_normalizes_to_1(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt=self.TRUST_PROMPT,
        )
        reply = _reply("trust")

        initial = mock_detector.last_output_time

        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await engine.handle_prompt_reply(event, reply)
        assert result.success is True
        call_kwargs = mock_adapter.inject_reply.call_args
        assert call_kwargs.kwargs.get("value") == "1" or call_kwargs[1].get("value") == "1"

    @pytest.mark.asyncio
    async def test_no_reply_normalizes_to_2(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt=self.TRUST_PROMPT,
        )
        reply = _reply("no")

        initial = mock_detector.last_output_time

        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await engine.handle_prompt_reply(event, reply)
        assert result.success is True
        call_kwargs = mock_adapter.inject_reply.call_args
        assert call_kwargs.kwargs.get("value") == "2" or call_kwargs[1].get("value") == "2"

    @pytest.mark.asyncio
    async def test_digit_1_passes_through(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt=self.TRUST_PROMPT,
        )
        reply = _reply("1")

        initial = mock_detector.last_output_time

        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await engine.handle_prompt_reply(event, reply)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_ambiguous_reply_asks_for_clarification(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
        mock_channel: AsyncMock,
    ) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt=self.TRUST_PROMPT,
        )
        reply = _reply("maybe")

        result = await engine.handle_prompt_reply(event, reply)

        assert result.success is False
        assert "1" in result.feedback_message and "2" in result.feedback_message
        mock_adapter.inject_reply.assert_not_called()


class TestFuserIntegration:
    """Engine uses fuser when provided, falls back to classifier when not."""

    @pytest.mark.asyncio
    async def test_engine_uses_fuser_when_provided(
        self,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
        mock_channel: AsyncMock,
        mock_session_manager: MagicMock,
    ) -> None:
        from atlasbridge.core.interaction.classifier import InteractionClassifier
        from atlasbridge.core.interaction.fuser import ClassificationFuser
        from atlasbridge.core.interaction.ml_classifier import NullMLClassifier

        fuser = ClassificationFuser(InteractionClassifier(), NullMLClassifier())
        engine = InteractionEngine(
            adapter=mock_adapter,
            session_id="test-session-fuser",
            detector=mock_detector,
            channel=mock_channel,
            session_manager=mock_session_manager,
            fuser=fuser,
        )

        # Advance detector time on inject
        original_time = mock_detector.last_output_time

        async def _advance(**kw: object) -> None:
            mock_detector.last_output_time = original_time + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        event = _event()
        reply = _reply("y")
        result = await engine.handle_prompt_reply(event, reply)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_engine_works_without_fuser(
        self,
        engine: InteractionEngine,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        # Advance detector time on inject
        original_time = mock_detector.last_output_time

        async def _advance(**kw: object) -> None:
            mock_detector.last_output_time = original_time + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        event = _event()
        reply = _reply("y")
        result = await engine.handle_prompt_reply(event, reply)
        assert result.success is True
