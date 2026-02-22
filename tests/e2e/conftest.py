"""Auto-apply @pytest.mark.e2e to all tests in tests/e2e/."""

from __future__ import annotations

from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add 'e2e' marker to every test collected from this directory."""
    marker = pytest.mark.e2e
    for item in items:
        if str(_E2E_DIR) in str(item.fspath):
            item.add_marker(marker)
