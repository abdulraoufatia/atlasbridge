"""Unit tests for FeatureRegistry — single enforcement point."""

from __future__ import annotations

import pytest

from atlasbridge.enterprise.capability import CAPABILITIES, CapabilityClass
from atlasbridge.enterprise.edition import AuthorityMode, Edition
from atlasbridge.enterprise.registry import (
    REGISTRY_VERSION,
    FeatureRegistry,
    ReasonCode,
)

# ---------------------------------------------------------------------------
# TOOLING capabilities — always allowed
# ---------------------------------------------------------------------------

TOOLING_CAPS = [cap for cap, cls in CAPABILITIES.items() if cls == CapabilityClass.TOOLING]
AUTHORITY_CAPS = [cap for cap, cls in CAPABILITIES.items() if cls == CapabilityClass.AUTHORITY]


class TestToolingAlwaysAllowed:
    """TOOLING capabilities are allowed on all editions and authority modes."""

    @pytest.mark.parametrize("cap_id", TOOLING_CAPS)
    def test_core_readonly(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap_id)
        assert d.allowed is True
        assert d.reason_code == ReasonCode.ALLOWED
        assert d.capability_class == "tooling"

    @pytest.mark.parametrize("cap_id", TOOLING_CAPS)
    def test_core_write_enabled(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.WRITE_ENABLED, cap_id)
        assert d.allowed is True

    @pytest.mark.parametrize("cap_id", TOOLING_CAPS)
    def test_enterprise_readonly(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.ENTERPRISE, AuthorityMode.READONLY, cap_id)
        assert d.allowed is True

    @pytest.mark.parametrize("cap_id", TOOLING_CAPS)
    def test_enterprise_write_enabled(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.ENTERPRISE, AuthorityMode.WRITE_ENABLED, cap_id)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# AUTHORITY capabilities — gated by edition + authority mode
# ---------------------------------------------------------------------------


class TestAuthorityGating:
    """AUTHORITY capabilities require ENTERPRISE + WRITE_ENABLED."""

    @pytest.mark.parametrize("cap_id", AUTHORITY_CAPS)
    def test_denied_on_core_readonly(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap_id)
        assert d.allowed is False
        assert d.reason_code == ReasonCode.EDITION_DENY
        assert d.capability_class == "authority"

    @pytest.mark.parametrize("cap_id", AUTHORITY_CAPS)
    def test_denied_on_core_write_enabled(self, cap_id: str) -> None:
        """CORE + WRITE_ENABLED still denies AUTHORITY (edition gate first)."""
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.WRITE_ENABLED, cap_id)
        assert d.allowed is False
        assert d.reason_code == ReasonCode.EDITION_DENY

    @pytest.mark.parametrize("cap_id", AUTHORITY_CAPS)
    def test_denied_on_enterprise_readonly(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.ENTERPRISE, AuthorityMode.READONLY, cap_id)
        assert d.allowed is False
        assert d.reason_code == ReasonCode.AUTHORITY_MODE_REQUIRED

    @pytest.mark.parametrize("cap_id", AUTHORITY_CAPS)
    def test_allowed_on_enterprise_write_enabled(self, cap_id: str) -> None:
        d = FeatureRegistry.is_allowed(Edition.ENTERPRISE, AuthorityMode.WRITE_ENABLED, cap_id)
        assert d.allowed is True
        assert d.reason_code == ReasonCode.ALLOWED
        assert d.capability_class == "authority"


# ---------------------------------------------------------------------------
# Unknown capabilities
# ---------------------------------------------------------------------------


class TestUnknownCapability:
    def test_unknown_denied(self) -> None:
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, "nonexistent.cap")
        assert d.allowed is False
        assert d.reason_code == ReasonCode.UNKNOWN_CAPABILITY
        assert d.capability_class == "unknown"

    def test_empty_string_denied(self) -> None:
        d = FeatureRegistry.is_allowed(Edition.ENTERPRISE, AuthorityMode.WRITE_ENABLED, "")
        assert d.allowed is False
        assert d.reason_code == ReasonCode.UNKNOWN_CAPABILITY


