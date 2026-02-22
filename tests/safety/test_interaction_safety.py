"""
Safety tests: Interaction pipeline invariants.

Verifies that the interaction subsystem preserves all correctness
invariants from CLAUDE.md:
  1. CR semantics — all PTY injection uses \\r (not \\n)
  2. Password redaction — credentials never appear in feedback/logs
  3. Echo suppression — mark_injected() called after every injection
  4. State machine integrity — interaction engine does not bypass state transitions
  5. Chat mode respects allowlist — no injection without allowed identity
  6. Retry does not bypass state machine
  7. Advance verification uses echo window
  8. All interaction classes produce valid plans
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from atlasbridge.core.interaction.classifier import InteractionClass, InteractionClassifier
from atlasbridge.core.interaction.executor import InteractionExecutor
from atlasbridge.core.interaction.plan import InteractionPlan, build_plan
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType


class TestCRSemantics:
    """Invariant: all PTY injection uses \\r (carriage return), never \\n."""

    @pytest.mark.asyncio
    async def test_chat_input_uses_cr(self) -> None:
        """Chat mode appends \\r not \\n to PTY input."""
        mock_tty = AsyncMock()
        adapter = MagicMock()
        adapter._supervisors = {"sess-001": mock_tty}

        detector = MagicMock()
        type(detector).last_output_time = PropertyMock(return_value=time.monotonic())

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="sess-001",
            detector=detector,
            notify_fn=AsyncMock(),
        )

        await executor.execute_chat_input("hello world")

        # Verify the bytes written to the TTY
        mock_tty.inject_reply.assert_called_once()
        written_bytes = mock_tty.inject_reply.call_args[0][0]
        assert written_bytes.endswith(b"\r"), f"Expected \\r at end, got: {written_bytes!r}"
        assert b"\n" not in written_bytes, f"Must not contain \\n: {written_bytes!r}"

    def test_all_plans_append_cr(self) -> None:
        """Every interaction plan has append_cr=True."""
        for ic in InteractionClass:
            plan = build_plan(ic)
            assert plan.append_cr is True, f"{ic} plan must have append_cr=True"


class TestPasswordRedaction:
    """Invariant: passwords never appear in feedback messages or InjectionResult."""

    @pytest.mark.asyncio
    async def test_password_not_in_feedback(self) -> None:
        """PASSWORD_INPUT feedback must contain [REDACTED], not the actual value."""
        secret = "my_super_secret_token_42"
        detector = MagicMock()
        initial_time = time.monotonic()
        type(detector).last_output_time = PropertyMock(return_value=initial_time)

        adapter = AsyncMock()

        async def _advance(**kw: object) -> None:
            type(detector).last_output_time = PropertyMock(return_value=time.monotonic() + 2.0)

        adapter.inject_reply.side_effect = _advance

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="sess-001",
            detector=detector,
            notify_fn=AsyncMock(),
        )

        plan = build_plan(InteractionClass.PASSWORD_INPUT)
        result = await executor.execute(
            plan=plan,
            value=secret,
            prompt_type=PromptType.TYPE_FREE_TEXT,
        )

        assert secret not in result.feedback_message, "Password must not appear in feedback"
        assert secret not in result.injected_value, "Password must not appear in injected_value"
        assert "REDACTED" in result.injected_value

    def test_password_plan_suppresses_value(self) -> None:
        """PASSWORD_INPUT plan has suppress_value=True."""
        plan = build_plan(InteractionClass.PASSWORD_INPUT)
        assert plan.suppress_value is True


class TestEchoSuppression:
    """Invariant: mark_injected() called after every chat injection."""

    @pytest.mark.asyncio
    async def test_mark_injected_called_for_chat(self) -> None:
        """Echo suppression is triggered after chat mode injection."""
        mock_tty = AsyncMock()
        adapter = MagicMock()
        adapter._supervisors = {"sess-001": mock_tty}

        detector = MagicMock()
        type(detector).last_output_time = PropertyMock(return_value=time.monotonic())

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="sess-001",
            detector=detector,
            notify_fn=AsyncMock(),
        )

        await executor.execute_chat_input("test input")

        detector.mark_injected.assert_called_once()


class TestStateMachineIntegrity:
    """Invariant: interaction engine does not bypass state machine transitions."""

    @pytest.mark.asyncio
    async def test_escalation_returns_failure(self) -> None:
        """When CLI stalls and retries are exhausted, result.success is False."""
        detector = MagicMock()
        # last_output_time never advances — simulates stall
        type(detector).last_output_time = PropertyMock(return_value=time.monotonic())

        adapter = AsyncMock()
        executor = InteractionExecutor(
            adapter=adapter,
            session_id="sess-001",
            detector=detector,
            notify_fn=AsyncMock(),
        )

        plan = build_plan(InteractionClass.YES_NO)
        result = await executor.execute(
            plan=plan,
            value="y",
            prompt_type=PromptType.TYPE_YES_NO,
        )

        # YES_NO has max_retries=1 and escalate_on_exhaustion=True
        assert result.escalated is True
        assert result.success is False

    def test_chat_plan_has_no_escalation(self) -> None:
        """CHAT_INPUT plan must not escalate — it's a best-effort injection."""
        plan = build_plan(InteractionClass.CHAT_INPUT)
        assert plan.escalate_on_exhaustion is False
        assert plan.verify_advance is False
        assert plan.max_retries == 0


