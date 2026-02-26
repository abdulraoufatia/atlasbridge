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
    # Sessions — 4 sessions with varied statuses and tools
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
    conn.execute(
        "INSERT INTO sessions (id, tool, command, cwd, status, started_at, label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "sess-003",
            "gemini",
            '["gemini"]',
            "/home/user/project",
            "crashed",
            "2025-01-13T08:00:00",
            "gemini debug",
        ),
    )
    conn.execute(
        "INSERT INTO sessions (id, tool, command, cwd, status, started_at, label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "sess-004",
            "openai",
            '["openai-cli"]',
            "/home/user/work",
            "running",
            "2025-01-16T11:00:00",
            "openai run",
        ),
    )

    # Prompts — varied types, confidences, and statuses
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
    conn.execute(
        "INSERT INTO prompts (id, session_id, prompt_type, confidence, excerpt, status, nonce, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "prompt-003",
            "sess-001",
            "yes_no",
            "low",
            "Proceed? [Y/n]",
            "expired",
            "nonce-3",
            "2025-01-01T00:00:00",
        ),
    )
    conn.execute(
        "INSERT INTO prompts (id, session_id, prompt_type, confidence, excerpt, status, nonce, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "prompt-004",
            "sess-004",
            "freeform",
            "high",
            "Enter your name:",
            "awaiting_reply",
            "nonce-4",
            "2025-12-31T23:59:59",
        ),
    )
    # Prompt with embedded tokens — used to verify export redaction
    conn.execute(
        "INSERT INTO prompts (id, session_id, prompt_type, confidence, excerpt, status, nonce, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "prompt-005",
            "sess-001",
            "freeform",
            "high",
            "Use token sk-abcdefghijklmnopqrstuvwxyz1234567890 and xoxb-123-456-abcdefghij and ghp_abcdefghijklmnopqrstuvwxyz1234567890ab to authenticate",
            "resolved",
            "nonce-5",
            "2025-12-31T23:59:59",
        ),
    )

    # Audit events with hash chain
    prev_hash = ""
    event_types = [
        "prompt_detected",
        "prompt_resolved",
        "prompt_detected",
        "session_started",
        "prompt_detected",
    ]
    for i in range(5):
        event_id = f"evt-{i:03d}"
        event_type = event_types[i]
        session_id = "sess-001" if i < 3 else "sess-004"
        payload = json.dumps({"detail": f"event {i}"}, separators=(",", ":"), sort_keys=True)
        chain_input = f"{prev_hash}{event_id}{event_type}{payload}"
        event_hash = hashlib.sha256(chain_input.encode()).hexdigest()
        conn.execute(
            "INSERT INTO audit_events (id, event_type, session_id, payload, timestamp, prev_hash, hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                event_type,
                session_id,
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
    action_types = ["auto_respond", "auto_respond", "escalate", "auto_respond", "escalate"]
    confidences = ["high", "high", "low", "medium", "low"]
    session_ids = ["sess-001", "sess-001", "sess-001", "sess-004", "sess-004"]
    for i in range(5):
        entry = {
            "idempotency_key": f"key-{i}",
            "action_type": action_types[i],
            "prompt_type": "yes_no",
            "confidence": confidences[i],
            "session_id": session_ids[i],
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
def client(db_with_data: Path, trace_file: Path, monkeypatch):
    """Create a FastAPI test client with test data (enterprise edition for full route coverage)."""
    pytest.importorskip("fastapi")
    monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
    from atlasbridge.dashboard.app import create_app

    app = create_app(db_path=db_with_data, trace_path=trace_file)
    from starlette.testclient import TestClient

    return TestClient(app)
