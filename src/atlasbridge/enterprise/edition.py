"""Edition and AuthorityMode enums for runtime capability gating.

Edition determines which capability classes are available.
AuthorityMode determines whether AUTHORITY capabilities are active
in the Enterprise edition.

Detection is from environment variables only — no network, no I/O,
fully deterministic for given inputs.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum

_log = logging.getLogger(__name__)


class Edition(StrEnum):
    """AtlasBridge edition tiers.

    CORE       — local governance + all tooling capabilities (default).
    ENTERPRISE — CORE + authority capabilities (RBAC, cloud, write ops).
    """

    CORE = "core"
    ENTERPRISE = "enterprise"


class AuthorityMode(StrEnum):
    """Controls whether AUTHORITY capabilities are active in Enterprise.

    READONLY       — all AUTHORITY capabilities denied (safe default).
    WRITE_ENABLED  — AUTHORITY capabilities allowed per registry.
    """

    READONLY = "readonly"
    WRITE_ENABLED = "write_enabled"


def detect_edition() -> Edition:
    """Detect the active edition from ``ATLASBRIDGE_EDITION`` env var.

    Mapping:
      ``""`` / unset / ``"core"``  → ``Edition.CORE``
      ``"community"``              → ``Edition.CORE`` (deprecated alias)
      ``"enterprise"``             → ``Edition.ENTERPRISE``

    Any other value falls back to ``Edition.CORE``.
    """
    env = os.environ.get("ATLASBRIDGE_EDITION", "").lower()
    if env == "community":
        _log.warning(
            "ATLASBRIDGE_EDITION='community' is deprecated — mapped to 'core'. "
            "Use 'core' or omit the env var."
        )
        return Edition.CORE
    if env == "enterprise":
        return Edition.ENTERPRISE
    return Edition.CORE


def detect_authority_mode() -> AuthorityMode:
    """Detect authority mode from ``ATLASBRIDGE_AUTHORITY_MODE`` env var.

    Defaults to ``AuthorityMode.READONLY`` (safe default).
    Only ``"write_enabled"`` activates write mode.
    """
    env = os.environ.get("ATLASBRIDGE_AUTHORITY_MODE", "").lower()
    if env == "write_enabled":
        return AuthorityMode.WRITE_ENABLED
    return AuthorityMode.READONLY