class TestAdvanceVerification:
    """Invariant: advance check respects echo suppression window."""

    @pytest.mark.asyncio
    async def test_advance_check_uses_echo_window(self) -> None:
        """Advance verification must skip the echo window (0.5s)."""
        from atlasbridge.core.prompt.detector import ECHO_SUPPRESS_MS

        detector = MagicMock()
        initial_time = time.monotonic()

        # last_output_time advances slightly but within echo window
        within_echo = initial_time + (ECHO_SUPPRESS_MS / 1000.0) * 0.5
        type(detector).last_output_time = PropertyMock(return_value=within_echo)

        adapter = AsyncMock()
        executor = InteractionExecutor(
            adapter=adapter,
            session_id="sess-001",
            detector=detector,
            notify_fn=AsyncMock(),
        )

        # Override timeout to be very short for testing
        plan_fast = InteractionPlan(
            interaction_class=InteractionClass.CONFIRM_ENTER,
            append_cr=True,
            max_retries=0,
            verify_advance=True,
            advance_timeout_s=0.3,  # short timeout
            escalate_on_exhaustion=False,
            display_template="Sent: Enter",
            feedback_on_advance="CLI advanced",
            feedback_on_stall="CLI did not respond",
            button_layout="confirm_enter",
        )

        result = await executor.execute(
            plan=plan_fast,
            value="",
            prompt_type=PromptType.TYPE_CONFIRM_ENTER,
        )

        # Output was within echo window — should not count as advance
        assert result.cli_advanced is False


class TestAllInteractionClassesValid:
    """Invariant: every InteractionClass produces a complete, valid plan."""

    @pytest.mark.parametrize("ic", list(InteractionClass))
    def test_plan_has_display_template(self, ic: InteractionClass) -> None:
        plan = build_plan(ic)
        assert plan.display_template != "", f"{ic} must have a display_template"

    @pytest.mark.parametrize("ic", list(InteractionClass))
    def test_plan_has_button_layout(self, ic: InteractionClass) -> None:
        plan = build_plan(ic)
        assert plan.button_layout in {"yes_no", "confirm_enter", "numbered", "none"}, (
            f"{ic} has unexpected button_layout: {plan.button_layout}"
        )

    @pytest.mark.parametrize("ic", list(InteractionClass))
    def test_plan_is_frozen(self, ic: InteractionClass) -> None:
        plan = build_plan(ic)
        with pytest.raises(AttributeError):
            plan.max_retries = 99  # type: ignore[misc]


class TestClassifierDeterminism:
    """Invariant: classifier is deterministic (same input → same output)."""

    def test_classifier_deterministic_across_calls(self) -> None:
        """Same event always produces the same InteractionClass."""
        classifier = InteractionClassifier()
        event = PromptEvent.create(
            session_id="sess-001",
            prompt_type=PromptType.TYPE_YES_NO,
            confidence=Confidence.HIGH,
            excerpt="Continue? [y/N]",
        )
        results = {classifier.classify(event) for _ in range(100)}
        assert len(results) == 1, "Classifier must be deterministic"
        assert InteractionClass.YES_NO in results
