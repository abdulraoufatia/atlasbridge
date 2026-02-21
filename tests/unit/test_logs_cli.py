"""Tests for atlasbridge logs CLI command."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from rich.console import Console


def _make_console():
    buf = StringIO()
    return Console(file=buf, force_terminal=False), buf


def _mock_row(data: dict):
    row = MagicMock()
    row.keys.return_value = list(data.keys())
    row.__iter__ = MagicMock(return_value=iter(data.values()))
    row.__getitem__ = MagicMock(side_effect=lambda key: data[key])
    return row


class TestCmdLogs:
    def test_no_config(self):
        from atlasbridge.cli._logs import cmd_logs
        from atlasbridge.core.exceptions import ConfigNotFoundError

        console, buf = _make_console()
        with patch("atlasbridge.core.config.load_config") as mock_cfg:
            mock_cfg.side_effect = ConfigNotFoundError("no config")
            cmd_logs(session_id="", tail=False, limit=50, as_json=False, console=console)
        output = buf.getvalue()
        assert "not configured" in output

    def test_no_db_file(self, tmp_path):
        from atlasbridge.cli._logs import cmd_logs

        console, buf = _make_console()
        with patch("atlasbridge.core.config.load_config") as mock_cfg:
            mock_cfg.return_value.db_path = tmp_path / "nonexistent.db"
            cmd_logs(session_id="", tail=False, limit=50, as_json=False, console=console)
        output = buf.getvalue()
        assert "No database found" in output

    def test_empty_log(self, tmp_path):
        from atlasbridge.cli._logs import cmd_logs

        console, buf = _make_console()
        db_path = tmp_path / "test.db"
        db_path.touch()

        mock_db = MagicMock()
        mock_db.get_recent_audit_events.return_value = []

        with (
            patch("atlasbridge.core.config.load_config") as mock_cfg,
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            mock_cfg.return_value.db_path = db_path
            cmd_logs(session_id="", tail=False, limit=50, as_json=False, console=console)
        output = buf.getvalue()
        assert "No log entries" in output

    def test_shows_events(self, tmp_path):
        from atlasbridge.cli._logs import cmd_logs

        console, buf = _make_console()
        db_path = tmp_path / "test.db"
        db_path.touch()

        row = _mock_row(
            {
                "id": "evt1",
                "event_type": "prompt_created",
                "session_id": "sess001",
                "prompt_id": "prompt001",
                "payload": "{}",
                "timestamp": "2026-02-21T10:00:00",
                "prev_hash": "",
                "hash": "",
            }
        )
        mock_db = MagicMock()
        mock_db.get_recent_audit_events.return_value = [row]

        with (
            patch("atlasbridge.core.config.load_config") as mock_cfg,
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            mock_cfg.return_value.db_path = db_path
            cmd_logs(session_id="", tail=False, limit=50, as_json=False, console=console)
        output = buf.getvalue()
        assert "prompt_created" in output

    def test_session_filter(self, tmp_path):
        from atlasbridge.cli._logs import cmd_logs

        console, buf = _make_console()
        db_path = tmp_path / "test.db"
        db_path.touch()

        rows = [
            _mock_row(
                {
                    "id": "evt1",
                    "event_type": "prompt_created",
                    "session_id": "sess001",
                    "prompt_id": "p1",
                    "payload": "{}",
                    "timestamp": "2026-02-21T10:00:00",
                    "prev_hash": "",
                    "hash": "",
                }
            ),
            _mock_row(
                {
                    "id": "evt2",
                    "event_type": "reply_received",
                    "session_id": "sess999",
                    "prompt_id": "p2",
                    "payload": "{}",
                    "timestamp": "2026-02-21T10:01:00",
                    "prev_hash": "",
                    "hash": "",
                }
            ),
        ]
        mock_db = MagicMock()
        mock_db.get_recent_audit_events.return_value = rows

        with (
            patch("atlasbridge.core.config.load_config") as mock_cfg,
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            mock_cfg.return_value.db_path = db_path
            cmd_logs(session_id="sess001", tail=False, limit=50, as_json=False, console=console)
        output = buf.getvalue()
        assert "prompt_created" in output
        # sess999 row should be filtered out
        assert "reply_received" not in output

    def test_json_output(self, tmp_path, capsys):
        from atlasbridge.cli._logs import cmd_logs

        console, _ = _make_console()
        db_path = tmp_path / "test.db"
        db_path.touch()

        row = _mock_row(
            {
                "id": "evt1",
                "event_type": "session_started",
                "session_id": "sess001",
                "prompt_id": "",
                "payload": "{}",
                "timestamp": "2026-02-21T10:00:00",
                "prev_hash": "",
                "hash": "",
            }
        )
        mock_db = MagicMock()
        mock_db.get_recent_audit_events.return_value = [row]

        with (
            patch("atlasbridge.core.config.load_config") as mock_cfg,
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            mock_cfg.return_value.db_path = db_path
            cmd_logs(session_id="", tail=False, limit=50, as_json=True, console=console)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert data[0]["event_type"] == "session_started"

    def test_no_db_json(self, tmp_path, capsys):
        from atlasbridge.cli._logs import cmd_logs

        console, _ = _make_console()
        with patch("atlasbridge.core.config.load_config") as mock_cfg:
            mock_cfg.return_value.db_path = tmp_path / "nonexistent.db"
            cmd_logs(session_id="", tail=False, limit=50, as_json=True, console=console)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == []
