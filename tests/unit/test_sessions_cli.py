"""Tests for atlasbridge sessions CLI command."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from rich.console import Console


def _make_console():
    buf = StringIO()
    return Console(file=buf, force_terminal=False), buf


def _mock_row(data: dict):
    """Create a sqlite3.Row-like mock that supports dict() and key access."""
    row = MagicMock()
    row.keys.return_value = list(data.keys())
    row.__iter__ = MagicMock(return_value=iter(data.values()))
    row.__getitem__ = MagicMock(side_effect=lambda key: data[key])
    return row


class TestCmdSessions:
    def test_no_config(self):
        from atlasbridge.cli._sessions import cmd_sessions
        from atlasbridge.core.exceptions import ConfigNotFoundError

        console, buf = _make_console()
        with patch("atlasbridge.core.config.load_config") as mock_cfg:
            mock_cfg.side_effect = ConfigNotFoundError("no config")
            cmd_sessions(as_json=False, console=console)
        output = buf.getvalue()
        assert "not configured" in output

    def test_no_config_json(self, capsys):
        from atlasbridge.cli._sessions import cmd_sessions
        from atlasbridge.core.exceptions import ConfigNotFoundError

        console, _ = _make_console()
        with patch("atlasbridge.core.config.load_config") as mock_cfg:
            mock_cfg.side_effect = ConfigNotFoundError("no config")
            cmd_sessions(as_json=True, console=console)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "error" in data

    def test_empty_sessions(self, tmp_path):
        from atlasbridge.cli._sessions import cmd_sessions

        console, buf = _make_console()
        db_path = tmp_path / "test.db"
        db_path.touch()

        mock_db = MagicMock()
        mock_db.list_active_sessions.return_value = []

        with (
            patch("atlasbridge.core.config.load_config") as mock_cfg,
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            mock_cfg.return_value.db_path = db_path
            cmd_sessions(as_json=False, console=console)
        output = buf.getvalue()
        assert "No active sessions" in output

    def test_one_session(self, tmp_path):
        from atlasbridge.cli._sessions import cmd_sessions

        console, buf = _make_console()
        db_path = tmp_path / "test.db"
        db_path.touch()

        row = _mock_row(
            {
                "id": "abc123def456",
                "tool": "claude",
                "status": "running",
                "started_at": "2026-02-21T10:00:00",
            }
        )
        mock_db = MagicMock()
        mock_db.list_active_sessions.return_value = [row]
        mock_db.list_pending_prompts.return_value = []

        with (
            patch("atlasbridge.core.config.load_config") as mock_cfg,
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            mock_cfg.return_value.db_path = db_path
            cmd_sessions(as_json=False, console=console)
        output = buf.getvalue()
        assert "abc123def456" in output
        assert "claude" in output

    def test_json_output(self, tmp_path, capsys):
        from atlasbridge.cli._sessions import cmd_sessions

        console, _ = _make_console()
        db_path = tmp_path / "test.db"
        db_path.touch()

        row = _mock_row(
            {
                "id": "sess001",
                "tool": "claude",
                "status": "running",
                "started_at": "2026-02-21T10:00:00",
            }
        )
        mock_db = MagicMock()
        mock_db.list_active_sessions.return_value = [row]
        mock_db.list_pending_prompts.return_value = []

        with (
            patch("atlasbridge.core.config.load_config") as mock_cfg,
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            mock_cfg.return_value.db_path = db_path
            cmd_sessions(as_json=True, console=console)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["tool"] == "claude"

    def test_db_not_exists(self, tmp_path):
        from atlasbridge.cli._sessions import cmd_sessions

        console, buf = _make_console()

        with patch("atlasbridge.core.config.load_config") as mock_cfg:
            mock_cfg.return_value.db_path = tmp_path / "nonexistent.db"
            cmd_sessions(as_json=False, console=console)
        output = buf.getvalue()
        assert "No active sessions" in output
