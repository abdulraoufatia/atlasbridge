"""
Workspace trust store.

Persists per-workspace trust decisions in the AtlasBridge SQLite database.
Trust is keyed by path_hash (SHA-256 of the canonical resolved path) so that
symlink variations of the same directory map to one record.

Correctness invariants:
  - get_trust() is read-only and always returns a definitive bool.
  - grant_trust() uses INSERT OR REPLACE so it is idempotent.
  - revoke_trust() sets trusted=0 and records the revocation timestamp.
  - No raw API keys or secrets are stored here.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

_TRUST_PROMPT_TEMPLATE = "Trust workspace {path} for this session?\nReply: yes or no"


def _hash_path(path: str) -> str:
    """SHA-256 of the canonical (resolved) absolute path."""
    canonical = str(Path(path).resolve())
    return hashlib.sha256(canonical.encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Channel-facing helpers
# ---------------------------------------------------------------------------


def build_trust_prompt(path: str) -> str:
    """Return the clean yes/no trust prompt text for a workspace path.

    The text must never contain terminal semantics (Enter, Esc, arrow keys).
    """
    return _TRUST_PROMPT_TEMPLATE.format(path=path)


def normalise_trust_reply(value: str) -> bool | None:
    """Normalise a channel reply to a trust decision.

    Returns True (trust), False (deny), or None if the reply is ambiguous.
    """
    v = value.strip().lower()
    if v in ("yes", "y"):
        return True
    if v in ("no", "n"):
        return False
    return None


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------


def get_trust(path: str, conn: sqlite3.Connection) -> bool:
    """Return True if the workspace at *path* is currently trusted."""
    ph = _hash_path(path)
    row = conn.execute(
        "SELECT trusted FROM workspace_trust WHERE path_hash = ?",
        (ph,),
    ).fetchone()
    return bool(row and row[0])


def grant_trust(
    path: str,
    conn: sqlite3.Connection,
    *,
    actor: str = "unknown",
    channel: str = "",
    session_id: str = "",
) -> None:
    """Record a trust grant for *path*."""
    ph = _hash_path(path)
    now = _now()
    conn.execute(
        """
        INSERT INTO workspace_trust
            (path, path_hash, trusted, actor, channel, session_id, granted_at, revoked_at)
        VALUES (?, ?, 1, ?, ?, ?, ?, NULL)
        ON CONFLICT(path_hash) DO UPDATE SET
            trusted     = 1,
            actor       = excluded.actor,
            channel     = excluded.channel,
            session_id  = excluded.session_id,
            granted_at  = excluded.granted_at,
            revoked_at  = NULL
        """,
        (path, ph, actor, channel, session_id, now),
    )
    conn.commit()
    logger.info("workspace_trust_granted", path=path, actor=actor, channel=channel)


def revoke_trust(path: str, conn: sqlite3.Connection) -> None:
    """Record a trust revocation for *path*."""
    ph = _hash_path(path)
    now = _now()
    conn.execute(
        """
        UPDATE workspace_trust
           SET trusted = 0, revoked_at = ?
         WHERE path_hash = ?
        """,
        (now, ph),
    )
    conn.commit()
    logger.info("workspace_trust_revoked", path=path)


def list_workspaces(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all workspace trust records as plain dicts."""
    rows = conn.execute(
        """
        SELECT id, path, path_hash, trusted, actor, channel, session_id,
               granted_at, revoked_at, created_at
          FROM workspace_trust
         ORDER BY created_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_workspace_status(path: str, conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the full trust record for *path*, or None if not known."""
    ph = _hash_path(path)
    row = conn.execute(
        """
        SELECT id, path, path_hash, trusted, actor, channel, session_id,
               granted_at, revoked_at, created_at
          FROM workspace_trust
         WHERE path_hash = ?
        """,
        (ph,),
    ).fetchone()
    return dict(row) if row else None
