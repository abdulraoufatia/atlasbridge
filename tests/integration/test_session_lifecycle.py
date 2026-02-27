"""
Integration tests for session lifecycle: start → pause → resume → stop.

Uses a real SQLite database (no mocks) to verify that the CLI commands
correctly update session state through the full lifecycle.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from atlasbridge.cli.main import cli
from atlasbridge.core.store.database import Database


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a real DB with schema and a running session."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "atlasbridge.db"
    db = Database(path)
    db.connect()
    # Insert a session with a known PID (our own PID so signals are valid)
    import os

    our_pid = os.getpid()
    db.save_session("sess-1111-2222-3333-444455556666", "claude", ["claude"], cwd="/tmp", label="test")
    db.update_session("sess-1111-2222-3333-444455556666", status="running", pid=our_pid)
    db.close()
    return path


def _patch_db(db_path: Path):
    """Patch _open_db to return a Database connected to our test file."""

    def _open():
        db = Database(db_path)
        db.connect()
        return db

    return patch("atlasbridge.cli._sessions._open_db", side_effect=_open)


def _get_status(db_path: Path, session_id: str) -> str:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return row["status"] if row else "NOT_FOUND"


SID = "sess-1111-2222-3333-444455556666"


class TestSessionLifecycle:
    """Full lifecycle: running → paused → running → canceled."""

    def test_pause_updates_db(self, runner: CliRunner, db_path: Path) -> None:
        with _patch_db(db_path), patch("os.kill"):
            result = runner.invoke(cli, ["sessions", "pause", SID, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert _get_status(db_path, SID) == "paused"

    def test_resume_updates_db(self, runner: CliRunner, db_path: Path) -> None:
        # First pause
        with _patch_db(db_path), patch("os.kill"):
            runner.invoke(cli, ["sessions", "pause", SID, "--json"])
        assert _get_status(db_path, SID) == "paused"
        # Then resume
        with _patch_db(db_path), patch("os.kill"):
            result = runner.invoke(cli, ["sessions", "resume", SID, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert _get_status(db_path, SID) == "running"

    def test_stop_updates_db(self, runner: CliRunner, db_path: Path) -> None:
        with _patch_db(db_path), patch("os.kill"):
            result = runner.invoke(cli, ["sessions", "stop", SID, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert _get_status(db_path, SID) == "canceled"

    def test_full_lifecycle(self, runner: CliRunner, db_path: Path) -> None:
        """running → paused → running → canceled"""
        assert _get_status(db_path, SID) == "running"

        with _patch_db(db_path), patch("os.kill"):
            runner.invoke(cli, ["sessions", "pause", SID, "--json"])
        assert _get_status(db_path, SID) == "paused"

        with _patch_db(db_path), patch("os.kill"):
            runner.invoke(cli, ["sessions", "resume", SID, "--json"])
        assert _get_status(db_path, SID) == "running"

        with _patch_db(db_path), patch("os.kill"):
            runner.invoke(cli, ["sessions", "stop", SID, "--json"])
        assert _get_status(db_path, SID) == "canceled"

    def test_cannot_pause_after_stop(self, runner: CliRunner, db_path: Path) -> None:
        with _patch_db(db_path), patch("os.kill"):
            runner.invoke(cli, ["sessions", "stop", SID, "--json"])
        assert _get_status(db_path, SID) == "canceled"

        with _patch_db(db_path):
            result = runner.invoke(cli, ["sessions", "pause", SID, "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False

    def test_cannot_resume_running(self, runner: CliRunner, db_path: Path) -> None:
        assert _get_status(db_path, SID) == "running"
        with _patch_db(db_path):
            result = runner.invoke(cli, ["sessions", "resume", SID, "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "not paused" in data["error"].lower()

    def test_stop_already_stopped(self, runner: CliRunner, db_path: Path) -> None:
        with _patch_db(db_path), patch("os.kill"):
            runner.invoke(cli, ["sessions", "stop", SID, "--json"])
        with _patch_db(db_path):
            result = runner.invoke(cli, ["sessions", "stop", SID, "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "already canceled" in data["error"].lower()


class TestSessionStartNoPid:
    """Sessions with no PID should be gracefully handled."""

    @pytest.fixture()
    def db_no_pid(self, tmp_path: Path) -> Path:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        path = data_dir / "atlasbridge.db"
        db = Database(path)
        db.connect()
        db.save_session("nopid-1111-2222-3333-444455556666", "claude", ["claude"])
        # Status is 'starting', no PID set
        db.close()
        return path

    def test_stop_no_pid_marks_canceled(self, runner: CliRunner, db_no_pid: Path) -> None:
        sid = "nopid-1111-2222-3333-444455556666"
        with _patch_db(db_no_pid):
            result = runner.invoke(cli, ["sessions", "stop", sid, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert _get_status(db_no_pid, sid) == "canceled"
