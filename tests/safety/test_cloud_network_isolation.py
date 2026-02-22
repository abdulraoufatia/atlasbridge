"""
Safety test: Cloud module removed — verify no residual cloud imports.

The cloud module (src/atlasbridge/cloud/) was extracted to docs/cloud-spec.md
in v0.8.2. These tests verify the module is fully removed and no production
code depends on it.

When Phase B implementation restores the cloud module, re-add the AST-based
network isolation scanner (see docs/cloud-spec.md for the interface spec).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlasbridge"
CLOUD_DIR = SRC_ROOT / "cloud"


class TestCloudModuleRemoved:
    """Guard: cloud module must not exist as source code."""

    def test_cloud_dir_does_not_exist(self) -> None:
        assert not CLOUD_DIR.exists(), (
            f"Cloud module should be removed — found {CLOUD_DIR}. "
            "Interfaces live in docs/cloud-spec.md."
        )

    def test_no_production_code_imports_cloud(self) -> None:
        """AST scan: no production .py file imports from atlasbridge.cloud."""
        violations: list[str] = []
        for py_file in SRC_ROOT.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith("atlasbridge.cloud"):
                        rel = py_file.relative_to(SRC_ROOT)
                        violations.append(f"{rel}:{node.lineno} imports {node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("atlasbridge.cloud"):
                            rel = py_file.relative_to(SRC_ROOT)
                            violations.append(f"{rel}:{node.lineno} imports {alias.name}")

        assert violations == [], (
            "Production code still imports from atlasbridge.cloud:\n"
            + "\n".join(f"  {v}" for v in violations)
        )
