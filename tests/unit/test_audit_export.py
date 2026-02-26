"""Unit tests for ``atlasbridge audit export``."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from atlasbridge.core.store.database import Database


@pytest.fixture()
def db_with_events(tmp_path: Path) -> Database:
    """Create a Database with sample audit events."""
    db = Database(tmp_path / "test.db")
    db.connect()
    db.append_audit_event(
        event_id="evt-001",
        event_type="session_started",
        payload={"tool": "claude"},
        session_id="sess-1",
    )
    db.append_audit_event(
        event_id="evt-002",
        event_type="prompt_detected",
        payload={"prompt_type": "yes_no"},
        session_id="sess-1",
        prompt_id="p-1",
    )
    db.append_audit_event(
        event_id="evt-003",
        event_type="session_started",
        payload={"tool": "claude"},
        session_id="sess-2",
    )
    return db


class TestGetAuditEventsFiltered:
    def test_no_filters_returns_all(self, db_with_events: Database) -> None:
        rows = db_with_events.get_audit_events_filtered()
        assert len(rows) == 3

    def test_filter_by_session(self, db_with_events: Database) -> None:
        rows = db_with_events.get_audit_events_filtered(session_id="sess-1")
        assert len(rows) == 2
        assert all(r["session_id"] == "sess-1" for r in rows)

    def test_filter_by_since(self, db_with_events: Database) -> None:
        all_rows = db_with_events.get_audit_events_filtered()
        mid_ts = all_rows[1]["timestamp"]
        rows = db_with_events.get_audit_events_filtered(since=mid_ts)
        assert len(rows) >= 2

    def test_filter_by_until(self, db_with_events: Database) -> None:
        all_rows = db_with_events.get_audit_events_filtered()
        first_ts = all_rows[0]["timestamp"]
        rows = db_with_events.get_audit_events_filtered(until=first_ts)
        assert len(rows) == 1

    def test_empty_result(self, db_with_events: Database) -> None:
        rows = db_with_events.get_audit_events_filtered(session_id="nonexistent")
        assert rows == []


class TestAuditExportCLI:
    def test_export_help(self) -> None:
        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_group

        runner = CliRunner()
        result = runner.invoke(audit_group, ["export", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--session" in result.output
        assert "--since" in result.output
        assert "--until" in result.output

    def test_export_jsonl(self, db_with_events: Database, tmp_path: Path) -> None:
        from unittest.mock import patch

        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_group

        runner = CliRunner()
        mock_config = type("C", (), {"db_path": db_with_events._path})()
        with patch("atlasbridge.core.config.load_config", return_value=mock_config):
            result = runner.invoke(audit_group, ["export", "--format", "jsonl"])
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().split("\n") if ln]
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "event_type" in obj
            assert "hash" in obj

    def test_export_json(self, db_with_events: Database) -> None:
        from unittest.mock import patch

        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_group

        runner = CliRunner()
        mock_config = type("C", (), {"db_path": db_with_events._path})()
        with patch("atlasbridge.core.config.load_config", return_value=mock_config):
            result = runner.invoke(audit_group, ["export", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_export_csv(self, db_with_events: Database) -> None:
        from unittest.mock import patch

        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_group

        runner = CliRunner()
        mock_config = type("C", (), {"db_path": db_with_events._path})()
        with patch("atlasbridge.core.config.load_config", return_value=mock_config):
            result = runner.invoke(audit_group, ["export", "--format", "csv"])
        assert result.exit_code == 0
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 3
        assert "event_type" in rows[0]
        assert "hash" in rows[0]

    def test_export_session_filter(self, db_with_events: Database) -> None:
        from unittest.mock import patch

        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_group

        runner = CliRunner()
        mock_config = type("C", (), {"db_path": db_with_events._path})()
        with patch("atlasbridge.core.config.load_config", return_value=mock_config):
            result = runner.invoke(audit_group, ["export", "--session", "sess-1"])
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().split("\n") if ln]
        assert len(lines) == 2

    def test_export_empty_db(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_group

        db = Database(tmp_path / "empty.db")
        db.connect()

        runner = CliRunner()
        mock_config = type("C", (), {"db_path": db._path})()
        with patch("atlasbridge.core.config.load_config", return_value=mock_config):
            result = runner.invoke(audit_group, ["export", "--format", "jsonl"])
        assert result.exit_code == 0
        assert result.output.strip() == ""
        db.close()
