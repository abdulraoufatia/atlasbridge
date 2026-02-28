"""Desktop AI app monitor — captures conversations from macOS desktop apps via Accessibility API.

Monitors:
- Claude Desktop (claude)
- ChatGPT macOS (chatgpt)

Requires macOS Accessibility permission granted to the terminal app.
Install: pip install atlasbridge[desktop-monitor]
"""

from __future__ import annotations

import asyncio
import logging
import platform
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# App bundle identifiers for target AI desktop applications
APP_TARGETS: dict[str, str] = {
    "com.anthropic.claudefordesktop": "desktop-claude",
    "com.openai.chat": "desktop-chatgpt",
}


@dataclass
class AppSnapshot:
    """Snapshot of text content from a monitored app window."""

    pid: int
    vendor: str
    texts: list[str] = field(default_factory=list)


def _check_accessibility_imports() -> bool:
    """Check if pyobjc Accessibility framework is available."""
    try:
        import ApplicationServices  # noqa: F401
        import Cocoa  # noqa: F401

        return True
    except ImportError:
        return False


def check_accessibility_permission() -> bool:
    """Check if the current process has Accessibility permission (macOS only)."""
    if platform.system() != "Darwin":
        logger.warning("Desktop monitor is only supported on macOS")
        return False

    if not _check_accessibility_imports():
        logger.error(
            "pyobjc-framework-ApplicationServices not installed. "
            "Install with: pip install atlasbridge[desktop-monitor]"
        )
        return False

    from ApplicationServices import AXIsProcessTrusted

    trusted = AXIsProcessTrusted()
    if not trusted:
        logger.warning(
            "Accessibility permission not granted. "
            "Open System Settings > Privacy & Security > Accessibility "
            "and add your terminal app."
        )
    return bool(trusted)


def find_target_apps() -> dict[str, int]:
    """Find running AI desktop apps and return {vendor: pid} mapping."""
    from Cocoa import NSWorkspace

    workspace = NSWorkspace.sharedWorkspace()
    running_apps = workspace.runningApplications()
    found: dict[str, int] = {}

    for app in running_apps:
        bundle_id = app.bundleIdentifier()
        if bundle_id and bundle_id in APP_TARGETS:
            vendor = APP_TARGETS[bundle_id]
            pid = app.processIdentifier()
            found[vendor] = pid
            logger.info("Found %s (pid=%d, bundle=%s)", vendor, pid, bundle_id)

    return found


def read_app_text(pid: int) -> list[str]:
    """Read visible text from a macOS app window via Accessibility API."""
    from ApplicationServices import (
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
    )

    app_ref = AXUIElementCreateApplication(pid)
    texts: list[str] = []

    def _traverse(element: Any, depth: int = 0) -> None:
        if depth > 15:
            return
        # Try to get text value
        err, value = AXUIElementCopyAttributeValue(element, "AXValue", None)
        if err == 0 and isinstance(value, str) and value.strip():
            texts.append(value.strip())

        # Try static text
        err, role = AXUIElementCopyAttributeValue(element, "AXRole", None)
        if err == 0 and role == "AXStaticText":
            err, value = AXUIElementCopyAttributeValue(element, "AXValue", None)
            if err == 0 and isinstance(value, str) and value.strip():
                if value.strip() not in texts:
                    texts.append(value.strip())

        # Traverse children
        err, children = AXUIElementCopyAttributeValue(element, "AXChildren", None)
        if err == 0 and children:
            for child in children:
                _traverse(child, depth + 1)

    try:
        _traverse(app_ref)
    except Exception as exc:
        logger.debug("AX traversal error for pid %d: %s", pid, exc)

    return texts


