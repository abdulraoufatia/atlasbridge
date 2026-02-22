"""
macOS PTY supervisor using ptyprocess.

Wraps ptyprocess.PtyProcess to provide the BaseTTY interface.
ptyprocess handles fork+exec, PTY allocation, and SIGWINCH propagation.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator

from atlasbridge.os.tty.base import BaseTTY, PTYConfig


class MacOSTTY(BaseTTY):
    """
    PTY supervisor for macOS using ptyprocess.

    ptyprocess allocates a PTY pair and exec()s the child in the slave end.
    We read from the master fd asynchronously via asyncio's add_reader.
    """

    def __init__(self, config: PTYConfig, session_id: str) -> None:
        super().__init__(config, session_id)
        self._proc = None  # ptyprocess.PtyProcess

    async def start(self) -> None:
        try:
            import ptyprocess
        except ImportError as exc:
            raise RuntimeError(
                "ptyprocess is required for macOS PTY support. Install with: pip install ptyprocess"
            ) from exc

        env = {**os.environ, **self.config.env} if self.config.env else None
        cwd = self.config.cwd or None

        self._proc = ptyprocess.PtyProcess.spawn(
            self.config.command,
            dimensions=(self.config.rows, self.config.cols),
            env=env,
            cwd=cwd,
        )

    async def stop(self, timeout_s: float = 5.0) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate(force=False)
            await asyncio.sleep(min(timeout_s, 2.0))
            if self._proc.isalive():
                self._proc.terminate(force=True)
        except Exception:  # noqa: BLE001
            pass

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.isalive()

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
        """Blocking read — run in executor to avoid blocking event loop."""
        if self._proc is None:
            raise EOFError
        try:
            return self._proc.read(self.config.max_buffer_bytes)
        except EOFError:
            raise

    async def inject_reply(self, data: bytes) -> None:
        if self._proc is None:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._proc.write, data)

    async def _pty_reader_task(self) -> None:
        async for chunk in self.read_output():
            self._notify_output(chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()

    async def _stdin_relay_task(self) -> None:
        """Relay raw stdin bytes to the PTY master fd."""
        if self._proc is None:
            return
        loop = asyncio.get_event_loop()
        while self._running and self.is_alive():
            try:
                chunk = await loop.run_in_executor(
                    None,
                    sys.stdin.buffer.read1,
                    1024,
                )
                if chunk:
                    await loop.run_in_executor(None, self._proc.write, chunk)
            except (OSError, EOFError):
                break

    async def _stall_watchdog_task(self) -> None:
        while self._running and self.is_alive():
            await asyncio.sleep(self.config.stall_watchdog_interval_s)
