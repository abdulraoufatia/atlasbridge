"""
Singleton poller lock — ensures only one Telegram getUpdates poller per bot token.

Uses fcntl.flock() on macOS/Linux for an OS-level exclusive lock.  The lock is
tied to the file descriptor lifetime: if the process crashes, the OS releases
the lock automatically.

Lock file path:
    <data_dir>/locks/telegram-<token_hash>.lock

The lock file contains the PID of the holder for diagnostics.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import structlog

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

logger = structlog.get_logger()


def _token_hash(token: str) -> str:
    """Return a short, filesystem-safe hash of the bot token."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _locks_dir() -> Path:
    """Return the locks directory inside the AtlasBridge data directory."""
    from atlasbridge.core.config import atlasbridge_dir

    return atlasbridge_dir() / "locks"


class PollerLock:
    """
    OS-level exclusive lock for the Telegram polling loop.

    Usage::

        lock = PollerLock(bot_token)
        if lock.acquire():
            # We own the poller — start polling
            ...
            lock.release()
        else:
            # Another process owns it
            print(f"Poller already running (PID {lock.holder_pid})")
    """

    def __init__(self, bot_token: str, *, locks_dir: Path | None = None) -> None:
        self._token_hash = _token_hash(bot_token)
        self._locks_dir = locks_dir or _locks_dir()
        self._lock_path = self._locks_dir / f"telegram-{self._token_hash}.lock"
        self._fd: int | None = None
        self._acquired = False

    @property
    def lock_path(self) -> Path:
        return self._lock_path

    @property
    def acquired(self) -> bool:
        return self._acquired

    @property
    def holder_pid(self) -> int | None:
        """Read the PID from the lock file (may be stale if process died)."""
        try:
            text = self._lock_path.read_text().strip()
            return int(text) if text else None
        except (FileNotFoundError, ValueError, OSError):
            return None

    def acquire(self) -> bool:
        """
        Try to acquire the exclusive poller lock.

        Returns True if acquired, False if another process holds it.
        """
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            if sys.platform == "win32":
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # Lock held by another process
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            self._acquired = False
            return False

        # Write our PID for diagnostics
        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, str(os.getpid()).encode())
        self._acquired = True
        logger.debug("poller_lock_acquired", path=str(self._lock_path), pid=os.getpid())
        return True

    def release(self) -> None:
        """Release the lock and close the file descriptor."""
        if self._fd is not None:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        self._acquired = False
        # Clean up the lock file
        self._lock_path.unlink(missing_ok=True)
        logger.debug("poller_lock_released", path=str(self._lock_path))

    def __del__(self) -> None:
        if self._fd is not None:
            self.release()


def check_stale_lock(bot_token: str, *, locks_dir: Path | None = None) -> dict:
    """
    Doctor check: detect stale poller lock.

    Returns a dict with 'status' and 'detail' keys.
    """
    token_hash = _token_hash(bot_token)
    base = locks_dir or _locks_dir()
    lock_path = base / f"telegram-{token_hash}.lock"

    if not lock_path.exists():
        return {
            "name": "Telegram poller lock",
            "status": "pass",
            "detail": "no lock file — poller is free",
        }

    # Try to read the PID
    try:
        pid_text = lock_path.read_text().strip()
        pid = int(pid_text) if pid_text else None
    except (ValueError, OSError):
        pid = None

    if pid is None:
        return {
            "name": "Telegram poller lock",
            "status": "warn",
            "detail": f"lock file exists but no PID — may be stale: {lock_path}",
        }

    # Check if the PID is alive
    try:
        os.kill(pid, 0)
        return {
            "name": "Telegram poller lock",
            "status": "pass",
            "detail": f"poller running (PID {pid})",
        }
    except ProcessLookupError:
        # Process is dead — stale lock
        lock_path.unlink(missing_ok=True)
        return {
            "name": "Telegram poller lock",
            "status": "warn",
            "detail": f"stale lock cleaned up (dead PID {pid})",
        }
    except PermissionError:
        return {
            "name": "Telegram poller lock",
            "status": "pass",
            "detail": f"poller running (PID {pid}, different user)",
        }
