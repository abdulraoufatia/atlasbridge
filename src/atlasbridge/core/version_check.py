"""Check PyPI for latest AtlasBridge version — cached, non-blocking.

Provides a single entry point ``check_version()`` that returns a
``VersionStatus`` with the current version, latest available version,
and whether an update is available.  Results are cached to a local
JSON file with a 24-hour TTL so repeated calls are effectively free.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from packaging.version import Version

from atlasbridge import __version__

_CACHE_TTL_SECONDS = 86_400  # 24 hours
_PYPI_URL = "https://pypi.org/pypi/atlasbridge/json"
_TIMEOUT = 5  # seconds


@dataclass(frozen=True)
class VersionStatus:
    """Result of a version check."""

    current: str
    latest: str | None
    update_available: bool
    error: str | None = None


def _cache_path() -> Path:
    from atlasbridge.core.constants import _default_data_dir

    return _default_data_dir() / ".version_cache.json"


def _read_cache() -> dict | None:
    """Read cached version info if still valid."""
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data.get("timestamp", 0) < _CACHE_TTL_SECONDS:
            return data
    except Exception:  # noqa: BLE001
        pass
    return None


def _write_cache(latest: str) -> None:
    """Write version info to the cache file."""
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"latest": latest, "timestamp": time.time()}))
    except Exception:  # noqa: BLE001
        pass


def check_version() -> VersionStatus:
    """Check if a newer version is available on PyPI.

    Reads from a local cache first (24h TTL).  Falls back to a
    synchronous HTTP request to PyPI with a 5-second timeout.
    Never raises — returns a ``VersionStatus`` with an error field
    on failure.
    """
    # Try cache first
    cached = _read_cache()
    if cached and "latest" in cached:
        latest = cached["latest"]
        return VersionStatus(
            current=__version__,
            latest=latest,
            update_available=Version(latest) > Version(__version__),
        )

    # Fetch from PyPI
    try:
        import httpx

        resp = httpx.get(_PYPI_URL, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        latest = resp.json()["info"]["version"]
        _write_cache(latest)
        return VersionStatus(
            current=__version__,
            latest=latest,
            update_available=Version(latest) > Version(__version__),
        )
    except Exception as exc:  # noqa: BLE001
        return VersionStatus(
            current=__version__,
            latest=None,
            update_available=False,
            error=str(exc),
        )
