"""Integration tests for Agent System of Record writer."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from atlasbridge.core.agent.sor import SystemOfRecordWriter
from atlasbridge.core.store.database import Database


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    database.connect()
    yield database
    database.close()


def _sid() -> str:
    return str(uuid.uuid4())


def _setup_session(db: Database) -> str:
    sid = _sid()
    db.save_session(sid, tool="agent", command=["agent"], cwd="/tmp")
    return sid


def _make_sor(db: Database, session_id: str, trace_id: str = "tr-test") -> SystemOfRecordWriter:
    return SystemOfRecordWriter(db, session_id=session_id, trace_id=trace_id)


class TestTurnRecording:
    def test_record_turn_returns_id(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        turn_id = sor.record_turn(role="user", content="hello", state="intake")
        assert turn_id
        assert isinstance(turn_id, str)

    def test_recorded_turn_readable(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        turn_id = sor.record_turn(role="user", content="test message", state="intake")
        turn = db.get_agent_turn(turn_id)
        assert turn is not None
        assert turn["content"] == "test message"
        assert turn["role"] == "user"

    def test_multiple_turns_ordered(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        sor.record_turn(role="user", content="first", state="intake")
        sor.record_turn(role="assistant", content="second", state="respond")
        turns = db.list_agent_turns(sid)
        assert len(turns) == 2
        assert turns[0]["turn_number"] == 1
        assert turns[1]["turn_number"] == 2


class TestPlanRecording:
    def test_record_plan_returns_id(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        turn_id = sor.record_turn(role="user", content="plan request", state="intake")
        plan_id = sor.record_plan(
            turn_id=turn_id,
            description="Do something",
            steps=[{"tool": "ab_list_sessions", "arguments_preview": "{}"}],
            risk_level="low",
        )
        assert plan_id
        assert isinstance(plan_id, str)

    def test_resolve_plan_updates_status(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        turn_id = sor.record_turn(role="user", content="need a plan", state="intake")
        plan_id = sor.record_plan(
            turn_id=turn_id,
            description="test plan",
            steps=[],
            risk_level="medium",
        )
        sor.resolve_plan(plan_id, status="approved", resolved_by="human")
        plan = db.get_agent_plan(plan_id)
        assert plan is not None
        assert plan["status"] == "approved"
        assert plan["resolved_by"] == "human"

    def test_plan_list_by_session(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        t1 = sor.record_turn(role="user", content="first", state="intake")
        t2 = sor.record_turn(role="user", content="second", state="intake")
        sor.record_plan(turn_id=t1, description="p1", steps=[], risk_level="low")
        sor.record_plan(turn_id=t2, description="p2", steps=[], risk_level="high")
        plans = db.list_agent_plans(sid)
        assert len(plans) == 2


class TestDecisionRecording:
    def test_record_decision(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        turn_id = sor.record_turn(role="user", content="decide", state="intake")
        dec_id = sor.record_decision(
            turn_id=turn_id,
            decision_type="tool_call",
            action="allow",
            rule_matched="rule-1",
            confidence="high",
            explanation="Policy allows this",
            risk_score=0.1,
        )
        assert dec_id
        decisions = db.list_agent_decisions(sid)
        assert len(decisions) == 1
        assert decisions[0]["action"] == "allow"


class TestToolRunRecording:
    def test_record_tool_run(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        turn_id = sor.record_turn(role="user", content="run tool", state="intake")
        run_id = sor.record_tool_run(
            turn_id=turn_id,
            tool_name="ab_list_sessions",
            arguments={"limit": 10},
            result='{"count":5}',
            is_error=False,
            duration_ms=42,
        )
        assert run_id
        runs = db.list_agent_tool_runs(sid)
        assert len(runs) == 1
        assert runs[0]["tool_name"] == "ab_list_sessions"
        assert runs[0]["duration_ms"] == 42


class TestOutcomeRecording:
    def test_record_outcome(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        turn_id = sor.record_turn(role="user", content="do work", state="intake")
        out_id = sor.record_outcome(
            turn_id=turn_id,
            status="success",
            summary="Completed 3 tool runs",
            tool_runs_count=3,
            total_duration_ms=500,
        )
        assert out_id
        outcomes = db.list_agent_outcomes(sid)
        assert len(outcomes) == 1
        assert outcomes[0]["status"] == "success"


class TestAuditIntegration:
    def test_turn_creates_audit_event(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        initial_count = db.count_audit_events()
        sor.record_turn(role="user", content="msg", state="intake")
        new_count = db.count_audit_events()
        assert new_count > initial_count

    def test_plan_creates_audit_event(self, db: Database) -> None:
        sid = _setup_session(db)
        sor = _make_sor(db, sid)
        turn_id = sor.record_turn(role="user", content="plan", state="intake")
        initial_count = db.count_audit_events()
        sor.record_plan(turn_id=turn_id, description="x", steps=[], risk_level="low")
        new_count = db.count_audit_events()
        assert new_count > initial_count
