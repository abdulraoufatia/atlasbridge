"""
Architecture invariant tests.

These tests enforce import-layering rules so that circular or forbidden
dependencies cannot creep in unnoticed.

Layering rules:
  core/prompt/  is a pure leaf — no imports from adapters, channels, or daemon
  adapters/     may import from core/prompt/ and os/
  channels/     may import from core/prompt/ only (not adapters/)
  core/routing/ may import from core/prompt/ and core/session/
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "atlasbridge"

# Modules in core/prompt/ must not import from these top-level packages:
_PROMPT_FORBIDDEN_PREFIXES = (
    "atlasbridge.adapters",
    "atlasbridge.channels",
    "atlasbridge.core.daemon",
    "atlasbridge.tui",
    "atlasbridge.ui",
)

# Channels must not import from adapters:
_CHANNEL_FORBIDDEN_PREFIXES = ("atlasbridge.adapters",)


def _collect_imports(module_path: Path) -> list[str]:
    """Parse a Python file and return all imported module names."""
    source = module_path.read_text()
    tree = ast.parse(source, filename=str(module_path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


class TestImportLayering:
    """Ensure core/prompt/ stays a pure leaf with no forbidden imports."""

    @pytest.mark.parametrize(
        "py_file",
        list((SRC / "core" / "prompt").glob("*.py")),
        ids=lambda p: p.name,
    )
    def test_prompt_module_no_forbidden_imports(self, py_file: Path) -> None:
        imports = _collect_imports(py_file)
        for imp in imports:
            for prefix in _PROMPT_FORBIDDEN_PREFIXES:
                assert not imp.startswith(prefix), (
                    f"{py_file.name} imports {imp!r} which violates the "
                    f"prompt-leaf layering rule (forbidden prefix: {prefix})"
                )

    @pytest.mark.parametrize(
        "py_file",
        list((SRC / "channels").rglob("*.py")),
        ids=lambda p: str(p.relative_to(SRC)),
    )
    def test_channel_no_adapter_imports(self, py_file: Path) -> None:
        imports = _collect_imports(py_file)
        for imp in imports:
            for prefix in _CHANNEL_FORBIDDEN_PREFIXES:
                assert not imp.startswith(prefix), (
                    f"{py_file.name} imports {imp!r} which violates the "
                    f"channel→adapter layering rule"
                )


class TestAdapterPublicAPI:
    """Verify the BaseAdapter exposes get_detector() so daemon doesn't need private access."""

    def test_base_adapter_has_get_detector(self) -> None:
        from atlasbridge.adapters.base import BaseAdapter

        assert hasattr(BaseAdapter, "get_detector"), (
            "BaseAdapter must expose get_detector() as a public method"
        )

    def test_claude_adapter_get_detector_returns_detector(self) -> None:
        from atlasbridge.adapters.claude_code import ClaudeCodeAdapter
        from atlasbridge.core.prompt.detector import PromptDetector

        adapter = ClaudeCodeAdapter()
        # No session started — should return None
        assert adapter.get_detector("nonexistent") is None

        # Manually populate a detector
        det = PromptDetector("test-session")
        adapter._detectors["test-session"] = det
        assert adapter.get_detector("test-session") is det


class TestDaemonNoPrivateAccess:
    """Verify daemon/manager.py does not access adapter._detectors directly."""

    def test_no_private_detector_access(self) -> None:
        source = (SRC / "core" / "daemon" / "manager.py").read_text()
        assert "._detectors" not in source, (
            "daemon/manager.py must not access adapter._detectors directly; "
            "use adapter.get_detector(session_id) instead"
        )
