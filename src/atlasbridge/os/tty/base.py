"""
Abstract PTY/ConPTY supervisor interface.

Concrete implementations:
  MacOSTTY   — ptyprocess (POSIX, macOS)
  LinuxTTY   — ptyprocess (POSIX, Linux)
  WindowsTTY — winpty / ConPTY (Windows, experimental)

All implementations share a four-task asyncio loop:
  pty_reader       — read PTY master fd; feed detector; forward to stdout
  stdin_relay      — relay user stdin to PTY master (passthrough mode)
  stall_watchdog   — periodically call detector.check_silence()
  response_consumer — drain reply queue; call inject_reply()

Injection gate:
  inject_reply() writes to PTY master fd, then calls detector.mark_injected()
  to open the echo-suppression window (ECHO_SUPPRESS_MS = 500 ms).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field


@dataclass
class PTYConfig:
    """Configuration for a PTY session."""

    command: list[str]  # argv to exec
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    cols: int = 220
    rows: int = 50
    read_timeout_s: float = 0.05  # Max seconds to block on PTY read
    max_buffer_bytes: int = 4096  # Rolling output buffer size
    stall_watchdog_interval_s: float = 1.0  # How often to call check_silence


class BaseTTY(ABC):
    """
    Abstract PTY supervisor.

    Subclasses wrap a concrete PTY implementation (ptyprocess, ConPTY)
    and expose a uniform async interface for the daemon.
    """

    def __init__(self, config: PTYConfig, session_id: str) -> None:
        self.config = config
        self.session_id = session_id
        self._reply_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._output_callbacks: list[Callable[[bytes], None]] = []
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def start(self) -> None:
        """Spawn the child process and open the PTY master fd."""

    @abstractmethod
    async def stop(self, timeout_s: float = 5.0) -> None:
        """Terminate the child process gracefully, then forcibly."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Return True if the child process is still running."""

    @abstractmethod
    def pid(self) -> int:
        """Return the PID of the child process."""

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    @abstractmethod
    def read_output(self) -> AsyncIterator[bytes]:
        """
        Yield raw byte chunks from the PTY master fd.

        Caller is responsible for ANSI stripping and detection.
        The iterator exits when the child process terminates (EOF).
        """
        ...

    @abstractmethod
    async def inject_reply(self, data: bytes) -> None:
        """
        Write *data* to the PTY master fd (child's stdin).

        Must call detector.mark_injected() after writing to open the
        echo-suppression window.
        """

    # ------------------------------------------------------------------
    # Output observation
    # ------------------------------------------------------------------

    def register_output_callback(self, cb: Callable[[bytes], None]) -> None:
        """Register a callback to be called with each output chunk (bytes)."""
        self._output_callbacks.append(cb)

    def _notify_output(self, chunk: bytes) -> None:
        for cb in self._output_callbacks:
            cb(chunk)

    # ------------------------------------------------------------------
    # Reply injection queue
    # ------------------------------------------------------------------

    def queue_reply(self, data: bytes) -> None:
        """Enqueue bytes to inject into the child's stdin."""
        self._reply_queue.put_nowait(data)

    async def _drain_reply_queue(self) -> None:
        """Coroutine: consume reply queue and inject each item."""
        while self._running and self.is_alive():
            try:
                data = await asyncio.wait_for(self._reply_queue.get(), timeout=0.1)
                await self.inject_reply(data)
            except TimeoutError:
                continue

    # ------------------------------------------------------------------
    # Four-task event loop (template method)
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Run the four-task supervisor loop until the child exits.

        Subclasses start with: await self.start()
        Then call: await self.run()
        """
        self._running = True
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._pty_reader_task(), name="pty_reader")
                tg.create_task(self._stdin_relay_task(), name="stdin_relay")
                tg.create_task(self._stall_watchdog_task(), name="stall_watchdog")
                tg.create_task(self._drain_reply_queue(), name="response_consumer")
        finally:
            self._running = False

    @abstractmethod
    async def _pty_reader_task(self) -> None:
        """Read PTY output, notify callbacks, forward to stdout."""

    @abstractmethod
    async def _stdin_relay_task(self) -> None:
        """Relay user stdin to PTY master (passthrough)."""

    @abstractmethod
    async def _stall_watchdog_task(self) -> None:
        """Periodically check for silence (Signal 3)."""
