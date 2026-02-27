"""
Tests for `atlasbridge sessions stop`, `sessions pause`, and `sessions resume` CLI commands.

Covers:
  - sessions stop (running session, already stopped, no PID, process not found, permission denied)
  - sessions pause (running session, wrong state, no PID, process not found, permission denied)
  - sessions resume (paused session, wrong state, no PID, process not found, permission denied)
  - JSON output for all commands
  - DB status updates on stop/pause/resume
"""

from __future__ import annotations

import json
import signal
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from atlasbridge.cli.main import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Fake sqlite3.Row-like objects
# ---------------------------------------------------------------------------


class _FakeRow(dict):
    """Dict that also supports integer index access (like sqlite3.Row)."""

    def __getitem__(self, key):  # type: ignore[override]
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


_RUNNING_SESSION = _FakeRow(
    id="aaaa1111-2222-3333-4444-555566667777",
    tool="claude",
    status="running",
    pid=12345,
    started_at="2025-06-15T10:00:00+00:00",
    ended_at=None,
    exit_code=None,
    cwd="/home/user/project",
    label="feat-branch",
    command='["claude"]',
    metadata="{}",
)

_PAUSED_SESSION = _FakeRow(**{**_RUNNING_SESSION, "status": "paused"})

_COMPLETED_SESSION = _FakeRow(**{**_RUNNING_SESSION, "status": "completed", "pid": 99999})

_NO_PID_SESSION = _FakeRow(**{**_RUNNING_SESSION, "pid": None})


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _mock_db(session: _FakeRow | None = None) -> MagicMock:
    db = MagicMock()
    db.get_session.return_value = session
    db.list_sessions.return_value = [session] if session else []
    db.update_session = MagicMock()
    db.close = MagicMock()
    return db


def _patch_open_db(mock_db: MagicMock | None):
    return patch("atlasbridge.cli._sessions._open_db", return_value=mock_db)


def _patch_kill(side_effect=None):
    return patch("os.kill", side_effect=side_effect)


# ---------------------------------------------------------------------------
# sessions stop
# ---------------------------------------------------------------------------


