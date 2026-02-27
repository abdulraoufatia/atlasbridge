"""
Agent data models — dataclasses mirroring the System of Record tables.

Each model has:
  - to_dict()  — serialise for JSON/API output
  - from_row() — construct from a sqlite3.Row
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Agent Profile (not persisted — defined in code)
# ---------------------------------------------------------------------------


@dataclass
class AgentProfile:
    """Definition of an agent type (e.g. atlasbridge_expert_v1)."""

    name: str
    version: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    system_prompt_template: str = ""
    risk_tier: str = "moderate"
    max_autonomy: str = "assist"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": self.capabilities,
            "risk_tier": self.risk_tier,
            "max_autonomy": self.max_autonomy,
        }


# ---------------------------------------------------------------------------
# SoR record models
# ---------------------------------------------------------------------------


@dataclass
class AgentTurn:
    """A single conversational turn in an agent session."""

    id: str
    session_id: str
    trace_id: str
    turn_number: int
    role: str  # "user" | "assistant" | "tool"
    content: str = ""
    state: str = "intake"
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "turn_number": self.turn_number,
            "role": self.role,
            "content": self.content,
            "state": self.state,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AgentTurn:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            trace_id=row["trace_id"],
            turn_number=row["turn_number"],
            role=row["role"],
            content=row["content"],
            state=row["state"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )


@dataclass
class AgentPlan:
    """An execution plan proposed by the agent for a turn."""

    id: str
    session_id: str
    trace_id: str
    turn_id: str
    status: str = "proposed"  # proposed | approved | denied | executing | completed | failed
    description: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    risk_level: str = "low"
    created_at: str = ""
    resolved_at: str | None = None
    resolved_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "turn_id": self.turn_id,
            "status": self.status,
            "description": self.description,
            "steps": self.steps,
            "risk_level": self.risk_level,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AgentPlan:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            trace_id=row["trace_id"],
            turn_id=row["turn_id"],
            status=row["status"],
            description=row["description"],
            steps=json.loads(row["steps"]) if row["steps"] else [],
            risk_level=row["risk_level"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            resolved_by=row["resolved_by"],
        )


@dataclass
class AgentDecision:
    """A policy evaluation record for an agent action."""

    id: str
    session_id: str
    trace_id: str
    plan_id: str | None
    turn_id: str
    decision_type: str  # "tool_approval" | "plan_gate" | "auto_approve"
    action: str  # "allow" | "deny" | "escalate"
    rule_matched: str | None = None
    confidence: str = "medium"
    explanation: str = ""
    risk_score: int = 0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "plan_id": self.plan_id,
            "turn_id": self.turn_id,
            "decision_type": self.decision_type,
            "action": self.action,
            "rule_matched": self.rule_matched,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "risk_score": self.risk_score,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AgentDecision:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            trace_id=row["trace_id"],
            plan_id=row["plan_id"],
            turn_id=row["turn_id"],
            decision_type=row["decision_type"],
            action=row["action"],
            rule_matched=row["rule_matched"],
            confidence=row["confidence"],
            explanation=row["explanation"],
            risk_score=row["risk_score"],
            created_at=row["created_at"],
        )


@dataclass
class AgentToolRun:
    """A single tool invocation record."""

    id: str
    session_id: str
    trace_id: str
    plan_id: str | None
    turn_id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    is_error: bool = False
    duration_ms: float | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "plan_id": self.plan_id,
            "turn_id": self.turn_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result,
            "is_error": self.is_error,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AgentToolRun:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            trace_id=row["trace_id"],
            plan_id=row["plan_id"],
            turn_id=row["turn_id"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments"]) if row["arguments"] else {},
            result=row["result"],
            is_error=bool(row["is_error"]),
            duration_ms=row["duration_ms"],
            created_at=row["created_at"],
        )


@dataclass
class AgentOutcome:
    """The final result of an agent turn."""

    id: str
    session_id: str
    trace_id: str
    turn_id: str
    status: str  # "success" | "partial" | "failed" | "denied"
    summary: str = ""
    tool_runs_count: int = 0
    total_duration_ms: float | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "turn_id": self.turn_id,
            "status": self.status,
            "summary": self.summary,
            "tool_runs_count": self.tool_runs_count,
            "total_duration_ms": self.total_duration_ms,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AgentOutcome:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            trace_id=row["trace_id"],
            turn_id=row["turn_id"],
            status=row["status"],
            summary=row["summary"],
            tool_runs_count=row["tool_runs_count"],
            total_duration_ms=row["total_duration_ms"],
            created_at=row["created_at"],
        )
