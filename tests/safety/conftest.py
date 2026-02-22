"""Auto-apply @pytest.mark.safety to all tests in tests/safety/."""

from __future__ import annotations

from pathlib import Path

import pytest

_SAFETY_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add 'safety' marker to every test collected from this directory."""
    marker = pytest.mark.safety
    for item in items:
        if str(_SAFETY_DIR) in str(item.fspath):
            item.add_marker(marker)
