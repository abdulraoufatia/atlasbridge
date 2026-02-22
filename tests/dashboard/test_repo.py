"""Tests for dashboard read-only repository."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


class TestDashboardRepoStats:
    def test_get_stats_with_data(self, repo):
        stats = repo.get_stats()
        assert stats["sessions"] == 4
        assert stats["prompts"] == 5
        assert stats["audit_events"] == 5
        assert stats["active_sessions"] == 2

    def test_get_stats_empty_db(self, empty_db, tmp_path):
        from atlasbridge.dashboard.repo import DashboardRepo

        r = DashboardRepo(empty_db, tmp_path / "nonexistent.jsonl")
        r.connect()
        stats = r.get_stats()
        assert stats["sessions"] == 0
        r.close()

    def test_get_stats_no_db(self, tmp_path):
        from atlasbridge.dashboard.repo import DashboardRepo

        r = DashboardRepo(tmp_path / "missing.db", tmp_path / "missing.jsonl")
        r.connect()
        stats = r.get_stats()
        assert stats["sessions"] == 0
        assert not r.db_available
        r.close()


class TestDashboardRepoSessions:
    def test_list_sessions(self, repo):
        sessions = repo.list_sessions()
        assert len(sessions) == 4
        # Most recent first (sess-004 started 2025-01-16)
        assert sessions[0]["id"] == "sess-004"

    def test_get_session(self, repo):
        session = repo.get_session("sess-001")
        assert session is not None
        assert session["tool"] == "claude"
        assert session["status"] == "running"

    def test_get_session_not_found(self, repo):
        assert repo.get_session("nonexistent") is None

    def test_list_sessions_no_db(self, tmp_path):
        from atlasbridge.dashboard.repo import DashboardRepo

        r = DashboardRepo(tmp_path / "missing.db", tmp_path / "missing.jsonl")
        r.connect()
        assert r.list_sessions() == []
        r.close()

    def test_list_sessions_filter_by_status(self, repo):
        sessions = repo.list_sessions(status="running")
        assert len(sessions) == 2
        assert all(s["status"] == "running" for s in sessions)

    def test_list_sessions_filter_by_tool(self, repo):
        sessions = repo.list_sessions(tool="claude")
        assert len(sessions) == 2
        assert all(s["tool"] == "claude" for s in sessions)

    def test_list_sessions_filter_by_tool_gemini(self, repo):
        sessions = repo.list_sessions(tool="gemini")
        assert len(sessions) == 1
        assert sessions[0]["id"] == "sess-003"

    def test_list_sessions_search_by_id(self, repo):
        sessions = repo.list_sessions(q="sess-001")
        assert len(sessions) == 1
        assert sessions[0]["id"] == "sess-001"

    def test_list_sessions_search_by_label(self, repo):
        sessions = repo.list_sessions(q="gemini")
        assert len(sessions) == 1
        assert sessions[0]["id"] == "sess-003"

    def test_list_sessions_combined_filters(self, repo):
        sessions = repo.list_sessions(status="running", tool="claude")
        assert len(sessions) == 1
        assert sessions[0]["id"] == "sess-001"

    def test_list_sessions_offset(self, repo):
        all_sessions = repo.list_sessions()
        offset_sessions = repo.list_sessions(offset=2)
        assert len(offset_sessions) == 2
        assert offset_sessions[0]["id"] == all_sessions[2]["id"]

    def test_list_sessions_limit(self, repo):
        sessions = repo.list_sessions(limit=2)
        assert len(sessions) == 2

    def test_list_sessions_filter_no_match(self, repo):
        sessions = repo.list_sessions(status="nonexistent")
        assert sessions == []

    def test_count_sessions(self, repo):
        assert repo.count_sessions() == 4

    def test_count_sessions_with_filter(self, repo):
        assert repo.count_sessions(status="running") == 2
        assert repo.count_sessions(tool="claude") == 2
        assert repo.count_sessions(tool="gemini") == 1

    def test_count_sessions_with_search(self, repo):
        assert repo.count_sessions(q="sess-001") == 1

    def test_count_sessions_no_db(self, tmp_path):
        from atlasbridge.dashboard.repo import DashboardRepo

        r = DashboardRepo(tmp_path / "missing.db", tmp_path / "missing.jsonl")
        r.connect()
        assert r.count_sessions() == 0
        r.close()


class TestDashboardRepoPrompts:
    def test_list_prompts_for_session(self, repo):
        prompts = repo.list_prompts_for_session("sess-001")
        assert len(prompts) == 4  # 3 original + 1 token-containing
        assert prompts[0]["id"] == "prompt-001"

    def test_list_prompts_empty(self, repo):
        assert repo.list_prompts_for_session("sess-002") == []

    def test_list_prompts_filter_by_type(self, repo):
        prompts = repo.list_prompts_for_session("sess-001", prompt_type="yes_no")
        assert len(prompts) == 2
        assert all(p["prompt_type"] == "yes_no" for p in prompts)

    def test_list_prompts_filter_by_confidence(self, repo):
        prompts = repo.list_prompts_for_session("sess-001", confidence="high")
        assert len(prompts) == 2  # prompt-001 + prompt-005
        assert prompts[0]["id"] == "prompt-001"

    def test_list_prompts_filter_by_status(self, repo):
        prompts = repo.list_prompts_for_session("sess-001", status="resolved")
        assert len(prompts) == 2  # prompt-002 + prompt-005
        assert prompts[0]["id"] == "prompt-002"


class TestDashboardRepoTrace:
    def test_trace_tail(self, repo):
        entries = repo.trace_tail(3)
        assert len(entries) == 3

    def test_trace_entry(self, repo):
        entry = repo.trace_entry(0)
        assert entry is not None
        assert "action_type" in entry

    def test_trace_entry_out_of_range(self, repo):
        assert repo.trace_entry(999) is None

    def test_verify_integrity(self, repo):
        valid, errors = repo.verify_integrity()
        assert valid
        assert errors == []

    def test_trace_not_available(self, db_with_data, tmp_path):
        from atlasbridge.dashboard.repo import DashboardRepo

        r = DashboardRepo(db_with_data, tmp_path / "nonexistent.jsonl")
        r.connect()
        assert not r.trace_available
        assert r.trace_tail() == []
        r.close()

    def test_trace_page_first_page(self, repo):
        entries, total = repo.trace_page(page=1, per_page=3)
        assert total == 5
        assert len(entries) == 3
        # Newest first
        assert entries[0]["idempotency_key"] == "key-4"

    def test_trace_page_second_page(self, repo):
        entries, total = repo.trace_page(page=2, per_page=3)
        assert total == 5
        assert len(entries) == 2

    def test_trace_page_filter_action_type(self, repo):
        entries, total = repo.trace_page(action_type="escalate")
        assert total == 2
        assert all(e["action_type"] == "escalate" for e in entries)

    def test_trace_page_filter_confidence(self, repo):
        entries, total = repo.trace_page(confidence="high")
        assert total == 2
        assert all(e["confidence"] == "high" for e in entries)

    def test_trace_page_empty_when_no_file(self, db_with_data, tmp_path):
        from atlasbridge.dashboard.repo import DashboardRepo

        r = DashboardRepo(db_with_data, tmp_path / "nonexistent.jsonl")
        r.connect()
        entries, total = r.trace_page()
        assert entries == []
        assert total == 0
        r.close()

    def test_trace_entries_for_session(self, repo):
        entries = repo.trace_entries_for_session("sess-001")
        assert len(entries) == 3
        assert all(e.get("session_id") == "sess-001" for e in entries)

    def test_trace_entries_for_session_with_limit(self, repo):
        entries = repo.trace_entries_for_session("sess-001", limit=1)
        assert len(entries) == 1

    def test_trace_entries_for_session_no_match(self, repo):
        entries = repo.trace_entries_for_session("nonexistent")
        assert entries == []

    def test_trace_entries_for_session_no_file(self, db_with_data, tmp_path):
        from atlasbridge.dashboard.repo import DashboardRepo

        r = DashboardRepo(db_with_data, tmp_path / "nonexistent.jsonl")
        r.connect()
        entries = r.trace_entries_for_session("sess-001")
        assert entries == []
        r.close()


class TestDashboardRepoAudit:
    def test_list_audit_events(self, repo):
        events = repo.list_audit_events()
        assert len(events) == 5

    def test_list_audit_events_with_offset(self, repo):
        events = repo.list_audit_events(limit=2, offset=2)
        assert len(events) == 2

    def test_list_audit_events_filter_by_type(self, repo):
        events = repo.list_audit_events(event_type="prompt_detected")
        assert len(events) == 3
        assert all(e["event_type"] == "prompt_detected" for e in events)

    def test_list_audit_events_filter_session_started(self, repo):
        events = repo.list_audit_events(event_type="session_started")
        assert len(events) == 1

    def test_verify_audit_integrity(self, repo):
        valid, errors = repo.verify_audit_integrity()
        assert valid
        assert errors == []


class TestReadOnlyGuard:
    def test_read_only_connection_rejects_writes(self, db_with_data):
        """Read-only SQLite connection must reject INSERT/UPDATE/DELETE."""
        conn = sqlite3.connect(f"file:{db_with_data}?mode=ro", uri=True)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO sessions (id) VALUES ('hack')")
        conn.close()
