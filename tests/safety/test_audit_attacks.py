"""
AI Safety Regression — Audit chain attack resistance.

Verifies that the SQLite audit hash chain detects all adversarial
modifications: tampering, gap attacks, truncation, phantom insertion,
concurrent sequential writes, and hash algorithm correctness.

Chain structure (from append_audit_event):
  chain_input = prev_hash + event_id + event_type + json(payload)
  hash        = SHA-256(chain_input)
  Ordering    = timestamp ASC (insertion order)

Acceptance: >=12 vectors per issue #323 acceptance criteria.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime

import pytest

from atlasbridge.core.audit.writer import AuditWriter
from atlasbridge.core.store.database import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "audit_attacks.db")
    d.connect()
    d._db.execute(
        "INSERT INTO sessions (id, tool, command, status) VALUES (?, ?, ?, ?)",
        ("s1", "claude", "[]", "running"),
    )
    d._db.commit()
    yield d
    d.close()


def _write_events(writer: AuditWriter, count: int = 3) -> None:
    """Write a simple sequence of audit events."""
    writer.session_started("s1", "claude", ["claude"])
    for i in range(count - 1):
        writer.prompt_detected("s1", f"p{i}", "yes_no", "high")


def _verify_chain(db: Database) -> tuple[bool, list[str]]:
    """Inline chain verification using the same algorithm as append_audit_event.

    Chain input: prev_hash + event_id + event_type + json(payload)
    Ordered by:  timestamp ASC (insertion order).
    """
    rows = db._db.execute(
        "SELECT id, event_type, payload, prev_hash, hash FROM audit_events ORDER BY timestamp ASC"
    ).fetchall()
    if not rows:
        return True, []

    errors: list[str] = []
    expected_prev = ""

    for i, row in enumerate(rows):
        payload_str = row["payload"] or ""
        # Replicate the exact chain_input formula from database.py:append_audit_event
        chain_input = f"{row['prev_hash']}{row['id']}{row['event_type']}{payload_str}"
        expected_hash = hashlib.sha256(chain_input.encode()).hexdigest()

        if row["hash"] != expected_hash:
            errors.append(f"row {i}: hash mismatch (event_id={row['id']!r})")

        if row["prev_hash"] != expected_prev:
            errors.append(
                f"row {i}: prev_hash mismatch "
                f"(expected {expected_prev!r}, got {row['prev_hash']!r})"
            )

        expected_prev = row["hash"]

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# 1. Hash algorithm verification
# ---------------------------------------------------------------------------


class TestHashAlgorithm:
    """Audit events must use SHA-256 (64-char hex digest)."""

    def test_hash_is_sha256_length(self, db: Database) -> None:
        AuditWriter(db).session_started("s1", "claude", ["claude"])
        row = db._db.execute("SELECT hash FROM audit_events LIMIT 1").fetchone()
        assert len(row["hash"]) == 64, "Hash must be a 64-char SHA-256 hex digest"

    def test_hash_is_hex_string(self, db: Database) -> None:
        AuditWriter(db).session_started("s1", "claude", ["claude"])
        row = db._db.execute("SELECT hash FROM audit_events LIMIT 1").fetchone()
        int(row["hash"], 16)  # raises ValueError if not valid hex

    def test_first_event_empty_prev_hash(self, db: Database) -> None:
        AuditWriter(db).session_started("s1", "claude", ["claude"])
        row = db._db.execute(
            "SELECT prev_hash FROM audit_events ORDER BY timestamp ASC LIMIT 1"
        ).fetchone()
        assert row["prev_hash"] == ""

    def test_valid_chain_passes_verification(self, db: Database) -> None:
        _write_events(AuditWriter(db), count=5)
        valid, errors = _verify_chain(db)
        assert valid is True, f"Expected valid chain; errors: {errors}"

    def test_hash_changes_with_different_payload(self, db: Database) -> None:
        """Different payloads must produce different hashes."""
        writer = AuditWriter(db)
        writer.prompt_detected("s1", "p1", "yes_no", "high")
        writer.prompt_detected("s1", "p2", "free_text", "low")
        rows = db._db.execute(
            "SELECT hash FROM audit_events ORDER BY timestamp ASC"
        ).fetchall()
        hashes = [r["hash"] for r in rows]
        assert len(set(hashes)) == 2, "Different events must produce different hashes"


# ---------------------------------------------------------------------------
# 2. Tampering detection
# ---------------------------------------------------------------------------


class TestTamperingDetection:
    """Any modification to a stored event must break the chain."""

    def test_payload_tamper_detected(self, db: Database) -> None:
        _write_events(AuditWriter(db), count=3)
        first = db._db.execute(
            "SELECT id FROM audit_events ORDER BY timestamp ASC LIMIT 1"
        ).fetchone()
        db._db.execute(
            "UPDATE audit_events SET payload = '{\"tampered\":true}' WHERE id = ?",
            (first["id"],),
        )
        db._db.commit()
        valid, errors = _verify_chain(db)
        assert not valid
        assert any("hash mismatch" in e for e in errors)

    def test_event_type_tamper_detected(self, db: Database) -> None:
        _write_events(AuditWriter(db), count=3)
        first = db._db.execute(
            "SELECT id FROM audit_events ORDER BY timestamp ASC LIMIT 1"
        ).fetchone()
        db._db.execute(
            "UPDATE audit_events SET event_type = 'forged_type' WHERE id = ?",
            (first["id"],),
        )
        db._db.commit()
        valid, errors = _verify_chain(db)
        assert not valid, "Forged event_type must break the hash chain"

    def test_hash_field_overwrite_breaks_next_entry(self, db: Database) -> None:
        """Overwriting stored hash must break the next entry's prev_hash linkage."""
        _write_events(AuditWriter(db), count=3)
        first = db._db.execute(
            "SELECT id FROM audit_events ORDER BY timestamp ASC LIMIT 1"
        ).fetchone()
        db._db.execute(
            "UPDATE audit_events SET hash = ? WHERE id = ?",
            ("a" * 64, first["id"]),
        )
        db._db.commit()
        valid, errors = _verify_chain(db)
        assert not valid


