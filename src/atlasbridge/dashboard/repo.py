"""
Read-only repository for the local dashboard.

Opens the SQLite database in ``mode=ro`` (read-only) to prevent accidental
writes and avoid WAL lock contention with a running daemon. Accesses the
decision trace via ``DecisionTrace.tail()`` and ``verify_integrity()``.

All methods return plain dicts so templates can consume them directly.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from atlasbridge.dashboard.sanitize import sanitize_for_display


class DashboardRepo:
    """Read-only data access for dashboard screens."""

    def __init__(self, db_path: Path, trace_path: Path) -> None:
        self._db_path = db_path
        self._trace_path = trace_path
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open a read-only connection to the database."""
        if not self._db_path.exists():
            return  # No DB yet — all queries return empty results
        self._conn = sqlite3.connect(
            f"file:{self._db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def db_available(self) -> bool:
        return self._conn is not None

    @property
    def trace_available(self) -> bool:
        return self._trace_path.exists()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return summary stats for the home page cards."""
        if not self.db_available:
            return {"sessions": 0, "prompts": 0, "audit_events": 0, "active_sessions": 0}

        assert self._conn is not None
        stats: dict[str, Any] = {}
        for table in ("sessions", "prompts", "audit_events"):
            row = self._conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
            stats[table] = row[0] if row else 0

        row = self._conn.execute(
            "SELECT count(*) FROM sessions WHERE status NOT IN ('completed', 'crashed', 'canceled')"
        ).fetchone()
        stats["active_sessions"] = row[0] if row else 0
        return stats

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.db_available:
            return []
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        if not self.db_available:
            return None
        assert self._conn is not None
        row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def list_prompts_for_session(self, session_id: str) -> list[dict[str, Any]]:
        if not self.db_available:
            return []
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM prompts WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------

    def list_audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.db_available:
            return []
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Decision trace (JSONL)
    # ------------------------------------------------------------------

    def trace_tail(self, n: int = 50) -> list[dict[str, Any]]:
        """Return the last n trace entries."""
        if not self.trace_available:
            return []
        from atlasbridge.core.autopilot.trace import DecisionTrace

        return DecisionTrace(self._trace_path).tail(n)

    def trace_entry(self, index: int) -> dict[str, Any] | None:
        """Return a single trace entry by 0-based index (from the tail)."""
        entries = self.trace_tail(index + 1)
        if index < len(entries):
            return entries[index]
        return None

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Verify hash chain integrity of the trace file."""
        if not self.trace_available:
            return True, []
        from atlasbridge.core.autopilot.trace import DecisionTrace

        return DecisionTrace.verify_integrity(self._trace_path)

    def verify_audit_integrity(self) -> tuple[bool, list[str]]:
        """Verify hash chain integrity of audit events in the database."""
        if not self.db_available:
            return True, []
        assert self._conn is not None

        errors: list[str] = []
        prev_hash = ""
        rows = self._conn.execute("SELECT * FROM audit_events ORDER BY timestamp ASC").fetchall()

        for i, row in enumerate(rows):
            row_dict = self._row_to_dict(row)
            stored_prev = row_dict.get("prev_hash", "")
            if stored_prev != prev_hash:
                errors.append(
                    f"Event {i + 1} (id={row_dict.get('id', '?')}): "
                    f"prev_hash mismatch — expected {prev_hash!r}, got {stored_prev!r}"
                )
            prev_hash = row_dict.get("hash", "")

        return len(errors) == 0, errors

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict with sanitized text fields."""
        d: dict[str, Any] = dict(row)
        # Sanitize text fields that might contain ANSI or tokens
        for key in ("excerpt", "value", "payload", "command"):
            if key in d and isinstance(d[key], str):
                d[key] = sanitize_for_display(d[key])
        # Parse JSON metadata/payload if present
        for key in ("metadata", "payload"):
            if key in d and isinstance(d[key], str):
                try:
                    d[f"{key}_parsed"] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[f"{key}_parsed"] = None
        return d
