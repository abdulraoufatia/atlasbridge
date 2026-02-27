"""Safety tests for Expert Agent policy gating.

Validates that:
- Dangerous tools always require gating
- State machine prevents out-of-order operations
- Risk assessment correctly classifies tools
"""

from __future__ import annotations

import pytest

from atlasbridge.core.agent.state import AgentState, AgentStateMachine
from atlasbridge.core.agent.tools import get_agent_registry


class TestDangerousToolsAlwaysGated:
    """Dangerous tools must always be identified for gating."""

    DANGEROUS_TOOLS = {"ab_set_mode", "ab_kill_switch"}

    def test_dangerous_tools_exist_in_registry(self) -> None:
        registry = get_agent_registry()
        for name in self.DANGEROUS_TOOLS:
            tool = registry.get(name)
            assert tool is not None, f"Dangerous tool {name} missing from registry"

    def test_dangerous_tools_marked_dangerous(self) -> None:
        registry = get_agent_registry()
        for name in self.DANGEROUS_TOOLS:
            tool = registry.get(name)
            assert tool is not None
            assert tool.risk_level == "dangerous", (
                f"Tool {name} must have risk_level='dangerous', got '{tool.risk_level}'"
            )

    def test_no_safe_tool_is_marked_dangerous(self) -> None:
        """Safe tools must not be incorrectly marked as dangerous."""
        safe_tools = {
            "ab_list_sessions",
            "ab_get_session",
            "ab_list_prompts",
            "ab_get_audit_events",
            "ab_get_traces",
            "ab_check_integrity",
            "ab_get_config",
            "ab_get_policy",
            "ab_explain_decision",
            "ab_get_stats",
        }
        registry = get_agent_registry()
        for name in safe_tools:
            tool = registry.get(name)
            assert tool is not None
            assert tool.risk_level == "safe", f"Tool {name} should be safe, got '{tool.risk_level}'"


class TestStateMachinePreventsOutOfOrder:
    """State machine must prevent invalid transitions."""

    def test_cannot_execute_from_init(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        with pytest.raises(ValueError):
            sm.transition(AgentState.EXECUTE)

    def test_cannot_execute_from_ready(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        with pytest.raises(ValueError):
            sm.transition(AgentState.EXECUTE)

    def test_cannot_skip_plan_to_execute(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.INTAKE)
        with pytest.raises(ValueError):
            sm.transition(AgentState.EXECUTE)

    def test_cannot_skip_intake(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        with pytest.raises(ValueError):
            sm.transition(AgentState.PLAN)

    def test_cannot_synthesise_from_intake(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.INTAKE)
        with pytest.raises(ValueError):
            sm.transition(AgentState.SYNTHESISE)

    def test_cannot_transition_after_stopped(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.STOPPING)
        sm.transition(AgentState.STOPPED)
        for state in AgentState:
            if state != AgentState.STOPPED:
                with pytest.raises(ValueError):
                    sm.transition(state)


class TestGateStateProperties:
    """Gate state correctly identifies when human approval is needed."""

    def test_gate_state_is_gated(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.INTAKE)
        sm.transition(AgentState.PLAN)
        sm.transition(AgentState.GATE)
        assert sm.is_gated is True

    def test_other_states_not_gated(self) -> None:
        non_gated = [
            AgentState.INIT,
            AgentState.READY,
            AgentState.INTAKE,
            AgentState.PLAN,
            AgentState.EXECUTE,
            AgentState.SYNTHESISE,
            AgentState.RESPOND,
        ]
        for state in non_gated:
            sm = AgentStateMachine(session_id="s1")
            sm.state = state  # Direct set for testing
            assert sm.is_gated is False, f"{state} should not be gated"

    def test_ready_and_gate_accept_input(self) -> None:
        """READY and GATE states should accept input."""
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        assert sm.can_accept_input is True

        # GATE also accepts input (for approve/deny)
        sm.state = AgentState.GATE
        assert sm.can_accept_input is True

        processing_states = [
            AgentState.INTAKE,
            AgentState.PLAN,
            AgentState.EXECUTE,
            AgentState.SYNTHESISE,
            AgentState.RESPOND,
        ]
        for state in processing_states:
            sm.state = state
            assert sm.can_accept_input is False, f"{state} should not accept input"


class TestRiskClassification:
    """Tool risk levels are correctly classified."""

    def test_all_tools_have_risk_level(self) -> None:
        registry = get_agent_registry()
        for tool in registry.list_all():
            assert tool.risk_level in ("safe", "moderate", "dangerous"), (
                f"Tool {tool.name} has invalid risk_level: {tool.risk_level}"
            )

    def test_moderate_tools_have_parameters(self) -> None:
        """Moderate tools require meaningful parameters (they validate/test something)."""
        registry = get_agent_registry()
        moderate = [t for t in registry.list_all() if t.risk_level == "moderate"]
        for tool in moderate:
            schema = tool.parameters
            assert schema.get("required"), (
                f"Moderate tool {tool.name} should have required parameters"
            )

    def test_tool_count_is_expected(self) -> None:
        registry = get_agent_registry()
        tools = registry.list_all()
        safe_count = sum(1 for t in tools if t.risk_level == "safe")
        moderate_count = sum(1 for t in tools if t.risk_level == "moderate")
        dangerous_count = sum(1 for t in tools if t.risk_level == "dangerous")

        assert safe_count == 10, f"Expected 10 safe tools, got {safe_count}"
        assert moderate_count == 2, f"Expected 2 moderate tools, got {moderate_count}"
        assert dangerous_count == 2, f"Expected 2 dangerous tools, got {dangerous_count}"