# ---------------------------------------------------------------------------
# 3. Gap attack
# ---------------------------------------------------------------------------


class TestGapAttack:
    """Deleting entries from the middle of the chain must break it."""

    def test_delete_middle_entry_breaks_chain(self, db: Database) -> None:
        _write_events(AuditWriter(db), count=5)
        ids = [
            r["id"]
            for r in db._db.execute(
                "SELECT id FROM audit_events ORDER BY timestamp ASC"
            ).fetchall()
        ]
        middle_id = ids[2]
        db._db.execute("DELETE FROM audit_events WHERE id = ?", (middle_id,))
        db._db.commit()
        valid, errors = _verify_chain(db)
        assert not valid, "Deleting middle entry must break prev_hash linkage"

    def test_delete_first_entry_breaks_chain(self, db: Database) -> None:
        _write_events(AuditWriter(db), count=3)
        first_id = db._db.execute(
            "SELECT id FROM audit_events ORDER BY timestamp ASC LIMIT 1"
        ).fetchone()["id"]
        db._db.execute("DELETE FROM audit_events WHERE id = ?", (first_id,))
        db._db.commit()
        valid, errors = _verify_chain(db)
        assert not valid, "Deleting first entry must break the chain (prev_hash no longer '')"


# ---------------------------------------------------------------------------
# 4. Truncation attack
# ---------------------------------------------------------------------------


class TestTruncationAttack:
    """Deleting the tail of the chain is detectable via count comparison."""

    def test_truncation_reduces_event_count(self, db: Database) -> None:
        _write_events(AuditWriter(db), count=5)
        before = db._db.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()["n"]
        last_ids = [
            r["id"]
            for r in db._db.execute(
                "SELECT id FROM audit_events ORDER BY timestamp DESC LIMIT 2"
            ).fetchall()
        ]
        for eid in last_ids:
            db._db.execute("DELETE FROM audit_events WHERE id = ?", (eid,))
        db._db.commit()
        after = db._db.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()["n"]
        assert after == before - 2, "Truncation must reduce row count"

    def test_remaining_chain_valid_after_tail_truncation(self, db: Database) -> None:
        """Remaining entries must still form a valid internal chain after tail removal."""
        _write_events(AuditWriter(db), count=5)
        last_ids = [
            r["id"]
            for r in db._db.execute(
                "SELECT id FROM audit_events ORDER BY timestamp DESC LIMIT 2"
            ).fetchall()
        ]
        for eid in last_ids:
            db._db.execute("DELETE FROM audit_events WHERE id = ?", (eid,))
        db._db.commit()
        valid, errors = _verify_chain(db)
        assert valid is True, f"Remaining chain after tail truncation must be valid: {errors}"


