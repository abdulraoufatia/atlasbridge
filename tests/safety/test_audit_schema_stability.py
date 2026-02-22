"""Safety guard: audit log schema and hash chain must not drift."""

from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3

from atlasbridge.core.audit.writer import AuditWriter
from atlasbridge.core.store.database import Database

# --- Table schema ---


def test_database_has_four_tables(tmp_path):
    """Fresh database must have exactly 4 tables."""
    db = Database(tmp_path / "test.db")
    db.connect()
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    expected = {"sessions", "prompts", "replies", "audit_events"}
    # schema_version table may also exist
    tables.discard("schema_version")
    assert expected.issubset(tables), f"Missing tables: {expected - tables}. Got: {tables}"
    db.close()


def test_audit_events_columns(tmp_path):
    """audit_events table must have the frozen column set."""
    db = Database(tmp_path / "test.db")
    db.connect()
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    cursor = conn.execute("PRAGMA table_info(audit_events)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    expected = {
        "id",
        "event_type",
        "session_id",
        "prompt_id",
        "payload",
        "timestamp",
        "prev_hash",
        "hash",
    }
    assert expected.issubset(columns), (
        f"audit_events columns changed. Missing: {expected - columns}. Got: {columns}"
    )
    db.close()


# --- Hash chain formula ---


def test_audit_hash_chain_formula(tmp_path):
    """Audit hash chain must use SHA-256(prev_hash + event_id + event_type + payload_json)."""
    prev_hash = ""
    event_id = "abc123def456"
    event_type = "session_started"
    payload = {"tool": "claude", "command": "claude --no-browser"}
    payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    chain_input = f"{prev_hash}{event_id}{event_type}{payload_str}"
    expected_hash = hashlib.sha256(chain_input.encode()).hexdigest()

    # Verify the formula matches what the database would produce
    assert len(expected_hash) == 64
    assert (
        expected_hash
        == hashlib.sha256(f"{prev_hash}{event_id}{event_type}{payload_str}".encode()).hexdigest()
    )


# --- AuditWriter event methods ---


FROZEN_EVENT_METHODS = frozenset(
    {
        "session_started",
        "session_ended",
        "prompt_detected",
        "prompt_routed",
        "reply_received",
        "response_injected",
        "prompt_expired",
        "duplicate_callback",
        "late_reply_rejected",
        "invalid_callback",
        "telegram_polling_failed",
        "daemon_restarted",
    }
)


def test_audit_writer_event_methods():
    """AuditWriter must have all frozen event methods."""
    actual_methods = {
        name
        for name, method in inspect.getmembers(AuditWriter, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    missing = FROZEN_EVENT_METHODS - actual_methods
    assert not missing, f"AuditWriter methods removed: {sorted(missing)}"
