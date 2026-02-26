"""Settings data collection for the dashboard.

This module is separate from app.py to avoid circular imports when router
modules need to call _collect_settings().
"""

from __future__ import annotations

import sys
from pathlib import Path


def collect_settings(
    db_path: Path,
    trace_path: Path,
    edition: str = "",
    authority_mode: str = "",
) -> dict:
    """Gather read-only settings data for the settings page."""
    import atlasbridge
    from atlasbridge.cli._doctor import (
        _check_adapters,
        _check_config,
        _check_database,
        _check_platform,
        _check_ptyprocess,
        _check_python_version,
        _check_ui_assets,
    )
    from atlasbridge.core.config import _config_file_path, atlasbridge_dir
    from atlasbridge.core.constants import AUDIT_FILENAME
    from atlasbridge.enterprise.edition import (
        AuthorityMode,
        Edition,
        detect_authority_mode,
        detect_edition,
    )
    from atlasbridge.enterprise.registry import FeatureRegistry

    ed = detect_edition() if not edition else None
    am = detect_authority_mode() if not authority_mode else None
    ed_val = edition or (ed.value if ed else "core")
    am_val = authority_mode or (am.value if am else "readonly")

    config_dir = atlasbridge_dir()
    config_file = _config_file_path()

    checks_raw = [
        _check_python_version(),
        _check_platform(),
        _check_ptyprocess(),
        _check_config(),
        _check_database(),
        _check_adapters(),
        _check_ui_assets(),
    ]
    diagnostics = [c for c in checks_raw if c is not None]

    ed_enum = Edition(ed_val) if ed_val in Edition.__members__.values() else Edition.CORE
    am_enum = (
        AuthorityMode(am_val)
        if am_val in AuthorityMode.__members__.values()
        else AuthorityMode.READONLY
    )

    vi = sys.version_info
    data: dict = {
        "runtime": {
            "edition": ed_enum.value,
            "authority_mode": am_enum.value,
            "version": atlasbridge.__version__,
            "python_version": f"{vi.major}.{vi.minor}.{vi.micro}",
            "platform": sys.platform,
        },
        "config_paths": {
            "config_dir": str(config_dir),
            "config_file": str(config_file),
            "db_path": str(db_path),
            "audit_log": str(config_dir / AUDIT_FILENAME),
            "trace_file": str(trace_path),
        },
        "dashboard": {
            "host": "127.0.0.1",
            "port": 8787,
            "loopback_only": True,
        },
        "diagnostics": diagnostics,
        "capabilities": FeatureRegistry.list_capabilities(ed_enum, am_enum),
    }

    return data
