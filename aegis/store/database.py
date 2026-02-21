"""Aegis SQLite store: connection management, migrations, and repositories."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegis.store.models import AuditEvent, PromptRecord, Session

# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------

MIGRATIONS: list[str] = [
    # Migration 001 — initial schema
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version     INTEGER NOT NULL,
        applied_at  TEXT    NOT NULL,
        description TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
        id          TEXT    NOT NULL PRIMARY KEY,
        tool        TEXT    NOT NULL,
        cwd         TEXT    NOT NULL DEFAULT '',
        pid         INTEGER,
        started_at  TEXT    NOT NULL,
        ended_at    TEXT,
        status      TEXT    NOT NULL DEFAULT 'active',
        exit_code   INTEGER,
        prompt_count INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS prompts (
        id                  TEXT    NOT NULL PRIMARY KEY,
        session_id          TEXT    NOT NULL REFERENCES sessions(id),
        input_type          TEXT    NOT NULL,
        excerpt             TEXT    NOT NULL DEFAULT '',
        choices_json        TEXT    NOT NULL DEFAULT '[]',
        confidence          REAL    NOT NULL DEFAULT 0.0,
        status              TEXT    NOT NULL DEFAULT 'pending',
        safe_default        TEXT    NOT NULL DEFAULT 'n',
        telegram_msg_id     INTEGER,
        nonce               TEXT    NOT NULL UNIQUE,
        nonce_used          INTEGER NOT NULL DEFAULT 0,
        created_at          TEXT    NOT NULL,
        expires_at          TEXT    NOT NULL,
        decided_at          TEXT,
        decided_by          TEXT,
        response_normalized TEXT,
        detection_method    TEXT    NOT NULL DEFAULT 'text_pattern'
    );

    CREATE INDEX IF NOT EXISTS idx_prompts_session ON prompts(session_id);
    CREATE INDEX IF NOT EXISTS idx_prompts_status  ON prompts(status);

    CREATE TABLE IF NOT EXISTS audit_events (
        seq         INTEGER PRIMARY KEY AUTOINCREMENT,
        id          TEXT    NOT NULL UNIQUE,
        event_type  TEXT    NOT NULL,
        ts          TEXT    NOT NULL,
        session_id  TEXT,
        prompt_id   TEXT,
        data_json   TEXT    NOT NULL DEFAULT '{}',
        prev_hash   TEXT    NOT NULL DEFAULT 'genesis',
        hash        TEXT    NOT NULL DEFAULT ''
    );
    """,
]

CURRENT_SCHEMA_VERSION = len(MIGRATIONS)


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------


