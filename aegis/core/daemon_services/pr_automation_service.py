"""
Aegis PR automation daemon service.

Runs the PRAutomationEngine on a configurable polling interval.
Manages lifecycle (start, stop, status) via a PID file so it can
be controlled from the CLI or an external process manager.

Architecture
------------
``start()`` forks a child process that runs the asyncio polling loop.
The parent writes a PID file and returns immediately.  The child runs
until signalled (SIGTERM / SIGINT) or until ``stop()`` is called from
another process.

This is a simple, dependency-free approach — no systemd, no Celery.
The longer-term path (webhooks instead of polling) is supported by
swapping out ``_polling_loop`` for a webhook receiver without changing
the lifecycle management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegis.core.pr_automation import AutoPRConfig, PRAutomationEngine, PRResult

log = logging.getLogger(__name__)

# PID file location
_PID_FILE = Path.home() / ".aegis" / "pr_auto.pid"
_STATUS_FILE = Path.home() / ".aegis" / "pr_auto_status.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start(config: AutoPRConfig, poll_interval: int = 300) -> int:
    """
    Fork and start the polling daemon.

    Returns the child PID. Raises RuntimeError if already running.
    """
    if is_running():
        pid = _read_pid()
        raise RuntimeError(f"PR automation already running (pid={pid})")

    pid = os.fork()
    if pid == 0:
        # Child process
        _run_daemon(config, poll_interval)
        sys.exit(0)

    # Parent: write PID file and return
    _write_pid(pid)
    log.info("PR automation daemon started (pid=%d)", pid)
    return pid


def stop() -> bool:
    """
    Send SIGTERM to the daemon process.
    Returns True if a running process was found and signalled.
    """
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        _clear_pid()
        log.info("Sent SIGTERM to PR automation daemon (pid=%d)", pid)
        return True
    except ProcessLookupError:
        _clear_pid()
        return False


def is_running() -> bool:
    """Return True if the daemon process appears to be running."""
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # signal 0 = existence check
        return True
    except (ProcessLookupError, PermissionError):
        _clear_pid()
        return False


def get_status() -> dict[str, Any]:
    """Return the last recorded status snapshot."""
    if not _STATUS_FILE.exists():
        return {"running": is_running(), "last_cycle": None, "results": []}
    try:
        data = json.loads(_STATUS_FILE.read_text())
        data["running"] = is_running()
        return data
    except Exception:
        return {"running": is_running(), "last_cycle": None, "results": []}


async def run_once(config: AutoPRConfig) -> list[PRResult]:
    """Run a single triage cycle synchronously (no daemon)."""
    engine = PRAutomationEngine(config)
    results = await engine.run_cycle()
    _write_status(results)
    return results


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------


def _run_daemon(config: AutoPRConfig, poll_interval: int) -> None:
    """Entry point for the forked daemon process."""
    # Detach from parent terminal
    os.setsid()

    # Set up signal handlers
    def _shutdown(sig: int, frame: Any) -> None:
        log.info("PR automation daemon shutting down (sig=%d)", sig)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s pr_auto: %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(_polling_loop(config, poll_interval))


async def _polling_loop(config: AutoPRConfig, interval: int) -> None:
    log.info(
        "PR automation polling loop started (interval=%ds, dry_run=%s)",
        interval, config.dry_run,
    )
    while True:
        try:
            engine = PRAutomationEngine(config)
            results = await engine.run_cycle()
            _write_status(results)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.exception("PR automation cycle error: %s", exc)

        log.debug("Next cycle in %ds", interval)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# PID / status file helpers
# ---------------------------------------------------------------------------


def _write_pid(pid: int) -> None:
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(pid))


def _read_pid() -> int | None:
    try:
        return int(_PID_FILE.read_text().strip())
    except Exception:
        return None


def _clear_pid() -> None:
    _PID_FILE.unlink(missing_ok=True)


def _write_status(results: list[PRResult]) -> None:
    _STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "last_cycle": datetime.now(UTC).isoformat(),
        "results": [
            {
                "pr_number": r.pr_number,
                "pr_title": r.pr_title,
                "branch": r.branch,
                "merged": r.merged,
                "skipped": r.skipped,
                "skip_reason": str(r.skip_reason) if r.skip_reason else None,
                "fix_attempts": r.fix_attempts,
                "commit_sha": r.commit_sha,
                "error": r.error,
                "timestamp": r.timestamp,
            }
            for r in results
        ],
    }
    _STATUS_FILE.write_text(json.dumps(data, indent=2))
