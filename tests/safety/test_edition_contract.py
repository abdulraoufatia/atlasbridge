"""Safety tests: Edition contract enforcement.

Parametrized tests verifying that the FeatureRegistry enforces the
edition/authority-mode matrix correctly across all capabilities.

Every TOOLING capability must be allowed in ALL edition+mode combinations.
Every AUTHORITY capability must be denied unless ENTERPRISE + WRITE_ENABLED.
"""

from __future__ import annotations

import pytest

from atlasbridge.enterprise.capability import CAPABILITIES, CapabilityClass
from atlasbridge.enterprise.edition import AuthorityMode, Edition
from atlasbridge.enterprise.guard import FeatureUnavailableError, require_capability
from atlasbridge.enterprise.registry import FeatureRegistry, ReasonCode

TOOLING_CAPS = [cap for cap, cls in CAPABILITIES.items() if cls == CapabilityClass.TOOLING]
AUTHORITY_CAPS = [cap for cap, cls in CAPABILITIES.items() if cls == CapabilityClass.AUTHORITY]

ALL_EDITION_MODE_COMBOS = [
    (Edition.CORE, AuthorityMode.READONLY),
    (Edition.CORE, AuthorityMode.WRITE_ENABLED),
    (Edition.ENTERPRISE, AuthorityMode.READONLY),
    (Edition.ENTERPRISE, AuthorityMode.WRITE_ENABLED),
]


# ---------------------------------------------------------------------------
# Contract: TOOLING allowed everywhere
# ---------------------------------------------------------------------------


class TestToolingAllowedEverywhere:
    """TOOLING capabilities must be allowed in ALL edition+mode combinations."""

    @pytest.mark.safety
    @pytest.mark.parametrize("cap_id", TOOLING_CAPS)
    @pytest.mark.parametrize("edition,authority_mode", ALL_EDITION_MODE_COMBOS)
    def test_tooling_always_allowed(
        self,
        edition: Edition,
        authority_mode: AuthorityMode,
        cap_id: str,
    ) -> None:
        d = FeatureRegistry.is_allowed(edition, authority_mode, cap_id)
        assert d.allowed is True, (
            f"{cap_id} denied on {edition.value}/{authority_mode.value}: {d.reason_code}"
        )


# ---------------------------------------------------------------------------
# Contract: CORE denies ALL AUTHORITY capabilities
# ---------------------------------------------------------------------------


class TestCoreDeniesAuthority:
    """CORE edition must deny every AUTHORITY capability regardless of mode."""

    @pytest.mark.safety
    @pytest.mark.parametrize("cap_id", AUTHORITY_CAPS)
    def test_core_readonly_denies(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap_id)
        assert d.allowed is False
        assert d.reason_code == ReasonCode.EDITION_DENY

    @pytest.mark.safety
    @pytest.mark.parametrize("cap_id", AUTHORITY_CAPS)
    def test_core_write_enabled_still_denies(self, cap_id: str) -> None:
        """CORE + WRITE_ENABLED must still deny AUTHORITY — edition gate first."""
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.WRITE_ENABLED, cap_id)
        assert d.allowed is False
        assert d.reason_code == ReasonCode.EDITION_DENY


# ---------------------------------------------------------------------------
# Contract: ENTERPRISE + READONLY denies AUTHORITY
# ---------------------------------------------------------------------------


class TestEnterpriseReadonlyDeniesAuthority:
    """ENTERPRISE + READONLY must deny all AUTHORITY capabilities."""

    @pytest.mark.safety
    @pytest.mark.parametrize("cap_id", AUTHORITY_CAPS)
    def test_enterprise_readonly_denies(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.ENTERPRISE, AuthorityMode.READONLY, cap_id)
        assert d.allowed is False
        assert d.reason_code == ReasonCode.AUTHORITY_MODE_REQUIRED


# ---------------------------------------------------------------------------
# Contract: ENTERPRISE + WRITE_ENABLED allows AUTHORITY
# ---------------------------------------------------------------------------


class TestEnterpriseWriteEnabledAllowsAuthority:
    """ENTERPRISE + WRITE_ENABLED must allow all AUTHORITY capabilities."""

    @pytest.mark.safety
    @pytest.mark.parametrize("cap_id", AUTHORITY_CAPS)
    def test_enterprise_write_enabled_allows(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.ENTERPRISE, AuthorityMode.WRITE_ENABLED, cap_id)
        assert d.allowed is True
        assert d.reason_code == ReasonCode.ALLOWED


# ---------------------------------------------------------------------------
# Contract: Fingerprints are stable
# ---------------------------------------------------------------------------


class TestFingerprintContract:
    """Decision fingerprints must be deterministic and stable."""

    @pytest.mark.safety
    @pytest.mark.parametrize("cap_id", list(CAPABILITIES.keys())[:5])
    def test_fingerprint_stable_across_calls(self, cap_id: str) -> None:
        d1 = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap_id)
        d2 = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap_id)
        assert d1.decision_fingerprint == d2.decision_fingerprint

    @pytest.mark.safety
    def test_capabilities_hash_stable(self) -> None:
        h1 = FeatureRegistry.capabilities_hash(Edition.CORE, AuthorityMode.READONLY)
        h2 = FeatureRegistry.capabilities_hash(Edition.CORE, AuthorityMode.READONLY)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Contract: Deny emits audit callback
# ---------------------------------------------------------------------------


class TestDenyEmitsAudit:
    """require_capability must invoke audit_callback on deny."""

    @pytest.mark.safety
    def test_deny_invokes_audit_callback(self) -> None:
        calls: list[tuple] = []

        def cb(event_type: str, payload: dict) -> None:
            calls.append((event_type, payload))

        with pytest.raises(FeatureUnavailableError):
            require_capability(
                Edition.CORE,
                AuthorityMode.READONLY,
                "authority.rbac",
                audit_callback=cb,
            )
        assert len(calls) == 1
        assert calls[0][0] == "capability.denied"
        assert calls[0][1]["capability_id"] == "authority.rbac"

    @pytest.mark.safety
    def test_allow_does_not_invoke_audit_callback(self) -> None:
        calls: list[tuple] = []

        def cb(event_type: str, payload: dict) -> None:
            calls.append((event_type, payload))

        require_capability(
            Edition.CORE,
            AuthorityMode.READONLY,
            "tooling.dashboard_read",
            audit_callback=cb,
        )
        assert len(calls) == 0


# ---------------------------------------------------------------------------
# Contract: No mutation routes in CORE dashboard
# ---------------------------------------------------------------------------


class TestNoMutationRoutes:
    """CORE dashboard must have no POST/PUT/DELETE routes that mutate data."""

    @pytest.mark.safety
    def test_no_write_routes_except_integrity_verify(self) -> None:
        """Only /api/integrity/verify is POST. No PUT/DELETE routes exist."""
        pytest.importorskip("fastapi")
        from atlasbridge.dashboard.app import create_app

        app = create_app()
        mutation_routes: list[tuple[str, str]] = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method in ("POST", "PUT", "DELETE", "PATCH"):
                        mutation_routes.append((method, route.path))

        # Only /api/integrity/verify is allowed as POST (read-only check)
        allowed_mutations = {("POST", "/api/integrity/verify")}
        unexpected = set(mutation_routes) - allowed_mutations
        assert not unexpected, f"Unexpected mutation routes: {unexpected}"
