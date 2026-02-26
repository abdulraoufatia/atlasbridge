"""Safety guard: capability registry is frozen — no capabilities added or removed without review."""

from __future__ import annotations

from atlasbridge.enterprise.capability import CAPABILITIES, CapabilityClass
from atlasbridge.enterprise.edition import AuthorityMode, Edition
from atlasbridge.enterprise.registry import FeatureRegistry

# Update this constant whenever a capability is intentionally added or removed.
EXPECTED_CAPABILITY_COUNT = 13

_VALID_GUARD_LOCATIONS = {"router_mount", "route_handler"}


class TestCapabilityRegistryFreeze:
    """Registry shape and count must not change without explicit test update."""

    def test_capability_count_is_frozen(self) -> None:
        assert len(CAPABILITIES) == EXPECTED_CAPABILITY_COUNT, (
            f"Capability count drift: expected {EXPECTED_CAPABILITY_COUNT}, "
            f"got {len(CAPABILITIES)}. Update EXPECTED_CAPABILITY_COUNT if intentional."
        )

    def test_all_capabilities_have_valid_guard_location(self) -> None:
        for cap_id, spec in CAPABILITIES.items():
            assert spec.guard_location in _VALID_GUARD_LOCATIONS, (
                f"Capability {cap_id!r} has invalid guard_location: {spec.guard_location!r}. "
                f"Must be one of {_VALID_GUARD_LOCATIONS}."
            )

    def test_all_capabilities_have_test_requirement_string(self) -> None:
        for cap_id, spec in CAPABILITIES.items():
            assert isinstance(spec.test_requirement, str), (
                f"Capability {cap_id!r} test_requirement must be a string, "
                f"got {type(spec.test_requirement)}"
            )

    def test_all_capabilities_have_edition_allowed_frozenset(self) -> None:
        valid_editions = {"core", "enterprise"}
        for cap_id, spec in CAPABILITIES.items():
            assert isinstance(spec.edition_allowed, frozenset), (
                f"Capability {cap_id!r} edition_allowed must be frozenset"
            )
            assert spec.edition_allowed <= valid_editions, (
                f"Capability {cap_id!r} edition_allowed contains unknown editions: "
                f"{spec.edition_allowed - valid_editions}"
            )

    def test_tooling_capabilities_all_allowed_on_core(self) -> None:
        edition = Edition.CORE
        authority_mode = AuthorityMode.READONLY
        for cap_id, spec in CAPABILITIES.items():
            if spec.capability_class == CapabilityClass.TOOLING:
                decision = FeatureRegistry.is_allowed(edition, authority_mode, cap_id)
                assert decision.allowed, (
                    f"TOOLING capability {cap_id!r} should be allowed on CORE "
                    f"but got reason_code: {decision.reason_code}"
                )

    def test_authority_capabilities_all_denied_on_core(self) -> None:
        edition = Edition.CORE
        authority_mode = AuthorityMode.READONLY
        for cap_id, spec in CAPABILITIES.items():
            if spec.capability_class == CapabilityClass.AUTHORITY:
                decision = FeatureRegistry.is_allowed(edition, authority_mode, cap_id)
                assert not decision.allowed, (
                    f"AUTHORITY capability {cap_id!r} should be denied on CORE but got allowed=True"
                )
                assert decision.reason_code == "EDITION_DENY", (
                    f"Expected EDITION_DENY for {cap_id!r} on CORE, got {decision.reason_code}"
                )

    def test_authority_capabilities_all_denied_in_enterprise_readonly(self) -> None:
        edition = Edition.ENTERPRISE
        authority_mode = AuthorityMode.READONLY
        for cap_id, spec in CAPABILITIES.items():
            if spec.capability_class == CapabilityClass.AUTHORITY:
                decision = FeatureRegistry.is_allowed(edition, authority_mode, cap_id)
                assert not decision.allowed, (
                    f"AUTHORITY capability {cap_id!r} should be denied in ENTERPRISE+READONLY "
                    f"but got allowed=True"
                )
                assert decision.reason_code == "AUTHORITY_MODE_REQUIRED", (
                    f"Expected AUTHORITY_MODE_REQUIRED for {cap_id!r} in ENTERPRISE+READONLY, "
                    f"got {decision.reason_code}"
                )

    def test_authority_capabilities_allowed_in_enterprise_write_enabled(self) -> None:
        edition = Edition.ENTERPRISE
        authority_mode = AuthorityMode.WRITE_ENABLED
        for cap_id, spec in CAPABILITIES.items():
            if spec.capability_class == CapabilityClass.AUTHORITY:
                decision = FeatureRegistry.is_allowed(edition, authority_mode, cap_id)
                assert decision.allowed, (
                    f"AUTHORITY capability {cap_id!r} should be allowed in "
                    f"ENTERPRISE+WRITE_ENABLED but got reason_code: {decision.reason_code}"
                )

    def test_capability_decision_includes_guard_metadata(self) -> None:
        """CapabilityDecision.to_dict() must include guard_location and test_requirement."""
        edition = Edition.CORE
        authority_mode = AuthorityMode.READONLY
        decision = FeatureRegistry.is_allowed(edition, authority_mode, "tooling.dashboard_read")
        d = decision.to_dict()
        assert "guard_location" in d, "guard_location missing from CapabilityDecision.to_dict()"
        assert "test_requirement" in d, "test_requirement missing from CapabilityDecision.to_dict()"
        assert d["guard_location"] == "router_mount"
