"""
Phase 1 Core Runtime Kernel tests.

Validates all Phase 1 exit criteria:
  A) Fresh install works (DB, adapters, doctor)
  B) Upgrade safety (schema versioning, auto-migration)
  C) Deterministic adapter registry
  D) Deterministic prompt correlation (no unknown prompt spam)
  E) Doctor is trustworthy (new checks: database, adapters)
  F) Clean console output (no deprecation warnings)
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch

from atlasbridge.core.store.database import Database
from atlasbridge.core.store.migrations import (
    LATEST_SCHEMA_VERSION,
    get_user_version,
)

# =====================================================================
# A) Fresh install — DB created cleanly, adapters available
# =====================================================================


class TestFreshInstall:
    def test_fresh_db_all_tables_and_indexes(self, tmp_path: Path) -> None:
        """A fresh Database.connect() creates all 4 tables + indexes."""
        db = Database(tmp_path / "fresh.db")
        db.connect()
        conn = db._db

        # Tables
        for table in ("sessions", "prompts", "replies", "audit_events"):
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            assert row is not None, f"table {table} missing"

        # Indexes
        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        idx_names = {r[0] for r in indexes}
        assert "idx_prompts_session_status" in idx_names
        assert "idx_audit_timestamp" in idx_names

        db.close()

    def test_fresh_db_schema_version_is_latest(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "fresh.db")
        db.connect()
        assert get_user_version(db._db) == LATEST_SCHEMA_VERSION
        db.close()

    def test_fresh_db_full_crud_cycle(self, tmp_path: Path) -> None:
        """Full session → prompt → audit cycle works on fresh DB."""
        db = Database(tmp_path / "fresh.db")
        db.connect()

        sid = str(uuid.uuid4())
        db.save_session(sid, "claude", ["claude"], "/tmp", "test-label")

        pid = str(uuid.uuid4())
        db.save_prompt(pid, sid, "yes_no", "high", "Continue?", "nonce-1", "2099-12-31T23:59:59")

        db.append_audit_event("evt-1", "prompt_created", {"pid": pid}, session_id=sid)

        # Verify
        session = db.get_session(sid)
        assert session["label"] == "test-label"

        prompt = db.get_prompt(pid)
        assert prompt["status"] == "awaiting_reply"

        events = db.get_recent_audit_events(1)
        assert len(events) == 1
        assert events[0]["hash"] != ""  # hash chain populated

        db.close()


# =====================================================================
# B) Upgrade safety — old schema auto-migrates
# =====================================================================


_OLD_SCHEMA_V0 = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, tool TEXT, command TEXT, cwd TEXT,
    status TEXT DEFAULT 'starting', pid INTEGER,
    started_at TEXT DEFAULT (datetime('now')), ended_at TEXT, exit_code INTEGER
);
CREATE TABLE prompts (
    id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id),
    prompt_type TEXT, confidence TEXT, excerpt TEXT DEFAULT '',
    status TEXT DEFAULT 'created', nonce TEXT, nonce_used INTEGER DEFAULT 0,
    expires_at TEXT, created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT, response_normalized TEXT, channel_identity TEXT
);
CREATE TABLE replies (
    id TEXT PRIMARY KEY, prompt_id TEXT REFERENCES prompts(id),
    session_id TEXT, value TEXT, channel_identity TEXT, nonce TEXT
);
CREATE TABLE audit_events (
    id TEXT PRIMARY KEY, event_type TEXT,
    session_id TEXT DEFAULT '', prompt_id TEXT DEFAULT '',
    payload TEXT DEFAULT '{}'
);
"""


class TestUpgradeSafety:
    def test_v0_schema_auto_migrates(self, tmp_path: Path) -> None:
        """DB missing timestamp/hash columns auto-upgrades to latest."""
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_OLD_SCHEMA_V0)
        conn.close()

        db = Database(db_path)
        db.connect()  # should NOT raise

        # Verify new columns exist
        cols = {r[1] for r in db._db.execute("PRAGMA table_info(audit_events)").fetchall()}
        assert "timestamp" in cols
        assert "prev_hash" in cols
        assert "hash" in cols

        assert get_user_version(db._db) == LATEST_SCHEMA_VERSION
        db.close()

    def test_upgraded_db_preserves_data(self, tmp_path: Path) -> None:
        """Existing rows survive migration."""
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_OLD_SCHEMA_V0)
        conn.execute(
            "INSERT INTO sessions (id, tool, command, cwd, status) "
            "VALUES ('s1', 'claude', '[]', '/tmp', 'running')"
        )
        conn.commit()
        conn.close()

        db = Database(db_path)
        db.connect()
        row = db.get_session("s1")
        assert row is not None
        assert row["tool"] == "claude"
        db.close()

    def test_double_connect_is_idempotent(self, tmp_path: Path) -> None:
        """Connecting twice to the same DB is a no-op."""
        db_path = tmp_path / "idem.db"
        db = Database(db_path)
        db.connect()
        db.close()

        db2 = Database(db_path)
        db2.connect()
        assert get_user_version(db2._db) == LATEST_SCHEMA_VERSION
        db2.close()


# =====================================================================
# C) Deterministic adapter registry
# =====================================================================


