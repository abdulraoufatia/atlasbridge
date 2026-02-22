"""Shared fixtures for dashboard tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create the AtlasBridge database schema."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            tool        TEXT NOT NULL DEFAULT '',
            command     TEXT NOT NULL DEFAULT '',
            cwd         TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'starting',
            pid         INTEGER,
            started_at  TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at    TEXT,
            exit_code   INTEGER,
            label       TEXT NOT NULL DEFAULT '',
            metadata    TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id                  TEXT PRIMARY KEY,
            session_id          TEXT NOT NULL REFERENCES sessions(id),
            prompt_type         TEXT NOT NULL,
            confidence          TEXT NOT NULL,
            excerpt             TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'created',
            nonce               TEXT NOT NULL,
            nonce_used          INTEGER NOT NULL DEFAULT 0,
            expires_at          TEXT NOT NULL,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at         TEXT,
            response_normalized TEXT,
            channel_identity    TEXT,
            channel_message_id  TEXT NOT NULL DEFAULT '',
            metadata            TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS replies (
            id               TEXT PRIMARY KEY,
            prompt_id        TEXT NOT NULL REFERENCES prompts(id),
            session_id       TEXT NOT NULL,
            value            TEXT NOT NULL,
            channel_identity TEXT NOT NULL,
            timestamp        TEXT NOT NULL DEFAULT (datetime('now')),
            nonce            TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id          TEXT PRIMARY KEY,
            event_type  TEXT NOT NULL,
            session_id  TEXT NOT NULL DEFAULT '',
            prompt_id   TEXT NOT NULL DEFAULT '',
            payload     TEXT NOT NULL DEFAULT '{}',
            timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
            prev_hash   TEXT NOT NULL DEFAULT '',
            hash        TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.commit()


def _seed_data(conn: sqlite3.Connection) -> None:
    """Insert sample data for tests."""
    # Sessions
    conn.execute(
        "INSERT INTO sessions (id, tool, command, cwd, status, started_at, label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "sess-001",
            "claude",
            '["claude"]',
            "/home/user",
            "running",
            "2025-01-15T10:00:00",
            "test session",
        ),
    )
    conn.execute(
        "INSERT INTO sessions (id, tool, command, cwd, status, started_at, ended_at, exit_code) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "sess-002",
            "claude",
            '["claude", "--help"]',
            "/tmp",
            "completed",
            "2025-01-14T09:00:00",
            "2025-01-14T09:30:00",
            0,
        ),
    )

    # Prompts
    conn.execute(
        "INSERT INTO prompts (id, session_id, prompt_type, confidence, excerpt, status, nonce, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "prompt-001",
            "sess-001",
            "yes_no",
            "high",
            "Continue? [y/n]",
            "awaiting_reply",
            "nonce-1",
            "2025-12-31T23:59:59",
        ),
    )
    conn.execute(
        "INSERT INTO prompts (id, session_id, prompt_type, confidence, excerpt, status, nonce, expires_at, resolved_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "prompt-002",
            "sess-001",
            "freeform",
            "medium",
            "What next?",
            "resolved",
            "nonce-2",
            "2025-12-31T23:59:59",
            "2025-01-15T10:05:00",
        ),
    )

    # Audit events with hash chain
    prev_hash = ""
    for i in range(3):
        event_id = f"evt-{i:03d}"
        event_type = "prompt_detected" if i % 2 == 0 else "prompt_resolved"
        payload = json.dumps({"detail": f"event {i}"}, separators=(",", ":"), sort_keys=True)
        chain_input = f"{prev_hash}{event_id}{event_type}{payload}"
        event_hash = hashlib.sha256(chain_input.encode()).hexdigest()
        conn.execute(
            "INSERT INTO audit_events (id, event_type, session_id, payload, timestamp, prev_hash, hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                event_type,
                "sess-001",
                payload,
                f"2025-01-15T10:0{i}:00",
                prev_hash,
                event_hash,
            ),
        )
        prev_hash = event_hash

    conn.commit()


@pytest.fixture
def db_with_data(tmp_path: Path) -> Path:
    """Create a temporary SQLite DB with schema and sample data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _create_schema(conn)
    _seed_data(conn)
    conn.close()
    return db_path


@pytest.fixture
def empty_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite DB with schema but no data."""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    _create_schema(conn)
    conn.close()
    return db_path


@pytest.fixture
def trace_file(tmp_path: Path) -> Path:
    """Create a temporary JSONL trace file with sample entries."""
    trace_path = tmp_path / "decisions.jsonl"
    prev_hash = ""
    entries = []
    for i in range(5):
        entry = {
            "idempotency_key": f"key-{i}",
            "action_type": "auto_respond",
            "prompt_type": "yes_no",
            "confidence": "high",
            "rule_id": f"rule-{i}",
            "timestamp": f"2025-01-15T10:0{i}:00",
            "prev_hash": prev_hash,
        }
        chain_input = (
            f"{prev_hash}"
            f"{entry['idempotency_key']}"
            f"{entry['action_type']}"
            f"{json.dumps(entry, separators=(',', ':'), sort_keys=True)}"
        )
        entry_hash = hashlib.sha256(chain_input.encode()).hexdigest()
        entry["hash"] = entry_hash
        entries.append(json.dumps(entry))
        prev_hash = entry_hash

    trace_path.write_text("\n".join(entries) + "\n")
    return trace_path


@pytest.fixture
def repo(db_with_data: Path, trace_file: Path):
    """Create a connected DashboardRepo with test data."""
    from atlasbridge.dashboard.repo import DashboardRepo

    r = DashboardRepo(db_with_data, trace_file)
    r.connect()
    yield r
    r.close()


@pytest.fixture
def client(db_with_data: Path, trace_file: Path):
    """Create a FastAPI test client with test data."""
    pytest.importorskip("fastapi")
    from atlasbridge.dashboard.app import create_app

    app = create_app(db_path=db_with_data, trace_path=trace_file)
    from starlette.testclient import TestClient

    return TestClient(app)
