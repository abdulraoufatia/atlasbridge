"""Unit tests for aegis.store.database — Database CRUD and decide_prompt guard."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aegis.core.constants import PromptStatus, PromptType
from aegis.store.database import Database
from aegis.store.models import AuditEvent, PromptRecord, Session


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "test.db")
    d.connect()
    yield d
    d.close()


def _session(sid: str | None = None) -> Session:
    return Session(id=sid or str(uuid.uuid4()), tool="claude", cwd="/tmp")


def _prompt(session_id: str, expires_in: float = 600.0) -> PromptRecord:
    now = datetime.now(UTC)
    return PromptRecord(
        id=str(uuid.uuid4()),
        session_id=session_id,
        input_type=PromptType.YES_NO,
        excerpt="Continue? (y/n)",
        confidence=0.90,
        nonce=secrets.token_hex(16),
        expires_at=(now + timedelta(seconds=expires_in)).isoformat(),
        status=PromptStatus.AWAITING_RESPONSE,
    )


# ---------------------------------------------------------------------------
# Session repository
# ---------------------------------------------------------------------------


class TestSessionRepo:
    def test_save_and_get(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        fetched = db.get_session(s.id)
        assert fetched is not None
        assert fetched.id == s.id
        assert fetched.tool == "claude"

    def test_update_session(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        db.update_session(s.id, status="completed", exit_code=0)
        fetched = db.get_session(s.id)
        assert fetched.status == "completed"
        assert fetched.exit_code == 0

    def test_list_active(self, db: Database) -> None:
        s1 = _session()
        s2 = _session()
        db.save_session(s1)
        db.save_session(s2)
        db.update_session(s2.id, status="completed")
        active = db.list_active_sessions()
        assert any(s.id == s1.id for s in active)
        assert not any(s.id == s2.id for s in active)

    def test_get_missing(self, db: Database) -> None:
        assert db.get_session("nonexistent") is None


# ---------------------------------------------------------------------------
# Prompt repository
# ---------------------------------------------------------------------------


class TestPromptRepo:
    def test_save_and_get(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        p = _prompt(s.id)
        db.save_prompt(p)
        fetched = db.get_prompt(p.id)
        assert fetched is not None
        assert fetched.nonce == p.nonce

    def test_decide_prompt_success(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        p = _prompt(s.id)
        db.save_prompt(p)
        rows = db.decide_prompt(p.id, PromptStatus.RESPONSE_RECEIVED, "telegram:42", "y", p.nonce)
        assert rows == 1
        updated = db.get_prompt(p.id)
        assert updated.status == PromptStatus.RESPONSE_RECEIVED
        assert updated.response_normalized == "y"
        assert updated.nonce_used is True

    def test_decide_prompt_replay_rejected(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        p = _prompt(s.id)
        db.save_prompt(p)
        db.decide_prompt(p.id, PromptStatus.RESPONSE_RECEIVED, "telegram:42", "y", p.nonce)
        # Second attempt with same nonce must be rejected
        rows = db.decide_prompt(p.id, PromptStatus.RESPONSE_RECEIVED, "telegram:42", "n", p.nonce)
        assert rows == 0

    def test_decide_prompt_expired_rejected(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        p = _prompt(s.id, expires_in=-10)  # already expired
        db.save_prompt(p)
        rows = db.decide_prompt(p.id, PromptStatus.RESPONSE_RECEIVED, "telegram:42", "y", p.nonce)
        assert rows == 0

    def test_decide_prompt_wrong_nonce_rejected(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        p = _prompt(s.id)
        db.save_prompt(p)
        rows = db.decide_prompt(
            p.id, PromptStatus.RESPONSE_RECEIVED, "telegram:42", "y", "wrong-nonce"
        )
        assert rows == 0

    def test_list_pending(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        p1 = _prompt(s.id)
        p2 = _prompt(s.id)
        db.save_prompt(p1)
        db.save_prompt(p2)
        db.decide_prompt(p2.id, PromptStatus.RESPONSE_RECEIVED, "user", "y", p2.nonce)
        pending = db.list_pending_prompts(session_id=s.id)
        ids = [p.id for p in pending]
        assert p1.id in ids
        assert p2.id not in ids

    def test_list_expired(self, db: Database) -> None:
        s = _session()
        db.save_session(s)
        exp = _prompt(s.id, expires_in=-1)
        fresh = _prompt(s.id, expires_in=600)
        db.save_prompt(exp)
        db.save_prompt(fresh)
        expired_list = db.list_expired_pending()
        assert any(p.id == exp.id for p in expired_list)
        assert not any(p.id == fresh.id for p in expired_list)


# ---------------------------------------------------------------------------
# Audit event repository
# ---------------------------------------------------------------------------


class TestAuditRepo:
    def test_save_and_retrieve(self, db: Database) -> None:
        ev = AuditEvent(id=str(uuid.uuid4()), event_type="test_event")
        db.save_audit_event(ev)
        last = db.get_last_audit_event()
        assert last is not None
        assert last.event_type == "test_event"

    def test_list_recent(self, db: Database) -> None:
        for i in range(5):
            db.save_audit_event(AuditEvent(id=str(uuid.uuid4()), event_type=f"ev_{i}"))
        events = db.list_recent_audit_events(limit=3)
        assert len(events) == 3
