"""Safety guard: release artifacts and metadata must be present."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_changelog_exists():
    """CHANGELOG.md must exist."""
    assert (ROOT / "CHANGELOG.md").is_file(), "CHANGELOG.md missing"


def test_license_exists():
    """LICENSE file must exist."""
    assert (ROOT / "LICENSE").is_file(), "LICENSE missing"


def test_readme_exists():
    """README.md must exist."""
    assert (ROOT / "README.md").is_file(), "README.md missing"


def test_ci_workflow_exists():
    """CI workflow must exist."""
    assert (ROOT / ".github" / "workflows" / "ci.yml").is_file(), "CI workflow missing"


def test_pyproject_has_project_urls():
    """pyproject.toml must have [project.urls] section."""
    with (ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    urls = data.get("project", {}).get("urls", {})
    assert urls, "pyproject.toml missing [project.urls] section"


def test_pyproject_classifier_is_pre_alpha():
    """Before v1.0, PyPI classifier must be Pre-Alpha or Alpha."""
    with (ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)

    version = data["project"]["version"]
    major = int(version.split(".")[0])

    if major < 1:
        classifiers = data["project"].get("classifiers", [])
        dev_status = [c for c in classifiers if "Development Status" in c]
        assert dev_status, "Missing Development Status classifier"
        # Pre-1.0 should not claim Production/Stable
        for c in dev_status:
            assert "5 - Production/Stable" not in c, (
                f"Pre-1.0 release must not claim Production/Stable: {c}"
            )


def test_version_strings_match():
    """Version in pyproject.toml and __init__.py must match."""
    with (ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    pyproject_version = data["project"]["version"]

    import atlasbridge

    assert atlasbridge.__version__ == pyproject_version, (
        f"Version mismatch: pyproject.toml='{pyproject_version}' "
        f"!= __init__.py='{atlasbridge.__version__}'"
    )


def test_safety_test_suite_has_minimum_files():
    """Safety test suite must have at least 19 test files."""
    safety_dir = ROOT / "tests" / "safety"
    test_files = list(safety_dir.glob("test_*.py"))
    assert len(test_files) >= 19, (
        f"Safety test suite has {len(test_files)} files, expected >= 18. "
        f"Files: {sorted(f.name for f in test_files)}"
    )
