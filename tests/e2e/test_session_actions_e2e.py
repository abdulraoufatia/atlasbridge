"""
E2E tests for session start/pause/resume/stop actions.

Uses a real Database and real CLI invocations through CliRunner.
Verifies the full end-to-end flow including DB persistence.
"""

from __future__ import annotations

import json
import os
import signal
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
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "atlasbridge"
    d.mkdir()
    return d


@pytest.fixture()
def db(data_dir: Path) -> Database:
    """Create a real DB and insert a running session with our PID."""
    database = Database(data_dir / "atlasbridge.db")
    database.connect()
    database.save_session(
        "e2e-sess-1111-2222-333344445555",
        "claude",
        ["claude"],
        cwd="/tmp",
        label="e2e-test",
    )
    database.update_session(
        "e2e-sess-1111-2222-333344445555",
        status="running",
        pid=os.getpid(),
    )
    database.close()
    return database


def _patch_open_db(data_dir: Path):
    def _open():
        db = Database(data_dir / "atlasbridge.db")
        db.connect()
        return db

    return patch("atlasbridge.cli._sessions._open_db", side_effect=_open)


def _read_status(data_dir: Path, session_id: str) -> str:
    conn = sqlite3.connect(str(data_dir / "atlasbridge.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return row["status"] if row else "NOT_FOUND"


SID = "e2e-sess-1111-2222-333344445555"


class TestE2ESessionPauseResumeStop:
    """End-to-end: pause → resume → stop with real DB and mocked signals."""

    def test_e2e_pause(self, runner: CliRunner, db: Database, data_dir: Path) -> None:
        with _patch_open_db(data_dir), patch("os.kill") as mock_kill:
            result = runner.invoke(cli, ["sessions", "pause", SID, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["signal"] == "SIGSTOP"
        mock_kill.assert_called_once_with(os.getpid(), signal.SIGSTOP)
        assert _read_status(data_dir, SID) == "paused"

    def test_e2e_resume(self, runner: CliRunner, db: Database, data_dir: Path) -> None:
        # Pause first
        with _patch_open_db(data_dir), patch("os.kill"):
            runner.invoke(cli, ["sessions", "pause", SID, "--json"])
        assert _read_status(data_dir, SID) == "paused"

        # Resume
        with _patch_open_db(data_dir), patch("os.kill") as mock_kill:
            result = runner.invoke(cli, ["sessions", "resume", SID, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["signal"] == "SIGCONT"
        mock_kill.assert_called_once_with(os.getpid(), signal.SIGCONT)
        assert _read_status(data_dir, SID) == "running"

    def test_e2e_stop(self, runner: CliRunner, db: Database, data_dir: Path) -> None:
        with _patch_open_db(data_dir), patch("os.kill") as mock_kill:
            result = runner.invoke(cli, ["sessions", "stop", SID, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["signal"] == "SIGTERM"
        mock_kill.assert_called_once_with(os.getpid(), signal.SIGTERM)
        assert _read_status(data_dir, SID) == "canceled"

    def test_e2e_full_lifecycle(self, runner: CliRunner, db: Database, data_dir: Path) -> None:
        """running → paused → running → canceled — all verified against real DB."""
        assert _read_status(data_dir, SID) == "running"

        # Pause
        with _patch_open_db(data_dir), patch("os.kill"):
            r = runner.invoke(cli, ["sessions", "pause", SID, "--json"])
        assert json.loads(r.output)["ok"] is True
        assert _read_status(data_dir, SID) == "paused"

        # Resume
        with _patch_open_db(data_dir), patch("os.kill"):
            r = runner.invoke(cli, ["sessions", "resume", SID, "--json"])
        assert json.loads(r.output)["ok"] is True
        assert _read_status(data_dir, SID) == "running"

        # Stop
        with _patch_open_db(data_dir), patch("os.kill"):
            r = runner.invoke(cli, ["sessions", "stop", SID, "--json"])
        assert json.loads(r.output)["ok"] is True
        assert _read_status(data_dir, SID) == "canceled"

        # Cannot pause after stop
        with _patch_open_db(data_dir):
            r = runner.invoke(cli, ["sessions", "pause", SID, "--json"])
        assert json.loads(r.output)["ok"] is False

    def test_e2e_stop_dead_process_marks_canceled(
        self, runner: CliRunner, db: Database, data_dir: Path
    ) -> None:
        """When the process is already dead, stop should still mark as canceled."""
        with _patch_open_db(data_dir), patch("os.kill", side_effect=ProcessLookupError):
            result = runner.invoke(cli, ["sessions", "stop", SID, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert _read_status(data_dir, SID) == "canceled"

    def test_e2e_short_id_resolution(
        self, runner: CliRunner, db: Database, data_dir: Path
    ) -> None:
        """Short ID prefix should resolve to the full session ID."""
        with _patch_open_db(data_dir), patch("os.kill"):
            result = runner.invoke(cli, ["sessions", "pause", "e2e-sess", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["session_id"] == SID
