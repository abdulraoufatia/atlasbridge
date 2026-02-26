"""Capability constants and classification.

Every capability in the system has a unique string ID, a class
(TOOLING or AUTHORITY), and enforcement metadata.
The ``CAPABILITIES`` dict is the single source of truth — no other module
defines capability IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CapabilityClass(StrEnum):
    """Classification of capabilities.

    TOOLING   — read-only, observability, explain, replay, export, inspect.
    AUTHORITY — mutations, identity, RBAC, admin ops, policy CRUD, key mgmt.
    """

    TOOLING = "tooling"
    AUTHORITY = "authority"


@dataclass(frozen=True)
class CapabilitySpec:
    """Metadata for a registered capability.

    Attributes:
        capability_class: TOOLING or AUTHORITY — determines edition/mode rules.
        edition_allowed: Frozenset of edition values where this capability is
            accessible (``{"core", "enterprise"}`` or ``{"enterprise"}``).
        guard_location: Where enforcement is applied.
            ``"router_mount"`` — the route is never registered on disallowed
            editions; ``"route_handler"`` — the handler calls
            ``require_capability()`` at entry.
        test_requirement: Path to the canonical test verifying this guard, or
            empty string if covered by a broader test class.
    """

    capability_class: CapabilityClass
    edition_allowed: frozenset[str]
    guard_location: str  # "router_mount" | "route_handler"
    test_requirement: str


_ALL = frozenset({"core", "enterprise"})
_ENT = frozenset({"enterprise"})

# ---------------------------------------------------------------------------
# Capability registry — single source of truth
# ---------------------------------------------------------------------------

CAPABILITIES: dict[str, CapabilitySpec] = {
    # TOOLING — available in CORE and ENTERPRISE
    "tooling.decision_trace_v2": CapabilitySpec(
        CapabilityClass.TOOLING,
        _ALL,
        "router_mount",
        "tests/safety/test_dashboard_route_freeze.py::TestDashboardRouteFreezeCore",
    ),
    "tooling.risk_classifier": CapabilitySpec(
        CapabilityClass.TOOLING,
        _ALL,
        "router_mount",
        "",
    ),
    "tooling.policy_pinning": CapabilitySpec(
        CapabilityClass.TOOLING,
        _ALL,
        "router_mount",
        "",
    ),
    "tooling.audit_integrity_check": CapabilitySpec(
        CapabilityClass.TOOLING,
        _ALL,
        "router_mount",
        "",
    ),
    "tooling.policy_lifecycle": CapabilitySpec(
        CapabilityClass.TOOLING,
        _ALL,
        "router_mount",
        "",
    ),
    "tooling.dashboard_read": CapabilitySpec(
        CapabilityClass.TOOLING,
        _ALL,
        "router_mount",
        "tests/safety/test_dashboard_route_freeze.py::TestDashboardRouteFreezeCore",
    ),
    "tooling.session_export": CapabilitySpec(
        CapabilityClass.TOOLING,
        _ALL,
        "router_mount",
        "tests/integration/test_dashboard_edition.py::TestEnterpriseRouteGating::test_export_404_on_core",
    ),
    # AUTHORITY — ENTERPRISE only, requires WRITE_ENABLED
    "authority.rbac": CapabilitySpec(
        CapabilityClass.AUTHORITY,
        _ENT,
        "router_mount",
        "tests/integration/test_edition_contract.py::TestAuthorityCapabilities",
    ),
    "authority.cloud_policy_sync": CapabilitySpec(
        CapabilityClass.AUTHORITY,
        _ENT,
        "router_mount",
        "",
    ),
    "authority.cloud_audit_stream": CapabilitySpec(
        CapabilityClass.AUTHORITY,
        _ENT,
        "router_mount",
        "",
    ),
    "authority.cloud_control_channel": CapabilitySpec(
        CapabilityClass.AUTHORITY,
        _ENT,
        "router_mount",
        "",
    ),
    "authority.web_dashboard_write": CapabilitySpec(
        CapabilityClass.AUTHORITY,
        _ENT,
        "router_mount",
        "",
    ),
    "authority.enterprise_settings": CapabilitySpec(
        CapabilityClass.AUTHORITY,
        _ENT,
        "route_handler",
        "tests/integration/test_dashboard_edition.py::TestEnterpriseRouteGating::test_enterprise_settings_not_found_on_core",
    ),
}
