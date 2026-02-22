"""Tests for dashboard read-only repository."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


class TestDashboardRepoStats:
    def test_get_stats_with_data(self, repo):
        stats = repo.get_stats()
        assert stats["sessions"] == 2
        assert stats["prompts"] == 2
        assert stats["audit_events"] == 3
        assert stats["active_sessions"] == 1

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
        assert len(sessions) == 2
        # Most recent first
        assert sessions[0]["id"] == "sess-001"

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


class TestDashboardRepoPrompts:
    def test_list_prompts_for_session(self, repo):
        prompts = repo.list_prompts_for_session("sess-001")
        assert len(prompts) == 2
        assert prompts[0]["id"] == "prompt-001"

    def test_list_prompts_empty(self, repo):
        assert repo.list_prompts_for_session("sess-002") == []


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


class TestDashboardRepoAudit:
    def test_list_audit_events(self, repo):
        events = repo.list_audit_events()
        assert len(events) == 3

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
