"""Safety guard: Core edition has no mutating routes. Enterprise mutation scope is bounded.

Core must be strictly read-only (GET only).
Enterprise may have exactly one POST route: /api/integrity/verify.
No PUT, DELETE, or PATCH routes may exist on either edition.
"""

from __future__ import annotations

import sqlite3

import pytest


def _get_app_routes(app) -> set[tuple[str, str]]:
    routes = set()
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    routes.add((method, route.path))
    return routes


def _make_app(tmp_path, edition: str, name: str = "test.db"):
    pytest.importorskip("fastapi")
    import os

    from atlasbridge.dashboard.app import create_app

    os.environ["ATLASBRIDGE_EDITION"] = edition

    db_path = tmp_path / name
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
    trace_path = tmp_path / "decisions.jsonl"
    trace_path.write_text("")
    return create_app(db_path=db_path, trace_path=trace_path)


class TestCoreMutationDenial:
    """Core edition must have zero mutating HTTP methods."""

    @pytest.fixture(autouse=True)
    def core_app(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")
        self._app = _make_app(tmp_path, "core")

    def test_core_has_no_post_routes(self) -> None:
        routes = _get_app_routes(self._app)
        post_routes = {(m, p) for (m, p) in routes if m == "POST"}
        assert not post_routes, f"Core has unexpected POST routes: {post_routes}"

    def test_core_has_no_put_routes(self) -> None:
        routes = _get_app_routes(self._app)
        assert not {(m, p) for (m, p) in routes if m == "PUT"}

    def test_core_has_no_delete_routes(self) -> None:
        routes = _get_app_routes(self._app)
        assert not {(m, p) for (m, p) in routes if m == "DELETE"}

    def test_core_has_no_patch_routes(self) -> None:
        routes = _get_app_routes(self._app)
        assert not {(m, p) for (m, p) in routes if m == "PATCH"}


class TestEnterpriseMutationScope:
    """Enterprise POST routes must be exactly the frozen set."""

    @pytest.fixture(autouse=True)
    def enterprise_app(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
        self._app = _make_app(tmp_path, "enterprise")

    def test_enterprise_only_post_is_integrity_verify(self) -> None:
        routes = _get_app_routes(self._app)
        post_routes = {(m, p) for (m, p) in routes if m == "POST"}
        assert post_routes == {("POST", "/api/integrity/verify")}, (
            f"Enterprise POST routes changed: {post_routes}. "
            "Update this test if adding a POST route is intentional."
        )

    def test_enterprise_has_no_put_routes(self) -> None:
        routes = _get_app_routes(self._app)
        assert not {(m, p) for (m, p) in routes if m == "PUT"}

    def test_enterprise_has_no_delete_routes(self) -> None:
        routes = _get_app_routes(self._app)
        assert not {(m, p) for (m, p) in routes if m == "DELETE"}

    def test_enterprise_has_no_patch_routes(self) -> None:
        routes = _get_app_routes(self._app)
        assert not {(m, p) for (m, p) in routes if m == "PATCH"}

    def test_integrity_verify_post_requires_enterprise(self, tmp_path, monkeypatch) -> None:
        """POST /api/integrity/verify must not exist on Core."""
        from starlette.testclient import TestClient

        monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")
        app = _make_app(tmp_path, "core", name="core_verify.db")
        client = TestClient(app)
        resp = client.post("/api/integrity/verify")
        assert resp.status_code == 404
