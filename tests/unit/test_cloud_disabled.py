"""Safety tests: cloud module removed — verify no production code depends on it.

The cloud module (Phase B spec) was extracted to docs/cloud-spec.md to reduce
maintenance surface. These tests ensure no production code imports from the
removed module, and that the enterprise CLI cloud commands still work.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlasbridge"


class TestCloudModuleRemoved:
    """Verify the cloud module is fully removed from source."""

    def test_cloud_package_does_not_exist(self) -> None:
        cloud_dir = _SRC_ROOT / "cloud"
        assert not cloud_dir.exists(), (
            f"src/atlasbridge/cloud/ should be removed — found {cloud_dir}"
        )

    def test_no_production_imports_from_cloud(self) -> None:
        """Scan all production .py files for imports from atlasbridge.cloud."""
        violations: list[str] = []
        for py_file in _SRC_ROOT.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            source = py_file.read_text()
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith("atlasbridge.cloud"):
                        rel = py_file.relative_to(_SRC_ROOT)
                        violations.append(f"{rel}:{node.lineno} imports {node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("atlasbridge.cloud"):
                            rel = py_file.relative_to(_SRC_ROOT)
                            violations.append(f"{rel}:{node.lineno} imports {alias.name}")
        assert violations == [], (
            "Production code still imports from atlasbridge.cloud:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_cloud_not_importable(self) -> None:
        """Verify importing atlasbridge.cloud raises ImportError."""
        with pytest.raises(ImportError):
            __import__("atlasbridge.cloud")


class TestEnterpriseCloudConfig:
    """Verify the inlined cloud config in _enterprise.py works correctly."""

    def test_cloud_config_defaults(self) -> None:
        from atlasbridge.cli._enterprise import _CloudConfig

        config = _CloudConfig()
        assert config.enabled is False
        assert config.endpoint == ""
        assert config.control_channel == "disabled"
        assert config.stream_audit is False

    def test_cloud_config_enabled_check(self) -> None:
        from atlasbridge.cli._enterprise import _CloudConfig

        # Disabled by default
        config = _CloudConfig()
        assert not (config.enabled and bool(config.endpoint))

        # Enabled but no endpoint
        config = _CloudConfig(enabled=True, endpoint="")
        assert not (config.enabled and bool(config.endpoint))

        # Fully configured
        config = _CloudConfig(enabled=True, endpoint="https://api.example.com")
        assert config.enabled and bool(config.endpoint)
