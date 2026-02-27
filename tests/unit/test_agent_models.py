"""Unit tests for Expert Agent dataclasses."""

from __future__ import annotations

import sqlite3

from atlasbridge.core.agent.models import (
    AgentDecision,
    AgentOutcome,
    AgentPlan,
    AgentProfile,
    AgentToolRun,
    AgentTurn,
)


def _make_row(data: dict) -> sqlite3.Row:
    """Create a sqlite3.Row from a dict for testing from_row()."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    conn.execute(f"CREATE TABLE t ({cols})")
    conn.execute(f"INSERT INTO t VALUES ({placeholders})", list(data.values()))
    row = conn.execute("SELECT * FROM t").fetchone()
    conn.close()
    return row


class TestAgentTurn:
    def test_construction(self) -> None:
        t = AgentTurn(
            id="t1",
            session_id="s1",
            trace_id="tr1",
            turn_number=1,
            role="user",
            content="hello",
            state="intake",
            created_at="2025-01-01T00:00:00",
            metadata={},
        )
        assert t.id == "t1"
        assert t.role == "user"

    def test_to_dict(self) -> None:
        t = AgentTurn(
            id="t1",
            session_id="s1",
            trace_id="tr1",
            turn_number=1,
            role="assistant",
            content="hi",
            state="respond",
            created_at="2025-01-01T00:00:00",
            metadata={"key": "val"},
        )
        d = t.to_dict()
        assert d["id"] == "t1"
        assert d["metadata"] == {"key": "val"}

    def test_from_row(self) -> None:
        row = _make_row(
            {
                "id": "t1",
                "session_id": "s1",
                "trace_id": "tr1",
                "turn_number": 2,
                "role": "user",
                "content": "test",
                "state": "intake",
                "created_at": "2025-01-01",
                "metadata": "{}",
            }
        )
        t = AgentTurn.from_row(row)
        assert t.id == "t1"
        assert t.turn_number == 2
        assert t.metadata == {}

    def test_from_row_with_json_metadata(self) -> None:
        row = _make_row(
            {
                "id": "t1",
                "session_id": "s1",
                "trace_id": "tr1",
                "turn_number": 1,
                "role": "user",
                "content": "",
                "state": "intake",
                "created_at": "2025-01-01",
                "metadata": '{"foo": "bar"}',
            }
        )
        t = AgentTurn.from_row(row)
        assert t.metadata == {"foo": "bar"}


class TestAgentPlan:
    def test_construction(self) -> None:
        p = AgentPlan(
            id="p1",
            session_id="s1",
            trace_id="tr1",
            turn_id="t1",
            status="proposed",
            description="Do something",
            steps=[{"tool": "ab_list_sessions", "arguments_preview": "{}"}],
            risk_level="low",
            created_at="2025-01-01",
        )
        assert p.status == "proposed"
        assert len(p.steps) == 1

    def test_to_dict(self) -> None:
        p = AgentPlan(
            id="p1",
            session_id="s1",
            trace_id="tr1",
            turn_id="t1",
            status="approved",
            description="x",
            steps=[],
            risk_level="high",
            created_at="2025-01-01",
            resolved_at="2025-01-02",
            resolved_by="human",
        )
        d = p.to_dict()
        assert d["resolved_by"] == "human"

    def test_from_row(self) -> None:
        row = _make_row(
            {
                "id": "p1",
                "session_id": "s1",
                "trace_id": "tr1",
                "turn_id": "t1",
                "status": "proposed",
                "description": "plan",
                "steps": '[{"tool":"t","arguments_preview":"a"}]',
                "risk_level": "medium",
                "created_at": "2025-01-01",
                "resolved_at": None,
                "resolved_by": None,
            }
        )
        p = AgentPlan.from_row(row)
        assert p.steps == [{"tool": "t", "arguments_preview": "a"}]


class TestAgentDecision:
    def test_construction_and_roundtrip(self) -> None:
        d = AgentDecision(
            id="d1",
            session_id="s1",
            trace_id="tr1",
            plan_id="p1",
            turn_id="t1",
            decision_type="tool_call",
            action="allow",
            rule_matched="rule-1",
            confidence="high",
            explanation="ok",
            risk_score=0.2,
            created_at="2025-01-01",
        )
        data = d.to_dict()
        assert data["action"] == "allow"
        assert data["risk_score"] == 0.2

    def test_from_row(self) -> None:
        row = _make_row(
            {
                "id": "d1",
                "session_id": "s1",
                "trace_id": "tr1",
                "plan_id": None,
                "turn_id": "t1",
                "decision_type": "escalate",
                "action": "escalate",
                "rule_matched": None,
                "confidence": "low",
                "explanation": "no match",
                "risk_score": 0.8,
                "created_at": "2025-01-01",
            }
        )
        d = AgentDecision.from_row(row)
        assert d.plan_id is None
        assert d.action == "escalate"


class TestAgentToolRun:
    def test_construction(self) -> None:
        r = AgentToolRun(
            id="r1",
            session_id="s1",
            trace_id="tr1",
            plan_id="p1",
            turn_id="t1",
            tool_name="ab_get_stats",
            arguments={"foo": "bar"},
            result='{"ok":true}',
            is_error=False,
            duration_ms=42,
            created_at="2025-01-01",
        )
        assert r.tool_name == "ab_get_stats"
        assert r.duration_ms == 42

    def test_from_row(self) -> None:
        row = _make_row(
            {
                "id": "r1",
                "session_id": "s1",
                "trace_id": "tr1",
                "plan_id": None,
                "turn_id": "t1",
                "tool_name": "ab_list_sessions",
                "arguments": '{"limit":10}',
                "result": "[]",
                "is_error": 0,
                "duration_ms": 100,
                "created_at": "2025-01-01",
            }
        )
        r = AgentToolRun.from_row(row)
        assert r.arguments == {"limit": 10}
        assert r.is_error is False


class TestAgentOutcome:
    def test_construction_and_dict(self) -> None:
        o = AgentOutcome(
            id="o1",
            session_id="s1",
            trace_id="tr1",
            turn_id="t1",
            status="success",
            summary="Completed",
            tool_runs_count=3,
            total_duration_ms=500,
            created_at="2025-01-01",
        )
        d = o.to_dict()
        assert d["tool_runs_count"] == 3

    def test_from_row(self) -> None:
        row = _make_row(
            {
                "id": "o1",
                "session_id": "s1",
                "trace_id": "tr1",
                "turn_id": "t1",
                "status": "failed",
                "summary": "oops",
                "tool_runs_count": 0,
                "total_duration_ms": None,
                "created_at": "2025-01-01",
            }
        )
        o = AgentOutcome.from_row(row)
        assert o.status == "failed"
        assert o.total_duration_ms is None


class TestAgentProfile:
    def test_construction(self) -> None:
        p = AgentProfile(
            name="expert_v1",
            version="1.0.0",
            description="Expert agent",
            capabilities=["policy", "audit"],
            system_prompt_template="You are...",
            risk_tier="moderate",
            max_autonomy="assist",
        )
        assert p.name == "expert_v1"
        assert "policy" in p.capabilities

    def test_to_dict(self) -> None:
        p = AgentProfile(
            name="test",
            version="0.1",
            description="t",
            capabilities=[],
            system_prompt_template="",
            risk_tier="low",
            max_autonomy="full",
        )
        d = p.to_dict()
        assert d["max_autonomy"] == "full"
