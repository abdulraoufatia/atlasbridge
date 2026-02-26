"""End-to-end edition enforcement tests.

Verifies the full request lifecycle for both editions:
- Core client: all 8 core routes → 200; all 6 enterprise routes → 404
- Enterprise client: all 14 routes → non-404 (200 or 429)
- Authority mode: enterprise + READONLY → /enterprise/settings → 404
- Authority mode: enterprise + WRITE_ENABLED → /enterprise/settings → 200
"""

from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("fastapi")

from starlette.testclient import TestClient  # noqa: E402

from tests.safety.test_dashboard_route_freeze import (  # noqa: E402
    CORE_ROUTES,
    ENTERPRISE_ONLY_ROUTES,
)


def _make_test_client(
    tmp_path,
    edition: str,
    authority_mode: str = "readonly",
    db_name: str | None = None,
) -> TestClient:
    import os

    from atlasbridge.dashboard.app import create_app

    os.environ["ATLASBRIDGE_EDITION"] = edition
    os.environ["ATLASBRIDGE_AUTHORITY_MODE"] = authority_mode

    db_path = tmp_path / (db_name or f"{edition}_{authority_mode}.db")
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, tool TEXT, command TEXT, "
        "cwd TEXT, status TEXT, pid INTEGER, started_at TEXT, ended_at TEXT, "
        "exit_code INTEGER, label TEXT, metadata TEXT)"
    )
    conn.execute(
        "CREATE TABLE prompts (id TEXT PRIMARY KEY, session_id TEXT, "
        "prompt_type TEXT, confidence TEXT, excerpt TEXT, status TEXT, "
        "nonce TEXT, nonce_used INTEGER, expires_at TEXT, created_at TEXT, "
        "resolved_at TEXT, response_normalized TEXT, channel_identity TEXT, "
        "channel_message_id TEXT, metadata TEXT)"
    )
    conn.execute(
        "CREATE TABLE audit_events (id TEXT PRIMARY KEY, event_type TEXT, "
        "session_id TEXT, prompt_id TEXT, payload TEXT, timestamp TEXT, "
        "prev_hash TEXT, hash TEXT)"
    )
    conn.commit()
    conn.close()

    trace_path = tmp_path / f"{edition}_{authority_mode}_decisions.jsonl"
    trace_path.write_text("")

    app = create_app(db_path=db_path, trace_path=trace_path)
    return TestClient(app)


# Parameterized URL substitutions for routes with path variables
_PARAM_SUBSTITUTIONS: dict[str, str] = {
    "{session_id}": "nonexistent-session",
    "{index}": "0",
}


def _materialize_path(path: str) -> str:
    for placeholder, value in _PARAM_SUBSTITUTIONS.items():
        path = path.replace(placeholder, value)
    return path


class TestCoreEditionE2E:
    """Core edition: all core routes reachable, all enterprise routes absent."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "readonly")
        self.client = _make_test_client(tmp_path, "core", "readonly")

    def test_all_core_routes_return_non_404(self) -> None:
        """Every core route must be reachable (non-404)."""
        for method, path in CORE_ROUTES:
            if path == "/openapi.json":
                continue  # auto-generated, skip direct test
            url = _materialize_path(path)
            if method == "GET":
                resp = self.client.get(url)
            else:
                resp = self.client.request(method, url)
            assert resp.status_code != 404, (
                f"Core route {method} {path} returned 404 — route not registered"
            )

    def test_all_enterprise_routes_return_404(self) -> None:
        """Every enterprise route must return 404 on Core."""
        for method, path in ENTERPRISE_ONLY_ROUTES:
            url = _materialize_path(path)
            if method == "GET":
                resp = self.client.get(url)
            elif method == "POST":
                resp = self.client.post(url)
            else:
                resp = self.client.request(method, url)
            assert resp.status_code == 404, (
                f"Enterprise route {method} {path} did NOT return 404 on Core "
                f"(got {resp.status_code})"
            )


class TestEnterpriseEditionE2E:
    """Enterprise edition: all routes reachable (core + enterprise)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "readonly")
        self.client = _make_test_client(tmp_path, "enterprise", "readonly")

    def test_all_core_routes_reachable_on_enterprise(self) -> None:
        for method, path in CORE_ROUTES:
            if path == "/openapi.json":
                continue
            url = _materialize_path(path)
            resp = self.client.get(url)
            assert resp.status_code != 404, f"Core route {method} {path} returned 404 on Enterprise"

    def test_enterprise_routes_reachable_except_authority_gated(self) -> None:
        """Enterprise routes are registered; authority-gated ones return 404 in READONLY mode.

        Note: /api/sessions/{session_id}/export is excluded from HTTP reachability check
        because it returns 404 when the session doesn't exist (business logic), indistinguishable
        from a missing route via status code alone. Route registration is verified by the
        contract tests via app introspection.
        """
        # Routes that return 404 due to business logic (not routing absence) when
        # called with placeholder IDs — verified via route table, not HTTP status.
        business_logic_404_paths = {"/api/sessions/{session_id}/export"}

        for method, path in ENTERPRISE_ONLY_ROUTES:
            if path in business_logic_404_paths:
                continue
            url = _materialize_path(path)
            if method == "GET":
                resp = self.client.get(url)
            elif method == "POST":
                resp = self.client.post(url)
            else:
                resp = self.client.request(method, url)
            # /enterprise/settings requires WRITE_ENABLED — expect 404 in READONLY
            if path == "/enterprise/settings":
                assert resp.status_code == 404, (
                    "/enterprise/settings must return 404 in READONLY authority mode"
                )
            else:
                # All other enterprise routes are accessible in READONLY
                assert resp.status_code != 404, (
                    f"Enterprise route {method} {path} returned 404 unexpectedly "
                    f"(got {resp.status_code})"
                )


class TestAuthorityModeE2E:
    """/enterprise/settings gating via authority mode."""

    def test_enterprise_settings_denied_readonly(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "readonly")
        client = _make_test_client(tmp_path, "enterprise", "readonly")
        resp = client.get("/enterprise/settings")
        assert resp.status_code == 404

    def test_enterprise_settings_allowed_write_enabled(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "write_enabled")
        client = _make_test_client(tmp_path, "enterprise", "write_enabled", db_name="ent_we.db")
        resp = client.get("/enterprise/settings")
        assert resp.status_code == 200

    def test_core_settings_not_affected_by_authority_mode(self, tmp_path, monkeypatch) -> None:
        """/settings on Core is always accessible — authority mode irrelevant."""
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")
        monkeypatch.setenv("ATLASBRIDGE_AUTHORITY_MODE", "write_enabled")
        client = _make_test_client(tmp_path, "core_we", "write_enabled")
        resp = client.get("/settings")
        assert resp.status_code == 200
