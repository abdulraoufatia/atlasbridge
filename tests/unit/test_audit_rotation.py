"""Unit tests for audit log rotation (archive_audit_events)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from atlasbridge.core.audit.writer import AuditWriter
from atlasbridge.core.store.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "atlasbridge.db")
    d.connect()
    yield d
    d.close()


@pytest.fixture
def writer(db: Database) -> AuditWriter:
    return AuditWriter(db)


def _insert_event_at(db: Database, timestamp: str, event_type: str = "test_event") -> None:
    """Insert a test audit event with a specific timestamp."""
    import secrets

    event_id = secrets.token_hex(12)
    db.append_audit_event(
        event_id=event_id,
        event_type=event_type,
        payload={"test": True},
    )
    # Overwrite the auto-generated timestamp
    db._db.execute(
        "UPDATE audit_events SET timestamp = ? WHERE id = ?",
        (timestamp, event_id),
    )
    db._db.commit()


class TestAuditArchive:
    def test_archive_moves_old_events(self, db: Database, tmp_path: Path) -> None:
        old_ts = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        recent_ts = datetime.now(UTC).isoformat()

        _insert_event_at(db, old_ts, "old_event")
        _insert_event_at(db, recent_ts, "recent_event")

        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        archive_path = tmp_path / "audit_archive.1.db"

        archived = db.archive_audit_events(archive_path, cutoff)

        assert archived == 1

        # Verify main DB only has the recent event
        remaining = db.get_recent_audit_events(limit=100)
        assert len(remaining) == 1
        assert remaining[0]["event_type"] == "recent_event"

        # Verify archive has the old event
        conn = sqlite3.connect(str(archive_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_events").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "old_event"

    def test_archive_returns_zero_when_nothing_to_archive(
        self, db: Database, tmp_path: Path
    ) -> None:
        recent_ts = datetime.now(UTC).isoformat()
        _insert_event_at(db, recent_ts)

        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        archive_path = tmp_path / "audit_archive.1.db"

        archived = db.archive_audit_events(archive_path, cutoff)
        assert archived == 0
        assert not archive_path.exists()

    def test_archive_preserves_hash_chain_in_archive(self, db: Database, tmp_path: Path) -> None:
        old_ts1 = (datetime.now(UTC) - timedelta(days=200)).isoformat()
        old_ts2 = (datetime.now(UTC) - timedelta(days=150)).isoformat()

        _insert_event_at(db, old_ts1, "event_1")
        _insert_event_at(db, old_ts2, "event_2")

        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        archive_path = tmp_path / "audit_archive.1.db"

        archived = db.archive_audit_events(archive_path, cutoff)
        assert archived == 2

        # Verify hash chain integrity in archive
        conn = sqlite3.connect(str(archive_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_events ORDER BY timestamp ASC").fetchall()
        conn.close()
        assert len(rows) == 2
        # First event's prev_hash should link to original chain
        # Second event's prev_hash should match first event's hash
        assert rows[1]["prev_hash"] == rows[0]["hash"]

    def test_archive_is_atomic_no_partial_writes(self, db: Database, tmp_path: Path) -> None:
        """Verify that after archiving, event counts are consistent."""
        old_ts = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        for _ in range(5):
            _insert_event_at(db, old_ts)
        recent_ts = datetime.now(UTC).isoformat()
        for _ in range(3):
            _insert_event_at(db, recent_ts)

        initial_count = db.count_audit_events()
        assert initial_count == 8

        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        archive_path = tmp_path / "audit_archive.1.db"
        archived = db.archive_audit_events(archive_path, cutoff)

        assert archived == 5
        assert db.count_audit_events() == 3

        # Archive has exactly the archived events
        conn = sqlite3.connect(str(archive_path))
        row = conn.execute("SELECT count(*) FROM audit_events").fetchone()
        conn.close()
        assert row[0] == 5

    def test_count_audit_events(self, db: Database) -> None:
        assert db.count_audit_events() == 0
        _insert_event_at(db, datetime.now(UTC).isoformat())
        assert db.count_audit_events() == 1
        _insert_event_at(db, datetime.now(UTC).isoformat())
        assert db.count_audit_events() == 2


class TestAuditArchiveSafety:
    """Safety tests: audit data is never lost."""

    def test_archived_data_not_deleted_only_moved(self, db: Database, tmp_path: Path) -> None:
        old_ts = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        _insert_event_at(db, old_ts, "important_event")

        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        archive_path = tmp_path / "audit_archive.1.db"

        db.archive_audit_events(archive_path, cutoff)

        # Event no longer in main DB
        remaining = db.get_recent_audit_events(limit=100)
        assert all(r["event_type"] != "important_event" for r in remaining)

        # But exists in archive
        conn = sqlite3.connect(str(archive_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_events WHERE event_type = 'important_event'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1

    def test_rotation_triggers_at_age_threshold(self, db: Database, tmp_path: Path) -> None:
        """Events older than the threshold are archived."""
        old_ts = (datetime.now(UTC) - timedelta(days=91)).isoformat()
        edge_ts = (datetime.now(UTC) - timedelta(days=89)).isoformat()

        _insert_event_at(db, old_ts, "should_archive")
        _insert_event_at(db, edge_ts, "should_keep")

        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        archive_path = tmp_path / "audit_archive.1.db"
        archived = db.archive_audit_events(archive_path, cutoff)

        assert archived == 1
        remaining = db.get_recent_audit_events(limit=100)
        assert len(remaining) == 1
        assert remaining[0]["event_type"] == "should_keep"
