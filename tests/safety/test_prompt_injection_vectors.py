"""
AI Safety Regression — Prompt injection & adversarial input vectors.

These tests verify that malicious or malformed inputs cannot bypass
the correctness invariants. Each vector targets a specific attack surface.

Minimum 20 vectors per issue #218 acceptance criteria.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from atlasbridge.core.store.database import Database

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path):
    """Create a fresh database with default session records."""
    d = Database(tmp_path / "test.db")
    d.connect()
    # Insert session records for FK constraints
    for sid in ("sess-1", "s1", "session-A", "session-B"):
        d._db.execute(
            "INSERT INTO sessions (id, tool, command, status) VALUES (?, ?, ?, ?)",
            (sid, "claude", "[]", "running"),
        )
    d._db.commit()
    yield d
    d.close()


def _expires_at(seconds: float = 300.0) -> str:
    """SQLite-compatible datetime string."""
    dt = datetime.now(UTC) + timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _ensure_session(db: Database, session_id: str) -> None:
    """Create session record if it doesn't exist (for FK constraint)."""
    existing = db._db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not existing:
        db._db.execute(
            "INSERT INTO sessions (id, tool, command, status) VALUES (?, ?, ?, ?)",
            (session_id, "claude", "[]", "running"),
        )
        db._db.commit()


def _save_prompt(db: Database, prompt_id: str, session_id: str, nonce: str, ttl_s: int = 300):
    """Save a prompt in awaiting_reply state."""
    _ensure_session(db, session_id)
    expires = _expires_at(ttl_s)
    db.save_prompt(
        prompt_id=prompt_id,
        session_id=session_id,
        prompt_type="yes_no",
        confidence="high",
        excerpt="Continue?",
        nonce=nonce,
        expires_at=expires,
    )


# ---------------------------------------------------------------------------
# 1. SQL injection in prompt_id / session_id / nonce
# ---------------------------------------------------------------------------


class TestSQLInjection:
    """Crafted IDs must never break the SQL guard."""

    @pytest.mark.parametrize(
        "malicious_id",
        [
            "'; DROP TABLE prompts; --",
            '" OR 1=1 --',
            "1; UPDATE prompts SET status='replied'",
            "' UNION SELECT * FROM prompts --",
            "Robert'); DROP TABLE sessions;--",
        ],
    )
    def test_sql_injection_in_prompt_id(self, db: Database, malicious_id: str):
        _save_prompt(db, "legit-prompt", "sess-1", "nonce-1")
        result = db.decide_prompt(malicious_id, "replied", "tg:123", "y", "nonce-1")
        assert result == 0
        # Verify the legit prompt is untouched
        row = db.get_prompt("legit-prompt")
        assert row is not None
        assert row["status"] == "awaiting_reply"

    @pytest.mark.parametrize(
        "malicious_nonce",
        [
            "'; DELETE FROM prompts; --",
            "' OR nonce_used=0 --",
            "nonce' AND 1=1 --",
        ],
    )
    def test_sql_injection_in_nonce(self, db: Database, malicious_nonce: str):
        _save_prompt(db, "p1", "s1", "real-nonce")
        result = db.decide_prompt("p1", "replied", "tg:123", "y", malicious_nonce)
        assert result == 0

    def test_sql_injection_in_session_id(self, db: Database):
        malicious = "sess'; DROP TABLE sessions;--"
        _save_prompt(db, "p1", malicious, "n1")
        # Should store cleanly, session_id is parameterized
        row = db.get_prompt("p1")
        assert row["session_id"] == malicious


# ---------------------------------------------------------------------------
# 2. Unicode and control character injection
# ---------------------------------------------------------------------------


class TestUnicodeInjection:
    """Unicode edge cases must not break detection or storage."""

    @pytest.mark.parametrize(
        "text",
        [
            "\x00null-byte-prompt",
            "\r\n\r\nCRLF-injection",
            "\x1b[31mANSI-escape",
            "\u202eRTL-override",
            "\ufeffBOM-prefix",
            "emoji-\U0001f4a3-bomb",
            "a" * 10000,  # oversized input
        ],
    )
    def test_unicode_in_excerpt(self, db: Database, text: str):
        """Special characters in excerpt must not crash save_prompt."""
        expires = _expires_at(300)
        db.save_prompt(
            prompt_id="p-unicode",
            session_id="s1",
            prompt_type="yes_no",
            confidence="high",
            excerpt=text,
            nonce="n-1",
            expires_at=expires,
        )
        row = db.get_prompt("p-unicode")
        assert row is not None
        assert row["excerpt"] == text

    def test_null_byte_in_nonce(self, db: Database):
        _save_prompt(db, "p1", "s1", "nonce\x00injected")
        result = db.decide_prompt("p1", "replied", "tg:123", "y", "nonce\x00injected")
        assert result == 1  # exact match succeeds

    def test_null_byte_in_nonce_mismatch(self, db: Database):
        _save_prompt(db, "p1", "s1", "nonce-real")
        result = db.decide_prompt("p1", "replied", "tg:123", "y", "nonce\x00real")
        assert result == 0  # mismatch


