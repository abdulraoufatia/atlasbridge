"""Unit tests for StreamingManager — accumulation, plan detection, presentation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.interaction.plan_detector import DetectedPlan
from atlasbridge.core.interaction.streaming import (
    _MAX_ACCUMULATOR_CHARS,
    PlanStatus,
    StreamingManager,
)


def _make_channel() -> MagicMock:
    ch = MagicMock()
    ch.send_plan = AsyncMock(return_value="plan-msg-123")
    ch.send_agent_message = AsyncMock()
    ch.notify = AsyncMock()
    return ch


class TestAccumulate:
    def test_returns_none_for_non_plan(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        result = mgr.accumulate("Just some normal CLI output")
        assert result is None

    def test_detects_plan(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        text = """Plan:
1. Create the module
2. Add tests
3. Update docs
"""
        result = mgr.accumulate(text)
        assert result is not None
        assert isinstance(result, DetectedPlan)
        assert len(result.steps) == 3

    def test_resets_after_detection(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        text = """Plan:
1. Step one
2. Step two
"""
        mgr.accumulate(text)
        # Accumulator should be reset after detection
        assert mgr._accumulator == ""

    def test_accumulator_bounded_at_max(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        # Feed more than max chars
        mgr.accumulate("x" * (_MAX_ACCUMULATOR_CHARS + 1000))
        assert len(mgr._accumulator) <= _MAX_ACCUMULATOR_CHARS

    def test_incremental_accumulation(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        # Feed plan in chunks
        mgr.accumulate("Plan:\n")
        result = mgr.accumulate("1. Create module\n2. Add tests\n")
        assert result is not None
        assert len(result.steps) == 2


class TestPresentPlan:
    @pytest.mark.asyncio
    async def test_present_plan_calls_send_plan(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        plan = DetectedPlan(
            title="Plan",
            steps=["Step 1", "Step 2"],
            raw_text="raw",
            start_offset=0,
            end_offset=10,
        )
        ctx = await mgr.present_plan(plan)
        ch.send_plan.assert_called_once_with(plan, session_id="sess-001")
        assert ctx.plan_message_id == "plan-msg-123"
        assert ctx.status == PlanStatus.PRESENTED

    @pytest.mark.asyncio
    async def test_active_plan_set_after_present(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        plan = DetectedPlan(
            title="Test",
            steps=["Step 1"],
            raw_text="raw",
            start_offset=0,
            end_offset=5,
        )
        await mgr.present_plan(plan)
        assert mgr.active_plan is not None
        assert mgr.active_plan.plan is plan


class TestResolvePlan:
    @pytest.mark.asyncio
    async def test_resolve_plan_clears_active(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        plan = DetectedPlan(
            title="Test",
            steps=["Step 1"],
            raw_text="raw",
            start_offset=0,
            end_offset=5,
        )
        await mgr.present_plan(plan)
        assert mgr.active_plan is not None
        mgr.resolve_plan("execute")
        assert mgr.active_plan is None

    def test_resolve_without_active_plan_is_noop(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        mgr.resolve_plan("cancel")  # Should not raise


class TestReset:
    @pytest.mark.asyncio
    async def test_reset_clears_state(self) -> None:
        ch = _make_channel()
        mgr = StreamingManager(ch, "sess-001")
        mgr.accumulate("some text")
        plan = DetectedPlan(
            title="Test",
            steps=["Step 1"],
            raw_text="raw",
            start_offset=0,
            end_offset=5,
        )
        await mgr.present_plan(plan)
        mgr.reset()
        assert mgr._accumulator == ""
        assert mgr.active_plan is None
