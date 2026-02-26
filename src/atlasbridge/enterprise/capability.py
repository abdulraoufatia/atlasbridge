"""Capability constants and classification.

Every capability in the system has a unique string ID and a class
(TOOLING or AUTHORITY). The ``CAPABILITIES`` dict is the single
source of truth — no other module defines capability IDs.
"""

from __future__ import annotations

from enum import StrEnum


class CapabilityClass(StrEnum):
    """Classification of capabilities.

    TOOLING   — read-only, observability, explain, replay, export, inspect.
    AUTHORITY — mutations, identity, RBAC, admin ops, policy CRUD, key mgmt.
    """

    TOOLING = "tooling"
    AUTHORITY = "authority"


# ---------------------------------------------------------------------------
# Capability registry — single source of truth
# ---------------------------------------------------------------------------

CAPABILITIES: dict[str, CapabilityClass] = {
    # TOOLING — available in CORE and ENTERPRISE
    "tooling.decision_trace_v2": CapabilityClass.TOOLING,
    "tooling.risk_classifier": CapabilityClass.TOOLING,
    "tooling.policy_pinning": CapabilityClass.TOOLING,
    "tooling.audit_integrity_check": CapabilityClass.TOOLING,
    "tooling.policy_lifecycle": CapabilityClass.TOOLING,
    "tooling.dashboard_read": CapabilityClass.TOOLING,
    "tooling.session_export": CapabilityClass.TOOLING,
    # AUTHORITY — ENTERPRISE only, requires WRITE_ENABLED
    "authority.rbac": CapabilityClass.AUTHORITY,
    "authority.cloud_policy_sync": CapabilityClass.AUTHORITY,
    "authority.cloud_audit_stream": CapabilityClass.AUTHORITY,
    "authority.cloud_control_channel": CapabilityClass.AUTHORITY,
    "authority.web_dashboard_write": CapabilityClass.AUTHORITY,
    "authority.enterprise_settings": CapabilityClass.AUTHORITY,
}
