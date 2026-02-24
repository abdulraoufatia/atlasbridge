"""AtlasBridge constants: filesystem layout, timeouts, and limits."""

from __future__ import annotations

import sys
from enum import IntEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class ExitCode(IntEnum):
    SUCCESS = 0
    ERROR = 1
    CONFIG_ERROR = 2
    ENV_ERROR = 3
    NETWORK_ERROR = 4
    PERMISSION_ERROR = 5
    DEPENDENCY_MISSING = 7


# ---------------------------------------------------------------------------
# Platform-specific config directory
# ---------------------------------------------------------------------------


def _default_data_dir() -> Path:
    """
    Return the platform-appropriate AtlasBridge data directory.

    macOS : ~/Library/Application Support/atlasbridge
    Linux : ~/.config/atlasbridge
    Other : ~/.atlasbridge
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "atlasbridge"
    if sys.platform.startswith("linux"):
        xdg = Path(__import__("os").environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        return xdg / "atlasbridge"
    return Path.home() / ".atlasbridge"


# Legacy path — migrated automatically on first run
LEGACY_AEGIS_DIR = Path.home() / ".aegis"

# ---------------------------------------------------------------------------
# Filesystem layout
# ---------------------------------------------------------------------------

CONFIG_FILENAME = "config.toml"
DB_FILENAME = "atlasbridge.db"
AUDIT_FILENAME = "audit.log"
PID_FILENAME = "atlasbridge.pid"
LOG_FILENAME = "atlasbridge.log"
PROFILES_DIR_NAME = "profiles"

# ---------------------------------------------------------------------------
# Timeouts and limits
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes — prompt TTL
DEFAULT_REMINDER_SECONDS: int | None = None  # reminder before TTL (None = disabled)
STUCK_TIMEOUT_SECONDS = 5.0  # silence threshold for Signal 3
MAX_BUFFER_BYTES = 4096  # rolling PTY output buffer
ECHO_SUPPRESS_MS = 500  # ms to suppress detection after injection
DEFAULT_DETECTION_THRESHOLD = 0.65  # confidence threshold for routing

# ---------------------------------------------------------------------------
# Audit log rotation
# ---------------------------------------------------------------------------

AUDIT_RETENTION_DAYS = 90  # default: archive events older than 90 days
AUDIT_MAX_ARCHIVES = 3  # keep at most 3 archive files
AUDIT_MAX_ROWS = 10_000  # default: archive when row count exceeds this

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

DEFAULT_TELEGRAM_POLL_TIMEOUT = 30  # long-poll timeout (seconds)
DEFAULT_TELEGRAM_MAX_RETRIES = 5
