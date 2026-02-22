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


class TestRiskFlagEnforcement:
    """Non-loopback binding requires explicit --i-understand-risk flag."""

    def test_default_binding_is_loopback(self):
        """Default host must be 127.0.0.1 — no flag needed."""
        from atlasbridge.cli._dashboard import dashboard_start

        params = {p.name: p.default for p in dashboard_start.params}
        assert params["host"] == "127.0.0.1"

    def test_start_server_rejects_non_loopback_without_flag(self):
        """start_server() must raise ValueError for non-loopback without allow_non_loopback."""
        pytest.importorskip("fastapi")
        from atlasbridge.dashboard.app import start_server

        with pytest.raises(ValueError, match="loopback"):
            start_server(host="0.0.0.0")

    def test_start_server_allows_non_loopback_with_flag(self):
        """start_server() must allow non-loopback when allow_non_loopback=True."""
        pytest.importorskip("fastapi")
        from unittest.mock import MagicMock, patch

        # uvicorn is imported inside start_server, so patch at module level
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            from atlasbridge.dashboard.app import start_server

            start_server(host="0.0.0.0", allow_non_loopback=True, open_browser=False)
            mock_uvicorn.run.assert_called_once()


class TestNoMutationRoutes:
    """Dashboard must not expose any mutation endpoints (PUT/DELETE/PATCH)."""

    def test_no_put_delete_patch_routes(self):
        """Introspect app routes — only GET and POST allowed."""
        pytest.importorskip("fastapi")
        from atlasbridge.dashboard.app import create_app

        app = create_app()
        forbidden_methods = {"PUT", "DELETE", "PATCH"}
        for route in app.routes:
            if hasattr(route, "methods"):
                overlap = forbidden_methods & route.methods
                assert not overlap, (
                    f"Route {getattr(route, 'path', '?')} exposes forbidden methods: {overlap}"
                )
