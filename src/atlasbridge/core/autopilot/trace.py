"""
Decision trace — append-only JSONL log of every autopilot decision.

Every PolicyDecision is written to ``~/.atlasbridge/autopilot_decisions.jsonl``.
Entries are never modified or deleted; when the file grows beyond ``max_bytes``
it is rotated (up to ``MAX_ARCHIVES`` archives are kept).

Usage::

    trace = DecisionTrace(path)
    trace.record(decision)

    for entry in trace.tail(n=20):
        print(entry)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

from atlasbridge.core.policy.model import PolicyDecision

logger = logging.getLogger(__name__)

TRACE_FILENAME = "autopilot_decisions.jsonl"


class DecisionTrace:
    """
    Append-only JSONL writer for autopilot decisions with size-based rotation.

    When the active trace file grows beyond ``max_bytes``, it is renamed to
    ``<name>.jsonl.1`` and a fresh file is started.  Older archives shift up
    (``...jsonl.1`` → ``...jsonl.2``, etc.).  At most ``MAX_ARCHIVES``
    archives are kept; the oldest is deleted when the limit is exceeded.

    Thread-safe for single-process use (standard append open; OS-level
    atomicity).  Not safe for concurrent multi-process writes without an
    external lock.
    """

    MAX_BYTES_DEFAULT: int = 10 * 1024 * 1024  # 10 MB
    MAX_ARCHIVES: int = 3

    def __init__(self, path: Path, max_bytes: int = MAX_BYTES_DEFAULT) -> None:
        self._path = path
        self._max_bytes = max_bytes
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def _maybe_rotate(self) -> None:
        """Rotate if the active file exceeds max_bytes."""
        if not self._path.exists():
            return
        try:
            size = self._path.stat().st_size
        except OSError:
            return
        if size < self._max_bytes:
            return

        # Shift existing archives: .jsonl.2 → .jsonl.3, .jsonl.1 → .jsonl.2
        for i in range(self.MAX_ARCHIVES - 1, 0, -1):
            old = self._path.with_suffix(f".jsonl.{i}")
            new = self._path.with_suffix(f".jsonl.{i + 1}")
            if old.exists():
                try:
                    old.rename(new)
                except OSError as exc:
                    logger.warning("DecisionTrace: cannot rotate %s → %s: %s", old, new, exc)

        # Move active file to .jsonl.1
        archive = self._path.with_suffix(".jsonl.1")
        try:
            self._path.rename(archive)
        except OSError as exc:
            logger.warning("DecisionTrace: cannot archive %s → %s: %s", self._path, archive, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, decision: PolicyDecision) -> None:
        """Append one decision to the trace file (rotating first if needed)."""
        self._maybe_rotate()
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(decision.to_json() + "\n")
        except OSError as exc:
            # Trace write failure must never crash the autopilot engine
            logger.error("DecisionTrace: failed to write to %s: %s", self._path, exc)

    def tail(self, n: int = 50) -> list[dict[str, object]]:
        """Return the last ``n`` trace entries as dicts (oldest first)."""
        if not self._path.exists():
            return []
        lines: list[str] = []
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            logger.error("DecisionTrace: cannot read %s: %s", self._path, exc)
            return []

        entries: list[dict[str, object]] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def __iter__(self) -> Iterator[dict[str, object]]:
        """Iterate over all entries in the active file (oldest first)."""
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            logger.error("DecisionTrace: cannot iterate %s: %s", self._path, exc)
