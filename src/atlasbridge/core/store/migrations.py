"""
Schema migrations for the AtlasBridge SQLite database.

Uses PRAGMA user_version as the version counter (atomic, no extra table).
Each migration is an idempotent function that upgrades from version N to N+1.

Migration contract:
  - Migrations run inside an explicit transaction (BEGIN / COMMIT).
  - Each migration MUST be idempotent — safe to re-run after a mid-flight crash.
  - After all migrations succeed, PRAGMA user_version is bumped.
  - If any migration fails, the transaction is rolled back and the error is
    surfaced with the DB path so the user can take recovery action.

Version history:
  0 → 1: Initial schema (sessions, prompts, replies, audit_events with timestamp cols)
  1 → 2: Delivery tracking (prompt_deliveries table for idempotent channel sends)
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import structlog

logger = structlog.get_logger()

# Bump this when adding a new migration.
LATEST_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Individual migrations
# ---------------------------------------------------------------------------


def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    """
    Version 0 → 1: ensure all four tables exist with the current column set.

    This handles three cases:
      a) Fresh install — no tables exist; creates everything.
      b) Upgrade from a pre-versioned DB — tables exist but may be missing
         columns (e.g. ``timestamp`` in ``replies`` / ``audit_events``).
      c) Partially-created DB after a crash — some tables may exist, others not.

    Strategy: CREATE TABLE IF NOT EXISTS for the full schema, then
    ALTER TABLE ADD COLUMN for any columns that older schemas may lack.
    ALTER TABLE ADD COLUMN is a no-op if the column already exists in modern
    SQLite (3.35+), but we guard with a helper for older builds.
    """
    # -- sessions -----------------------------------------------------------
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

    # -- prompts ------------------------------------------------------------
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

    # -- replies ------------------------------------------------------------
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

    # -- audit_events -------------------------------------------------------
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

    # -- add columns that may be missing from older schemas -----------------
    _add_column_if_missing(conn, "replies", "timestamp", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "audit_events", "timestamp", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "audit_events", "prev_hash", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "audit_events", "hash", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "sessions", "label", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "sessions", "metadata", "TEXT NOT NULL DEFAULT '{}'")
    _add_column_if_missing(conn, "prompts", "channel_message_id", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "prompts", "metadata", "TEXT NOT NULL DEFAULT '{}'")

    # -- indexes ------------------------------------------------------------
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_prompts_session_status
            ON prompts(session_id, status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_events(timestamp)
    """)

    # -- drop the old schema_version table if it exists ---------------------
    # (we now use PRAGMA user_version instead)
    conn.execute("DROP TABLE IF EXISTS schema_version")


# ---------------------------------------------------------------------------
# Migration registry (version_from → callable)
# ---------------------------------------------------------------------------


def _migrate_1_to_2(conn: sqlite3.Connection) -> None:
    """Version 1 → 2: add prompt_deliveries table for idempotent channel sends."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompt_deliveries (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id        TEXT NOT NULL,
            session_id       TEXT NOT NULL,
            channel          TEXT NOT NULL,
            channel_identity TEXT NOT NULL,
            message_id       TEXT NOT NULL DEFAULT '',
            delivered_at     TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(prompt_id, channel, channel_identity)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_deliveries_prompt
            ON prompt_deliveries(prompt_id)
    """)


_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    0: _migrate_0_to_1,
    1: _migrate_1_to_2,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    column_def: str,
) -> None:
    """Add a column to *table* if it does not already exist."""
    cursor = conn.execute(f"PRAGMA table_info({table})")  # noqa: S608
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")  # noqa: S608
        logger.info("migration_added_column", table=table, column=column)


def get_user_version(conn: sqlite3.Connection) -> int:
    """Read the current PRAGMA user_version."""
    row = conn.execute("PRAGMA user_version").fetchone()
    return row[0] if row else 0


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    """Set PRAGMA user_version (must be outside a transaction in some drivers)."""
    conn.execute(f"PRAGMA user_version = {version}")  # noqa: S608


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_migrations(conn: sqlite3.Connection, db_path: Path) -> None:
    """
    Run all pending schema migrations on *conn*.

    Raises ``RuntimeError`` with a user-friendly message (including the DB
    path) if any migration fails, so the caller can display recovery steps.
    """
    current = get_user_version(conn)

    if current > LATEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database {db_path} has schema version {current}, but this build of "
            f"AtlasBridge only supports up to version {LATEST_SCHEMA_VERSION}. "
            f"Please upgrade AtlasBridge or remove the database file."
        )

    if current == LATEST_SCHEMA_VERSION:
        return  # already up to date

    logger.info(
        "migration_starting",
        from_version=current,
        to_version=LATEST_SCHEMA_VERSION,
    )

    for from_version in range(current, LATEST_SCHEMA_VERSION):
        migration = _MIGRATIONS.get(from_version)
        if migration is None:
            raise RuntimeError(
                f"No migration registered for v{from_version} → v{from_version + 1}. "
                f"Database: {db_path}"
            )

        target = from_version + 1
        logger.info("migration_step", from_version=from_version, to_version=target)

        try:
            migration(conn)
            _set_user_version(conn, target)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(
                f"Schema migration v{from_version} → v{target} failed: {exc}\n"
                f"Database path: {db_path}\n"
                f"Recovery: delete (or rename) the database file and restart.\n"
                f"  mv '{db_path}' '{db_path}.bak'"
            ) from exc

    final = get_user_version(conn)
    logger.info("migration_complete", version=final)