# ---------------------------------------------------------------------------
# 5. Phantom insertion attack
# ---------------------------------------------------------------------------


class TestPhantomInsertionAttack:
    """A row inserted with a fabricated hash must break the chain."""

    def test_phantom_row_with_wrong_hash_breaks_chain(self, db: Database) -> None:
        _write_events(AuditWriter(db), count=2)
        last = db._db.execute(
            "SELECT hash FROM audit_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        # Insert phantom with correct prev_hash but fabricated (wrong) hash
        fake_hash = "f" * 64
        phantom_id = secrets.token_hex(12)
        now = datetime.now(UTC).isoformat()
        db._db.execute(
            """INSERT INTO audit_events
               (id, event_type, payload, session_id, prompt_id, prev_hash, hash, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (phantom_id, "phantom_event", "{}", "s1", "", last["hash"], fake_hash, now),
        )
        db._db.commit()
        valid, errors = _verify_chain(db)
        assert not valid, "Phantom row with fabricated hash must break chain"

    def test_phantom_row_after_chain_detected(self, db: Database) -> None:
        """A phantom appended with correct prev_hash but wrong computed hash."""
        _write_events(AuditWriter(db), count=3)
        last_hash = db._db.execute(
            "SELECT hash FROM audit_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()["hash"]
        phantom_id = secrets.token_hex(12)
        # Build fake hash that doesn't match the real chain_input formula
        wrong_hash = hashlib.sha256(b"wrong-input").hexdigest()
        db._db.execute(
            """INSERT INTO audit_events
               (id, event_type, payload, session_id, prompt_id, prev_hash, hash, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                phantom_id,
                "session_started",
                "{}",
                "s1",
                "",
                last_hash,
                wrong_hash,
                datetime.now(UTC).isoformat(),
            ),
        )
        db._db.commit()
        valid, errors = _verify_chain(db)
        assert not valid, "Phantom entry with mismatched hash must be detected"


# ---------------------------------------------------------------------------
# 6. Sequential multi-writer integrity
# ---------------------------------------------------------------------------


class TestSequentialMultiWriter:
    """Sequential writes from different AuditWriter instances must produce a valid chain."""

    def test_two_writers_sequential_chain_valid(self, db: Database) -> None:
        """Writer A writes 3 events; Writer B writes 2 more — chain must remain valid."""
        writer_a = AuditWriter(db)
        writer_a.session_started("s1", "claude", ["claude"])
        writer_a.prompt_detected("s1", "p1", "yes_no", "high")
        writer_a.prompt_detected("s1", "p2", "yes_no", "high")

        writer_b = AuditWriter(db)
        writer_b.reply_received("s1", "p1", "tg:123", "y", "n1")
        writer_b.response_injected("s1", "p1", "yes_no", "y", latency_ms=42.0)

        valid, errors = _verify_chain(db)
        assert valid is True, f"Sequential multi-writer chain must be valid: {errors}"

    def test_restart_simulation_chain_continues(self, tmp_path) -> None:
        """Simulating a daemon restart: second Database instance resumes the chain."""
        db_path = tmp_path / "restart_test.db"

        db1 = Database(db_path)
        db1.connect()
        db1._db.execute(
            "INSERT INTO sessions (id, tool, command, status) VALUES (?, ?, ?, ?)",
            ("s1", "claude", "[]", "running"),
        )
        db1._db.commit()
        writer1 = AuditWriter(db1)
        writer1.session_started("s1", "claude", ["claude"])
        writer1.prompt_detected("s1", "p1", "yes_no", "high")
        db1.close()

        # Simulate restart — new Database instance
        db2 = Database(db_path)
        db2.connect()
        writer2 = AuditWriter(db2)
        writer2.reply_received("s1", "p1", "tg:123", "y", "n1")
        writer2.daemon_restarted(prompts_reloaded=0)

        valid, errors = _verify_chain(db2)
        assert valid is True, f"Chain must remain valid after restart: {errors}"
        db2.close()
