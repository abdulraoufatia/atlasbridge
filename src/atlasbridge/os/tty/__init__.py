"""PTY supervisor dispatch — macOS and Linux only."""

from __future__ import annotations

import sys


def get_tty_class() -> type:
    """Return the appropriate TTY class for the current platform."""
    if sys.platform == "darwin":
        from atlasbridge.os.tty.macos import MacOSTTY

        return MacOSTTY
    elif sys.platform.startswith("linux"):
        from atlasbridge.os.tty.linux import LinuxTTY

        return LinuxTTY
    else:
        raise RuntimeError(
            f"Unsupported platform: {sys.platform}. AtlasBridge supports macOS and Linux only."
        )
