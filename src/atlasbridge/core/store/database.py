"""
SQLite-backed persistence store.

Schema (4 tables):
  sessions       — session lifecycle records
  prompts        — prompt records with atomic decide_prompt guard
  replies        — reply records (one per decide_prompt success)
  audit_events   — append-only audit log with hash chain

The decide_prompt() method is the idempotency guard:
  UPDATE prompts
     SET status = ?, response_normalized = ?, nonce_used = 1, ...
   WHERE id = ?
     AND status = 'awaiting_reply'
     AND expires_at > datetime('now')
     AND nonce = ?
     AND nonce_used = 0
  Returns rowcount — 0 means rejected (replay, expired, wrong nonce).

Thread safety:
  SQLite WAL mode is enabled. The database is opened with check_same_thread=False
  because asyncio runs all coroutines on the same thread, but executor calls
  may cross thread boundaries. All writes use parameterised queries.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

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
);

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
);

CREATE TABLE IF NOT EXISTS replies (
    id               TEXT PRIMARY KEY,
    prompt_id        TEXT NOT NULL REFERENCES prompts(id),
    session_id       TEXT NOT NULL,
    value            TEXT NOT NULL,
    channel_identity TEXT NOT NULL,
    timestamp        TEXT NOT NULL DEFAULT (datetime('now')),
    nonce            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id          TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    session_id  TEXT NOT NULL DEFAULT '',
    prompt_id   TEXT NOT NULL DEFAULT '',
    payload     TEXT NOT NULL DEFAULT '{}',
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    prev_hash   TEXT NOT NULL DEFAULT '',
    hash        TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_prompts_session_status
    ON prompts(session_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp
    ON audit_events(timestamp);
"""


class Database:
    """SQLite persistence layer for AtlasBridge."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._ensure_schema_version()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _ensure_schema_version(self) -> None:
        row = self._conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,)
            )
            self._conn.commit()

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def save_session(
        self, session_id: str, tool: str, command: list[str], cwd: str = "", label: str = ""
    ) -> None:
        self._db.execute(
            """
            INSERT INTO sessions (id, tool, command, cwd, label, status)
            VALUES (?, ?, ?, ?, ?, 'starting')
            """,
            (session_id, tool, json.dumps(command), cwd, label),
        )
        self._db.commit()

    def update_session(self, session_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        columns = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [session_id]
        self._db.execute(
            f"UPDATE sessions SET {columns} WHERE id = ?",
            values,  # noqa: S608
        )
        self._db.commit()

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        return self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def list_active_sessions(self) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM sessions WHERE status NOT IN ('completed', 'crashed', 'canceled')"
        ).fetchall()

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def save_prompt(
        self,
        prompt_id: str,
        session_id: str,
        prompt_type: str,
        confidence: str,
        excerpt: str,
        nonce: str,
        expires_at: str,
        channel_message_id: str = "",
    ) -> None:
        self._db.execute(
            """
            INSERT INTO prompts
              (id, session_id, prompt_type, confidence, excerpt, nonce, expires_at,
               channel_message_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_reply')
            """,
            (
                prompt_id,
                session_id,
                prompt_type,
                confidence,
                excerpt,
                nonce,
                expires_at,
                channel_message_id,
            ),
        )
        self._db.commit()

    def decide_prompt(
        self,
        prompt_id: str,
        new_status: str,
        channel_identity: str,
        response_normalized: str,
        nonce: str,
    ) -> int:
        """
        Atomic idempotency guard for prompt decisions.

        Returns 1 if the update succeeded (prompt accepted).
        Returns 0 if rejected (replay, expired, wrong nonce, wrong status).
        """
        now = datetime.now(UTC).isoformat()
        cur = self._db.execute(
            """
            UPDATE prompts
               SET status              = ?,
                   response_normalized = ?,
                   nonce_used          = 1,
                   channel_identity    = ?,
                   resolved_at         = ?
             WHERE id         = ?
               AND status     = 'awaiting_reply'
               AND expires_at > datetime('now')
               AND nonce      = ?
               AND nonce_used = 0
            """,
            (new_status, response_normalized, channel_identity, now, prompt_id, nonce),
        )
        self._db.commit()
        return cur.rowcount

    def get_prompt(self, prompt_id: str) -> sqlite3.Row | None:
        return self._db.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()

    def list_pending_prompts(self, session_id: str = "") -> list[sqlite3.Row]:
        if session_id:
            return self._db.execute(
                "SELECT * FROM prompts WHERE status = 'awaiting_reply' AND session_id = ?",
                (session_id,),
            ).fetchall()
        return self._db.execute("SELECT * FROM prompts WHERE status = 'awaiting_reply'").fetchall()

    def list_expired_pending(self) -> list[sqlite3.Row]:
        return self._db.execute(
            """
            SELECT * FROM prompts
             WHERE status = 'awaiting_reply'
               AND expires_at < datetime('now')
            """
        ).fetchall()

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def append_audit_event(
        self,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: str = "",
        prompt_id: str = "",
    ) -> None:
        """Append an event to the audit log with hash chaining."""
        last = self._db.execute(
            "SELECT hash FROM audit_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        prev_hash = last["hash"] if last else ""

        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        chain_input = f"{prev_hash}{event_id}{event_type}{payload_str}"
        event_hash = hashlib.sha256(chain_input.encode()).hexdigest()

        self._db.execute(
            """
            INSERT INTO audit_events
              (id, event_type, session_id, prompt_id, payload, prev_hash, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, event_type, session_id, prompt_id, payload_str, prev_hash, event_hash),
        )
        self._db.commit()

    def get_recent_audit_events(self, limit: int = 100) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
