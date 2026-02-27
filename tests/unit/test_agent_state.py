"""Unit tests for the Expert Agent state machine."""

from __future__ import annotations

import pytest

from atlasbridge.core.agent.state import VALID_AGENT_TRANSITIONS, AgentState, AgentStateMachine


class TestAgentStateEnum:
    """AgentState enum has exactly 10 values."""

    def test_all_states_exist(self) -> None:
        expected = {
            "init",
            "ready",
            "intake",
            "plan",
            "gate",
            "execute",
            "synthesise",
            "respond",
            "stopping",
            "stopped",
        }
        assert {s.value for s in AgentState} == expected

    def test_state_values_are_lowercase(self) -> None:
        for s in AgentState:
            assert s.value == s.value.lower()


class TestValidTransitions:
    """VALID_AGENT_TRANSITIONS defines all allowed state changes."""

    def test_all_states_have_entries(self) -> None:
        for state in AgentState:
            assert state in VALID_AGENT_TRANSITIONS, f"Missing transitions for {state}"

    def test_terminal_states_have_no_outgoing(self) -> None:
        assert VALID_AGENT_TRANSITIONS[AgentState.STOPPED] == set()

    def test_init_goes_to_ready(self) -> None:
        assert AgentState.READY in VALID_AGENT_TRANSITIONS[AgentState.INIT]

    def test_ready_goes_to_intake_and_stopping(self) -> None:
        targets = VALID_AGENT_TRANSITIONS[AgentState.READY]
        assert AgentState.INTAKE in targets
        assert AgentState.STOPPING in targets

    def test_plan_can_gate_or_execute(self) -> None:
        targets = VALID_AGENT_TRANSITIONS[AgentState.PLAN]
        assert AgentState.GATE in targets
        assert AgentState.EXECUTE in targets

    def test_gate_resolves_to_execute_or_respond(self) -> None:
        targets = VALID_AGENT_TRANSITIONS[AgentState.GATE]
        assert AgentState.EXECUTE in targets
        assert AgentState.RESPOND in targets

    def test_respond_loops_back_to_ready(self) -> None:
        assert AgentState.READY in VALID_AGENT_TRANSITIONS[AgentState.RESPOND]


class TestAgentStateMachine:
    """AgentStateMachine transition logic."""

    def test_initial_state_is_init(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        assert sm.state == AgentState.INIT

    def test_valid_transition_updates_state(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        assert sm.state == AgentState.READY

    def test_invalid_transition_raises(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        with pytest.raises(ValueError, match="Invalid.*transition"):
            sm.transition(AgentState.EXECUTE)

    def test_full_happy_path(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        path = [
            AgentState.READY,
            AgentState.INTAKE,
            AgentState.PLAN,
            AgentState.EXECUTE,
            AgentState.SYNTHESISE,
            AgentState.RESPOND,
            AgentState.READY,
        ]
        for target in path:
            sm.transition(target)
        assert sm.state == AgentState.READY

    def test_gate_path(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.INTAKE)
        sm.transition(AgentState.PLAN)
        sm.transition(AgentState.GATE)
        assert sm.is_gated
        sm.transition(AgentState.EXECUTE)
        assert not sm.is_gated

    def test_gate_denial_goes_to_respond(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.INTAKE)
        sm.transition(AgentState.PLAN)
        sm.transition(AgentState.GATE)
        sm.transition(AgentState.RESPOND)
        assert sm.state == AgentState.RESPOND
        sm.transition(AgentState.READY)
        assert sm.state == AgentState.READY

    def test_is_terminal_on_stopped(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.STOPPING)
        sm.transition(AgentState.STOPPED)
        assert sm.is_terminal

    def test_is_terminal_false_for_non_terminal(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        assert not sm.is_terminal

    def test_can_accept_input(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        assert sm.can_accept_input
        sm.transition(AgentState.INTAKE)
        assert not sm.can_accept_input

    def test_gate_also_accepts_input(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.INTAKE)
        sm.transition(AgentState.PLAN)
        sm.transition(AgentState.GATE)
        assert sm.can_accept_input

    def test_history_records_transitions(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.INTAKE)
        assert len(sm.history) == 2
        # History stores (new_state, reason_string)
        assert sm.history[0][0] == AgentState.READY
        assert sm.history[1][0] == AgentState.INTAKE

    def test_on_transition_callback(self) -> None:
        calls: list[tuple[AgentState, AgentState, str]] = []
        sm = AgentStateMachine(
            session_id="s1",
            on_transition=lambda f, t, r: calls.append((f, t, r)),
        )
        sm.transition(AgentState.READY)
        assert len(calls) == 1
        assert calls[0][0] == AgentState.INIT
        assert calls[0][1] == AgentState.READY

    def test_to_dict(self) -> None:
        sm = AgentStateMachine(session_id="s1", trace_id="t1")
        sm.transition(AgentState.READY)
        d = sm.to_dict()
        assert d["session_id"] == "s1"
        assert d["state"] == "ready"
        assert d["trace_id"] == "t1"

    def test_stopping_goes_to_stopped(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.STOPPING)
        sm.transition(AgentState.STOPPED)
        assert sm.is_terminal

    def test_cannot_transition_from_stopped(self) -> None:
        sm = AgentStateMachine(session_id="s1")
        sm.transition(AgentState.READY)
        sm.transition(AgentState.STOPPING)
        sm.transition(AgentState.STOPPED)
        with pytest.raises(ValueError, match="Invalid.*transition"):
            sm.transition(AgentState.READY)