class Database:
    """
    Synchronous SQLite wrapper with WAL mode, migrations, and typed methods.

    Designed for use in asyncio via run_in_executor, or directly from sync code.
    All writes are atomic.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Open the database connection and apply pending migrations."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions manually
        )
        self._conn.row_factory = sqlite3.Row
        # Enable WAL for crash-safe concurrent reads
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._run_migrations()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for an explicit transaction."""
        assert self._conn is not None
        self._conn.execute("BEGIN")
        try:
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    def _run_migrations(self) -> None:
        assert self._conn is not None
        applied = self._get_schema_version()
        for i, sql in enumerate(MIGRATIONS[applied:], start=applied + 1):
            # executescript issues an implicit COMMIT before executing, so we
            # cannot wrap it in our transaction() context manager.  Run the DDL
            # first, then record the version in a separate explicit transaction.
            self._conn.executescript(sql)
            with self.transaction():
                self._conn.execute(
                    "INSERT INTO schema_version(version, applied_at, description) "
                    "VALUES (?, ?, ?)",
                    (i, datetime.now(UTC).isoformat(), f"Migration {i:03d}"),
                )

    def _get_schema_version(self) -> int:
        assert self._conn is not None
        try:
            row = self._conn.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
            return row[0] or 0
        except sqlite3.OperationalError:
            return 0

    # ------------------------------------------------------------------
    # Session repository
    # ------------------------------------------------------------------

    def save_session(self, session: Session) -> None:
        assert self._conn is not None
        row = session.to_row()
        placeholders = ", ".join(f":{k}" for k in row)
        cols = ", ".join(row.keys())
        with self.transaction():
            self._conn.execute(
                f"INSERT OR REPLACE INTO sessions ({cols}) VALUES ({placeholders})",
                row,
            )

    def update_session(self, session_id: str, **fields: Any) -> None:
        assert self._conn is not None
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        params = {**fields, "id": session_id}
        with self.transaction():
            self._conn.execute(
                f"UPDATE sessions SET {sets} WHERE id = :id", params
            )

    def get_session(self, session_id: str) -> Session | None:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return Session.from_row(dict(row)) if row else None

    def list_active_sessions(self) -> list[Session]:
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE status = 'active' ORDER BY started_at DESC"
        ).fetchall()
        return [Session.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Prompt repository
    # ------------------------------------------------------------------

    def save_prompt(self, prompt: PromptRecord) -> None:
        assert self._conn is not None
        row = prompt.to_row()
        placeholders = ", ".join(f":{k}" for k in row)
        cols = ", ".join(row.keys())
        with self.transaction():
            self._conn.execute(
                f"INSERT OR REPLACE INTO prompts ({cols}) VALUES ({placeholders})",
                row,
            )

    def update_prompt(self, prompt_id: str, **fields: Any) -> int:
        """Update prompt fields. Returns rows affected."""
        assert self._conn is not None
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        params = {**fields, "id": prompt_id}
        with self.transaction():
            cur = self._conn.execute(
                f"UPDATE prompts SET {sets} WHERE id = :id", params
            )
            return cur.rowcount

    def decide_prompt(
        self,
        prompt_id: str,
        status: str,
        decided_by: str,
        response_normalized: str,
        nonce: str,
    ) -> int:
        """
        Atomically transition a pending prompt to a decision.
        Returns rows affected (0 if already decided / nonce mismatch / expired).
        """
        assert self._conn is not None
        with self.transaction():
            cur = self._conn.execute(
                """
                UPDATE prompts
                SET status = :status,
                    decided_at = :decided_at,
                    decided_by = :decided_by,
                    response_normalized = :response_normalized,
                    nonce_used = 1
                WHERE id = :id
                  AND status IN ('awaiting_response', 'telegram_sent')
                  AND nonce = :nonce
                  AND nonce_used = 0
                  AND expires_at > :now
                """,
                {
                    "id": prompt_id,
                    "status": status,
                    "decided_at": datetime.now(UTC).isoformat(),
                    "decided_by": decided_by,
                    "response_normalized": response_normalized,
                    "nonce": nonce,
                    "now": datetime.now(UTC).isoformat(),
                },
            )
            return cur.rowcount

    def get_prompt(self, prompt_id: str) -> PromptRecord | None:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
        ).fetchone()
        return PromptRecord.from_row(dict(row)) if row else None

    def list_pending_prompts(self, session_id: str | None = None) -> list[PromptRecord]:
        assert self._conn is not None
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM prompts WHERE status IN ('pending','telegram_sent','awaiting_response') "  # noqa: E501
                "AND session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM prompts WHERE status IN ('pending','telegram_sent','awaiting_response') "  # noqa: E501
                "ORDER BY created_at ASC"
            ).fetchall()
        return [PromptRecord.from_row(dict(r)) for r in rows]

    def list_expired_pending(self) -> list[PromptRecord]:
        assert self._conn is not None
        now = datetime.now(UTC).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM prompts WHERE status IN ('pending','telegram_sent','awaiting_response') "
            "AND expires_at < ?",
            (now,),
        ).fetchall()
        return [PromptRecord.from_row(dict(r)) for r in rows]

    def list_prompts_for_session(
        self, session_id: str, limit: int = 50
    ) -> list[PromptRecord]:
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM prompts WHERE session_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [PromptRecord.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Audit event repository
    # ------------------------------------------------------------------

    def save_audit_event(self, event: AuditEvent) -> None:
        assert self._conn is not None
        row = event.to_row()
        with self.transaction():
            self._conn.execute(
                "INSERT INTO audit_events "
                "(id, event_type, ts, session_id, prompt_id, data_json, prev_hash, hash) "
                "VALUES (:id, :event_type, :ts, :session_id, :prompt_id, :data_json, :prev_hash, :hash)",  # noqa: E501
                row,
            )

    def get_last_audit_event(self) -> AuditEvent | None:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM audit_events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        if row:
            d = dict(row)
            fields = AuditEvent.__dataclass_fields__
            return AuditEvent(**{k: v for k, v in d.items() if k in fields})
        return None

    def list_recent_audit_events(self, limit: int = 50) -> list[AuditEvent]:
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM audit_events ORDER BY seq DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            fields = AuditEvent.__dataclass_fields__
            result.append(AuditEvent(**{k: v for k, v in d.items() if k in fields}))
        return result