class DesktopMonitor:
    """Poll macOS desktop AI apps for conversation text via Accessibility API."""

    def __init__(
        self,
        dashboard_url: str = "http://localhost:5000",
        poll_interval: float = 3.0,
    ) -> None:
        self._dashboard_url = dashboard_url.rstrip("/")
        self._poll_interval = poll_interval
        self._sessions: dict[str, str] = {}  # vendor → session_id
        self._previous_texts: dict[str, list[str]] = {}  # vendor → last snapshot
        self._seq_counters: dict[str, int] = {}  # session_id → seq
        self._running = False
        self._client = httpx.AsyncClient(timeout=10.0)

    async def _create_session(self, vendor: str, pid: int) -> str:
        """Create a monitor session on the dashboard."""
        session_id = str(uuid.uuid4())
        try:
            await self._client.post(
                f"{self._dashboard_url}/api/monitor/sessions",
                json={
                    "id": session_id,
                    "vendor": vendor,
                    "conversation_id": f"{vendor}-{pid}",
                    "tab_url": f"desktop://{vendor}",
                },
            )
        except Exception as exc:
            logger.error("Failed to create monitor session: %s", exc)
        self._sessions[vendor] = session_id
        self._seq_counters[session_id] = 0
        return session_id

    async def _send_messages(self, session_id: str, new_texts: list[str], vendor: str) -> None:
        """Send new text chunks to dashboard as messages."""
        messages = []
        for text in new_texts:
            self._seq_counters[session_id] = self._seq_counters.get(session_id, 0) + 1
            messages.append(
                {
                    "role": "assistant",  # Desktop apps: we capture visible text
                    "content": text,
                    "vendor": vendor,
                    "seq": self._seq_counters[session_id],
                    "captured_at": _iso_now(),
                }
            )
        if messages:
            try:
                await self._client.post(
                    f"{self._dashboard_url}/api/monitor/sessions/{session_id}/messages",
                    json={"messages": messages},
                )
            except Exception as exc:
                logger.error("Failed to send monitor messages: %s", exc)

    async def poll_loop(self) -> None:
        """Main polling loop — discover apps, diff text, relay to dashboard."""
        self._running = True
        logger.info(
            "Desktop monitor started (poll=%.1fs, dashboard=%s)",
            self._poll_interval,
            self._dashboard_url,
        )

        while self._running:
            try:
                apps = find_target_apps()
                for vendor, pid in apps.items():
                    # Ensure session exists
                    if vendor not in self._sessions:
                        await self._create_session(vendor, pid)

                    # Read current text
                    current_texts = read_app_text(pid)
                    previous = self._previous_texts.get(vendor, [])

                    # Diff: find new text not in previous snapshot
                    prev_set = set(previous)
                    new_texts = [t for t in current_texts if t not in prev_set]

                    if new_texts:
                        session_id = self._sessions[vendor]
                        await self._send_messages(session_id, new_texts, vendor)

                    self._previous_texts[vendor] = current_texts

            except Exception as exc:
                logger.error("Desktop monitor poll error: %s", exc)

            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False


def _iso_now() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


async def run_desktop_monitor(
    dashboard_url: str = "http://localhost:5000",
    poll_interval: float = 3.0,
) -> None:
    """Entry point for desktop monitoring."""
    if platform.system() != "Darwin":
        print("Desktop monitor is only supported on macOS.", file=sys.stderr)
        raise SystemExit(1)

    if not _check_accessibility_imports():
        print(
            "Missing dependency: pyobjc-framework-ApplicationServices\n"
            "Install with: pip install atlasbridge[desktop-monitor]",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not check_accessibility_permission():
        print(
            "\nAccessibility permission required.\n"
            "Open System Settings > Privacy & Security > Accessibility\n"
            "Add your terminal app (Terminal.app / iTerm2 / VS Code)\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    monitor = DesktopMonitor(dashboard_url=dashboard_url, poll_interval=poll_interval)
    print(f"Desktop monitor active — polling every {poll_interval}s")
    print(f"Dashboard: {dashboard_url}")
    print("Press Ctrl+C to stop.\n")

    try:
        await monitor.poll_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        monitor.stop()
        print("\nDesktop monitor stopped.")
