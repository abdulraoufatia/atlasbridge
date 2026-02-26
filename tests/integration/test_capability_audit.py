"""Integration tests for capability denial audit events.

Verifies that require_capability() raises the correct exception type with
the correct reason_code, and that the audit_callback is invoked on deny.
"""

from __future__ import annotations

import pytest

from atlasbridge.enterprise.edition import AuthorityMode, Edition
from atlasbridge.enterprise.guard import FeatureUnavailableError, require_capability
from atlasbridge.enterprise.registry import ReasonCode


class TestCapabilityDenialAudit:
    """require_capability raises correctly and invokes audit_callback on deny."""

    def test_edition_deny_raises_feature_unavailable_error(self) -> None:
        with pytest.raises(FeatureUnavailableError) as exc_info:
            require_capability(
                Edition.CORE, AuthorityMode.READONLY, "authority.enterprise_settings"
            )
        assert exc_info.value.capability_id == "authority.enterprise_settings"
        assert exc_info.value.decision.reason_code == ReasonCode.EDITION_DENY

    def test_authority_mode_required_raises_feature_unavailable_error(self) -> None:
        with pytest.raises(FeatureUnavailableError) as exc_info:
            require_capability(
                Edition.ENTERPRISE, AuthorityMode.READONLY, "authority.enterprise_settings"
            )
        assert exc_info.value.capability_id == "authority.enterprise_settings"
        assert exc_info.value.decision.reason_code == ReasonCode.AUTHORITY_MODE_REQUIRED

    def test_unknown_capability_raises_feature_unavailable_error(self) -> None:
        with pytest.raises(FeatureUnavailableError) as exc_info:
            require_capability(
                Edition.ENTERPRISE, AuthorityMode.WRITE_ENABLED, "authority.nonexistent"
            )
        assert exc_info.value.decision.reason_code == ReasonCode.UNKNOWN_CAPABILITY

    def test_audit_callback_called_on_deny(self) -> None:
        events: list[tuple[str, dict]] = []

        def callback(event_type: str, payload: dict) -> None:
            events.append((event_type, payload))

        with pytest.raises(FeatureUnavailableError):
            require_capability(
                Edition.CORE,
                AuthorityMode.READONLY,
                "authority.enterprise_settings",
                audit_callback=callback,
            )

        assert len(events) == 1
        event_type, payload = events[0]
        assert event_type == "capability.denied"
        assert payload["capability_id"] == "authority.enterprise_settings"
        assert payload["reason_code"] == ReasonCode.EDITION_DENY
        assert payload["edition"] == "core"
        assert payload["authority_mode"] == "readonly"
        assert "decision_fingerprint" in payload

    def test_audit_callback_not_called_on_allow(self) -> None:
        events: list[tuple[str, dict]] = []

        def callback(event_type: str, payload: dict) -> None:
            events.append((event_type, payload))

        require_capability(
            Edition.ENTERPRISE,
            AuthorityMode.WRITE_ENABLED,
            "authority.enterprise_settings",
            audit_callback=callback,
        )
        assert len(events) == 0

    def test_audit_callback_called_for_authority_mode_required(self) -> None:
        events: list[tuple[str, dict]] = []

        def callback(event_type: str, payload: dict) -> None:
            events.append((event_type, payload))

        with pytest.raises(FeatureUnavailableError):
            require_capability(
                Edition.ENTERPRISE,
                AuthorityMode.READONLY,
                "authority.enterprise_settings",
                audit_callback=callback,
            )

        assert len(events) == 1
        _, payload = events[0]
        assert payload["reason_code"] == ReasonCode.AUTHORITY_MODE_REQUIRED
        assert payload["edition"] == "enterprise"
        assert payload["authority_mode"] == "readonly"
