"""Integration tests for transcript_chunks migration (v6 → v7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlasbridge.core.store.database import Database
from atlasbridge.core.store.migrations import LATEST_SCHEMA_VERSION


@pytest.fixture()
def db(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.connect()
    yield db
    db.close()


class TestTranscriptMigration:
    def test_latest_schema_version(self):
        assert LATEST_SCHEMA_VERSION >= 7

    def test_transcript_chunks_table_exists(self, db):
        tables = db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transcript_chunks'"
        ).fetchall()
        assert len(tables) == 1

    def test_transcript_chunks_index_exists(self, db):
        indexes = db._db.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='index' AND name='idx_transcript_session_seq'"
        ).fetchall()
        assert len(indexes) == 1

    def test_save_and_list_transcript_chunks(self, db):
        # Create a session first (FK not enforced on transcript_chunks but good practice)
        db._db.execute(
            "INSERT INTO sessions (id, tool, command, status, started_at) "
            "VALUES ('s1', 'claude', '[]', 'running', datetime('now'))"
        )
        db._db.commit()

        db.save_transcript_chunk("s1", "agent", "Hello from agent", seq=1)
        db.save_transcript_chunk("s1", "user", "yes", seq=2, prompt_id="p1")
        db.save_transcript_chunk("s1", "agent", "Continuing...", seq=3)

        chunks = db.list_transcript_chunks("s1")
        assert len(chunks) == 3
        assert chunks[0]["role"] == "agent"
        assert chunks[0]["content"] == "Hello from agent"
        assert chunks[1]["role"] == "user"
        assert chunks[1]["prompt_id"] == "p1"

    def test_list_transcript_chunks_cursor(self, db):
        db.save_transcript_chunk("s2", "agent", "chunk1", seq=1)
        db.save_transcript_chunk("s2", "agent", "chunk2", seq=2)
        db.save_transcript_chunk("s2", "agent", "chunk3", seq=3)

        # Get chunks after seq 1
        chunks = db.list_transcript_chunks("s2", after_seq=1)
        assert len(chunks) == 2
        assert chunks[0]["seq"] == 2
        assert chunks[1]["seq"] == 3

    def test_list_transcript_chunks_limit(self, db):
        for i in range(10):
            db.save_transcript_chunk("s3", "agent", f"chunk{i}", seq=i + 1)

        chunks = db.list_transcript_chunks("s3", limit=3)
        assert len(chunks) == 3

    def test_list_transcript_chunks_session_isolation(self, db):
        db.save_transcript_chunk("s4", "agent", "session4", seq=1)
        db.save_transcript_chunk("s5", "agent", "session5", seq=1)

        chunks = db.list_transcript_chunks("s4")
        assert len(chunks) == 1
        assert chunks[0]["content"] == "session4"
