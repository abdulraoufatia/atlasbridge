"""Safety guard: version strings must stay in sync across all sources."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_init_version_matches_pyproject():
    """__init__.py __version__ must equal pyproject.toml [project].version."""
    pyproject = ROOT / "pyproject.toml"
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    pyproject_version = data["project"]["version"]

    import atlasbridge

    assert atlasbridge.__version__ == pyproject_version, (
        f"Version mismatch: pyproject.toml='{pyproject_version}' "
        f"!= __init__.py='{atlasbridge.__version__}'. "
        "Both must be updated together."
    )


def test_version_is_valid_semver():
    """Version string must look like a valid semver (X.Y.Z or X.Y.Z-suffix)."""
    import re

    import atlasbridge

    pattern = r"^\d+\.\d+\.\d+(-[\w.]+)?$"
    assert re.match(pattern, atlasbridge.__version__), (
        f"Version '{atlasbridge.__version__}' is not valid semver."
    )
