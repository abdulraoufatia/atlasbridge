"""Tests for atlasbridge.core.autopilot.actions — execute_action() dispatcher."""

from __future__ import annotations

import pytest

from atlasbridge.core.autopilot.actions import ActionResult, execute_action
from atlasbridge.core.policy.model import (
    AutoReplyAction,
    DenyAction,
    NotifyOnlyAction,
    PolicyDecision,
    RequireHumanAction,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_decision(
    action_type: str = "auto_reply",
    action_value: str = "y",
    reason: str | None = None,
    message: str | None = None,
    explanation: str = "Rule matched",
) -> PolicyDecision:
    """Build a PolicyDecision with the specified action."""
    actions = {
        "auto_reply": AutoReplyAction(value=action_value),
        "require_human": RequireHumanAction(message=message),
        "deny": DenyAction(reason=reason),
        "notify_only": NotifyOnlyAction(message=message),
    }
    return PolicyDecision(
        prompt_id="p1",
        session_id="s1",
        policy_hash="abc123",
        matched_rule_id="rule-1",
        action=actions[action_type],
        explanation=explanation,
        confidence="high",
        prompt_type="yes_no",
        autonomy_mode="full",
    )


class _Recorder:
    """Simple callback recorder for inject/route/notify."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[object] = []
        self._fail = fail

    async def __call__(self, arg: object) -> None:
        self.calls.append(arg)
        if self._fail:
            raise RuntimeError("callback failed")


DUMMY_EVENT = object()


# ---------------------------------------------------------------------------
# AutoReplyAction tests
# ---------------------------------------------------------------------------


class TestAutoReply:
    @pytest.mark.asyncio
    async def test_success(self):
        inject = _Recorder()
        route = _Recorder()
        notify = _Recorder()
        decision = _make_decision(action_type="auto_reply", action_value="y")

        result = await execute_action(decision, DUMMY_EVENT, inject, route, notify)

        assert result.injected is True
        assert result.injected_value == "y"
        assert result.action_type == "auto_reply"
        assert result.error is None
        assert inject.calls == ["y"]

    @pytest.mark.asyncio
    async def test_inject_error(self):
        inject = _Recorder(fail=True)
        route = _Recorder()
        notify = _Recorder()
        decision = _make_decision(action_type="auto_reply", action_value="y")

        result = await execute_action(decision, DUMMY_EVENT, inject, route, notify)

        assert result.injected is False
        assert result.error is not None
        assert "callback failed" in result.error


# ---------------------------------------------------------------------------
# RequireHumanAction tests
# ---------------------------------------------------------------------------


class TestRequireHuman:
    @pytest.mark.asyncio
    async def test_success(self):
        inject = _Recorder()
        route = _Recorder()
        notify = _Recorder()
        decision = _make_decision(action_type="require_human")

        result = await execute_action(decision, DUMMY_EVENT, inject, route, notify)

        assert result.routed_to_human is True
        assert result.action_type == "require_human"
        assert result.error is None
        assert route.calls == [DUMMY_EVENT]

    @pytest.mark.asyncio
    async def test_route_error(self):
        inject = _Recorder()
        route = _Recorder(fail=True)
        notify = _Recorder()
        decision = _make_decision(action_type="require_human")

        result = await execute_action(decision, DUMMY_EVENT, inject, route, notify)

        assert result.routed_to_human is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# DenyAction tests
# ---------------------------------------------------------------------------


class TestDeny:
    @pytest.mark.asyncio
    async def test_success(self):
        inject = _Recorder()
        route = _Recorder()
        notify = _Recorder()
        decision = _make_decision(action_type="deny", reason="Blocked by policy")

        result = await execute_action(decision, DUMMY_EVENT, inject, route, notify)

        assert result.denied is True
        assert result.action_type == "deny"
        assert len(notify.calls) == 1
        assert "[DENY]" in notify.calls[0]
        assert "Blocked by policy" in notify.calls[0]

    @pytest.mark.asyncio
    async def test_custom_reason(self):
        notify = _Recorder()
        decision = _make_decision(action_type="deny", reason="Destructive op")

        result = await execute_action(decision, DUMMY_EVENT, _Recorder(), _Recorder(), notify)

        assert result.denied is True
        assert "Destructive op" in notify.calls[0]

    @pytest.mark.asyncio
    async def test_default_reason(self):
        notify = _Recorder()
        decision = _make_decision(action_type="deny", reason=None)

        result = await execute_action(decision, DUMMY_EVENT, _Recorder(), _Recorder(), notify)

        assert result.denied is True
        assert "Prompt denied by policy" in notify.calls[0]

    @pytest.mark.asyncio
    async def test_notify_error_still_returns_denied(self):
        notify = _Recorder(fail=True)
        decision = _make_decision(action_type="deny", reason="Blocked")

        result = await execute_action(decision, DUMMY_EVENT, _Recorder(), _Recorder(), notify)

        # Deny result is returned even if notification fails
        assert result.denied is True
        assert result.error is None  # error is swallowed for deny


# ---------------------------------------------------------------------------
# NotifyOnlyAction tests
# ---------------------------------------------------------------------------


class TestNotifyOnly:
    @pytest.mark.asyncio
    async def test_success(self):
        notify = _Recorder()
        decision = _make_decision(action_type="notify_only", message="Heads up")

        result = await execute_action(decision, DUMMY_EVENT, _Recorder(), _Recorder(), notify)

        assert result.notified is True
        assert result.action_type == "notify_only"
        assert result.error is None
        assert notify.calls == ["Heads up"]

    @pytest.mark.asyncio
    async def test_custom_message(self):
        notify = _Recorder()
        decision = _make_decision(action_type="notify_only", message="Deploy detected")

        await execute_action(decision, DUMMY_EVENT, _Recorder(), _Recorder(), notify)

        assert notify.calls == ["Deploy detected"]

    @pytest.mark.asyncio
    async def test_fallback_to_explanation(self):
        notify = _Recorder()
        decision = _make_decision(
            action_type="notify_only",
            message=None,
            explanation="Rule triggered notification",
        )

        result = await execute_action(decision, DUMMY_EVENT, _Recorder(), _Recorder(), notify)

        assert result.notified is True
        assert notify.calls == ["Rule triggered notification"]

    @pytest.mark.asyncio
    async def test_notify_error(self):
        notify = _Recorder(fail=True)
        decision = _make_decision(action_type="notify_only", message="test")

        result = await execute_action(decision, DUMMY_EVENT, _Recorder(), _Recorder(), notify)

        assert result.notified is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# Unknown action fallback
# ---------------------------------------------------------------------------


class TestUnknownAction:
    @pytest.mark.asyncio
    async def test_falls_back_to_route(self):
        route = _Recorder()
        # Create a decision with a fake action type to trigger the else branch
        decision = _make_decision(action_type="auto_reply")
        # Manually override the action to something unexpected
        decision.action = type("FakeAction", (), {"type": "unknown_action"})()

        result = await execute_action(decision, DUMMY_EVENT, _Recorder(), route, _Recorder())

        assert result.action_type == "unknown"
        assert result.routed_to_human is True
        assert route.calls == [DUMMY_EVENT]


# ---------------------------------------------------------------------------
# ActionResult dataclass
# ---------------------------------------------------------------------------


class TestActionResult:
    def test_defaults(self):
        r = ActionResult(action_type="auto_reply")
        assert r.injected is False
        assert r.injected_value == ""
        assert r.routed_to_human is False
        assert r.denied is False
        assert r.notified is False
        assert r.error is None
