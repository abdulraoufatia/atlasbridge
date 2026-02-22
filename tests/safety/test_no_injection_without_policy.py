"""Safety guard: no auto-reply injection without policy evaluation.

Verifies that AutopilotEngine never calls inject_fn without first
calling evaluate() when in FULL mode. Also verifies that PAUSED and
OFF modes never auto-inject.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from atlasbridge.core.autopilot.engine import AutopilotEngine, AutopilotState
from atlasbridge.core.policy.model import (
    AutonomyMode,
    AutoReplyAction,
    MatchCriteria,
    Policy,
    PolicyRule,
)


def _make_engine(
    tmp_path: Path,
    mode: AutonomyMode = AutonomyMode.FULL,
    state: AutopilotState = AutopilotState.RUNNING,
) -> tuple[AutopilotEngine, AsyncMock, AsyncMock, AsyncMock]:
    """Create an engine with mock functions and a simple auto-reply policy."""
    policy = Policy(
        policy_version="0",
        name="test",
        autonomy_mode=mode,
        rules=[
            PolicyRule(
                id="auto-yes",
                match=MatchCriteria(prompt_type=["yes_no"]),
                action=AutoReplyAction(type="auto_reply", value="y"),
            ),
        ],
    )

    inject_fn = AsyncMock()
    route_fn = AsyncMock()
    notify_fn = AsyncMock()

    engine = AutopilotEngine(
        policy=policy,
        trace_path=tmp_path / "trace.jsonl",
        state_path=tmp_path / "state.json",
        inject_fn=inject_fn,
        route_fn=route_fn,
        notify_fn=notify_fn,
    )

    # Override state if needed (bypass persistence)
    engine._state = state

    return engine, inject_fn, route_fn, notify_fn


@pytest.mark.asyncio
async def test_full_mode_evaluates_before_injecting(tmp_path):
    """In FULL mode, evaluate() must be called. If rule matches, inject_fn fires."""
    engine, inject_fn, route_fn, _ = _make_engine(tmp_path, AutonomyMode.FULL)

    with patch(
        "atlasbridge.core.autopilot.engine.evaluate",
        wraps=__import__("atlasbridge.core.policy.evaluator", fromlist=["evaluate"]).evaluate,
    ) as mock_eval:
        result = await engine.handle_prompt(
            prompt_event=object(),
            prompt_id="p1",
            session_id="s1",
            prompt_type="yes_no",
            confidence="high",
            prompt_text="Continue? [y/n]",
        )

    # evaluate() was called
    assert mock_eval.called, "evaluate() was NOT called before injection in FULL mode"
    # auto_reply action was taken
    assert result.action_type == "auto_reply"


@pytest.mark.asyncio
async def test_paused_never_auto_injects(tmp_path):
    """When PAUSED, engine must route to human, never inject."""
    engine, inject_fn, route_fn, _ = _make_engine(
        tmp_path, AutonomyMode.FULL, AutopilotState.PAUSED
    )

    result = await engine.handle_prompt(
        prompt_event=object(),
        prompt_id="p1",
        session_id="s1",
        prompt_type="yes_no",
        confidence="high",
        prompt_text="Continue? [y/n]",
    )

    inject_fn.assert_not_called()
    route_fn.assert_called_once()
    assert result.action_type == "require_human"


@pytest.mark.asyncio
async def test_off_mode_never_auto_injects(tmp_path):
    """When autonomy_mode=OFF, engine must route to human, never inject."""
    engine, inject_fn, route_fn, _ = _make_engine(tmp_path, AutonomyMode.OFF)

    result = await engine.handle_prompt(
        prompt_event=object(),
        prompt_id="p1",
        session_id="s1",
        prompt_type="yes_no",
        confidence="high",
        prompt_text="Continue? [y/n]",
    )

    inject_fn.assert_not_called()
    route_fn.assert_called_once()
    assert result.action_type == "require_human"


@pytest.mark.asyncio
async def test_stopped_never_auto_injects(tmp_path):
    """When STOPPED, engine must not inject or route."""
    engine, inject_fn, route_fn, _ = _make_engine(
        tmp_path, AutonomyMode.FULL, AutopilotState.STOPPED
    )

    result = await engine.handle_prompt(
        prompt_event=object(),
        prompt_id="p1",
        session_id="s1",
        prompt_type="yes_no",
        confidence="high",
        prompt_text="Continue? [y/n]",
    )

    inject_fn.assert_not_called()
    route_fn.assert_not_called()
    assert result.action_type == "stopped"
