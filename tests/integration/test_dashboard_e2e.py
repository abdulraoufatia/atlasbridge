"""Integration e2e tests for dashboard server — verifies loopback-only binding.

Tests that the dashboard:
1. Starts and serves on 127.0.0.1
2. Returns 200 for key routes (/, /api/stats, /api/sessions)
3. Rejects non-loopback binding without allow_non_loopback flag
4. Cleans up properly on shutdown
"""

from __future__ import annotations

import hashlib
import json
import socket
import sqlite3
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")
httpx = pytest.importorskip("httpx")


def _find_free_port() -> int:
    """Find a free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _create_test_db(tmp_path: Path) -> Path:
    """Create a minimal SQLite DB with schema and one session."""
    db_path = tmp_path / "e2e_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, tool TEXT NOT NULL DEFAULT '',
            command TEXT NOT NULL DEFAULT '', cwd TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'starting', pid INTEGER,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at TEXT, exit_code INTEGER,
            label TEXT NOT NULL DEFAULT '', metadata TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE TABLE prompts (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
            prompt_type TEXT NOT NULL, confidence TEXT NOT NULL,
            excerpt TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'created',
            nonce TEXT NOT NULL, nonce_used INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT, response_normalized TEXT,
            channel_identity TEXT, channel_message_id TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE TABLE replies (
            id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL REFERENCES prompts(id),
            session_id TEXT NOT NULL, value TEXT NOT NULL,
            channel_identity TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            nonce TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE audit_events (
            id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT '', prompt_id TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}',
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            prev_hash TEXT NOT NULL DEFAULT '', hash TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute(
        "INSERT INTO sessions (id, tool, command, cwd, status, started_at) "
        "VALUES ('sess-e2e', 'claude', '[\"claude\"]', '/tmp', 'running', '2025-01-15T10:00:00')"
    )
    conn.commit()
    conn.close()
    return db_path


def _create_test_trace(tmp_path: Path) -> Path:
    """Create a minimal JSONL trace file."""
    trace_path = tmp_path / "e2e_decisions.jsonl"
    entry = {
        "idempotency_key": "key-e2e",
        "action_type": "auto_respond",
        "prompt_type": "yes_no",
        "confidence": "high",
        "session_id": "sess-e2e",
        "rule_id": "rule-1",
        "timestamp": "2025-01-15T10:00:00",
        "prev_hash": "",
    }
    chain_input = (
        f"{entry['idempotency_key']}"
        f"{entry['action_type']}"
        f"{json.dumps(entry, separators=(',', ':'), sort_keys=True)}"
    )
    entry["hash"] = hashlib.sha256(chain_input.encode()).hexdigest()
    trace_path.write_text(json.dumps(entry) + "\n")
    return trace_path


class _ServerRunner:
    """Run uvicorn in a background thread with clean shutdown."""

    def __init__(self, app, host: str, port: int):
        self.config = uvicorn.Config(app, host=host, port=port, log_level="error")
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, timeout: float = 5.0):
        self.thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("Server failed to start within timeout")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5.0)


@pytest.fixture
def e2e_server(tmp_path):
    """Start a real dashboard server on a random loopback port."""
    from atlasbridge.dashboard.app import create_app

    db_path = _create_test_db(tmp_path)
    trace_path = _create_test_trace(tmp_path)
    app = create_app(db_path=db_path, trace_path=trace_path)
    port = _find_free_port()
    runner = _ServerRunner(app, "127.0.0.1", port)
    runner.start()
    yield f"http://127.0.0.1:{port}"
    runner.stop()


class TestDashboardE2EServer:
    """Verify the dashboard serves requests over HTTP on loopback."""

    def test_home_returns_200(self, e2e_server):
        resp = httpx.get(f"{e2e_server}/", timeout=5.0)
        assert resp.status_code == 200
        assert "READ-ONLY GOVERNANCE VIEW" in resp.text

    def test_api_stats_returns_json(self, e2e_server):
        resp = httpx.get(f"{e2e_server}/api/stats", timeout=5.0)
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert data["sessions"] >= 1

    def test_api_sessions_returns_data(self, e2e_server):
        resp = httpx.get(f"{e2e_server}/api/sessions", timeout=5.0)
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert "total" in data

    def test_session_detail_returns_200(self, e2e_server):
        resp = httpx.get(f"{e2e_server}/sessions/sess-e2e", timeout=5.0)
        assert resp.status_code == 200

    def test_traces_page_returns_200(self, e2e_server):
        resp = httpx.get(f"{e2e_server}/traces", timeout=5.0)
        assert resp.status_code == 200

    def test_integrity_page_returns_200(self, e2e_server):
        resp = httpx.get(f"{e2e_server}/integrity", timeout=5.0)
        assert resp.status_code == 200

    def test_nonexistent_session_returns_200_with_empty(self, e2e_server):
        resp = httpx.get(f"{e2e_server}/sessions/does-not-exist", timeout=5.0)
        assert resp.status_code == 200


class TestDashboardLoopbackBinding:
    """Verify the server only binds to loopback addresses."""

    def test_start_server_rejects_all_interfaces(self):
        from atlasbridge.dashboard.app import start_server

        with pytest.raises(ValueError, match="loopback"):
            start_server(host="0.0.0.0", open_browser=False)

    def test_start_server_rejects_public_ip(self):
        from atlasbridge.dashboard.app import start_server

        with pytest.raises(ValueError, match="loopback"):
            start_server(host="192.168.1.1", open_browser=False)

    def test_start_server_accepts_localhost(self, tmp_path):
        """Verify start_server accepts localhost (blocks, so test validation only)."""
        from atlasbridge.dashboard.sanitize import is_loopback

        assert is_loopback("127.0.0.1")
        assert is_loopback("localhost")
        assert is_loopback("::1")
        assert not is_loopback("0.0.0.0")
        assert not is_loopback("10.0.0.1")

    def test_server_not_accessible_on_non_loopback(self, e2e_server):
        """Verify the server is NOT listening on non-loopback interfaces."""
        # Extract port from the e2e_server URL
        port = int(e2e_server.rsplit(":", 1)[1])

        # Get all non-loopback IPs on this machine
        non_loopback_ips = []
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if ip != "127.0.0.1" and not ip.startswith("127."):
                    non_loopback_ips.append(ip)
        except socket.gaierror:
            pass

        # If we found non-loopback IPs, verify they can't connect
        for ip in non_loopback_ips[:1]:  # Test just the first one
            with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
                httpx.get(f"http://{ip}:{port}/", timeout=1.0)
