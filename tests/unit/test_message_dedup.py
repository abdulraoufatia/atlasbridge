"""Unit tests for atlasbridge.core.store.message_dedup."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atlasbridge.core.store.message_dedup import mark_processed
from atlasbridge.core.store.migrations import run_migrations


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    run_migrations(c, db_path)
    yield c
    c.close()


class TestMarkProcessed:
    def test_first_call_returns_true(self, conn: sqlite3.Connection) -> None:
        result = mark_processed("telegram", "user123", "msg-001", conn)
        assert result is True

    def test_second_call_same_message_returns_false(self, conn: sqlite3.Connection) -> None:
        mark_processed("telegram", "user123", "msg-001", conn)
        result = mark_processed("telegram", "user123", "msg-001", conn)
        assert result is False

    def test_different_message_id_returns_true(self, conn: sqlite3.Connection) -> None:
        mark_processed("telegram", "user123", "msg-001", conn)
        result = mark_processed("telegram", "user123", "msg-002", conn)
        assert result is True

    def test_different_channel_identity_returns_true(self, conn: sqlite3.Connection) -> None:
        mark_processed("telegram", "user123", "msg-001", conn)
        result = mark_processed("telegram", "user456", "msg-001", conn)
        assert result is True

    def test_different_channel_returns_true(self, conn: sqlite3.Connection) -> None:
        mark_processed("telegram", "user123", "msg-001", conn)
        result = mark_processed("slack", "user123", "msg-001", conn)
        assert result is True

    def test_idempotent_across_multiple_calls(self, conn: sqlite3.Connection) -> None:
        for _ in range(5):
            result = mark_processed("telegram", "user999", "msg-unique", conn)
        # Only first should be True
        assert result is False

    def test_records_persisted(self, conn: sqlite3.Connection) -> None:
        mark_processed("telegram", "user123", "msg-persistent", conn)
        count = conn.execute(
            "SELECT COUNT(*) FROM processed_messages WHERE message_id = 'msg-persistent'"
        ).fetchone()[0]
        assert count == 1
