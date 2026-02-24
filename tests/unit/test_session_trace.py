"""Tests for atlasbridge.core.session.trace — session trace timeline."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from atlasbridge.core.session.trace import (
    SessionTrace,
    TraceEvent,
    build_session_trace,
    format_trace,
    trace_to_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_row(data: dict):
    """Create a mock that behaves like sqlite3.Row."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    row.keys = lambda: list(data.keys())
    return row


def _mock_db(session=None, audit_events=None, prompts=None):
    """Create a mock Database with configurable return values."""
    db = MagicMock()
    db.get_session.return_value = session
    db.get_audit_events_for_session.return_value = audit_events or []
    db.list_prompts_for_session.return_value = prompts or []
    return db


def _make_session_row(
    session_id="sess-001",
    tool="claude",
    status="completed",
    started_at="2026-01-01T10:00:00",
    ended_at="2026-01-01T10:30:00",
):
    return _mock_row(
        {
            "id": session_id,
            "tool": tool,
            "status": status,
            "started_at": started_at,
            "ended_at": ended_at,
        }
    )


def _make_audit_row(
    event_type="prompt_detected",
    session_id="sess-001",
    prompt_id="prompt-001",
    timestamp="2026-01-01T10:05:00",
    payload="{}",
):
    return _mock_row(
        {
            "id": f"evt-{event_type[:8]}",
            "event_type": event_type,
            "session_id": session_id,
            "prompt_id": prompt_id,
            "timestamp": timestamp,
            "payload": payload,
        }
    )


# ---------------------------------------------------------------------------
# build_session_trace() tests
# ---------------------------------------------------------------------------


class TestBuildSessionTrace:
    def test_returns_none_for_missing_session(self):
        db = _mock_db(session=None)
        result = build_session_trace(db, "nonexistent")
        assert result is None

    def test_basic_trace(self):
        session = _make_session_row()
        audit = [
            _make_audit_row("session_started", timestamp="2026-01-01T10:00:00"),
            _make_audit_row(
                "prompt_detected",
                timestamp="2026-01-01T10:05:00",
                payload=json.dumps(
                    {"prompt_type": "yes_no", "confidence": "high", "trigger": "pattern_match"}
                ),
            ),
            _make_audit_row("session_ended", timestamp="2026-01-01T10:30:00"),
        ]
        db = _mock_db(session=session, audit_events=audit)

        trace = build_session_trace(db, "sess-001")

        assert trace is not None
        assert trace.session_id == "sess-001"
        assert trace.tool == "claude"
        assert trace.event_count == 3
        assert trace.events[0].event_type == "session_started"
        assert trace.events[1].event_type == "prompt_detected"
        assert trace.events[2].event_type == "session_ended"

    def test_prompt_count(self):
        session = _make_session_row()
        prompts = [_mock_row({"id": f"p{i}"}) for i in range(3)]
        db = _mock_db(session=session, prompts=prompts)

        trace = build_session_trace(db, "sess-001")

        assert trace is not None
        assert trace.prompt_count == 3

    def test_event_details_parsed(self):
        session = _make_session_row()
        audit = [
            _make_audit_row(
                "prompt_detected",
                payload=json.dumps({"prompt_type": "yes_no", "confidence": "high"}),
            ),
        ]
        db = _mock_db(session=session, audit_events=audit)

        trace = build_session_trace(db, "sess-001")

        assert trace.events[0].details["prompt_type"] == "yes_no"
        assert trace.events[0].details["confidence"] == "high"

    def test_empty_payload_handled(self):
        session = _make_session_row()
        audit = [_make_audit_row("session_started", payload="")]
        db = _mock_db(session=session, audit_events=audit)

        trace = build_session_trace(db, "sess-001")

        assert trace.events[0].details == {}

    def test_invalid_json_payload_handled(self):
        session = _make_session_row()
        audit = [_make_audit_row("session_started", payload="not-json")]
        db = _mock_db(session=session, audit_events=audit)

        trace = build_session_trace(db, "sess-001")

        assert trace.events[0].details == {}

    def test_event_labels(self):
        session = _make_session_row()
        audit = [
            _make_audit_row("session_started"),
            _make_audit_row("prompt_detected"),
            _make_audit_row("response_injected"),
        ]
        db = _mock_db(session=session, audit_events=audit)

        trace = build_session_trace(db, "sess-001")

        assert trace.events[0].label == "Session Started"
        assert trace.events[1].label == "Prompt Detected"
        assert trace.events[2].label == "Response Injected"


