"""
Agent lifecycle state machine.

  INIT → READY → INTAKE → PLAN → GATE → EXECUTE → SYNTHESISE → RESPOND → READY
                                   ↓                                       ↑
                              (denied) ────────────────────────────────────┘
  READY → STOPPING → STOPPED (terminal)

Rules:
  - The PLAN → GATE → EXECUTE sequence is mandatory when tools or SoR mutations
    are involved.
  - Every state transition writes to the audit trail.
  - The agent never writes to SoR except through the runtime's SoR writer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class AgentState(StrEnum):
    """States for the Expert Agent state machine."""

    INIT = "init"
    READY = "ready"
    INTAKE = "intake"
    PLAN = "plan"
    GATE = "gate"
    EXECUTE = "execute"
    SYNTHESISE = "synthesise"
    RESPOND = "respond"
    STOPPING = "stopping"
    STOPPED = "stopped"


VALID_AGENT_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.INIT: {AgentState.READY},
    AgentState.READY: {AgentState.INTAKE, AgentState.STOPPING},
    AgentState.INTAKE: {AgentState.PLAN, AgentState.RESPOND},
    AgentState.PLAN: {AgentState.GATE, AgentState.EXECUTE, AgentState.RESPOND},
    AgentState.GATE: {AgentState.EXECUTE, AgentState.RESPOND, AgentState.STOPPING},
    AgentState.EXECUTE: {AgentState.SYNTHESISE, AgentState.GATE},
    AgentState.SYNTHESISE: {AgentState.RESPOND},
    AgentState.RESPOND: {AgentState.READY},
    AgentState.STOPPING: {AgentState.STOPPED},
    AgentState.STOPPED: set(),
}

TERMINAL_STATES = {AgentState.STOPPED}


@dataclass
class AgentStateMachine:
    """Tracks state for a single Expert Agent session."""

    session_id: str
    state: AgentState = AgentState.INIT
    trace_id: str = ""
    active_turn_id: str = ""
    active_plan_id: str = ""
    history: list[tuple[AgentState, str]] = field(default_factory=list)
    on_transition: Callable[[AgentState, AgentState, str], None] | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def can_accept_input(self) -> bool:
        return self.state in (AgentState.READY, AgentState.GATE)

    @property
    def is_gated(self) -> bool:
        return self.state == AgentState.GATE

    def transition(self, new_state: AgentState, reason: str = "") -> None:
        """Advance state; raise ValueError on invalid transition."""
        allowed = VALID_AGENT_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid agent transition {self.state!r} → {new_state!r} "
                f"(session {self.session_id[:8]})"
            )
        old = self.state
        self.state = new_state
        self.history.append((new_state, reason or f"{old} → {new_state}"))
        if self.on_transition:
            self.on_transition(old, new_state, reason)

    def to_dict(self) -> dict[str, object]:
        """Serialise current state for API responses."""
        return {
            "session_id": self.session_id,
            "state": str(self.state),
            "trace_id": self.trace_id,
            "active_turn_id": self.active_turn_id,
            "active_plan_id": self.active_plan_id,
            "is_terminal": self.is_terminal,
            "can_accept_input": self.can_accept_input,
            "is_gated": self.is_gated,
        }
