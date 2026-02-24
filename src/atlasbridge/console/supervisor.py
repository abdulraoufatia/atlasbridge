"""
ProcessSupervisor — manages daemon, dashboard, and agent subprocesses.

Pure Python + asyncio + subprocess. No Textual dependency.
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


@dataclass
class ProcessInfo:
    """Status snapshot for a managed process."""

    name: str  # "daemon" | "dashboard" | "agent"
    pid: int | None = None
    running: bool = False
    started_at: datetime | None = None
    tool: str = ""  # For agent: "claude", "openai", etc.
    port: int | None = None  # For dashboard

    @property
    def uptime_seconds(self) -> float:
        if self.started_at is None or not self.running:
            return 0.0
        return (datetime.now(UTC) - self.started_at).total_seconds()

    @property
    def uptime_display(self) -> str:
        secs = int(self.uptime_seconds)
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m {secs % 60}s"
        hours = secs // 3600
        mins = (secs % 3600) // 60
        return f"{hours}h {mins}m"


class SystemHealth(Enum):
    """Aggregate system health state."""

    GREEN = "green"  # All processes healthy, doctor checks pass
    YELLOW = "yellow"  # Some processes stopped or doctor warnings
    RED = "red"  # Critical failures


def compute_health(
    statuses: list[ProcessInfo],
    doctor_checks: list[dict] | None = None,
) -> SystemHealth:
    """Derive aggregate health from process statuses and doctor checks."""
    # RED: any doctor check failed
    if doctor_checks:
        if any(c.get("status") == "fail" for c in doctor_checks):
            return SystemHealth.RED

    # Check process states
    daemon = next((s for s in statuses if s.name == "daemon"), None)

    # RED: daemon not running but something else IS running (fault)
    if daemon and not daemon.running:
        others_running = any(s.running for s in statuses if s.name != "daemon")
        if others_running:
            return SystemHealth.RED

    # YELLOW: any doctor warning
    if doctor_checks and any(c.get("status") == "warn" for c in doctor_checks):
        return SystemHealth.YELLOW

    # YELLOW: nothing running at all
    if not any(s.running for s in statuses):
        return SystemHealth.YELLOW

    return SystemHealth.GREEN


def _pid_alive(pid: int) -> bool:
    """Check if a PID is alive using os.kill(pid, 0)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is listening by attempting a TCP connect."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    finally:
        sock.close()


def _dashboard_healthy(port: int, host: str = "127.0.0.1") -> bool:
    """Check if an AtlasBridge dashboard is responding on the given port."""
    import json
    import urllib.request

    for path in ("/api/overview", "/api/stats"):
        try:
            url = f"http://{host}:{port}{path}"
            req = urllib.request.Request(url, method="GET")  # noqa: S310
            with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310
                data = json.loads(resp.read())
                if "activeSessions" in data or "active_sessions" in data:
                    return True
        except Exception:  # noqa: BLE001, S112
            continue
    return False


