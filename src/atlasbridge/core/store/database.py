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

Schema versioning:
  Uses PRAGMA user_version and the migrations module. On connect(), WAL mode
  and foreign keys are set first, then run_migrations() applies any pending
  schema changes idempotently. This handles fresh installs, upgrades from
  older schema versions, and partially-created databases after crashes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class Database:
    """SQLite persistence layer for AtlasBridge."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def path(self) -> Path:
        return self._path

    def connect(self) -> None:
        from atlasbridge.core.store.migrations import run_migrations

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row

        # Set pragmas before any DDL / migration work
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        # Run idempotent schema migrations (fresh install or upgrade)
        run_migrations(self._conn, self._path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

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

    # Columns that callers may update on the sessions table.  Any key not in
    # this set is rejected to prevent accidental SQL column injection even
    # though callers are all internal/trusted code.
    _ALLOWED_SESSION_COLUMNS: frozenset[str] = frozenset(
        {
            "status",
            "pid",
            "ended_at",
            "exit_code",
            "label",
            "metadata",
            "cwd",
        }
    )

    def update_session(self, session_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        bad = set(kwargs) - self._ALLOWED_SESSION_COLUMNS
        if bad:
            raise ValueError(
                f"update_session: disallowed column(s): {sorted(bad)}. "
                f"Allowed: {sorted(self._ALLOWED_SESSION_COLUMNS)}"
            )
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

    def list_sessions(self, limit: int = 50) -> list[sqlite3.Row]:
        """Return all sessions ordered by most recent first."""
        return self._db.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def count_prompts_for_session(self, session_id: str) -> int:
        """Return the number of prompts associated with a session."""
        row = self._db.execute(
            "SELECT count(*) FROM prompts WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0] if row else 0

    def list_prompts_for_session(self, session_id: str) -> list[sqlite3.Row]:
        """Return all prompts for a session, ordered by creation time."""
        return self._db.execute(
            "SELECT * FROM prompts WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
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

        now = datetime.now(UTC).isoformat()
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        chain_input = f"{prev_hash}{event_id}{event_type}{payload_str}"
        event_hash = hashlib.sha256(chain_input.encode()).hexdigest()

        self._db.execute(
            """
            INSERT INTO audit_events
              (id, event_type, session_id, prompt_id, payload, timestamp,
               prev_hash, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                session_id,
                prompt_id,
                payload_str,
                now,
                prev_hash,
                event_hash,
            ),
        )
        self._db.commit()

    def get_recent_audit_events(self, limit: int = 100) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()

    def count_audit_events(self) -> int:
        """Return the total number of audit events."""
        row = self._db.execute("SELECT count(*) FROM audit_events").fetchone()
        return row[0] if row else 0

    def archive_audit_events(
        self,
        archive_path: Path,
        before_date: str,
    ) -> int:
        """Move audit events older than *before_date* to *archive_path*.

        The archived events are written to a new SQLite file with the
        same ``audit_events`` schema, preserving hash chain order.
        Events are then deleted from the main database.

        Returns the number of events archived.
        """
        rows = self._db.execute(
            "SELECT * FROM audit_events WHERE timestamp < ? ORDER BY timestamp ASC",
            (before_date,),
        ).fetchall()

        if not rows:
            return 0

        # Create archive database with same schema
        archive_db = sqlite3.connect(str(archive_path))
        archive_db.execute("PRAGMA journal_mode=WAL")
        archive_db.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id          TEXT PRIMARY KEY,
                event_type  TEXT NOT NULL,
                session_id  TEXT NOT NULL DEFAULT '',
                prompt_id   TEXT NOT NULL DEFAULT '',
                payload     TEXT NOT NULL DEFAULT '{}',
                timestamp   TEXT NOT NULL,
                prev_hash   TEXT NOT NULL DEFAULT '',
                hash        TEXT NOT NULL DEFAULT ''
            )
            """
        )
        archive_db.execute("CREATE INDEX IF NOT EXISTS idx_archive_ts ON audit_events(timestamp)")

        # Copy rows to archive
        for row in rows:
            archive_db.execute(
                """INSERT OR IGNORE INTO audit_events
                   (id, event_type, session_id, prompt_id, payload,
                    timestamp, prev_hash, hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["id"],
                    row["event_type"],
                    row["session_id"],
                    row["prompt_id"],
                    row["payload"],
                    row["timestamp"],
                    row["prev_hash"],
                    row["hash"],
                ),
            )
        archive_db.commit()
        archive_db.close()

        # Delete archived events from main database
        self._db.execute("DELETE FROM audit_events WHERE timestamp < ?", (before_date,))
        self._db.commit()

        return len(rows)
