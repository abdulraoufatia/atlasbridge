"""Safety test: ChannelMessageGate import boundary.

The gate engine must NOT import from channels/, adapters/, or UI modules.
It is a core-only module that evaluates decisions without side effects.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent.parent / "src" / "atlasbridge"
GATE_DIR = SRC / "core" / "gate"

_FORBIDDEN_PREFIXES = (
    "atlasbridge.channels",
    "atlasbridge.adapters",
    "atlasbridge.ui",
    "atlasbridge.tui",
    "atlasbridge.console",
    "atlasbridge.dashboard",
    "atlasbridge.cli",
)


def _collect_imports(path: Path) -> list[str]:
    """Collect all import module names from a Python file using AST."""
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


@pytest.mark.safety
class TestGateImportBoundary:
    """Gate module must not import from channels, adapters, or UI."""

    def test_gate_engine_has_no_forbidden_imports(self):
        engine_path = GATE_DIR / "engine.py"
        assert engine_path.exists(), "core/gate/engine.py not found"
        imports = _collect_imports(engine_path)
        for imp in imports:
            for prefix in _FORBIDDEN_PREFIXES:
                assert not imp.startswith(prefix), f"Gate engine imports forbidden module: {imp}"

    def test_gate_init_has_no_forbidden_imports(self):
        init_path = GATE_DIR / "__init__.py"
        assert init_path.exists(), "core/gate/__init__.py not found"
        imports = _collect_imports(init_path)
        for imp in imports:
            for prefix in _FORBIDDEN_PREFIXES:
                assert not imp.startswith(prefix), f"Gate __init__ imports forbidden module: {imp}"

    def test_all_gate_files_have_no_forbidden_imports(self):
        """Scan every .py in core/gate/ for forbidden imports."""
        for pyfile in GATE_DIR.glob("*.py"):
            imports = _collect_imports(pyfile)
            for imp in imports:
                for prefix in _FORBIDDEN_PREFIXES:
                    assert not imp.startswith(prefix), (
                        f"{pyfile.name} imports forbidden module: {imp}"
                    )