class ProcessSupervisor:
    """Manages daemon, dashboard, and agent subprocesses.

    Spawns AtlasBridge CLI subcommands as subprocesses rather than calling
    underlying Python functions directly. This preserves process isolation
    and matches the behavior of running commands in separate terminals.
    """

    def __init__(self) -> None:
        self._dashboard_proc: asyncio.subprocess.Process | None = None
        self._dashboard_port: int = 3737
        self._dashboard_started: datetime | None = None

        self._agent_proc: asyncio.subprocess.Process | None = None
        self._agent_tool: str = ""
        self._agent_started: datetime | None = None

    # ------------------------------------------------------------------
    # Daemon
    # ------------------------------------------------------------------

    async def start_daemon(self) -> ProcessInfo:
        """Start the AtlasBridge daemon via ``atlasbridge start``.

        The daemon forks internally. The subprocess exits quickly once
        the daemon is backgrounded. Status comes from the PID file.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "atlasbridge",
                "start",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            # Give the daemon a moment to write its PID file
            await asyncio.sleep(0.5)
        except Exception:  # noqa: BLE001
            return ProcessInfo(name="daemon", running=False)

        return self.daemon_status()

    async def stop_daemon(self) -> bool:
        """Stop the daemon by reading its PID file and sending SIGTERM."""
        try:
            from atlasbridge.cli._daemon import _pid_alive, _read_pid

            pid = _read_pid()
            if pid is None or not _pid_alive(pid):
                return False
            os.kill(pid, signal.SIGTERM)
            # Wait briefly for process to exit
            for _ in range(10):
                await asyncio.sleep(0.2)
                if not _pid_alive(pid):
                    return True
            # Force kill if still alive
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return True
        except Exception:  # noqa: BLE001
            return False

    def daemon_status(self) -> ProcessInfo:
        """Check daemon status via PID file."""
        try:
            from atlasbridge.cli._daemon import _read_pid

            pid = _read_pid()
            if pid is not None and _pid_alive(pid):
                return ProcessInfo(name="daemon", pid=pid, running=True)
        except Exception:  # noqa: BLE001
            pass
        return ProcessInfo(name="daemon", running=False)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    async def start_dashboard(self, port: int = 3737) -> ProcessInfo:
        """Start the dashboard as a long-running subprocess."""
        if self._dashboard_proc is not None and self._dashboard_proc.returncode is None:
            return self.dashboard_status(port)

        try:
            self._dashboard_port = port
            self._dashboard_proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "atlasbridge",
                "dashboard",
                "start",
                "--no-browser",
                "--port",
                str(port),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._dashboard_started = datetime.now(UTC)
            # Give server time to bind
            await asyncio.sleep(1.0)
        except Exception:  # noqa: BLE001
            return ProcessInfo(name="dashboard", running=False, port=port)

        return self.dashboard_status(port)

    async def stop_dashboard(self) -> bool:
        """Stop the managed dashboard subprocess."""
        proc = self._dashboard_proc
        if proc is None or proc.returncode is not None:
            return False

        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except TimeoutError:
                proc.kill()
            self._dashboard_proc = None
            self._dashboard_started = None
            return True
        except Exception:  # noqa: BLE001
            return False

    def dashboard_status(self, port: int = 3737) -> ProcessInfo:
        """Check dashboard status via socket probe."""
        effective_port = port or self._dashboard_port
        listening = _dashboard_healthy(effective_port)
        pid: int | None = None
        if self._dashboard_proc is not None and self._dashboard_proc.returncode is None:
            pid = self._dashboard_proc.pid

        return ProcessInfo(
            name="dashboard",
            pid=pid,
            running=listening,
            started_at=self._dashboard_started if listening else None,
            port=effective_port,
        )

    # ------------------------------------------------------------------
    # Agent
    # ------------------------------------------------------------------

    async def start_agent(self, tool: str = "claude", args: list[str] | None = None) -> ProcessInfo:
        """Start an agent subprocess via ``atlasbridge run <tool>``."""
        if self._agent_proc is not None and self._agent_proc.returncode is None:
            return self.agent_status()

        try:
            cmd = [sys.executable, "-m", "atlasbridge", "run", tool]
            if args:
                cmd.extend(args)
            self._agent_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                stdin=asyncio.subprocess.DEVNULL,
            )
            self._agent_tool = tool
            self._agent_started = datetime.now(UTC)
        except Exception:  # noqa: BLE001
            return ProcessInfo(name="agent", running=False, tool=tool)

        return self.agent_status()

    async def stop_agent(self) -> bool:
        """Stop the managed agent subprocess."""
        proc = self._agent_proc
        if proc is None or proc.returncode is not None:
            return False

        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()
            self._agent_proc = None
            self._agent_started = None
            return True
        except Exception:  # noqa: BLE001
            return False

    def agent_status(self) -> ProcessInfo:
        """Check agent subprocess status."""
        proc = self._agent_proc
        if proc is not None and proc.returncode is None:
            return ProcessInfo(
                name="agent",
                pid=proc.pid,
                running=True,
                started_at=self._agent_started,
                tool=self._agent_tool,
            )
        return ProcessInfo(name="agent", running=False, tool=self._agent_tool)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def shutdown_all(self) -> None:
        """Stop all managed processes in reverse start order."""
        await self.stop_agent()
        await self.stop_dashboard()
        await self.stop_daemon()

    def all_status(self) -> list[ProcessInfo]:
        """Return status of all managed process types."""
        return [
            self.daemon_status(),
            self.dashboard_status(self._dashboard_port),
            self.agent_status(),
        ]
