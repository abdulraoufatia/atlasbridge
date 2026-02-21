"""
Enterprise audit integrity — hash-chained decision trace v2.

Provides:
  - DecisionTraceEntryV2 — enriched trace schema with hash chaining
  - EnterpriseTraceIntegrity — trace verification and integrity checking

Maturity: Experimental (Phase A scaffolding)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger()


@dataclass
class DecisionTraceEntryV2:
    """Enriched decision trace entry with full governance context.

    This is a superset of the v1 trace entry.  All new fields are optional
    to maintain backward compatibility — existing v1 entries can be read
    alongside v2 entries.

    Hash chaining: each entry includes ``previous_hash`` (the hash of the
    prior entry) and ``current_hash`` (SHA-256 of this entry's content
    excluding ``current_hash`` itself).  This forms an append-only chain
    where tampering or truncation is detectable.
    """

    # Identity
    session_id: str = ""
    prompt_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Policy context
    policy_version: str = ""
    policy_hash: str = ""
    matched_rule: str = ""
    evaluation_details: str = ""

    # Risk assessment
    risk_level: str = "low"  # low | medium | high | critical

    # Decision
    confidence: str = ""
    action_taken: str = ""
    idempotency_key: str = ""

    # Escalation
    escalation_status: str = ""  # "" | "escalated" | "resolved" | "timeout"
    human_actor: str = ""  # channel identity of human who responded

    # CI context
    ci_status_snapshot: str = ""  # "passing" | "failing" | "unknown" | ""

    # Integrity
    replay_safe: bool = True
    previous_hash: str = ""
    current_hash: str = ""

    # Schema version
    trace_version: str = "2"

    def compute_hash(self) -> str:
        """Compute SHA-256 of this entry (excluding current_hash)."""
        d = asdict(self)
        d.pop("current_hash", None)
        canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def seal(self, previous_hash: str = "") -> None:
        """Set previous_hash and compute current_hash."""
        self.previous_hash = previous_hash
        self.current_hash = self.compute_hash()

    def to_json(self) -> str:
        """Serialize to a single JSON line."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> DecisionTraceEntryV2:
        """Deserialize from a JSON line."""
        data = json.loads(line)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class EnterpriseTraceIntegrity:
    """Verify integrity of the hash-chained decision trace.

    This class reads trace files and validates:
    - Each entry's current_hash matches its content
    - Each entry's previous_hash matches the prior entry's current_hash
    - No entries have been removed or reordered
    """

    @staticmethod
    def verify_chain(path: Path) -> dict[str, object]:
        """Verify the hash chain of a trace file.

        Returns:
            {
                "valid": bool,
                "entries_checked": int,
                "first_broken_at": int | None,
                "error": str | None,
            }
        """
        if not path.exists():
            return {
                "valid": True,
                "entries_checked": 0,
                "first_broken_at": None,
                "error": None,
            }

        entries: list[DecisionTraceEntryV2] = []
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # Only validate v2 entries (v1 entries lack hash fields)
                    if data.get("trace_version") == "2":
                        entries.append(DecisionTraceEntryV2.from_json(line))
        except OSError as exc:
            return {
                "valid": False,
                "entries_checked": 0,
                "first_broken_at": None,
                "error": str(exc),
            }

        prev_hash = ""
        for i, entry in enumerate(entries):
            # Verify self-hash
            expected = entry.compute_hash()
            if entry.current_hash != expected:
                return {
                    "valid": False,
                    "entries_checked": i + 1,
                    "first_broken_at": i,
                    "error": f"Entry {i}: current_hash mismatch",
                }
            # Verify chain link
            if entry.previous_hash != prev_hash:
                return {
                    "valid": False,
                    "entries_checked": i + 1,
                    "first_broken_at": i,
                    "error": f"Entry {i}: previous_hash mismatch",
                }
            prev_hash = entry.current_hash

        return {
            "valid": True,
            "entries_checked": len(entries),
            "first_broken_at": None,
            "error": None,
        }
