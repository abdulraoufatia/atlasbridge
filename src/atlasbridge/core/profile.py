"""
Agent profile schema and YAML-file-backed storage.

A profile bundles session defaults (label, policy, adapter, metadata) into a
reusable named configuration.  Profiles live as individual YAML files in
``<atlasbridge_dir>/profiles/<name>.yaml``.

Usage::

    store = ProfileStore()
    store.save(AgentProfile(name="ci", session_label="ci", policy_file="policy-ci.yaml"))
    profile = store.get("ci")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from atlasbridge.core.config import atlasbridge_dir
from atlasbridge.core.constants import PROFILES_DIR_NAME

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


class AgentProfile(BaseModel):
    """Named agent profile — bundles session defaults for reuse."""

    name: str = Field(
        ...,
        description="Unique profile identifier (lowercase alphanumeric, hyphens, underscores).",
    )
    description: str = ""
    session_label: str = ""
    policy_file: str = ""
    adapter: str = "claude"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not _NAME_RE.fullmatch(v):
            raise ValueError(
                f"Profile name {v!r} is invalid. "
                "Must be 1-64 chars: lowercase letters, digits, hyphens, underscores. "
                "Must start with a letter or digit."
            )
        return v


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_DEFAULT_MARKER = ".default"


class ProfileStore:
    """YAML-file-backed profile storage."""

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self._dir = profiles_dir or (atlasbridge_dir() / PROFILES_DIR_NAME)
        self._dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    @property
    def profiles_dir(self) -> Path:
        return self._dir

    # -- CRUD ---------------------------------------------------------------

    def list_profiles(self) -> list[AgentProfile]:
        """Return all profiles sorted by name."""
        profiles: list[AgentProfile] = []
        for p in sorted(self._dir.glob("*.yaml")):
            try:
                profiles.append(self._load_file(p))
            except Exception:  # noqa: BLE001, S112 — skip corrupt files
                continue
        return profiles

    def get(self, name: str) -> AgentProfile | None:
        """Load a profile by name, or ``None`` if not found."""
        path = self._path_for(name)
        if not path.exists():
            return None
        return self._load_file(path)

    def save(self, profile: AgentProfile) -> Path:
        """Write (create or overwrite) a profile to disk."""
        import yaml

        path = self._path_for(profile.name)
        data = profile.model_dump(exclude_defaults=True)
        data["name"] = profile.name  # always include name
        with open(path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        return path

    def delete(self, name: str) -> bool:
        """Delete a profile. Returns True if it existed."""
        path = self._path_for(name)
        if not path.exists():
            return False
        path.unlink()
        # Clear default if it pointed to this profile
        if self.get_default() == name:
            marker = self._dir / _DEFAULT_MARKER
            marker.unlink(missing_ok=True)
        return True

    # -- Default profile ----------------------------------------------------

    def get_default(self) -> str | None:
        """Return the default profile name, or None."""
        marker = self._dir / _DEFAULT_MARKER
        if not marker.exists():
            return None
        text = marker.read_text().strip()
        return text if text else None

    def set_default(self, name: str) -> None:
        """Set the default profile (must already exist)."""
        if not self._path_for(name).exists():
            raise FileNotFoundError(f"Profile {name!r} does not exist")
        marker = self._dir / _DEFAULT_MARKER
        marker.write_text(name)

    # -- Internals ----------------------------------------------------------

    def _path_for(self, name: str) -> Path:
        return self._dir / f"{name}.yaml"

    def _load_file(self, path: Path) -> AgentProfile:
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Profile file {path} does not contain a YAML mapping")
        return AgentProfile.model_validate(data)