class TestAdapterRegistry:
    def test_all_builtin_adapters_registered(self) -> None:
        import atlasbridge.adapters  # noqa: F401
        from atlasbridge.adapters.base import AdapterRegistry

        adapters = AdapterRegistry.list_all()
        assert len(adapters) >= 3
        assert "claude" in adapters
        assert "openai" in adapters
        assert "gemini" in adapters

    def test_get_unknown_falls_back_to_custom_adapter(self) -> None:
        """Unknown adapter names fall back to CustomCLIAdapter."""
        import atlasbridge.adapters  # noqa: F401
        from atlasbridge.adapters.base import AdapterRegistry

        adapter_cls = AdapterRegistry.get("nonexistent-adapter")
        assert adapter_cls is not None
        assert adapter_cls.tool_name == "custom"

    def test_adapter_classes_have_required_attributes(self) -> None:
        import atlasbridge.adapters  # noqa: F401
        from atlasbridge.adapters.base import AdapterRegistry

        for name, cls in AdapterRegistry.list_all().items():
            assert hasattr(cls, "tool_name"), f"{name} missing tool_name"
            assert hasattr(cls, "start_session"), f"{name} missing start_session"
            assert hasattr(cls, "inject_reply"), f"{name} missing inject_reply"


# =====================================================================
# D) Deterministic prompt correlation
# =====================================================================


class TestPromptCorrelation:
    def test_prompt_event_has_stable_ids(self) -> None:
        from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType

        e = PromptEvent.create(
            session_id="sess-1",
            prompt_type=PromptType.TYPE_YES_NO,
            confidence=Confidence.HIGH,
            excerpt="Continue?",
        )
        assert len(e.prompt_id) == 24  # secrets.token_hex(12)
        assert len(e.idempotency_key) == 16  # secrets.token_hex(8)
        assert e.timestamp != ""

    def test_db_decide_prompt_rejects_duplicate_nonce(self, tmp_path: Path) -> None:
        """Same nonce cannot be used twice (idempotency guard)."""
        db = Database(tmp_path / "dup.db")
        db.connect()

        sid = str(uuid.uuid4())
        db.save_session(sid, "claude", ["claude"], "/tmp")

        pid = str(uuid.uuid4())
        db.save_prompt(pid, sid, "yes_no", "high", "Continue?", "nonce-1", "2099-12-31T23:59:59")

        # First decide: succeeds
        result1 = db.decide_prompt(pid, "resolved", "telegram:123", "y", "nonce-1")
        assert result1 == 1

        # Second decide with same nonce: rejected
        result2 = db.decide_prompt(pid, "resolved", "telegram:123", "y", "nonce-1")
        assert result2 == 0

        db.close()

    def test_db_decide_prompt_rejects_expired(self, tmp_path: Path) -> None:
        """Expired prompts are rejected by decide_prompt."""
        db = Database(tmp_path / "expired.db")
        db.connect()

        sid = str(uuid.uuid4())
        db.save_session(sid, "claude", ["claude"], "/tmp")

        pid = str(uuid.uuid4())
        db.save_prompt(pid, sid, "yes_no", "high", "Continue?", "nonce-1", "2000-01-01T00:00:00")

        result = db.decide_prompt(pid, "resolved", "telegram:123", "y", "nonce-1")
        assert result == 0  # rejected — expired

        db.close()


# =====================================================================
# E) Doctor — new checks
# =====================================================================


class TestDoctorNewChecks:
    def test_check_database_no_db(self) -> None:
        from atlasbridge.cli._doctor import _check_database

        with patch("atlasbridge.core.config.atlasbridge_dir") as mock_dir:
            mock_dir.return_value = Path("/nonexistent/atlasbridge")
            result = _check_database()
            assert result["status"] == "pass"
            assert "no database yet" in result["detail"]

    def test_check_database_with_db(self, tmp_path: Path) -> None:
        from atlasbridge.cli._doctor import _check_database

        # Create a fresh DB
        db = Database(tmp_path / "atlasbridge.db")
        db.connect()
        db.close()

        with patch("atlasbridge.core.config.atlasbridge_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            result = _check_database()
            assert result["status"] == "pass"
            assert f"v{LATEST_SCHEMA_VERSION}" in result["detail"]

    def test_check_adapters_pass(self) -> None:
        from atlasbridge.cli._doctor import _check_adapters

        result = _check_adapters()
        assert result["status"] == "pass"
        assert "claude" in result["detail"]

    def test_check_database_old_version(self, tmp_path: Path) -> None:
        from atlasbridge.cli._doctor import _check_database

        # Create a DB with user_version=0
        db_path = tmp_path / "atlasbridge.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA user_version = 0")
        conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")
        conn.close()

        with patch("atlasbridge.core.config.atlasbridge_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            result = _check_database()
            assert result["status"] == "warn"
            assert "auto-migrate" in result["detail"]


# =====================================================================
# F) No deprecation warnings in core code
# =====================================================================


class TestNoDeprecations:
    def test_prompt_state_machine_no_utcnow(self) -> None:
        """PromptStateMachine uses datetime.now(UTC), not utcnow()."""
        from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType
        from atlasbridge.core.prompt.state import PromptStateMachine

        event = PromptEvent.create(
            session_id="sess-1",
            prompt_type=PromptType.TYPE_YES_NO,
            confidence=Confidence.HIGH,
            excerpt="Continue?",
        )
        sm = PromptStateMachine(event=event)
        # If utcnow() was used, expires_at would be naive (no tzinfo)
        assert sm.expires_at.tzinfo is not None