class TestSessionsStop:
    def test_no_database(self, runner: CliRunner) -> None:
        with _patch_open_db(None):
            result = runner.invoke(cli, ["sessions", "stop", "aaaa1111"])
        assert result.exit_code != 0
        assert "No database" in result.output

    def test_no_database_json(self, runner: CliRunner) -> None:
        with _patch_open_db(None):
            result = runner.invoke(cli, ["sessions", "stop", "aaaa1111", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "Database not found" in data["error"]

    def test_session_not_found(self, runner: CliRunner) -> None:
        db = _mock_db(session=None)
        db.get_session.return_value = None
        db.list_sessions.return_value = []
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "stop", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_already_completed(self, runner: CliRunner) -> None:
        db = _mock_db(session=_COMPLETED_SESSION)
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "stop", _COMPLETED_SESSION["id"]])
        assert result.exit_code == 0
        assert "already completed" in result.output.lower()

    def test_already_completed_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_COMPLETED_SESSION)
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "stop", _COMPLETED_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "already completed" in data["error"].lower()

    def test_no_pid_marks_canceled(self, runner: CliRunner) -> None:
        db = _mock_db(session=_NO_PID_SESSION)
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "stop", _NO_PID_SESSION["id"]])
        assert result.exit_code == 0
        assert "canceled" in result.output.lower()
        db.update_session.assert_called_once_with(_NO_PID_SESSION["id"], status="canceled")

    def test_no_pid_marks_canceled_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_NO_PID_SESSION)
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "stop", _NO_PID_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["action"] == "canceled"

    def test_sigterm_sent_and_db_updated(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill() as mock_kill:
            result = runner.invoke(cli, ["sessions", "stop", _RUNNING_SESSION["id"]])
        assert result.exit_code == 0
        assert "SIGTERM" in result.output
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)
        db.update_session.assert_called_once_with(_RUNNING_SESSION["id"], status="canceled")

    def test_sigterm_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill():
            result = runner.invoke(cli, ["sessions", "stop", _RUNNING_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["pid"] == 12345
        assert data["signal"] == "SIGTERM"

    def test_process_not_found_marks_canceled(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=ProcessLookupError):
            result = runner.invoke(cli, ["sessions", "stop", _RUNNING_SESSION["id"]])
        assert result.exit_code == 0
        assert "canceled" in result.output.lower()
        db.update_session.assert_called_once_with(_RUNNING_SESSION["id"], status="canceled")

    def test_process_not_found_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=ProcessLookupError):
            result = runner.invoke(cli, ["sessions", "stop", _RUNNING_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["action"] == "canceled"

    def test_permission_denied(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=PermissionError):
            result = runner.invoke(cli, ["sessions", "stop", _RUNNING_SESSION["id"]])
        assert result.exit_code != 0
        assert "Permission denied" in result.output

    def test_permission_denied_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=PermissionError):
            result = runner.invoke(cli, ["sessions", "stop", _RUNNING_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "Permission denied" in data["error"]


# ---------------------------------------------------------------------------
# sessions pause
# ---------------------------------------------------------------------------


class TestSessionsPause:
    def test_no_database(self, runner: CliRunner) -> None:
        with _patch_open_db(None):
            result = runner.invoke(cli, ["sessions", "pause", "aaaa1111"])
        assert result.exit_code != 0
        assert "No database" in result.output

    def test_no_database_json(self, runner: CliRunner) -> None:
        with _patch_open_db(None):
            result = runner.invoke(cli, ["sessions", "pause", "aaaa1111", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False

    def test_session_not_found(self, runner: CliRunner) -> None:
        db = _mock_db(session=None)
        db.get_session.return_value = None
        db.list_sessions.return_value = []
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "pause", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_wrong_state_completed(self, runner: CliRunner) -> None:
        db = _mock_db(session=_COMPLETED_SESSION)
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "pause", _COMPLETED_SESSION["id"]])
        assert result.exit_code == 0
        assert "Cannot pause" in result.output

    def test_wrong_state_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_COMPLETED_SESSION)
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "pause", _COMPLETED_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "Cannot pause" in data["error"]

    def test_no_pid(self, runner: CliRunner) -> None:
        db = _mock_db(session=_FakeRow(**{**_RUNNING_SESSION, "pid": None}))
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "pause", _RUNNING_SESSION["id"]])
        assert result.exit_code != 0
        assert "No PID" in result.output

    def test_sigstop_sent_and_db_updated(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill() as mock_kill:
            result = runner.invoke(cli, ["sessions", "pause", _RUNNING_SESSION["id"]])
        assert result.exit_code == 0
        assert "paused" in result.output.lower()
        mock_kill.assert_called_once_with(12345, signal.SIGSTOP)
        db.update_session.assert_called_once_with(_RUNNING_SESSION["id"], status="paused")

    def test_sigstop_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill():
            result = runner.invoke(cli, ["sessions", "pause", _RUNNING_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["pid"] == 12345
        assert data["signal"] == "SIGSTOP"

    def test_process_not_found(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=ProcessLookupError):
            result = runner.invoke(cli, ["sessions", "pause", _RUNNING_SESSION["id"]])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_permission_denied(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=PermissionError):
            result = runner.invoke(cli, ["sessions", "pause", _RUNNING_SESSION["id"]])
        assert result.exit_code != 0
        assert "Permission denied" in result.output

    def test_permission_denied_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=PermissionError):
            result = runner.invoke(cli, ["sessions", "pause", _RUNNING_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "Permission denied" in data["error"]

    def test_awaiting_reply_can_be_paused(self, runner: CliRunner) -> None:
        session = _FakeRow(**{**_RUNNING_SESSION, "status": "awaiting_reply"})
        db = _mock_db(session=session)
        with _patch_open_db(db), _patch_kill():
            result = runner.invoke(cli, ["sessions", "pause", session["id"]])
        assert result.exit_code == 0
        assert "paused" in result.output.lower()


# ---------------------------------------------------------------------------
# sessions resume
# ---------------------------------------------------------------------------


class TestSessionsResume:
    def test_no_database(self, runner: CliRunner) -> None:
        with _patch_open_db(None):
            result = runner.invoke(cli, ["sessions", "resume", "aaaa1111"])
        assert result.exit_code != 0
        assert "No database" in result.output

    def test_no_database_json(self, runner: CliRunner) -> None:
        with _patch_open_db(None):
            result = runner.invoke(cli, ["sessions", "resume", "aaaa1111", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False

    def test_session_not_found(self, runner: CliRunner) -> None:
        db = _mock_db(session=None)
        db.get_session.return_value = None
        db.list_sessions.return_value = []
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "resume", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_wrong_state_running(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "resume", _RUNNING_SESSION["id"]])
        assert result.exit_code == 0
        assert "not paused" in result.output.lower()

    def test_wrong_state_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_RUNNING_SESSION)
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "resume", _RUNNING_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "not paused" in data["error"].lower()

    def test_no_pid(self, runner: CliRunner) -> None:
        db = _mock_db(session=_FakeRow(**{**_PAUSED_SESSION, "pid": None}))
        with _patch_open_db(db):
            result = runner.invoke(cli, ["sessions", "resume", _PAUSED_SESSION["id"]])
        assert result.exit_code != 0
        assert "No PID" in result.output

    def test_sigcont_sent_and_db_updated(self, runner: CliRunner) -> None:
        db = _mock_db(session=_PAUSED_SESSION)
        with _patch_open_db(db), _patch_kill() as mock_kill:
            result = runner.invoke(cli, ["sessions", "resume", _PAUSED_SESSION["id"]])
        assert result.exit_code == 0
        assert "resumed" in result.output.lower()
        mock_kill.assert_called_once_with(12345, signal.SIGCONT)
        db.update_session.assert_called_once_with(_PAUSED_SESSION["id"], status="running")

    def test_sigcont_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_PAUSED_SESSION)
        with _patch_open_db(db), _patch_kill():
            result = runner.invoke(cli, ["sessions", "resume", _PAUSED_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["pid"] == 12345
        assert data["signal"] == "SIGCONT"

    def test_process_not_found(self, runner: CliRunner) -> None:
        db = _mock_db(session=_PAUSED_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=ProcessLookupError):
            result = runner.invoke(cli, ["sessions", "resume", _PAUSED_SESSION["id"]])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_permission_denied(self, runner: CliRunner) -> None:
        db = _mock_db(session=_PAUSED_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=PermissionError):
            result = runner.invoke(cli, ["sessions", "resume", _PAUSED_SESSION["id"]])
        assert result.exit_code != 0
        assert "Permission denied" in result.output

    def test_permission_denied_json(self, runner: CliRunner) -> None:
        db = _mock_db(session=_PAUSED_SESSION)
        with _patch_open_db(db), _patch_kill(side_effect=PermissionError):
            result = runner.invoke(cli, ["sessions", "resume", _PAUSED_SESSION["id"], "--json"])
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "Permission denied" in data["error"]


# ---------------------------------------------------------------------------
# sessions help includes new commands
# ---------------------------------------------------------------------------


class TestSessionsHelpIncludesNewCommands:
    def test_help_shows_stop(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["sessions", "--help"])
        assert "stop" in result.output

    def test_help_shows_pause(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["sessions", "--help"])
        assert "pause" in result.output

    def test_help_shows_resume(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["sessions", "--help"])
        assert "resume" in result.output
