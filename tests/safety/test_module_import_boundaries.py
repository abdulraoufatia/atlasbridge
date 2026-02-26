"""Safety tests: module import boundary enforcement.

Verifies that the deprecated ``atlasbridge.tui`` package has been fully removed
and no source or test code imports from it.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "atlasbridge"


def _collect_imports(filepath: Path) -> list[str]:
    """Return all import source strings from a Python file."""
    try:
        tree = ast.parse(filepath.read_text(), filename=str(filepath))
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
    return imports


def test_tui_package_removed() -> None:
    """The tui/ directory must no longer exist in src/."""
    tui_dir = SRC / "tui"
    assert not tui_dir.exists(), "src/atlasbridge/tui/ still exists — it should have been removed"


def test_no_tui_imports_in_src() -> None:
    """No source file should import from atlasbridge.tui."""
    violations: list[str] = []
    for pyfile in SRC.rglob("*.py"):
        for imp in _collect_imports(pyfile):
            if imp.startswith("atlasbridge.tui"):
                violations.append(f"{pyfile.relative_to(ROOT)}: {imp}")

    assert not violations, "Found imports from atlasbridge.tui in src/:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


def test_no_tui_imports_in_tests() -> None:
    """No test file should import from atlasbridge.tui."""
    tests_dir = ROOT / "tests"
    violations: list[str] = []
    for pyfile in tests_dir.rglob("*.py"):
        for imp in _collect_imports(pyfile):
            if imp.startswith("atlasbridge.tui"):
                violations.append(f"{pyfile.relative_to(ROOT)}: {imp}")

    assert not violations, "Found imports from atlasbridge.tui in tests/:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


def test_ui_state_defines_core_types() -> None:
    """ui/state.py must define (not re-export) the core state types."""
    from atlasbridge.ui.state import (
        AppState,
        ChannelStatus,
        ConfigStatus,
        DaemonStatus,
        WizardState,
        guidance_message,
    )

    assert AppState
    assert ChannelStatus
    assert ConfigStatus
    assert DaemonStatus
    assert WizardState
    assert callable(guidance_message)


def test_ui_services_defines_service_classes() -> None:
    """ui/services.py must define all service classes."""
    from atlasbridge.ui.services import (
        ConfigService,
        DaemonService,
        DoctorService,
        LogsService,
        SessionService,
    )

    assert ConfigService
    assert DaemonService
    assert DoctorService
    assert LogsService
    assert SessionService
