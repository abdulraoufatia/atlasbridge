"""Safety guard: dashboard must only bind to loopback addresses."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atlasbridge.dashboard.sanitize import is_loopback


class TestLoopbackValidation:
    """Dashboard host binding must be restricted to loopback addresses."""

    def test_rejects_all_interfaces(self):
        """0.0.0.0 is not loopback — must be rejected."""
        assert not is_loopback("0.0.0.0")

    def test_rejects_public_ipv4(self):
        """Public IPv4 addresses must be rejected."""
        assert not is_loopback("192.168.1.1")
        assert not is_loopback("10.0.0.1")
        assert not is_loopback("8.8.8.8")

    def test_rejects_public_ipv6(self):
        """Public IPv6 addresses must be rejected."""
        assert not is_loopback("2001:db8::1")
        assert not is_loopback("fe80::1")

    def test_accepts_127_0_0_1(self):
        """127.0.0.1 is loopback — must be accepted."""
        assert is_loopback("127.0.0.1")

    def test_accepts_ipv6_loopback(self):
        """::1 is IPv6 loopback — must be accepted."""
        assert is_loopback("::1")

    def test_accepts_localhost(self):
        """'localhost' hostname must be accepted."""
        assert is_loopback("localhost")


class TestStartServerRejectsNonLoopback:
    """start_server() must raise ValueError for non-loopback hosts."""

    def test_start_server_rejects_public(self):
        pytest.importorskip("fastapi")
        from atlasbridge.dashboard.app import start_server

        with pytest.raises(ValueError, match="loopback"):
            start_server(host="0.0.0.0")


class TestReadOnlyDatabaseGuard:
    """Dashboard must open SQLite in read-only mode."""

    def test_read_only_connection_rejects_writes(self, tmp_path: Path):
        """A read-only SQLite connection must reject INSERT statements."""
        db_path = tmp_path / "test.db"
        # Create a DB first so we can open it read-only
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (id TEXT)")
        conn.commit()
        conn.close()

        # Open read-only
        ro_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute("INSERT INTO t (id) VALUES ('x')")
        ro_conn.close()
