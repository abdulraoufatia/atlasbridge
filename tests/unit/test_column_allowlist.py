"""Unit tests for the update_session column allowlist."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlasbridge.core.store.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    database.connect()
    yield database
    database.close()


class TestColumnAllowlist:
    def test_allowed_column_succeeds(self, db: Database) -> None:
        db.save_session("s1", "claude", ["claude"])
        # Should not raise
        db.update_session("s1", status="running")
        row = db.get_session("s1")
        assert row is not None
        assert row["status"] == "running"

    def test_multiple_allowed_columns(self, db: Database) -> None:
        db.save_session("s2", "claude", ["claude"])
        db.update_session("s2", status="completed", exit_code=0)
        row = db.get_session("s2")
        assert row is not None
        assert row["status"] == "completed"
        assert row["exit_code"] == 0

    def test_disallowed_column_raises(self, db: Database) -> None:
        db.save_session("s3", "claude", ["claude"])
        with pytest.raises(ValueError, match="disallowed column"):
            db.update_session("s3", id="injected-id")

    def test_mixed_allowed_disallowed_raises(self, db: Database) -> None:
        db.save_session("s4", "claude", ["claude"])
        with pytest.raises(ValueError, match="disallowed column"):
            db.update_session("s4", status="running", drop_table="sessions")

    def test_empty_kwargs_noop(self, db: Database) -> None:
        db.save_session("s5", "claude", ["claude"])
        # Should not raise or do anything
        db.update_session("s5")

    def test_all_allowed_columns(self, db: Database) -> None:
        """Every column in the allowlist should work."""
        db.save_session("s6", "claude", ["claude"])
        for col in Database._ALLOWED_SESSION_COLUMNS:
            # Use a safe value for each column
            val = "test" if col not in ("pid", "exit_code") else 1
            db.update_session("s6", **{col: val})
