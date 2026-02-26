"""Integration tests for the edition contract — route availability and method constraints.

These tests verify the formal contract between Core and Enterprise editions:
- Core routes are exactly the frozen set
- Enterprise routes are exactly the frozen set
- Core has no mutating routes (GET-only)
- Enterprise includes exactly one POST (integrity verify)
"""

from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("fastapi")


from tests.safety.test_dashboard_route_freeze import (  # noqa: E402
    ALL_ROUTES,
    CORE_ROUTES,
    ENTERPRISE_ONLY_ROUTES,
    _get_app_routes,
)


def _minimal_db(tmp_path, name: str = "test.db") -> object:
    """Return (db_path, trace_path) for a minimal test DB."""
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
    return db_path, trace_path


@pytest.fixture
def core_app(tmp_path, monkeypatch):
    from atlasbridge.dashboard.app import create_app

    monkeypatch.setenv("ATLASBRIDGE_EDITION", "core")
    db_path, trace_path = _minimal_db(tmp_path)
    return create_app(db_path=db_path, trace_path=trace_path)


@pytest.fixture
def enterprise_app(tmp_path, monkeypatch):
    from atlasbridge.dashboard.app import create_app

    monkeypatch.setenv("ATLASBRIDGE_EDITION", "enterprise")
    db_path, trace_path = _minimal_db(tmp_path)
    return create_app(db_path=db_path, trace_path=trace_path)


class TestCoreEditionContract:
    """Core edition routes must match the frozen set exactly."""

    def test_core_routes_exactly_match_frozen_set(self, core_app) -> None:
        actual = _get_app_routes(core_app)
        assert actual == CORE_ROUTES, (
            f"Core route mismatch. Extra: {actual - CORE_ROUTES}. Missing: {CORE_ROUTES - actual}."
        )

    def test_enterprise_routes_not_present_on_core(self, core_app) -> None:
        actual = _get_app_routes(core_app)
        leaked = ENTERPRISE_ONLY_ROUTES & actual
        assert not leaked, f"Enterprise routes leaked into Core: {leaked}"

    def test_core_route_methods_are_readonly(self, core_app) -> None:
        """Core edition must have no mutating routes (POST/PUT/DELETE/PATCH)."""
        actual = _get_app_routes(core_app)
        mutating = {
            (method, path)
            for (method, path) in actual
            if method in ("POST", "PUT", "DELETE", "PATCH")
        }
        assert not mutating, f"Core has mutating routes: {mutating}"


class TestEnterpriseEditionContract:
    """Enterprise edition routes must match the frozen set exactly."""

    def test_enterprise_routes_exactly_match_frozen_set(self, enterprise_app) -> None:
        actual = _get_app_routes(enterprise_app)
        assert actual == ALL_ROUTES, (
            f"Enterprise route mismatch. Extra: {actual - ALL_ROUTES}. "
            f"Missing: {ALL_ROUTES - actual}."
        )

    def test_enterprise_includes_all_core_routes(self, enterprise_app) -> None:
        actual = _get_app_routes(enterprise_app)
        missing = CORE_ROUTES - actual
        assert not missing, f"Core routes missing from Enterprise: {missing}"

    def test_enterprise_route_methods_include_post(self, enterprise_app) -> None:
        actual = _get_app_routes(enterprise_app)
        assert ("POST", "/api/integrity/verify") in actual


class TestAuthorityCapabilities:
    """Authority capabilities must be denied on Core regardless of authority_mode."""

    def test_authority_capabilities_denied_on_core(self) -> None:
        from atlasbridge.enterprise.capability import CAPABILITIES, CapabilityClass
        from atlasbridge.enterprise.edition import AuthorityMode, Edition
        from atlasbridge.enterprise.registry import FeatureRegistry

        edition = Edition.CORE
        authority_mode = AuthorityMode.READONLY
        for cap_id, spec in CAPABILITIES.items():
            if spec.capability_class == CapabilityClass.AUTHORITY:
                decision = FeatureRegistry.is_allowed(edition, authority_mode, cap_id)
                assert not decision.allowed, (
                    f"AUTHORITY capability {cap_id!r} must be denied on CORE"
                )
                assert decision.reason_code == "EDITION_DENY", (
                    f"Expected EDITION_DENY for {cap_id!r} on CORE, got {decision.reason_code}"
                )

    def test_tooling_capabilities_allowed_on_core(self) -> None:
        from atlasbridge.enterprise.capability import CAPABILITIES, CapabilityClass
        from atlasbridge.enterprise.edition import AuthorityMode, Edition
        from atlasbridge.enterprise.registry import FeatureRegistry

        edition = Edition.CORE
        authority_mode = AuthorityMode.READONLY
        for cap_id, spec in CAPABILITIES.items():
            if spec.capability_class == CapabilityClass.TOOLING:
                decision = FeatureRegistry.is_allowed(edition, authority_mode, cap_id)
                assert decision.allowed, f"TOOLING capability {cap_id!r} must be allowed on CORE"
