"""Aegis audit log: append-only, hash-chained JSON Lines writer."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.store.models import AuditEvent


class AuditWriter:
    """
    Thread-safe append-only audit log with SHA-256 hash chain.

    Each line is a JSON object; the ``hash`` field commits to the
    previous entry's hash (``prev_hash``), forming an immutable chain.
    The chain head is kept in memory so the writer never needs to seek.

    File is opened in append mode so concurrent readers (e.g. ``aegis
    logs``) see complete lines.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._prev_hash: str = "genesis"
        self._file = None

    def open(self) -> None:
        """Open (or create) the audit log and replay last hash from disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)

        # Replay the last line to recover the hash chain head
        last_hash = _read_last_hash(self.path)
        if last_hash:
            self._prev_hash = last_hash

        self._file = open(self.path, "a", buffering=1, encoding="utf-8")  # line-buffered

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    def write(self, event: AuditEvent) -> None:
        """Compute hash, update chain, append JSON line. Thread-safe."""
        with self._lock:
            event.prev_hash = self._prev_hash
            event.hash = _compute_hash(event)
            line = _serialize(event)
            assert self._file is not None, "AuditWriter.open() not called"
            self._file.write(line + "\n")
            self._prev_hash = event.hash

    def write_event(
        self,
        event_id: str,
        event_type: str,
        session_id: str | None = None,
        prompt_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Convenience wrapper — build and write an AuditEvent."""
        ev = AuditEvent(
            id=event_id,
            event_type=event_type,
            ts=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            prompt_id=prompt_id,
            data_json=json.dumps(data or {}),
        )
        self.write(ev)
        return ev


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_hash(event: AuditEvent) -> str:
    payload = json.dumps(
        {
            "id": event.id,
            "event_type": event.event_type,
            "ts": event.ts,
            "session_id": event.session_id,
            "prompt_id": event.prompt_id,
            "data_json": event.data_json,
            "prev_hash": event.prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _serialize(event: AuditEvent) -> str:
    return json.dumps(
        {
            "id": event.id,
            "event_type": event.event_type,
            "ts": event.ts,
            "session_id": event.session_id,
            "prompt_id": event.prompt_id,
            "data_json": event.data_json,
            "prev_hash": event.prev_hash,
            "hash": event.hash,
        },
        separators=(",", ":"),
    )


def _read_last_hash(path: Path) -> str | None:
    """Read the ``hash`` field of the final line without loading the whole file."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)  # end
            size = f.tell()
            if size == 0:
                return None
            # Read up to the last 4 KB to find the final line efficiently
            f.seek(max(0, size - 4096))
            content = f.read().rstrip(b"\n")
            last_nl = content.rfind(b"\n")
            line = content[last_nl + 1:] if last_nl != -1 else content
        if not line:
            return None
        obj = json.loads(line)
        return obj.get("hash") or None
    except Exception:
        return None


def verify_chain(path: Path) -> tuple[bool, int, str | None]:
    """
    Verify the entire hash chain in the log file.

    Returns ``(ok, lines_checked, error_message)``.
    """
    prev = "genesis"
    count = 0
    try:
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    return False, count, f"line {lineno}: invalid JSON — {exc}"

                if obj.get("prev_hash") != prev:
                    return (
                        False,
                        count,
                        f"line {lineno}: prev_hash mismatch "
                        f"(expected {prev!r}, got {obj.get('prev_hash')!r})",
                    )

                # Rebuild event for hash verification
                ev = AuditEvent(
                    id=obj["id"],
                    event_type=obj["event_type"],
                    ts=obj["ts"],
                    session_id=obj.get("session_id"),
                    prompt_id=obj.get("prompt_id"),
                    data_json=obj.get("data_json", "{}"),
                    prev_hash=obj["prev_hash"],
                )
                expected = _compute_hash(ev)
                if obj.get("hash") != expected:
                    return (
                        False,
                        count,
                        f"line {lineno}: hash mismatch "
                        f"(expected {expected[:16]}…, got {str(obj.get('hash', ''))[:16]}…)",
                    )

                prev = obj["hash"]
                count += 1
    except FileNotFoundError:
        return False, 0, "audit log not found"
    except Exception as exc:
        return False, count, str(exc)

    return True, count, None
