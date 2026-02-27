"""Integration tests for Agent SoR migration (v5 → v6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlasbridge.core.store.database import Database


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    database.connect()
    yield database
    database.close()


AGENT_TABLES = [
    "agent_turns",
    "agent_plans",
    "agent_decisions",
    "agent_tool_runs",
    "agent_outcomes",
]


class TestFreshInstall:
    """Fresh install creates all agent tables."""

    def test_all_agent_tables_exist(self, db: Database) -> None:
        conn = db._conn
        assert conn is not None
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'agent_%'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        for table in AGENT_TABLES:
            assert table in tables, f"Missing table: {table}"

    def test_agent_turns_schema(self, db: Database) -> None:
        conn = db._conn
        assert conn is not None
        cursor = conn.execute("PRAGMA table_info(agent_turns)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {
            "id",
            "session_id",
            "trace_id",
            "turn_number",
            "role",
            "content",
            "state",
            "created_at",
            "metadata",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_agent_plans_schema(self, db: Database) -> None:
        conn = db._conn
        assert conn is not None
        cursor = conn.execute("PRAGMA table_info(agent_plans)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {
            "id",
            "session_id",
            "trace_id",
            "turn_id",
            "status",
            "description",
            "steps",
            "risk_level",
            "created_at",
            "resolved_at",
            "resolved_by",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_agent_decisions_schema(self, db: Database) -> None:
        conn = db._conn
        assert conn is not None
        cursor = conn.execute("PRAGMA table_info(agent_decisions)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {
            "id",
            "session_id",
            "trace_id",
            "plan_id",
            "turn_id",
            "decision_type",
            "action",
            "rule_matched",
            "confidence",
            "explanation",
            "risk_score",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_agent_tool_runs_schema(self, db: Database) -> None:
        conn = db._conn
        assert conn is not None
        cursor = conn.execute("PRAGMA table_info(agent_tool_runs)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {
            "id",
            "session_id",
            "trace_id",
            "plan_id",
            "turn_id",
            "tool_name",
            "arguments",
            "result",
            "is_error",
            "duration_ms",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_agent_outcomes_schema(self, db: Database) -> None:
        conn = db._conn
        assert conn is not None
        cursor = conn.execute("PRAGMA table_info(agent_outcomes)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {
            "id",
            "session_id",
            "trace_id",
            "turn_id",
            "status",
            "summary",
            "tool_runs_count",
            "total_duration_ms",
            "created_at",
        }
        assert expected.issubset(cols)


class TestIndexes:
    """Indexes exist for efficient queries."""

    def test_session_id_indexes(self, db: Database) -> None:
        conn = db._conn
        assert conn is not None
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_agent_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        for table in AGENT_TABLES:
            idx_name = f"idx_{table}_session"
            assert idx_name in indexes, f"Missing index: {idx_name}"


class TestSchemaVersion:
    def test_schema_version_is_6(self, db: Database) -> None:
        conn = db._conn
        assert conn is not None
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 6


class TestMigrationIdempotency:
    """Running migration twice produces the same result."""

    def test_double_connect_is_safe(self, tmp_path: Path) -> None:
        db1 = Database(tmp_path / "idempotent.db")
        db1.connect()
        db1.close()

        db2 = Database(tmp_path / "idempotent.db")
        db2.connect()

        conn = db2._conn
        assert conn is not None
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'agent_%'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        for table in AGENT_TABLES:
            assert table in tables
        db2.close()
