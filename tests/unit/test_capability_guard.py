"""Unit tests for require_capability() guard helper."""

from __future__ import annotations

import pytest

from atlasbridge.enterprise.edition import AuthorityMode, Edition
from atlasbridge.enterprise.guard import FeatureUnavailableError, require_capability
from atlasbridge.enterprise.registry import CapabilityDecision, ReasonCode


class TestRequireCapabilityAllow:
    """require_capability returns CapabilityDecision on allow."""

    def test_returns_decision_on_allow(self) -> None:
        decision = require_capability(
            Edition.CORE, AuthorityMode.READONLY, "tooling.risk_classifier"
        )
        assert isinstance(decision, CapabilityDecision)
        assert decision.allowed is True
        assert decision.reason_code == ReasonCode.ALLOWED

    def test_no_audit_callback_on_allow(self) -> None:
        calls: list[tuple] = []

        def cb(event_type: str, payload: dict) -> None:
            calls.append((event_type, payload))

        require_capability(
            Edition.CORE,
            AuthorityMode.READONLY,
            "tooling.risk_classifier",
            audit_callback=cb,
        )
        assert len(calls) == 0


class TestRequireCapabilityDeny:
    """require_capability raises FeatureUnavailableError on deny."""

    def test_raises_on_edition_deny(self) -> None:
        with pytest.raises(FeatureUnavailableError) as exc_info:
            require_capability(Edition.CORE, AuthorityMode.READONLY, "authority.rbac")
        assert exc_info.value.capability_id == "authority.rbac"
        assert exc_info.value.decision.reason_code == ReasonCode.EDITION_DENY

    def test_raises_on_authority_mode_required(self) -> None:
        with pytest.raises(FeatureUnavailableError) as exc_info:
            require_capability(Edition.ENTERPRISE, AuthorityMode.READONLY, "authority.rbac")
        assert exc_info.value.decision.reason_code == ReasonCode.AUTHORITY_MODE_REQUIRED

    def test_raises_on_unknown_capability(self) -> None:
        with pytest.raises(FeatureUnavailableError) as exc_info:
            require_capability(Edition.CORE, AuthorityMode.READONLY, "nonexistent.cap")
        assert exc_info.value.decision.reason_code == ReasonCode.UNKNOWN_CAPABILITY

    def test_error_message_contains_capability_id(self) -> None:
        with pytest.raises(FeatureUnavailableError, match="authority.rbac"):
            require_capability(Edition.CORE, AuthorityMode.READONLY, "authority.rbac")


class TestAuditCallback:
    """Audit callback is invoked on deny only."""

    def test_callback_invoked_on_deny(self) -> None:
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
        event_type, payload = calls[0]
        assert event_type == "capability.denied"
        assert payload["capability_id"] == "authority.rbac"
        assert payload["reason_code"] == ReasonCode.EDITION_DENY
        assert payload["edition"] == "core"
        assert payload["authority_mode"] == "readonly"
        assert "decision_fingerprint" in payload

    def test_callback_not_invoked_on_allow(self) -> None:
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

    def test_callback_receives_all_deny_fields(self) -> None:
        calls: list[tuple] = []

        def cb(event_type: str, payload: dict) -> None:
            calls.append((event_type, payload))

        with pytest.raises(FeatureUnavailableError):
            require_capability(
                Edition.ENTERPRISE,
                AuthorityMode.READONLY,
                "authority.enterprise_settings",
                audit_callback=cb,
            )

        _, payload = calls[0]
        required_fields = {
            "capability_id",
            "reason_code",
            "capability_class",
            "decision_fingerprint",
            "edition",
            "authority_mode",
        }
        assert required_fields.issubset(set(payload.keys()))


class TestFeatureUnavailableError:
    """FeatureUnavailableError stores decision and capability_id."""

    def test_attributes(self) -> None:
        decision = CapabilityDecision(
            allowed=False,
            reason_code=ReasonCode.EDITION_DENY,
            capability_class="authority",
            decision_fingerprint="abc123",
            guard_location="router_mount",
            test_requirement="",
        )
        err = FeatureUnavailableError(decision, "authority.rbac")
        assert err.decision is decision
        assert err.capability_id == "authority.rbac"
        assert "authority.rbac" in str(err)
        assert ReasonCode.EDITION_DENY in str(err)

    def test_is_exception(self) -> None:
        decision = CapabilityDecision(
            allowed=False,
            reason_code=ReasonCode.EDITION_DENY,
            capability_class="authority",
            decision_fingerprint="abc123",
            guard_location="router_mount",
            test_requirement="",
        )
        err = FeatureUnavailableError(decision, "authority.rbac")
        assert isinstance(err, Exception)
