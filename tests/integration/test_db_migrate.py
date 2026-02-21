"""Integration tests for the `atlasbridge db migrate` CLI command."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from atlasbridge.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestDbMigrateCommand:
    def test_migrate_dry_run_up_to_date(self, runner: CliRunner, tmp_path: Path) -> None:
        """Dry-run on an up-to-date DB should say so."""
        from atlasbridge.core.store.database import Database

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db = Database(data_dir / "atlasbridge.db")
        db.connect()
        db.close()

        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=data_dir):
            result = runner.invoke(
                cli,
                ["db", "migrate", "--dry-run"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    def test_migrate_dry_run_json(self, runner: CliRunner, tmp_path: Path) -> None:
        """JSON output should include expected fields."""
        from atlasbridge.core.store.database import Database

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db = Database(data_dir / "atlasbridge.db")
        db.connect()
        db.close()

        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=data_dir):
            result = runner.invoke(
                cli,
                ["db", "migrate", "--dry-run", "--json"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "current_version" in data
        assert "latest_version" in data
        assert "status" in data

    def test_migrate_dry_run_shows_pending(self, runner: CliRunner, tmp_path: Path) -> None:
        """Dry-run on an old DB should list pending migrations."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "atlasbridge.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA user_version = 0")
        conn.close()

        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=data_dir):
            result = runner.invoke(
                cli,
                ["db", "migrate", "--dry-run"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "Pending migrations" in result.output
        assert "v0 -> v1" in result.output

    def test_migrate_applies_migrations(self, runner: CliRunner, tmp_path: Path) -> None:
        """Running without --dry-run should apply migrations."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "atlasbridge.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA user_version = 0")
        conn.close()

        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=data_dir):
            result = runner.invoke(
                cli,
                ["db", "migrate"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "applied successfully" in result.output.lower()

        # Verify version bumped
        from atlasbridge.core.store.migrations import LATEST_SCHEMA_VERSION, get_user_version

        conn = sqlite3.connect(str(db_path))
        assert get_user_version(conn) == LATEST_SCHEMA_VERSION
        conn.close()

    def test_migrate_no_database(self, runner: CliRunner, tmp_path: Path) -> None:
        """When no DB exists, should report that."""
        data_dir = tmp_path / "empty"
        data_dir.mkdir()

        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=data_dir):
            result = runner.invoke(
                cli,
                ["db", "migrate"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "does not exist" in result.output
