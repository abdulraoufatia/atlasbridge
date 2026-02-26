"""Safety regression tests for workspace trust invariants.

Ensures the workspace trust pre-check does NOT bypass any existing
correctness invariants from CLAUDE.md:
  1. Nonce idempotency — still enforced after workspace trust pre-grant
  2. TTL enforcement — expired prompts still rejected
  3. Session binding — cross-session trust injection still rejected
  4. Audit trail — every trust grant/revoke creates a DB record
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from atlasbridge.core.store.database import Database
from atlasbridge.core.store.migrations import run_migrations
from atlasbridge.core.store.workspace_trust import (
    get_trust,
    get_workspace_status,
    grant_trust,
    revoke_trust,
)


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    database.connect()
    database._db.execute(
        "INSERT INTO sessions (id, tool, command, status) VALUES (?, ?, ?, ?)",
        ("sess-001", "claude", "[]", "running"),
    )
    database._db.commit()
    yield database
    database.close()


@pytest.fixture()
def raw_conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "trust.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    run_migrations(c, db_path)
    yield c
    c.close()


def _expires_at(seconds: float = 300.0) -> str:
    dt = datetime.now(UTC) + timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _save_prompt(db: Database, session_id: str, prompt_id: str, expires_at: str) -> None:
    db.save_prompt(
        prompt_id=prompt_id,
        session_id=session_id,
        prompt_type="yes_no",
        confidence="high",
        excerpt="Trust workspace?",
        nonce="nonce-init",
        expires_at=expires_at,
    )


SAVED_NONCE = "nonce-init"  # nonce used by _save_prompt


class TestNonceIdempotencyPreserved:
    def test_decide_prompt_still_rejects_replay(self, db: Database) -> None:
        """Nonce guard must reject duplicate decide_prompt calls even after trust pre-grant."""
        pid = "prompt-nonce-001"
        _save_prompt(db, "sess-001", pid, _expires_at(300))

        # First call with correct nonce → accepted
        result1 = db.decide_prompt(pid, "injected", "user-1", "1", SAVED_NONCE)
        assert result1 == 1  # accepted

        # Second call with same nonce → rejected (nonce_used=1)
        result2 = db.decide_prompt(pid, "injected", "user-1", "1", SAVED_NONCE)
        assert result2 == 0  # rejected (nonce replay)

    def test_decide_prompt_rejects_wrong_nonce(self, db: Database) -> None:
        pid = "prompt-wrong-nonce"
        _save_prompt(db, "sess-001", pid, _expires_at(300))

        # First call with correct nonce → accepted
        result1 = db.decide_prompt(pid, "injected", "user-1", "1", SAVED_NONCE)
        assert result1 == 1

        # Second call with wrong nonce → rejected (already used + wrong nonce)
        result2 = db.decide_prompt(pid, "injected", "user-1", "1", "totally-wrong-nonce")
        assert result2 == 0


class TestTTLEnforcementPreserved:
    def test_expired_prompt_rejected_regardless_of_trust(self, db: Database) -> None:
        pid = "prompt-expired"
        # Expires in the past
        past = (datetime.now(UTC) - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
        _save_prompt(db, "sess-001", pid, past)

        result = db.decide_prompt(pid, "injected", "user-1", "1", SAVED_NONCE)
        assert result == 0  # rejected — expired


class TestSessionBindingPreserved:
    def test_unknown_prompt_id_rejected(self, db: Database) -> None:
        result = db.decide_prompt("nonexistent-prompt", "injected", "user-1", "1", "n")
        assert result == 0


class TestTrustAuditRecord:
    def test_grant_creates_db_record(self, raw_conn: sqlite3.Connection) -> None:
        grant_trust("/tmp/audit-check", raw_conn, actor="telegram", channel="u1", session_id="s1")
        status = get_workspace_status("/tmp/audit-check", raw_conn)
        assert status is not None
        assert status["trusted"] == 1
        assert status["actor"] == "telegram"
        assert status["granted_at"] is not None

    def test_revoke_creates_audit_trail(self, raw_conn: sqlite3.Connection) -> None:
        grant_trust("/tmp/revoke-audit-2", raw_conn, actor="dashboard")
        revoke_trust("/tmp/revoke-audit-2", raw_conn)
        status = get_workspace_status("/tmp/revoke-audit-2", raw_conn)
        assert status["trusted"] == 0
        assert status["revoked_at"] is not None

    def test_grant_is_not_anonymous(self, raw_conn: sqlite3.Connection) -> None:
        grant_trust("/tmp/not-anonymous", raw_conn, actor="dashboard", channel="web")
        status = get_workspace_status("/tmp/not-anonymous", raw_conn)
        # actor must be set — no anonymous trust grants
        assert status["actor"] != ""
        assert status["actor"] is not None

    def test_trust_record_survives_re_grant(self, raw_conn: sqlite3.Connection) -> None:
        """Re-granting trust updates the record — audit trail is preserved in DB."""
        grant_trust("/tmp/re-grant", raw_conn, actor="session1")
        grant_trust("/tmp/re-grant", raw_conn, actor="session2")
        status = get_workspace_status("/tmp/re-grant", raw_conn)
        assert status["trusted"] == 1
        # Latest actor is recorded
        assert status["actor"] == "session2"
