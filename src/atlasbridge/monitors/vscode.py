"""VS Code / Claude Code monitor — captures conversations from Claude Code sessions.

Two detection approaches:
1. Lock file discovery: ~/.claude/ide/*.lock contains port + auth info
2. Process detection: find running `claude` processes spawned by VS Code

Install: pip install atlasbridge[vscode-monitor]
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CLAUDE_IDE_DIR = Path.home() / ".claude" / "ide"


@dataclass
class ClaudeSession:
    """Discovered Claude Code session from lock file."""

    session_file: str
    port: int | None
    token: str
    pid: int | None = None
    workspace: str | None = None
    ide_name: str | None = None
    transport: str | None = None


def find_claude_sessions() -> list[ClaudeSession]:
    """Scan ~/.claude/ide/ for active Claude Code lock files."""
    sessions: list[ClaudeSession] = []

    if not CLAUDE_IDE_DIR.exists():
        return sessions

    for lock_file in CLAUDE_IDE_DIR.glob("*.lock"):
        try:
            data = json.loads(lock_file.read_text())
            port = data.get("port")
            token = data.get("token", data.get("authToken", ""))
            pid = data.get("pid")
            workspace_folders = data.get("workspaceFolders", [])
            workspace = workspace_folders[0] if workspace_folders else None
            ide_name = data.get("ideName")
            transport = data.get("transport")

            # Check if the process is still running
            if pid:
                try:
                    os.kill(int(pid), 0)
                except (OSError, ValueError):
                    logger.debug("Stale lock file %s (pid %s not running)", lock_file.name, pid)
                    continue

            # Accept sessions with or without a port — process-based
            # monitoring works even without a WebSocket port
            sessions.append(
                ClaudeSession(
                    session_file=lock_file.name,
                    port=int(port) if port else None,
                    token=str(token),
                    pid=int(pid) if pid else None,
                    workspace=workspace,
                    ide_name=ide_name,
                    transport=transport,
                )
            )
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.debug("Skipping lock file %s: %s", lock_file.name, exc)

    return sessions


def find_claude_processes() -> list[dict[str, Any]]:
    """Find running Claude Code processes via psutil."""
    try:
        import psutil
    except ImportError:
        logger.debug("psutil not available — process detection disabled")
        return []

    result: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "ppid"]):
        try:
            info = proc.info
            name = info.get("name", "")
            cmdline = info.get("cmdline", []) or []
            cmd_str = " ".join(cmdline)

            # Look for Claude Code processes
            if "claude" in name.lower() or "claude" in cmd_str.lower():
                # Check if parent is VS Code
                ppid = info.get("ppid")
                parent_name = ""
                if ppid:
                    try:
                        parent = psutil.Process(ppid)
                        parent_name = parent.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                result.append(
                    {
                        "pid": info["pid"],
                        "name": name,
                        "cmdline": cmd_str,
                        "parent": parent_name,
                        "is_vscode": "code" in parent_name.lower()
                        or "electron" in parent_name.lower(),
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return result


@dataclass
class MonitoredSession:
    """Tracked session in the monitor."""

    session_id: str
    key: str  # lock file name or process pid
    seq: int = 0


class VSCodeMonitor:
    """Monitor Claude Code sessions running inside VS Code."""

    def __init__(
        self,
        dashboard_url: str = "http://localhost:5000",
        poll_interval: float = 5.0,
    ) -> None:
        self._dashboard_url = dashboard_url.rstrip("/")
        self._poll_interval = poll_interval
        self._sessions: dict[str, MonitoredSession] = {}  # key → session
        self._running = False
        self._client = httpx.AsyncClient(timeout=10.0)

    async def _register_session(
        self, key: str, vendor: str, conversation_id: str, tab_url: str
    ) -> MonitoredSession:
        """Register a monitor session on the dashboard."""
        session_id = str(uuid.uuid4())
        try:
            await self._client.post(
                f"{self._dashboard_url}/api/monitor/sessions",
                json={
                    "id": session_id,
                    "vendor": vendor,
                    "conversation_id": conversation_id,
                    "tab_url": tab_url,
                },
            )
            logger.info("Registered monitor session %s for %s", session_id, key)
        except Exception as exc:
            logger.error("Failed to create monitor session: %s", exc)
        ms = MonitoredSession(session_id=session_id, key=key)
        self._sessions[key] = ms
        return ms

    async def _try_websocket(self, cs: ClaudeSession, ms: MonitoredSession) -> None:
        """Try to connect to Claude Code WebSocket and stream messages."""
        if not cs.port:
            return

        try:
            import websockets
        except ImportError:
            logger.debug("websockets not available — WebSocket monitoring disabled")
            return

        url = f"ws://localhost:{cs.port}"
        headers = {}
        if cs.token:
            headers["Authorization"] = f"Bearer {cs.token}"

        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                logger.info("Connected to Claude Code at port %d", cs.port)
                async for message in ws:
                    try:
                        data = json.loads(message)
                        role = data.get("role", "assistant")
                        content = data.get("content", "")
                        if content:
                            ms.seq += 1
                            await self._send_message(ms.session_id, role, content, ms.seq)
                    except (json.JSONDecodeError, KeyError):
                        if isinstance(message, (str, bytes)):
                            text = (
                                message
                                if isinstance(message, str)
                                else message.decode("utf-8", errors="replace")
                            )
                            if text.strip():
                                ms.seq += 1
                                await self._send_message(ms.session_id, "assistant", text, ms.seq)
        except Exception as exc:
            logger.debug("WebSocket connection to port %d failed: %s", cs.port, exc)

    async def _send_message(self, session_id: str, role: str, content: str, seq: int) -> None:
        """Send a captured message to the dashboard."""
        try:
            await self._client.post(
                f"{self._dashboard_url}/api/monitor/sessions/{session_id}/messages",
                json={
                    "messages": [
                        {
                            "role": role,
                            "content": content,
                            "vendor": "vscode-claude",
                            "seq": seq,
                            "captured_at": _iso_now(),
                        }
                    ]
                },
            )
        except Exception as exc:
            logger.error("Failed to send monitor message: %s", exc)

    async def monitor_loop(self) -> None:
        """Main loop: discover sessions, connect, capture, relay to dashboard."""
        self._running = True
        logger.info(
            "VS Code monitor started (poll=%.1fs, dashboard=%s)",
            self._poll_interval,
            self._dashboard_url,
        )

        while self._running:
            try:
                # 1. Discover from lock files (preferred — has workspace info)
                sessions = find_claude_sessions()
                for cs in sessions:
                    key = f"lock:{cs.session_file}"
                    if key not in self._sessions:
                        workspace = cs.workspace or cs.session_file
                        tab_url = f"vscode://claude-code/{workspace}"
                        conversation_id = f"claude-code-{cs.pid or cs.session_file}"
                        ms = await self._register_session(
                            key, "vscode-claude", conversation_id, tab_url
                        )
                        # Attempt WebSocket if port is available
                        if cs.port:
                            asyncio.create_task(self._try_websocket(cs, ms))

                # 2. Discover from running processes (fallback)
                lock_pids = {cs.pid for cs in sessions if cs.pid}
                processes = find_claude_processes()
                for proc in processes:
                    pid = proc["pid"]
                    # Skip if already tracked via lock file
                    if pid in lock_pids:
                        continue
                    key = f"proc:{pid}"
                    if key not in self._sessions:
                        vscode_tag = " (VS Code)" if proc["is_vscode"] else ""
                        logger.info(
                            "Registering Claude process: pid=%d %s%s",
                            pid,
                            proc["name"],
                            vscode_tag,
                        )
                        await self._register_session(
                            key,
                            "vscode-claude",
                            f"claude-process-{pid}",
                            f"process://{proc['name']}/{pid}",
                        )

            except Exception as exc:
                logger.error("VS Code monitor poll error: %s", exc)

            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False


def _iso_now() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


async def run_vscode_monitor(
    dashboard_url: str = "http://localhost:5000",
    poll_interval: float = 5.0,
) -> None:
    """Entry point for VS Code / Claude Code monitoring."""
    if not CLAUDE_IDE_DIR.exists():
        print(
            f"Claude IDE directory not found at {CLAUDE_IDE_DIR}\n"
            "Ensure Claude Code extension is installed in VS Code.",
        )

    monitor = VSCodeMonitor(dashboard_url=dashboard_url, poll_interval=poll_interval)
    print(f"VS Code monitor active — polling every {poll_interval}s")
    print(f"Dashboard: {dashboard_url}")
    print(f"Watching: {CLAUDE_IDE_DIR}")
    print("Press Ctrl+C to stop.\n")

    # Show initial discovery
    sessions = find_claude_sessions()
    if sessions:
        print(f"Found {len(sessions)} active Claude Code session(s):")
        for cs in sessions:
            parts = [f"pid={cs.pid}"]
            if cs.port:
                parts.append(f"port={cs.port}")
            if cs.ide_name:
                parts.append(f"ide={cs.ide_name}")
            if cs.workspace:
                parts.append(f"workspace={cs.workspace}")
            print(f"  - {' '.join(parts)}")
    else:
        print("No active Claude Code lock files found. Watching for new ones...")

    processes = find_claude_processes()
    if processes:
        print(f"\nDetected {len(processes)} Claude process(es):")
        for p in processes:
            vscode_tag = " (VS Code)" if p["is_vscode"] else ""
            print(f"  - pid={p['pid']} {p['name']}{vscode_tag}")

    print()

    try:
        await monitor.monitor_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        monitor.stop()
        print("\nVS Code monitor stopped.")
