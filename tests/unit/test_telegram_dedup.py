"""Unit tests for prompt delivery deduplication (schema migration + DB methods)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlasbridge.core.store.database import Database
from atlasbridge.core.store.migrations import (
    LATEST_SCHEMA_VERSION,
    _migrate_1_to_2,
    get_user_version,
)


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    """Fresh in-memory-style SQLite database with migrations applied."""
    d = Database(tmp_path / "test.db")
    d.connect()
    return d


class TestMigration1To2:
    def test_creates_prompt_deliveries_table(self, db: Database) -> None:
        row = db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='prompt_deliveries'"
        ).fetchone()
        assert row is not None

    def test_schema_version_is_latest(self, db: Database) -> None:
        assert get_user_version(db._db) == LATEST_SCHEMA_VERSION

    def test_unique_constraint_exists(self, db: Database) -> None:
        """Insert same (prompt_id, channel, channel_identity) twice — second is ignored."""
        db._db.execute(
            "INSERT INTO prompt_deliveries (prompt_id, session_id, channel, channel_identity) "
            "VALUES ('p1', 's1', 'telegram', 'telegram:123')"
        )
        db._db.commit()
        cur = db._db.execute(
            "INSERT OR IGNORE INTO prompt_deliveries "
            "(prompt_id, session_id, channel, channel_identity) "
            "VALUES ('p1', 's1', 'telegram', 'telegram:123')"
        )
        db._db.commit()
        assert cur.rowcount == 0

    def test_migrate_idempotent(self, db: Database) -> None:
        """Running migration again does not fail (CREATE TABLE IF NOT EXISTS)."""
        _migrate_1_to_2(db._db)


class TestRecordDelivery:
    def test_first_time_returns_true(self, db: Database) -> None:
        assert db.record_delivery("p1", "s1", "telegram", "telegram:100") is True

    def test_duplicate_returns_false(self, db: Database) -> None:
        db.record_delivery("p1", "s1", "telegram", "telegram:100")
        assert db.record_delivery("p1", "s1", "telegram", "telegram:100") is False

    def test_different_identity_returns_true(self, db: Database) -> None:
        db.record_delivery("p1", "s1", "telegram", "telegram:100")
        assert db.record_delivery("p1", "s1", "telegram", "telegram:200") is True

    def test_different_prompt_returns_true(self, db: Database) -> None:
        db.record_delivery("p1", "s1", "telegram", "telegram:100")
        assert db.record_delivery("p2", "s1", "telegram", "telegram:100") is True

    def test_message_id_stored(self, db: Database) -> None:
        db.record_delivery("p1", "s1", "telegram", "telegram:100", message_id="msg42")
        row = db._db.execute(
            "SELECT message_id FROM prompt_deliveries WHERE prompt_id='p1'"
        ).fetchone()
        assert row["message_id"] == "msg42"


class TestWasDelivered:
    def test_false_before_record(self, db: Database) -> None:
        assert db.was_delivered("p1", "telegram", "telegram:100") is False

    def test_true_after_record(self, db: Database) -> None:
        db.record_delivery("p1", "s1", "telegram", "telegram:100")
        assert db.was_delivered("p1", "telegram", "telegram:100") is True

    def test_false_for_different_identity(self, db: Database) -> None:
        db.record_delivery("p1", "s1", "telegram", "telegram:100")
        assert db.was_delivered("p1", "telegram", "telegram:200") is False

    def test_false_for_different_channel(self, db: Database) -> None:
        db.record_delivery("p1", "s1", "telegram", "telegram:100")
        assert db.was_delivered("p1", "slack", "telegram:100") is False


class TestDeliverySurvivesReconnect:
    def test_data_persists_across_connections(self, tmp_path: Path) -> None:
        db_path = tmp_path / "persist.db"

        db1 = Database(db_path)
        db1.connect()
        db1.record_delivery("p1", "s1", "telegram", "telegram:100")
        db1.close()

        db2 = Database(db_path)
        db2.connect()
        assert db2.was_delivered("p1", "telegram", "telegram:100") is True
        db2.close()
