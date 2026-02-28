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
            INSERT INTO sessions (id, tool, command, cwd, label, status, started_at)
            VALUES (?, ?, ?, ?, ?, 'starting', datetime('now'))
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

    def list_reply_received(self) -> list[sqlite3.Row]:
        """Return prompts that have been replied to but not yet injected."""
        return self._db.execute("SELECT * FROM prompts WHERE status = 'reply_received'").fetchall()

    def update_prompt_status(self, prompt_id: str, new_status: str) -> None:
        """Update a prompt's status (used after dashboard relay injection)."""
        self._db.execute(
            "UPDATE prompts SET status = ? WHERE id = ?",
            (new_status, prompt_id),
        )
        self._db.commit()

    def list_expired_pending(self) -> list[sqlite3.Row]:
        return self._db.execute(
            """
            SELECT * FROM prompts
             WHERE status = 'awaiting_reply'
               AND expires_at < datetime('now')
            """
        ).fetchall()

    # ------------------------------------------------------------------
    # Transcript
    # ------------------------------------------------------------------

    def save_transcript_chunk(
        self,
        session_id: str,
        role: str,
        content: str,
        seq: int,
        prompt_id: str = "",
    ) -> None:
        self._db.execute(
            "INSERT INTO transcript_chunks (session_id, role, content, prompt_id, seq) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, prompt_id or None, seq),
        )
        self._db.commit()

    def list_transcript_chunks(
        self, session_id: str, after_seq: int = 0, limit: int = 200
    ) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM transcript_chunks WHERE session_id = ? AND seq > ? "
            "ORDER BY seq ASC LIMIT ?",
            (session_id, after_seq, limit),
        ).fetchall()

    # ------------------------------------------------------------------
    # Operator directives
    # ------------------------------------------------------------------

    def insert_operator_directive(
        self, session_id: str, content: str, actor: str = "dashboard"
    ) -> str:
        """Insert a pending operator directive and return its id."""
        import uuid

        directive_id = uuid.uuid4().hex
        self._db.execute(
            "INSERT INTO operator_directives (id, session_id, content, status, actor) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (directive_id, session_id, content, actor),
        )
        self._db.commit()
        return directive_id

    def list_pending_directives(self) -> list[sqlite3.Row]:
        """Return operator directives awaiting processing."""
        return self._db.execute(
            "SELECT * FROM operator_directives WHERE status = 'pending' ORDER BY created_at ASC"
        ).fetchall()

    def mark_directive_processed(self, directive_id: str) -> None:
        """Mark an operator directive as processed."""
        self._db.execute(
            "UPDATE operator_directives SET status = 'processed', "
            "processed_at = datetime('now') WHERE id = ?",
            (directive_id,),
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Delivery tracking
    # ------------------------------------------------------------------

    def record_delivery(
        self,
        prompt_id: str,
        session_id: str,
        channel: str,
        channel_identity: str,
        message_id: str = "",
    ) -> bool:
        """Record that a prompt was delivered to a channel identity.

        Returns True if newly recorded, False if already delivered (duplicate).
        Uses INSERT OR IGNORE on the UNIQUE(prompt_id, channel, channel_identity)
        constraint as the idempotency guard.
        """
        cur = self._db.execute(
            """
            INSERT OR IGNORE INTO prompt_deliveries
                (prompt_id, session_id, channel, channel_identity, message_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (prompt_id, session_id, channel, channel_identity, message_id),
        )
        self._db.commit()
        return cur.rowcount == 1

    def was_delivered(
        self,
        prompt_id: str,
        channel: str,
        channel_identity: str,
    ) -> bool:
        """Check if a prompt was already delivered to this channel+identity."""
        row = self._db.execute(
            """
            SELECT 1 FROM prompt_deliveries
             WHERE prompt_id = ? AND channel = ? AND channel_identity = ?
             LIMIT 1
            """,
            (prompt_id, channel, channel_identity),
        ).fetchone()
        return row is not None

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

    def get_audit_events_for_session(self, session_id: str, limit: int = 500) -> list[sqlite3.Row]:
        """Return audit events for a session, ordered chronologically (oldest first)."""
        return self._db.execute(
            "SELECT * FROM audit_events WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()

    def get_audit_events_filtered(
        self,
        session_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[sqlite3.Row]:
        """Return audit events matching optional filters, ordered chronologically."""
        clauses: list[str] = []
        params: list[str] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until:
            clauses.append("timestamp <= ?")
            params.append(until)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._db.execute(
            f"SELECT * FROM audit_events{where} ORDER BY timestamp ASC",
            params,
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

    # ------------------------------------------------------------------
    # Agent SoR tables
    # ------------------------------------------------------------------

    def save_agent_turn(
        self,
        turn_id: str,
        session_id: str,
        trace_id: str,
        turn_number: int,
        role: str,
        content: str = "",
        state: str = "intake",
        metadata: str = "{}",
    ) -> None:
        self._db.execute(
            """
            INSERT INTO agent_turns
                (id, session_id, trace_id, turn_number, role, content, state, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (turn_id, session_id, trace_id, turn_number, role, content, state, metadata),
        )
        self._db.commit()

    def update_agent_turn(self, turn_id: str, **kwargs: Any) -> None:
        allowed = {"content", "state", "metadata"}
        bad = set(kwargs) - allowed
        if bad:
            raise ValueError(f"update_agent_turn: disallowed column(s): {sorted(bad)}")
        if not kwargs:
            return
        columns = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [turn_id]
        self._db.execute(f"UPDATE agent_turns SET {columns} WHERE id = ?", values)  # noqa: S608
        self._db.commit()

    def get_agent_turn(self, turn_id: str) -> sqlite3.Row | None:
        return self._db.execute("SELECT * FROM agent_turns WHERE id = ?", (turn_id,)).fetchone()

    def list_agent_turns(self, session_id: str, limit: int = 200) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM agent_turns WHERE session_id = ? ORDER BY turn_number ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()

    def save_agent_plan(
        self,
        plan_id: str,
        session_id: str,
        trace_id: str,
        turn_id: str,
        description: str = "",
        steps: str = "[]",
        risk_level: str = "low",
    ) -> None:
        self._db.execute(
            """
            INSERT INTO agent_plans
                (id, session_id, trace_id, turn_id, description, steps, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (plan_id, session_id, trace_id, turn_id, description, steps, risk_level),
        )
        self._db.commit()

    def update_agent_plan(self, plan_id: str, **kwargs: Any) -> None:
        allowed = {"status", "resolved_at", "resolved_by"}
        bad = set(kwargs) - allowed
        if bad:
            raise ValueError(f"update_agent_plan: disallowed column(s): {sorted(bad)}")
        if not kwargs:
            return
        columns = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [plan_id]
        self._db.execute(f"UPDATE agent_plans SET {columns} WHERE id = ?", values)  # noqa: S608
        self._db.commit()

    def get_agent_plan(self, plan_id: str) -> sqlite3.Row | None:
        return self._db.execute("SELECT * FROM agent_plans WHERE id = ?", (plan_id,)).fetchone()

    def list_agent_plans(self, session_id: str, limit: int = 100) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM agent_plans WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()

    def save_agent_decision(
        self,
        decision_id: str,
        session_id: str,
        trace_id: str,
        turn_id: str,
        decision_type: str,
        action: str,
        plan_id: str | None = None,
        rule_matched: str | None = None,
        confidence: str = "medium",
        explanation: str = "",
        risk_score: int = 0,
    ) -> None:
        self._db.execute(
            """
            INSERT INTO agent_decisions
              (id, session_id, trace_id, plan_id, turn_id, decision_type, action,
               rule_matched, confidence, explanation, risk_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                session_id,
                trace_id,
                plan_id,
                turn_id,
                decision_type,
                action,
                rule_matched,
                confidence,
                explanation,
                risk_score,
            ),
        )
        self._db.commit()

    def list_agent_decisions(self, session_id: str, limit: int = 200) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM agent_decisions WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()

    def save_agent_tool_run(
        self,
        tool_run_id: str,
        session_id: str,
        trace_id: str,
        turn_id: str,
        tool_name: str,
        arguments: str = "{}",
        result: str = "",
        is_error: int = 0,
        duration_ms: float | None = None,
        plan_id: str | None = None,
    ) -> None:
        self._db.execute(
            """
            INSERT INTO agent_tool_runs
              (id, session_id, trace_id, plan_id, turn_id, tool_name,
               arguments, result, is_error, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_run_id,
                session_id,
                trace_id,
                plan_id,
                turn_id,
                tool_name,
                arguments,
                result,
                is_error,
                duration_ms,
            ),
        )
        self._db.commit()

    def list_agent_tool_runs(self, session_id: str, limit: int = 200) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM agent_tool_runs WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()

    def save_agent_outcome(
        self,
        outcome_id: str,
        session_id: str,
        trace_id: str,
        turn_id: str,
        status: str,
        summary: str = "",
        tool_runs_count: int = 0,
        total_duration_ms: float | None = None,
    ) -> None:
        self._db.execute(
            """
            INSERT INTO agent_outcomes
              (id, session_id, trace_id, turn_id, status, summary,
               tool_runs_count, total_duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id,
                session_id,
                trace_id,
                turn_id,
                status,
                summary,
                tool_runs_count,
                total_duration_ms,
            ),
        )
        self._db.commit()

    def list_agent_outcomes(self, session_id: str, limit: int = 100) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM agent_outcomes WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()

    def archive_oldest_audit_events(
        self,
        archive_path: Path,
        keep_count: int,
    ) -> int:
        """Archive the oldest events, keeping only the newest *keep_count*.

        Returns the number of events archived.
        """
        total = self.count_audit_events()
        if total <= keep_count:
            return 0

        # Select oldest events to archive (everything except the newest keep_count)
        rows = self._db.execute(
            """SELECT * FROM audit_events
               ORDER BY timestamp ASC
               LIMIT ?""",
            (total - keep_count,),
        ).fetchall()

        if not rows:
            return 0

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

        # Delete archived events by their IDs
        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" for _ in ids)
        self._db.execute(f"DELETE FROM audit_events WHERE id IN ({placeholders})", ids)
        self._db.commit()

        return len(rows)
