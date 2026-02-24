"""Tests for audit hash chain verification (verify_audit_chain)."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch

from atlasbridge.core.audit.verify import (
    AuditVerifyResult,
    format_verify_result,
    verify_audit_chain,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(
    event_id: str,
    event_type: str,
    payload: dict | None = None,
    prev_hash: str = "",
    hash_val: str | None = None,
    session_id: str = "sess-1",
) -> MagicMock:
    """Build a mock sqlite3.Row with correct hash chain."""
    payload_str = json.dumps(payload or {}, separators=(",", ":"), sort_keys=True)
    if hash_val is None:
        chain_input = f"{prev_hash}{event_id}{event_type}{payload_str}"
        hash_val = hashlib.sha256(chain_input.encode()).hexdigest()

    data = {
        "id": event_id,
        "event_type": event_type,
        "session_id": session_id,
        "prompt_id": "",
        "payload": payload_str,
        "timestamp": "2026-02-24T00:00:00+00:00",
        "prev_hash": prev_hash,
        "hash": hash_val,
    }
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    row.keys = lambda: list(data.keys())
    return row, hash_val


def _build_chain(count: int = 3, session_id: str = "sess-1") -> list:
    """Build a valid chain of count events."""
    rows = []
    prev = ""
    for i in range(count):
        row, h = _make_row(
            event_id=f"evt-{i}",
            event_type="test_event",
            payload={"i": i},
            prev_hash=prev,
            session_id=session_id,
        )
        rows.append(row)
        prev = h
    return rows


# ---------------------------------------------------------------------------
# Tests — verify_audit_chain
# ---------------------------------------------------------------------------


class TestVerifyAuditChainValid:
    """Tests for valid hash chains."""

    def test_empty_log(self):
        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = []
        result = verify_audit_chain(db)
        assert result.valid is True
        assert result.total_events == 0
        assert result.verified_events == 0
        assert result.errors == []

    def test_single_event(self):
        rows = _build_chain(count=1)
        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = rows
        result = verify_audit_chain(db)
        assert result.valid is True
        assert result.total_events == 1
        assert result.verified_events == 1

    def test_multi_event_chain(self):
        rows = _build_chain(count=5)
        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = rows
        result = verify_audit_chain(db)
        assert result.valid is True
        assert result.total_events == 5
        assert result.verified_events == 5
        assert result.errors == []

    def test_session_scoped(self):
        rows = _build_chain(count=3, session_id="sess-abc")
        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = rows
        result = verify_audit_chain(db, session_id="sess-abc")
        assert result.valid is True
        assert result.total_events == 3
        assert result.verified_events == 3


class TestVerifyAuditChainTampered:
    """Tests for tampered/broken hash chains."""

    def test_tampered_payload(self):
        """Modifying a payload should break its hash."""
        rows = _build_chain(count=3)
        # Tamper with event #1's payload (row stores serialized JSON)
        original_data = {
            "id": "evt-1",
            "event_type": "test_event",
            "session_id": "sess-1",
            "prompt_id": "",
            "payload": '{"i":999}',  # tampered
            "timestamp": "2026-02-24T00:00:00+00:00",
            "prev_hash": rows[1]["prev_hash"],
            "hash": rows[1]["hash"],  # old hash won't match
        }
        tampered = MagicMock()
        tampered.__getitem__ = lambda self, key: original_data[key]
        rows[1] = tampered

        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = rows
        result = verify_audit_chain(db)
        assert result.valid is False
        assert len(result.errors) >= 1
        assert result.first_break_event_id == "evt-1"
        assert result.first_break_position == 1

    def test_broken_prev_hash_link(self):
        """Breaking the prev_hash link between events."""
        rows = _build_chain(count=3)
        # Overwrite event #2's prev_hash to something wrong
        bad_data = {
            "id": "evt-2",
            "event_type": "test_event",
            "session_id": "sess-1",
            "prompt_id": "",
            "payload": rows[2]["payload"],
            "timestamp": "2026-02-24T00:00:00+00:00",
            "prev_hash": "0000000000000000",  # wrong link
            "hash": rows[2]["hash"],
        }
        tampered = MagicMock()
        tampered.__getitem__ = lambda self, key: bad_data[key]
        rows[2] = tampered

        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = rows
        result = verify_audit_chain(db)
        assert result.valid is False
        assert result.first_break_position == 2
        assert any("prev_hash mismatch" in e for e in result.errors)

    def test_deleted_event_gap(self):
        """Deleting an event from the middle should break the chain."""
        rows = _build_chain(count=4)
        # Remove event #1 — event #2 prev_hash won't match event #0's hash
        del rows[1]

        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = rows
        result = verify_audit_chain(db)
        assert result.valid is False
        assert len(result.errors) >= 1

    def test_session_scoped_skips_prev_hash_check(self):
        """Session-scoped verification skips prev_hash linkage check."""
        rows = _build_chain(count=3)
        # Force wrong prev_hash on event #1 — session scope should skip linkage
        bad_data = {
            "id": "evt-1",
            "event_type": "test_event",
            "session_id": "sess-1",
            "prompt_id": "",
            "payload": rows[1]["payload"],
            "timestamp": "2026-02-24T00:00:00+00:00",
            "prev_hash": "wrong-link",
            "hash": rows[1]["hash"],  # This will also mismatch due to prev_hash in hash input
        }
        tampered = MagicMock()
        tampered.__getitem__ = lambda self, key: bad_data[key]
        rows[1] = tampered

        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = rows
        result = verify_audit_chain(db, session_id="sess-1")
        # Hash mismatch still detected (prev_hash is part of hash input),
        # but no "prev_hash mismatch" error
        assert any("hash mismatch" in e for e in result.errors)
        assert not any("prev_hash mismatch" in e for e in result.errors)

    def test_multiple_errors_all_reported(self):
        """All errors in the chain should be reported."""
        rows = _build_chain(count=4)
        # Tamper events #1 and #3
        for idx in (1, 3):
            bad_data = {
                "id": f"evt-{idx}",
                "event_type": "test_event",
                "session_id": "sess-1",
                "prompt_id": "",
                "payload": '{"tampered":true}',
                "timestamp": "2026-02-24T00:00:00+00:00",
                "prev_hash": rows[idx]["prev_hash"],
                "hash": rows[idx]["hash"],
            }
            tampered = MagicMock()
            tampered.__getitem__ = lambda self, key, d=bad_data: d[key]
            rows[idx] = tampered

        db = MagicMock()
        db._db.execute.return_value.fetchall.return_value = rows
        result = verify_audit_chain(db)
        assert result.valid is False
        assert len(result.errors) >= 2
        assert result.first_break_event_id == "evt-1"


# ---------------------------------------------------------------------------
# Tests — format_verify_result
# ---------------------------------------------------------------------------


class TestFormatVerifyResult:
    def test_valid_result(self):
        result = AuditVerifyResult(valid=True, total_events=10, verified_events=10)
        text = format_verify_result(result)
        assert "VALID" in text
        assert "10" in text

    def test_broken_result(self):
        result = AuditVerifyResult(
            valid=False,
            total_events=5,
            verified_events=5,
            errors=["Event #2 (evt-2): prev_hash mismatch"],
            first_break_event_id="evt-2",
            first_break_position=2,
        )
        text = format_verify_result(result)
        assert "BROKEN" in text
        assert "1 error" in text
        assert "evt-2" in text

    def test_session_scoped_label(self):
        result = AuditVerifyResult(valid=True, total_events=3, verified_events=3)
        text = format_verify_result(result, session_id="abc123def456")
        assert "session abc123def456" in text

    def test_truncated_errors(self):
        errors = [f"error-{i}" for i in range(15)]
        result = AuditVerifyResult(valid=False, total_events=15, verified_events=15, errors=errors)
        text = format_verify_result(result)
        assert "and 5 more" in text


# ---------------------------------------------------------------------------
# Tests — CLI command
# ---------------------------------------------------------------------------


class TestAuditVerifyCLI:
    def test_command_exists(self):
        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_group

        runner = CliRunner()
        result = runner.invoke(audit_group, ["verify", "--help"])
        assert result.exit_code == 0
        assert "hash chain" in result.output.lower()

    @patch("atlasbridge.core.config.load_config")
    def test_no_database(self, mock_config):
        from pathlib import Path
        from unittest.mock import PropertyMock

        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_verify

        cfg = MagicMock()
        type(cfg).db_path = PropertyMock(return_value=Path("/nonexistent/db.sqlite"))
        mock_config.return_value = cfg

        runner = CliRunner()
        result = runner.invoke(audit_verify, [])
        assert result.exit_code == 0
        assert "nothing to verify" in result.output.lower()

    @patch("atlasbridge.core.config.load_config")
    def test_valid_chain_json(self, mock_config, tmp_path):
        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_verify
        from atlasbridge.core.store.database import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.connect()
        # Write a few events via the real writer
        from atlasbridge.core.audit.writer import AuditWriter

        writer = AuditWriter(db)
        writer.session_started("s1", "claude", ["claude"])
        writer.prompt_detected("s1", "p1", "yes_no", "high")

        cfg = MagicMock()
        type(cfg).db_path = MagicMock(return_value=db_path)
        cfg.db_path = db_path
        mock_config.return_value = cfg

        runner = CliRunner()
        result = runner.invoke(audit_verify, ["--json"])
        assert result.exit_code == 0
        import json as json_mod

        data = json_mod.loads(result.output)
        assert data["valid"] is True
        assert data["total_events"] == 2
        db.close()

    @patch("atlasbridge.core.config.load_config")
    def test_valid_chain_text(self, mock_config, tmp_path):
        from click.testing import CliRunner

        from atlasbridge.cli._audit_cmd import audit_verify
        from atlasbridge.core.store.database import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.connect()
        from atlasbridge.core.audit.writer import AuditWriter

        writer = AuditWriter(db)
        writer.session_started("s1", "claude", ["claude"])

        cfg = MagicMock()
        cfg.db_path = db_path
        mock_config.return_value = cfg

        runner = CliRunner()
        result = runner.invoke(audit_verify, [])
        assert result.exit_code == 0
        assert "VALID" in result.output
        db.close()
