"""Capability enforcement guard.

``require_capability()`` is the single guard helper called at capability
entrypoints.  On deny it optionally emits an audit event and raises
``FeatureUnavailableError``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from atlasbridge.enterprise.edition import AuthorityMode, Edition
from atlasbridge.enterprise.registry import CapabilityDecision, FeatureRegistry

# Callback signature: (event_type: str, payload: dict) -> None
AuditCallback = Callable[[str, dict[str, Any]], None]


class FeatureUnavailableError(Exception):
    """Raised when a capability is denied by the FeatureRegistry."""

    def __init__(self, decision: CapabilityDecision, capability_id: str) -> None:
        self.decision = decision
        self.capability_id = capability_id
        super().__init__(f"Capability {capability_id!r} denied: {decision.reason_code}")


def require_capability(
    edition: Edition,
    authority_mode: AuthorityMode,
    capability_id: str,
    *,
    audit_callback: AuditCallback | None = None,
    context: dict[str, Any] | None = None,
) -> CapabilityDecision:
    """Guard: check capability and raise ``FeatureUnavailableError`` on deny.

    On deny:
      1. Calls ``audit_callback("capability.denied", {...})`` if provided.
      2. Raises ``FeatureUnavailableError`` with the decision and capability_id.

    On allow:
      Returns the ``CapabilityDecision``.
    """
    decision = FeatureRegistry.is_allowed(
        edition,
        authority_mode,
        capability_id,
        context,
    )

    if not decision.allowed:
        if audit_callback is not None:
            audit_callback(
                "capability.denied",
                {
                    "capability_id": capability_id,
                    "reason_code": decision.reason_code,
                    "capability_class": decision.capability_class,
                    "decision_fingerprint": decision.decision_fingerprint,
                    "edition": edition.value,
                    "authority_mode": authority_mode.value,
                },
            )
        raise FeatureUnavailableError(decision, capability_id)

    return decision
