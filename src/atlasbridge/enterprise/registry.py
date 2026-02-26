"""FeatureRegistry — single enforcement point for capability access control.

Pure functions only.  No I/O, no time, no randomness.
Same inputs always produce the same ``CapabilityDecision`` and fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from atlasbridge.enterprise.capability import CAPABILITIES, CapabilityClass, CapabilitySpec
from atlasbridge.enterprise.edition import AuthorityMode, Edition

REGISTRY_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Stable reason codes
# ---------------------------------------------------------------------------


class ReasonCode:
    """Stable string constants for deny/allow reasons."""

    ALLOWED = "ALLOWED"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    EDITION_DENY = "EDITION_DENY"
    AUTHORITY_MODE_REQUIRED = "AUTHORITY_MODE_REQUIRED"


# ---------------------------------------------------------------------------
# Decision result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityDecision:
    """Immutable result of a capability access check."""

    allowed: bool
    reason_code: str
    capability_class: str  # "tooling" | "authority" | "unknown"
    decision_fingerprint: str  # stable SHA-256 hex
    guard_location: str  # "router_mount" | "route_handler" | ""
    test_requirement: str  # canonical test path or ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "capability_class": self.capability_class,
            "decision_fingerprint": self.decision_fingerprint,
            "guard_location": self.guard_location,
            "test_requirement": self.test_requirement,
        }


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def _compute_fingerprint(
    edition: str,
    authority_mode: str,
    capability_id: str,
    allowed: bool,
    reason_code: str,
) -> str:
    """Compute a stable SHA-256 fingerprint for a decision.

    Deterministic: same inputs always produce the same hash.
    Note: guard_location and test_requirement are spec metadata and are NOT
    included in the fingerprint — they do not affect the allow/deny outcome.
    """
    canonical = json.dumps(
        {
            "edition": edition,
            "authority_mode": authority_mode,
            "capability_id": capability_id,
            "allowed": allowed,
            "reason_code": reason_code,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _make_decision(
    edition: Edition,
    authority_mode: AuthorityMode,
    capability_id: str,
    allowed: bool,
    reason_code: str,
    capability_class: str,
    guard_location: str,
    test_requirement: str,
) -> CapabilityDecision:
    return CapabilityDecision(
        allowed=allowed,
        reason_code=reason_code,
        capability_class=capability_class,
        decision_fingerprint=_compute_fingerprint(
            edition,
            authority_mode,
            capability_id,
            allowed,
            reason_code,
        ),
        guard_location=guard_location,
        test_requirement=test_requirement,
    )


class FeatureRegistry:
    """Single enforcement point for capability access control.

    All methods are static.  No instance state, no I/O, no time.
    Fully deterministic.

    Rules::

        1. Unknown capability_id            → deny  UNKNOWN_CAPABILITY
        2. TOOLING capability               → allow (all editions, all modes)
        3. AUTHORITY + CORE                 → deny  EDITION_DENY
        4. AUTHORITY + ENTERPRISE + READONLY → deny  AUTHORITY_MODE_REQUIRED
        5. AUTHORITY + ENTERPRISE + WRITE    → allow
    """

    @staticmethod
    def is_allowed(
        edition: Edition,
        authority_mode: AuthorityMode,
        capability_id: str,
        context: dict[str, Any] | None = None,
    ) -> CapabilityDecision:
        """Check if a capability is allowed under the given configuration."""
        spec: CapabilitySpec | None = CAPABILITIES.get(capability_id)

        if spec is None:
            return _make_decision(
                edition,
                authority_mode,
                capability_id,
                False,
                ReasonCode.UNKNOWN_CAPABILITY,
                "unknown",
                "",
                "",
            )

        # TOOLING — always allowed
        if spec.capability_class == CapabilityClass.TOOLING:
            return _make_decision(
                edition,
                authority_mode,
                capability_id,
                True,
                ReasonCode.ALLOWED,
                spec.capability_class.value,
                spec.guard_location,
                spec.test_requirement,
            )

        # AUTHORITY — requires ENTERPRISE edition
        if edition != Edition.ENTERPRISE:
            return _make_decision(
                edition,
                authority_mode,
                capability_id,
                False,
                ReasonCode.EDITION_DENY,
                spec.capability_class.value,
                spec.guard_location,
                spec.test_requirement,
            )

        # AUTHORITY in ENTERPRISE — requires WRITE_ENABLED
        if authority_mode != AuthorityMode.WRITE_ENABLED:
            return _make_decision(
                edition,
                authority_mode,
                capability_id,
                False,
                ReasonCode.AUTHORITY_MODE_REQUIRED,
                spec.capability_class.value,
                spec.guard_location,
                spec.test_requirement,
            )

        # AUTHORITY in ENTERPRISE + WRITE_ENABLED — allowed
        return _make_decision(
            edition,
            authority_mode,
            capability_id,
            True,
            ReasonCode.ALLOWED,
            spec.capability_class.value,
            spec.guard_location,
            spec.test_requirement,
        )

    @staticmethod
    def list_capabilities(
        edition: Edition,
        authority_mode: AuthorityMode,
    ) -> dict[str, dict[str, Any]]:
        """Return all capabilities with their current status."""
        result: dict[str, dict[str, Any]] = {}
        for cap_id in sorted(CAPABILITIES):
            decision = FeatureRegistry.is_allowed(edition, authority_mode, cap_id)
            result[cap_id] = decision.to_dict()
        return result

    @staticmethod
    def capabilities_hash(
        edition: Edition,
        authority_mode: AuthorityMode,
    ) -> str:
        """Compute a SHA-256 hash over all enabled capability IDs.

        Stable ordering — sorted alphabetically.
        """
        enabled = sorted(
            cap_id
            for cap_id in CAPABILITIES
            if FeatureRegistry.is_allowed(edition, authority_mode, cap_id).allowed
        )
        canonical = json.dumps(enabled, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
