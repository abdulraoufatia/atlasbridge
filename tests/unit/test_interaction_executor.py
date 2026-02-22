"""Unit tests for InteractionExecutor."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.interaction.classifier import InteractionClass
from atlasbridge.core.interaction.executor import InteractionExecutor
from atlasbridge.core.interaction.plan import build_plan
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType


@pytest.fixture
def mock_adapter() -> AsyncMock:
    adapter = AsyncMock()
    adapter.inject_reply = AsyncMock()
    adapter._supervisors = {}
    return adapter


@pytest.fixture
def mock_detector() -> MagicMock:
    detector = MagicMock()
    detector.last_output_time = time.monotonic()
    detector.mark_injected = MagicMock()
    return detector


@pytest.fixture
def mock_notify() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def executor(
    mock_adapter: AsyncMock,
    mock_detector: MagicMock,
    mock_notify: AsyncMock,
) -> InteractionExecutor:
    return InteractionExecutor(
        adapter=mock_adapter,
        session_id="test-session-abc123",
        detector=mock_detector,
        notify_fn=mock_notify,
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


# ---------------------------------------------------------------------------
# Basic injection
# ---------------------------------------------------------------------------


class TestBasicInjection:
    @pytest.mark.asyncio
    async def test_calls_adapter_inject_reply(
        self, executor: InteractionExecutor, mock_adapter: AsyncMock
    ) -> None:
        plan = build_plan(InteractionClass.CHAT_INPUT)  # No verification
        result = await executor.execute(plan, "hello", "free_text")
        mock_adapter.inject_reply.assert_called_once_with(
            session_id="test-session-abc123",
            value="hello",
            prompt_type="free_text",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_feedback_message_uses_display_template(
        self, executor: InteractionExecutor
    ) -> None:
        plan = build_plan(InteractionClass.CHAT_INPUT)
        result = await executor.execute(plan, "hello", "free_text")
        assert "hello" in result.feedback_message

    @pytest.mark.asyncio
    async def test_adapter_exception_returns_failure(
        self,
        executor: InteractionExecutor,
        mock_adapter: AsyncMock,
    ) -> None:
        mock_adapter.inject_reply.side_effect = RuntimeError("PTY dead")
        plan = build_plan(InteractionClass.CHAT_INPUT)
        result = await executor.execute(plan, "hello", "free_text")
        assert result.success is False
        assert "PTY dead" in result.feedback_message


# ---------------------------------------------------------------------------
# Advance verification
# ---------------------------------------------------------------------------


class TestAdvanceVerification:
    @pytest.mark.asyncio
    async def test_advance_detected(
        self,
        executor: InteractionExecutor,
        mock_detector: MagicMock,
    ) -> None:
        # Simulate CLI advancing: output_time moves forward after injection
        plan = build_plan(InteractionClass.YES_NO)
        # Override to short timeout for test speed
        plan = plan.__class__(**{**plan.__dict__, "advance_timeout_s": 0.5, "max_retries": 0})
        initial_time = time.monotonic()
        mock_detector.last_output_time = initial_time

        # After a small delay, simulate output arriving
        async def _advance_output() -> None:
            await asyncio.sleep(0.1)
            mock_detector.last_output_time = initial_time + 1.0

        task = asyncio.create_task(_advance_output())
        result = await executor.execute(plan, "y", "yes_no")
        await task

        assert result.success is True
        assert result.cli_advanced is True

    @pytest.mark.asyncio
    async def test_stall_no_advance(
        self,
        executor: InteractionExecutor,
        mock_detector: MagicMock,
    ) -> None:
        # CLI does not advance — last_output_time stays the same
        plan = build_plan(InteractionClass.FREE_TEXT)
        plan = plan.__class__(**{**plan.__dict__, "advance_timeout_s": 0.3, "max_retries": 0})
        mock_detector.last_output_time = time.monotonic()

        result = await executor.execute(plan, "test", "free_text")

        assert result.cli_advanced is False

    @pytest.mark.asyncio
    async def test_no_verify_skips_check(
        self,
        executor: InteractionExecutor,
    ) -> None:
        plan = build_plan(InteractionClass.CHAT_INPUT)
        assert plan.verify_advance is False

        result = await executor.execute(plan, "msg", "free_text")

        assert result.success is True
        assert result.cli_advanced is None


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_on_stall(
        self,
        executor: InteractionExecutor,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
        mock_notify: AsyncMock,
    ) -> None:
        # First attempt stalls, second advances
        plan = build_plan(InteractionClass.YES_NO)
        plan = plan.__class__(
            **{
                **plan.__dict__,
                "advance_timeout_s": 0.2,
                "retry_delay_s": 0.1,
                "max_retries": 1,
            }
        )
        initial_time = time.monotonic()
        mock_detector.last_output_time = initial_time

        call_count = 0

        async def _inject_side_effect(**kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Simulate advance on retry
                mock_detector.last_output_time = initial_time + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_inject_side_effect)

        result = await executor.execute(plan, "y", "yes_no")

        assert result.success is True
        assert result.retries_used == 1
        assert mock_adapter.inject_reply.call_count == 2
        # Stall notification sent
        assert mock_notify.call_count >= 1

    @pytest.mark.asyncio
    async def test_no_retry_when_max_zero(
        self,
        executor: InteractionExecutor,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        plan = build_plan(InteractionClass.FREE_TEXT)
        assert plan.max_retries == 0
        plan = plan.__class__(**{**plan.__dict__, "advance_timeout_s": 0.2})
        mock_detector.last_output_time = time.monotonic()

        await executor.execute(plan, "text", "free_text")

        assert mock_adapter.inject_reply.call_count == 1


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


class TestEscalation:
    @pytest.mark.asyncio
    async def test_escalation_after_retry(
        self,
        executor: InteractionExecutor,
        mock_detector: MagicMock,
        mock_notify: AsyncMock,
    ) -> None:
        plan = build_plan(InteractionClass.YES_NO)
        plan = plan.__class__(
            **{
                **plan.__dict__,
                "advance_timeout_s": 0.2,
                "retry_delay_s": 0.1,
                "max_retries": 1,
                "escalate_on_exhaustion": True,
            }
        )
        mock_detector.last_output_time = time.monotonic()

        result = await executor.execute(plan, "y", "yes_no")

        assert result.escalated is True
        assert result.success is False
        assert "arrow keys" in result.feedback_message


# ---------------------------------------------------------------------------
# Password redaction
# ---------------------------------------------------------------------------


class TestPasswordRedaction:
    @pytest.mark.asyncio
    async def test_password_value_redacted(
        self,
        executor: InteractionExecutor,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        plan = build_plan(InteractionClass.PASSWORD_INPUT)
        initial_time = time.monotonic()
        mock_detector.last_output_time = initial_time

        # Simulate CLI advancing after injection
        async def _advance(**kwargs: object) -> None:
            mock_detector.last_output_time = initial_time + 2.0

        mock_adapter.inject_reply = AsyncMock(side_effect=_advance)

        result = await executor.execute(plan, "my-secret-password", "free_text")

        assert "my-secret-password" not in result.feedback_message
        assert "REDACTED" in result.feedback_message
        assert result.injected_value == "[REDACTED]"


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------


class TestChatInput:
    @pytest.mark.asyncio
    async def test_direct_stdin_injection(
        self,
        executor: InteractionExecutor,
        mock_adapter: AsyncMock,
        mock_detector: MagicMock,
    ) -> None:
        tty = AsyncMock()
        mock_adapter._supervisors["test-session-abc123"] = tty

        result = await executor.execute_chat_input("hello world")

        tty.inject_reply.assert_called_once_with(b"hello world\r")
        mock_detector.mark_injected.assert_called_once()
        assert result.success is True
        assert result.injected_value == "hello world"

    @pytest.mark.asyncio
    async def test_no_tty_returns_failure(self, executor: InteractionExecutor) -> None:
        # No supervisor registered
        result = await executor.execute_chat_input("hello")
        assert result.success is False
        assert "No active PTY" in result.feedback_message

    @pytest.mark.asyncio
    async def test_uses_cr_not_newline(
        self,
        executor: InteractionExecutor,
        mock_adapter: AsyncMock,
    ) -> None:
        tty = AsyncMock()
        mock_adapter._supervisors["test-session-abc123"] = tty

        await executor.execute_chat_input("test")

        injected_bytes = tty.inject_reply.call_args[0][0]
        assert injected_bytes.endswith(b"\r")
        assert b"\n" not in injected_bytes


# ---------------------------------------------------------------------------
# CR semantics
# ---------------------------------------------------------------------------


class TestCrSemantics:
    @pytest.mark.asyncio
    async def test_adapter_inject_called_with_value(
        self,
        executor: InteractionExecutor,
        mock_adapter: AsyncMock,
    ) -> None:
        """The executor delegates to adapter.inject_reply which handles \\r."""
        plan = build_plan(InteractionClass.CHAT_INPUT)
        await executor.execute(plan, "y", "yes_no")

        mock_adapter.inject_reply.assert_called_once_with(
            session_id="test-session-abc123",
            value="y",
            prompt_type="yes_no",
        )