# ---------------------------------------------------------------------------
# 3. Replay and nonce attacks
# ---------------------------------------------------------------------------


class TestReplayAttacks:
    """Nonce idempotency must hold under all circumstances."""

    def test_double_decide_rejected(self, db: Database):
        _save_prompt(db, "p1", "s1", "n1")
        r1 = db.decide_prompt("p1", "replied", "tg:123", "y", "n1")
        r2 = db.decide_prompt("p1", "replied", "tg:123", "y", "n1")
        assert r1 == 1
        assert r2 == 0  # nonce_used = 1 blocks replay

    def test_wrong_nonce_rejected(self, db: Database):
        _save_prompt(db, "p1", "s1", "correct-nonce")
        result = db.decide_prompt("p1", "replied", "tg:123", "y", "wrong-nonce")
        assert result == 0

    def test_empty_nonce_rejected(self, db: Database):
        _save_prompt(db, "p1", "s1", "real-nonce")
        result = db.decide_prompt("p1", "replied", "tg:123", "y", "")
        assert result == 0


# ---------------------------------------------------------------------------
# 4. TTL and expiry attacks
# ---------------------------------------------------------------------------


class TestTTLAttacks:
    """Expired prompts must never be injectable."""

    def test_expired_prompt_rejected(self, db: Database):
        """A prompt with expires_at in the past must be rejected."""
        _save_prompt(db, "p-exp", "s1", "n1", ttl_s=-60)
        result = db.decide_prompt("p-exp", "replied", "tg:123", "y", "n1")
        assert result == 0

    def test_zero_ttl_prompt(self, db: Database):
        """TTL=0 means immediately expired."""
        now = _expires_at(0)
        db.save_prompt(
            prompt_id="p-zero",
            session_id="s1",
            prompt_type="yes_no",
            confidence="high",
            excerpt="?",
            nonce="n1",
            expires_at=now,
        )
        result = db.decide_prompt("p-zero", "replied", "tg:123", "y", "n1")
        assert result == 0


# ---------------------------------------------------------------------------
# 5. Cross-session injection attempts
# ---------------------------------------------------------------------------


class TestCrossSession:
    """A reply for one session must never affect another."""

    def test_prompt_id_bound_to_session(self, db: Database):
        _save_prompt(db, "p1", "session-A", "n1")
        _save_prompt(db, "p2", "session-B", "n2")
        # Trying to decide p2 doesn't affect p1
        r2 = db.decide_prompt("p2", "replied", "tg:123", "y", "n2")
        assert r2 == 1
        row = db.get_prompt("p1")
        assert row["status"] == "awaiting_reply"


# ---------------------------------------------------------------------------
# 6. Audit hash chain tamper resistance
# ---------------------------------------------------------------------------


class TestAuditTamperResistance:
    """Verify the audit log detects all forms of tampering."""

    def test_hash_chain_valid_after_writes(self, db: Database):
        from atlasbridge.core.audit.writer import AuditWriter

        writer = AuditWriter(db)
        writer.session_started("s1", "claude", ["claude"])
        writer.prompt_detected("s1", "p1", "yes_no", "high")
        writer.reply_received("s1", "p1", "tg:123", "y", "n1")

        rows = db._db.execute("SELECT * FROM audit_events ORDER BY timestamp ASC").fetchall()
        assert len(rows) == 3

        prev_hash = ""
        for row in rows:
            payload_str = row["payload"] or ""
            chain_input = f"{row['prev_hash']}{row['id']}{row['event_type']}{payload_str}"
            expected = hashlib.sha256(chain_input.encode()).hexdigest()
            assert row["hash"] == expected
            if prev_hash:
                assert row["prev_hash"] == prev_hash
            prev_hash = row["hash"]

    def test_tampered_payload_detected(self, db: Database):
        """Tampering with event payload breaks hash chain integrity."""
        verify_mod = pytest.importorskip(
            "atlasbridge.core.audit.verify",
            reason="verify module not yet merged (PR #321)",
        )
        from atlasbridge.core.audit.writer import AuditWriter

        writer = AuditWriter(db)
        writer.session_started("s1", "claude", ["claude"])
        writer.prompt_detected("s1", "p1", "yes_no", "high")

        # Tamper with first event's payload
        db._db.execute("UPDATE audit_events SET payload = '{\"tampered\":true}' WHERE rowid = 1")
        db._db.commit()

        result = verify_mod.verify_audit_chain(db)
        assert result.valid is False
        assert len(result.errors) >= 1