# ---------------------------------------------------------------------------
# Fingerprint stability
# ---------------------------------------------------------------------------


class TestFingerprintStability:
    """Same inputs must always produce the same fingerprint."""

    def test_deterministic_fingerprint(self) -> None:
        cap = "tooling.risk_classifier"
        d1 = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap)
        d2 = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap)
        assert d1.decision_fingerprint == d2.decision_fingerprint
        assert len(d1.decision_fingerprint) == 64  # SHA-256 hex

    def test_different_inputs_different_fingerprints(self) -> None:
        cap = "tooling.risk_classifier"
        d1 = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap)
        d2 = FeatureRegistry.is_allowed(Edition.ENTERPRISE, AuthorityMode.READONLY, cap)
        assert d1.decision_fingerprint != d2.decision_fingerprint

    def test_fingerprint_changes_with_outcome(self) -> None:
        """Same cap, different edition → different fingerprint (different edition in hash)."""
        d_allow = FeatureRegistry.is_allowed(
            Edition.ENTERPRISE, AuthorityMode.WRITE_ENABLED, "authority.rbac"
        )
        d_deny = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, "authority.rbac")
        assert d_allow.decision_fingerprint != d_deny.decision_fingerprint


# ---------------------------------------------------------------------------
# list_capabilities + capabilities_hash
# ---------------------------------------------------------------------------


class TestListCapabilities:
    def test_all_capabilities_present(self) -> None:
        caps = FeatureRegistry.list_capabilities(Edition.CORE, AuthorityMode.READONLY)
        assert set(caps.keys()) == set(CAPABILITIES.keys())

    def test_each_entry_has_required_fields(self) -> None:
        caps = FeatureRegistry.list_capabilities(Edition.CORE, AuthorityMode.READONLY)
        for _cap_id, info in caps.items():
            assert "allowed" in info
            assert "reason_code" in info
            assert "capability_class" in info
            assert "decision_fingerprint" in info

    def test_sorted_alphabetically(self) -> None:
        caps = FeatureRegistry.list_capabilities(Edition.CORE, AuthorityMode.READONLY)
        keys = list(caps.keys())
        assert keys == sorted(keys)


class TestCapabilitiesHash:
    def test_hash_is_stable(self) -> None:
        h1 = FeatureRegistry.capabilities_hash(Edition.CORE, AuthorityMode.READONLY)
        h2 = FeatureRegistry.capabilities_hash(Edition.CORE, AuthorityMode.READONLY)
        assert h1 == h2
        assert len(h1) == 64

    def test_different_editions_different_hash(self) -> None:
        h_core = FeatureRegistry.capabilities_hash(Edition.CORE, AuthorityMode.READONLY)
        h_ent = FeatureRegistry.capabilities_hash(Edition.ENTERPRISE, AuthorityMode.WRITE_ENABLED)
        assert h_core != h_ent

    def test_core_only_includes_tooling(self) -> None:
        """CORE hash should only reflect TOOLING caps being enabled."""
        caps = FeatureRegistry.list_capabilities(Edition.CORE, AuthorityMode.READONLY)
        enabled = [k for k, v in caps.items() if v["allowed"]]
        assert all(CAPABILITIES[c].capability_class == CapabilityClass.TOOLING for c in enabled)


class TestRegistryVersion:
    def test_registry_version_is_set(self) -> None:
        assert REGISTRY_VERSION == "1.0.0"


class TestCapabilityDecision:
    def test_to_dict(self) -> None:
        cap = "tooling.dashboard_read"
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap)
        as_dict = d.to_dict()
        assert as_dict["allowed"] is True
        assert as_dict["reason_code"] == ReasonCode.ALLOWED
        assert as_dict["capability_class"] == "tooling"
        assert "decision_fingerprint" in as_dict

    def test_frozen(self) -> None:
        cap = "tooling.dashboard_read"
        d = FeatureRegistry.is_allowed(Edition.CORE, AuthorityMode.READONLY, cap)
        with pytest.raises(AttributeError):
            d.allowed = False  # type: ignore[misc]
