"""
Windows ConPTY supervisor (experimental).

Uses pywinpty to allocate a ConPTY pair. Requires Windows 10 1809+ or Windows 11.
Gated behind ``--experimental`` flag on ``atlasbridge run``.

ConPTY API reference:
  https://devblogs.microsoft.com/commandline/windows-command-line-introducing-the-windows-pseudo-console-conpty/

Key differences from POSIX ptyprocess:
  - Output uses CRLF (\\r\\n) line endings; we normalise to LF (\\n) on read.
  - inject_reply() sends CRLF (\\r\\n) instead of bare CR (\\r).
  - winpty.PTY.spawn() takes a command string, not argv list.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from typing import Any

from atlasbridge.os.tty.base import BaseTTY, PTYConfig

# Minimum Windows version: 10 1809 (build 17763) where ConPTY was introduced.
_MIN_WINDOWS_BUILD = 17763


class WindowsTTY(BaseTTY):
    """
    ConPTY supervisor for Windows (experimental).

    Requires ``pywinpty`` and Windows 10 1809+.
    """

    _proc: Any  # winpty.PTY instance or None
    _alive: bool

    def __init__(self, config: PTYConfig, session_id: str) -> None:
        if sys.platform != "win32":
            raise NotImplementedError(
                "WindowsTTY is only valid on Windows (win32). "
                "Use MacOSTTY or LinuxTTY on POSIX platforms."
            )
        super().__init__(config, session_id)
        self._proc = None
        self._alive = False

    async def start(self) -> None:
        try:
            import winpty
        except ImportError as exc:
            raise RuntimeError(
                "pywinpty is required for Windows ConPTY support. "
                "Install with: pip install pywinpty"
            ) from exc

        # Validate Windows build number
        if sys.platform == "win32":
            build = _get_windows_build()
            if build < _MIN_WINDOWS_BUILD:
                raise RuntimeError(
                    f"Windows ConPTY requires build {_MIN_WINDOWS_BUILD}+ "
                    f"(Windows 10 1809). Current build: {build}"
                )

        # winpty.PTY.spawn() takes a command string, not argv list
        cmd_str = " ".join(self.config.command)
        env_str = (
            "\0".join(f"{k}={v}" for k, v in self.config.env.items()) + "\0"
            if self.config.env
            else None
        )

        self._proc = winpty.PTY(self.config.cols, self.config.rows)
        self._proc.spawn(
            cmd_str,
            cwd=self.config.cwd or None,
            env=env_str,
        )
        self._alive = True

    async def stop(self, timeout_s: float = 5.0) -> None:
        if self._proc is None:
            return
        self._alive = False
        # winpty doesn't have a graceful terminate — just close the handle
        try:
            # Give the process a moment to finish
            await asyncio.sleep(min(timeout_s, 1.0))
        except Exception:  # noqa: BLE001
            pass

    def is_alive(self) -> bool:
        if self._proc is None:
            return False
        return self._alive and self._proc.isalive()

    def pid(self) -> int:
        if self._proc is None:
            return -1
        return self._proc.pid

    async def read_output(self) -> AsyncIterator[bytes]:
        if self._proc is None:
            return
        loop = asyncio.get_event_loop()
        while self.is_alive():
            try:
                chunk = await loop.run_in_executor(None, self._read_chunk)
                if chunk:
                    yield chunk
            except EOFError:
                break

    def _read_chunk(self) -> bytes:
        """Blocking read — run in executor."""
        if self._proc is None:
            raise EOFError
        try:
            data = self._proc.read(self.config.max_buffer_bytes)
            if not data:
                raise EOFError
            # Normalise CRLF → LF in output
            return data.encode("utf-8", errors="replace").replace(b"\r\n", b"\n")
        except Exception:
            self._alive = False
            raise EOFError  # noqa: B904

    async def inject_reply(self, data: bytes) -> None:
        if self._proc is None:
            return
        loop = asyncio.get_event_loop()
        # Decode bytes to str for winpty's write method
        text = data.decode("utf-8", errors="replace")
        await loop.run_in_executor(None, self._proc.write, text)

    async def _pty_reader_task(self) -> None:
        async for chunk in self.read_output():
            self._notify_output(chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()

    async def _stdin_relay_task(self) -> None:
        """Relay raw stdin bytes to the ConPTY."""
        if self._proc is None:
            return
        loop = asyncio.get_event_loop()
        while self._running and self.is_alive():
            try:
                reader = getattr(sys.stdin.buffer, "read1", sys.stdin.buffer.read)
                chunk = await loop.run_in_executor(None, reader, 1024)
                if chunk and self._proc is not None:
                    text = chunk.decode("utf-8", errors="replace")
                    await loop.run_in_executor(None, self._proc.write, text)
            except (OSError, EOFError):
                break

    async def _stall_watchdog_task(self) -> None:
        while self._running and self.is_alive():
            await asyncio.sleep(self.config.stall_watchdog_interval_s)


def _get_windows_build() -> int:
    """Return the Windows build number, or 0 if not determinable."""
    try:
        ver = sys.getwindowsversion()  # type: ignore[attr-defined]
        return ver.build
    except AttributeError:
        return 0


def get_tty_class(*, experimental: bool = False) -> type:
    """Return the appropriate TTY class for the current platform.

    Args:
        experimental: If True, allow experimental backends (e.g. Windows ConPTY).
    """
    if sys.platform == "darwin":
        from atlasbridge.os.tty.macos import MacOSTTY

        return MacOSTTY
    elif sys.platform.startswith("linux"):
        from atlasbridge.os.tty.linux import LinuxTTY

        return LinuxTTY
    elif sys.platform == "win32":
        if not experimental:
            raise RuntimeError(
                "Windows ConPTY support is experimental. "
                "Pass --experimental to 'atlasbridge run' to enable it, "
                "or use WSL2 (recommended)."
            )
        return WindowsTTY
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
