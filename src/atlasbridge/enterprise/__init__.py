"""
AtlasBridge Enterprise — local-first governance extensions.

This module provides enterprise-grade governance capabilities that layer
on top of the core AtlasBridge runtime.  All enterprise features:

  - Are optional (core runtime works without them)
  - Are deterministic (no ML, no heuristics)
  - Run locally (no cloud dependency)
  - Are gated via the FeatureRegistry

Edition detection::

    >>> from atlasbridge.enterprise import Edition, detect_edition
    >>> detect_edition()
    <Edition.CORE: 'core'>

Capability check::

    >>> from atlasbridge.enterprise import FeatureRegistry, AuthorityMode
    >>> decision = FeatureRegistry.is_allowed(
    ...     Edition.CORE, AuthorityMode.READONLY, "tooling.risk_classifier"
    ... )
    >>> decision.allowed
    True

Maturity: Experimental (Phase A — local governance scaffolding)
"""

from __future__ import annotations

from atlasbridge.enterprise.capability import CAPABILITIES, CapabilityClass
from atlasbridge.enterprise.edition import (
    AuthorityMode,
    Edition,
    detect_authority_mode,
    detect_edition,
)
from atlasbridge.enterprise.guard import FeatureUnavailableError, require_capability
from atlasbridge.enterprise.registry import (
    REGISTRY_VERSION,
    CapabilityDecision,
    FeatureRegistry,
    ReasonCode,
)

__all__ = [
    "AuthorityMode",
    "CAPABILITIES",
    "CapabilityClass",
    "CapabilityDecision",
    "Edition",
    "FeatureRegistry",
    "FeatureUnavailableError",
    "REGISTRY_VERSION",
    "ReasonCode",
    "detect_authority_mode",
    "detect_edition",
    "require_capability",
]