# ---------------------------------------------------------------------------
# format_trace() tests
# ---------------------------------------------------------------------------


class TestFormatTrace:
    def test_output_contains_session_info(self):
        trace = SessionTrace(
            session_id="sess-001",
            tool="claude",
            status="completed",
            started_at="2026-01-01T10:00:00",
            ended_at="2026-01-01T10:30:00",
            event_count=0,
        )
        output = format_trace(trace)

        assert "sess-001" in output
        assert "claude" in output
        assert "completed" in output
        assert "Timeline:" in output

    def test_empty_events(self):
        trace = SessionTrace(
            session_id="sess-001",
            tool="claude",
            status="completed",
            started_at="2026-01-01T10:00:00",
            ended_at=None,
        )
        output = format_trace(trace)

        assert "no events recorded" in output

    def test_events_formatted(self):
        trace = SessionTrace(
            session_id="sess-001",
            tool="claude",
            status="completed",
            started_at="2026-01-01T10:00:00",
            ended_at="2026-01-01T10:30:00",
            events=[
                TraceEvent(
                    timestamp="2026-01-01T10:00:00",
                    event_type="session_started",
                    label="Session Started",
                    prompt_id="",
                    details={"tool": "claude"},
                ),
                TraceEvent(
                    timestamp="2026-01-01T10:05:00",
                    event_type="prompt_detected",
                    label="Prompt Detected",
                    prompt_id="prompt-001",
                    details={"prompt_type": "yes_no", "confidence": "high"},
                ),
            ],
            event_count=2,
        )
        output = format_trace(trace)

        assert "Session Started" in output
        assert "Prompt Detected" in output
        assert "2026-01-01T10:00:00" in output
        assert "type=yes_no" in output
        assert "confidence=high" in output

    def test_response_injected_shows_latency(self):
        trace = SessionTrace(
            session_id="s1",
            tool="claude",
            status="completed",
            started_at="t0",
            ended_at="t1",
            events=[
                TraceEvent(
                    timestamp="t0",
                    event_type="response_injected",
                    label="Response Injected",
                    prompt_id="p1",
                    details={"prompt_type": "yes_no", "latency_ms": 42},
                ),
            ],
            event_count=1,
        )
        output = format_trace(trace)

        assert "latency=42ms" in output


# ---------------------------------------------------------------------------
# trace_to_json() tests
# ---------------------------------------------------------------------------


class TestTraceToJson:
    def test_valid_json_output(self):
        trace = SessionTrace(
            session_id="sess-001",
            tool="claude",
            status="completed",
            started_at="2026-01-01T10:00:00",
            ended_at="2026-01-01T10:30:00",
            events=[
                TraceEvent(
                    timestamp="2026-01-01T10:00:00",
                    event_type="session_started",
                    label="Session Started",
                    prompt_id="",
                ),
            ],
            prompt_count=1,
            event_count=1,
        )
        result = trace_to_json(trace)
        data = json.loads(result)

        assert data["session_id"] == "sess-001"
        assert data["tool"] == "claude"
        assert data["event_count"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "session_started"

    def test_json_contains_all_fields(self):
        trace = SessionTrace(
            session_id="s1",
            tool="claude",
            status="running",
            started_at="t0",
            ended_at=None,
            prompt_count=3,
            event_count=5,
        )
        result = trace_to_json(trace)
        data = json.loads(result)

        assert "session_id" in data
        assert "tool" in data
        assert "status" in data
        assert "started_at" in data
        assert "ended_at" in data
        assert "prompt_count" in data
        assert "event_count" in data
        assert "events" in data
