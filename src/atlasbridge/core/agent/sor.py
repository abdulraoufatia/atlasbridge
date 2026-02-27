"""
System of Record writer — structured persistence for agent operations.

All writes go through this class, ensuring:
  - Record IDs are generated and returned
  - Audit events are appended to the hash chain for every SoR write
  - Records follow the canonical schema
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from atlasbridge.core.store.database import Database

logger = structlog.get_logger()


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SystemOfRecordWriter:
    """Writes structured records to the agent SoR tables."""

    def __init__(self, db: Database, session_id: str, trace_id: str) -> None:
        self._db = db
        self._session_id = session_id
        self._trace_id = trace_id
        self._turn_counter = 0

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def record_turn(
        self,
        role: str,
        content: str = "",
        state: str = "intake",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write a turn record. Returns the turn_id."""
        turn_id = _new_id()
        self._turn_counter += 1
        self._db.save_agent_turn(
            turn_id=turn_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
            turn_number=self._turn_counter,
            role=role,
            content=content,
            state=state,
            metadata=json.dumps(metadata or {}, separators=(",", ":")),
        )
        self._audit("agent_turn_recorded", {"turn_id": turn_id, "role": role, "state": state})
        logger.info("sor_turn_recorded", turn_id=turn_id[:8], role=role)
        return turn_id

    def update_turn(self, turn_id: str, **kwargs: Any) -> None:
        """Update a turn record (content, state, metadata)."""
        if "metadata" in kwargs and isinstance(kwargs["metadata"], dict):
            kwargs["metadata"] = json.dumps(kwargs["metadata"], separators=(",", ":"))
        self._db.update_agent_turn(turn_id, **kwargs)

    def record_plan(
        self,
        turn_id: str,
        description: str,
        steps: list[dict[str, Any]],
        risk_level: str = "low",
    ) -> str:
        """Write a plan record. Returns the plan_id."""
        plan_id = _new_id()
        self._db.save_agent_plan(
            plan_id=plan_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
            turn_id=turn_id,
            description=description,
            steps=json.dumps(steps, separators=(",", ":")),
            risk_level=risk_level,
        )
        self._audit(
            "agent_plan_proposed",
            {"plan_id": plan_id, "turn_id": turn_id, "risk_level": risk_level},
        )
        logger.info("sor_plan_recorded", plan_id=plan_id[:8], risk=risk_level)
        return plan_id

    def resolve_plan(self, plan_id: str, status: str, resolved_by: str = "policy") -> None:
        """Update a plan's resolution status."""
        self._db.update_agent_plan(
            plan_id,
            status=status,
            resolved_at=_now(),
            resolved_by=resolved_by,
        )
        self._audit(
            "agent_plan_resolved",
            {"plan_id": plan_id, "status": status, "resolved_by": resolved_by},
        )

    def record_decision(
        self,
        turn_id: str,
        decision_type: str,
        action: str,
        plan_id: str | None = None,
        rule_matched: str | None = None,
        confidence: str = "medium",
        explanation: str = "",
        risk_score: int = 0,
    ) -> str:
        """Write a decision record. Returns the decision_id."""
        decision_id = _new_id()
        self._db.save_agent_decision(
            decision_id=decision_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
            turn_id=turn_id,
            decision_type=decision_type,
            action=action,
            plan_id=plan_id,
            rule_matched=rule_matched,
            confidence=confidence,
            explanation=explanation,
            risk_score=risk_score,
        )
        self._audit(
            "agent_decision_recorded",
            {"decision_id": decision_id, "type": decision_type, "action": action},
        )
        return decision_id

    def record_tool_run(
        self,
        turn_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
        is_error: bool = False,
        duration_ms: float | None = None,
        plan_id: str | None = None,
    ) -> str:
        """Write a tool run record. Returns the tool_run_id."""
        tool_run_id = _new_id()
        self._db.save_agent_tool_run(
            tool_run_id=tool_run_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
            turn_id=turn_id,
            tool_name=tool_name,
            arguments=json.dumps(arguments, separators=(",", ":")),
            result=result[:10_000],  # Truncate large results
            is_error=1 if is_error else 0,
            duration_ms=duration_ms,
            plan_id=plan_id,
        )
        self._audit(
            "agent_tool_executed",
            {
                "tool_run_id": tool_run_id,
                "tool": tool_name,
                "is_error": is_error,
                "duration_ms": duration_ms,
            },
        )
        logger.info("sor_tool_run_recorded", tool_run_id=tool_run_id[:8], tool=tool_name)
        return tool_run_id

    def record_outcome(
        self,
        turn_id: str,
        status: str,
        summary: str = "",
        tool_runs_count: int = 0,
        total_duration_ms: float | None = None,
    ) -> str:
        """Write an outcome record. Returns the outcome_id."""
        outcome_id = _new_id()
        self._db.save_agent_outcome(
            outcome_id=outcome_id,
            session_id=self._session_id,
            trace_id=self._trace_id,
            turn_id=turn_id,
            status=status,
            summary=summary,
            tool_runs_count=tool_runs_count,
            total_duration_ms=total_duration_ms,
        )
        self._audit(
            "agent_outcome_recorded",
            {"outcome_id": outcome_id, "status": status, "tool_runs": tool_runs_count},
        )
        logger.info("sor_outcome_recorded", outcome_id=outcome_id[:8], status=status)
        return outcome_id

    def _audit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Append an audit event to the hash chain."""
        payload["trace_id"] = self._trace_id
        self._db.append_audit_event(
            event_id=_new_id(),
            event_type=event_type,
            payload=payload,
            session_id=self._session_id,
        )
