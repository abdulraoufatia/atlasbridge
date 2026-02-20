"""Unit tests for aegis.audit.writer — AuditWriter and hash chain."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from aegis.audit.writer import AuditWriter, verify_chain
from aegis.store.models import AuditEvent


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "audit.log"


@pytest.fixture
def writer(log_path: Path) -> AuditWriter:
    w = AuditWriter(log_path)
    w.open()
    yield w
    w.close()


class TestAuditWriter:
    def test_creates_file(self, writer: AuditWriter, log_path: Path) -> None:
        assert log_path.exists()

    def test_write_produces_json_line(self, writer: AuditWriter, log_path: Path) -> None:
        ev = AuditEvent(id=str(uuid.uuid4()), event_type="test")
        writer.write(ev)
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["event_type"] == "test"

    def test_hash_is_populated(self, writer: AuditWriter, log_path: Path) -> None:
        ev = AuditEvent(id=str(uuid.uuid4()), event_type="test")
        writer.write(ev)
        obj = json.loads(log_path.read_text().strip())
        assert len(obj["hash"]) == 64  # SHA-256 hex

    def test_first_entry_prev_hash_is_genesis(self, writer: AuditWriter, log_path: Path) -> None:
        ev = AuditEvent(id=str(uuid.uuid4()), event_type="test")
        writer.write(ev)
        obj = json.loads(log_path.read_text().strip())
        assert obj["prev_hash"] == "genesis"

    def test_chained_prev_hash(self, writer: AuditWriter, log_path: Path) -> None:
        ev1 = AuditEvent(id=str(uuid.uuid4()), event_type="first")
        ev2 = AuditEvent(id=str(uuid.uuid4()), event_type="second")
        writer.write(ev1)
        writer.write(ev2)
        lines = log_path.read_text().strip().splitlines()
        obj1 = json.loads(lines[0])
        obj2 = json.loads(lines[1])
        assert obj2["prev_hash"] == obj1["hash"]

    def test_write_event_convenience(self, writer: AuditWriter, log_path: Path) -> None:
        writer.write_event(
            str(uuid.uuid4()), "session_started", session_id="abc", data={"tool": "claude"}
        )
        obj = json.loads(log_path.read_text().strip())
        assert obj["event_type"] == "session_started"
        assert obj["session_id"] == "abc"

    def test_chain_survives_reopen(self, log_path: Path) -> None:
        """A new AuditWriter should continue the chain from the last hash."""
        w1 = AuditWriter(log_path)
        w1.open()
        w1.write(AuditEvent(id=str(uuid.uuid4()), event_type="first"))
        w1.close()

        w2 = AuditWriter(log_path)
        w2.open()
        w2.write(AuditEvent(id=str(uuid.uuid4()), event_type="second"))
        w2.close()

        ok, count, err = verify_chain(log_path)
        assert ok, err
        assert count == 2


class TestVerifyChain:
    def test_valid_chain(self, writer: AuditWriter, log_path: Path) -> None:
        for _ in range(5):
            writer.write(AuditEvent(id=str(uuid.uuid4()), event_type="ev"))
        ok, count, err = verify_chain(log_path)
        assert ok, err
        assert count == 5

    def test_tampered_chain(self, writer: AuditWriter, log_path: Path) -> None:
        for _ in range(3):
            writer.write(AuditEvent(id=str(uuid.uuid4()), event_type="ev"))
        writer.close()

        # Tamper: replace second line's event_type
        lines = log_path.read_text().splitlines()
        obj = json.loads(lines[1])
        obj["event_type"] = "TAMPERED"
        lines[1] = json.dumps(obj)
        log_path.write_text("\n".join(lines) + "\n")

        ok, _count, err = verify_chain(log_path)
        assert not ok
        assert err is not None

    def test_empty_log(self, log_path: Path) -> None:
        log_path.touch()
        ok, count, err = verify_chain(log_path)
        assert ok
        assert count == 0

    def test_missing_log(self, tmp_path: Path) -> None:
        ok, count, err = verify_chain(tmp_path / "no_such_file.log")
        assert not ok
