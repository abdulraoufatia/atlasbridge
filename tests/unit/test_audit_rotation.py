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


class TestSizeBasedRotation:
    """Tests for size-based (row count) audit rotation."""

    def test_rotation_triggers_at_size_threshold(self, db: Database, tmp_path: Path) -> None:
        """When row count exceeds max_rows, oldest events are archived."""
        for i in range(10):
            ts = (datetime.now(UTC) - timedelta(hours=10 - i)).isoformat()
            _insert_event_at(db, ts, f"event_{i}")

        assert db.count_audit_events() == 10

        archive_path = tmp_path / "audit_archive.1.db"
        archived = db.archive_oldest_audit_events(archive_path, keep_count=5)

        assert archived == 5
        assert db.count_audit_events() == 5

        # Verify the 5 newest events were kept
        remaining = db.get_recent_audit_events(limit=100)
        types = {r["event_type"] for r in remaining}
        for i in range(5, 10):
            assert f"event_{i}" in types

    def test_no_rotation_when_under_threshold(self, db: Database, tmp_path: Path) -> None:
        """No archival when row count is at or below max_rows."""
        for i in range(5):
            _insert_event_at(db, datetime.now(UTC).isoformat(), f"event_{i}")

        archive_path = tmp_path / "audit_archive.1.db"
        archived = db.archive_oldest_audit_events(archive_path, keep_count=5)

        assert archived == 0
        assert not archive_path.exists()
        assert db.count_audit_events() == 5

    def test_size_rotation_preserves_hash_chain(self, db: Database, tmp_path: Path) -> None:
        """Archived events maintain hash chain integrity."""
        for i in range(6):
            ts = (datetime.now(UTC) - timedelta(hours=6 - i)).isoformat()
            _insert_event_at(db, ts, f"event_{i}")

        archive_path = tmp_path / "audit_archive.1.db"
        archived = db.archive_oldest_audit_events(archive_path, keep_count=2)

        assert archived == 4

        conn = sqlite3.connect(str(archive_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_events ORDER BY timestamp ASC").fetchall()
        conn.close()
        assert len(rows) == 4
        # Hash chain links should be preserved
        for j in range(1, len(rows)):
            assert rows[j]["prev_hash"] == rows[j - 1]["hash"]

    def test_size_and_age_combined_archives_more(self, db: Database, tmp_path: Path) -> None:
        """When both thresholds apply, the larger set is archived."""
        # 3 old events (age-archivable) + 7 recent events = 10 total
        for i in range(3):
            ts = (datetime.now(UTC) - timedelta(days=100 + i)).isoformat()
            _insert_event_at(db, ts, f"old_{i}")
        for i in range(7):
            ts = (datetime.now(UTC) - timedelta(hours=i + 1)).isoformat()
            _insert_event_at(db, ts, f"recent_{i}")

        assert db.count_audit_events() == 10

        # Age threshold: 3 events older than 90 days
        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        archive_age = tmp_path / "age.db"
        # Size threshold: keep 5, archive 5 (> 3 from age)
        archive_size = tmp_path / "size.db"

        age_count = db.archive_audit_events(archive_age, cutoff)
        assert age_count == 3
        assert db.count_audit_events() == 7

        # Now apply size threshold on the remaining 7
        size_count = db.archive_oldest_audit_events(archive_size, keep_count=5)
        assert size_count == 2
        assert db.count_audit_events() == 5
