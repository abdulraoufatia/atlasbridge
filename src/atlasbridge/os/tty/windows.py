"""
Windows ConPTY supervisor stub.

Full implementation is gated behind v0.5.0 (Windows experimental).
This stub raises NotImplementedError on instantiation so that the adapter
registry can detect platform capability at import time.

ConPTY API reference:
  https://devblogs.microsoft.com/commandline/windows-command-line-introducing-the-windows-pseudo-console-conpty/

Planned implementation:
  - Use winpty or pywinpty to allocate a ConPTY pair
  - CRLF normalization (\\r\\n → \\n) in the output stream
  - inject_reply() uses CRLF (\\r\\n) on Windows

Feature flag: atlasbridge.config.experimental.conpty_backend
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator

from atlasbridge.os.tty.base import BaseTTY, PTYConfig


class WindowsTTY(BaseTTY):
    """
    ConPTY supervisor for Windows (v0.5.0 experimental).

    Not yet implemented. Raises NotImplementedError on construction.
    """

    def __init__(self, config: PTYConfig, session_id: str) -> None:
        if sys.platform != "win32":
            raise NotImplementedError(
                "WindowsTTY is only valid on Windows (win32). "
                "Use MacOSTTY or LinuxTTY on POSIX platforms."
            )
        raise NotImplementedError(
            "WindowsTTY (ConPTY) is not yet implemented. "
            "It is planned for AtlasBridge v0.9.0. "
            "Track progress: https://github.com/abdulraoufatia/atlasbridge/issues"
        )

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self, timeout_s: float = 5.0) -> None:
        raise NotImplementedError

    def is_alive(self) -> bool:
        raise NotImplementedError

    def pid(self) -> int:
        raise NotImplementedError

    async def read_output(self) -> AsyncIterator[bytes]:  # type: ignore[override]
        raise NotImplementedError
        yield  # make this a generator (unreachable)

    async def inject_reply(self, data: bytes) -> None:
        raise NotImplementedError

    async def _pty_reader_task(self) -> None:
        raise NotImplementedError

    async def _stdin_relay_task(self) -> None:
        raise NotImplementedError

    async def _stall_watchdog_task(self) -> None:
        raise NotImplementedError


def get_tty_class() -> type:
    """Return the appropriate TTY class for the current platform."""
    if sys.platform == "darwin":
        from atlasbridge.os.tty.macos import MacOSTTY

        return MacOSTTY
    elif sys.platform.startswith("linux"):
        from atlasbridge.os.tty.linux import LinuxTTY

        return LinuxTTY
    elif sys.platform == "win32":
        return WindowsTTY
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
