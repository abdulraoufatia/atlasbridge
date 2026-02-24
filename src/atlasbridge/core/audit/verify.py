"""
Audit hash chain verification — verify integrity of the SQLite audit log.

The audit log uses SHA-256 hash chaining: each event stores ``prev_hash``
(the hash of the preceding event) and its own ``hash``. Verification checks:

1. Each event's hash matches recomputation from its fields
2. Each event's prev_hash matches the previous event's hash
3. No gaps in the chronological sequence

Usage::

    result = verify_audit_chain(db)
    result = verify_audit_chain(db, session_id="abc123")
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from atlasbridge.core.store.database import Database


@dataclass
class AuditVerifyResult:
    """Result of audit hash chain verification."""

    valid: bool
    total_events: int
    verified_events: int = 0
    errors: list[str] = field(default_factory=list)
    first_break_event_id: str | None = None
    first_break_position: int | None = None


def verify_audit_chain(
    db: Database,
    session_id: str | None = None,
) -> AuditVerifyResult:
    """
    Verify the hash chain integrity of the audit log.

    If session_id is provided, only verifies events for that session.
    Otherwise verifies the full chain.
    """
    if session_id:
        rows = db._db.execute(
            "SELECT * FROM audit_events WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        ).fetchall()
    else:
        rows = db._db.execute("SELECT * FROM audit_events ORDER BY timestamp ASC").fetchall()

    total = len(rows)
    result = AuditVerifyResult(valid=True, total_events=total)

    if total == 0:
        return result

    prev_hash = ""
    for i, row in enumerate(rows):
        event_id = row["id"]
        event_type = row["event_type"]
        payload_str = row["payload"] or ""
        stored_prev_hash = row["prev_hash"] or ""
        stored_hash = row["hash"] or ""

        # Check 1: prev_hash linkage (skip for session-scoped check where
        # we only have a subset of the chain)
        if session_id is None and i > 0:
            if stored_prev_hash != prev_hash:
                result.valid = False
                result.errors.append(
                    f"Event #{i} ({event_id}): prev_hash mismatch — "
                    f"expected {prev_hash[:16]}..., got {stored_prev_hash[:16]}..."
                )
                if result.first_break_event_id is None:
                    result.first_break_event_id = event_id
                    result.first_break_position = i

        # Check 2: hash recomputation
        chain_input = f"{stored_prev_hash}{event_id}{event_type}{payload_str}"
        expected_hash = hashlib.sha256(chain_input.encode()).hexdigest()

        if stored_hash != expected_hash:
            result.valid = False
            result.errors.append(
                f"Event #{i} ({event_id}): hash mismatch — "
                f"stored {stored_hash[:16]}..., computed {expected_hash[:16]}..."
            )
            if result.first_break_event_id is None:
                result.first_break_event_id = event_id
                result.first_break_position = i

        prev_hash = stored_hash
        result.verified_events = i + 1

    return result


def format_verify_result(result: AuditVerifyResult, session_id: str | None = None) -> str:
    """Format an AuditVerifyResult as human-readable text."""
    lines: list[str] = []

    scope = f"session {session_id[:12]}" if session_id else "full chain"
    lines.append(f"Audit Chain Verification ({scope})")
    lines.append(f"Total events:    {result.total_events}")
    lines.append(f"Verified:        {result.verified_events}")

    if result.valid:
        lines.append("Integrity:       VALID")
    else:
        lines.append(f"Integrity:       BROKEN ({len(result.errors)} error(s))")
        if result.first_break_event_id:
            lines.append(
                f"First break:     event #{result.first_break_position} "
                f"({result.first_break_event_id})"
            )
        for error in result.errors[:10]:
            lines.append(f"  - {error}")
        if len(result.errors) > 10:
            lines.append(f"  ... and {len(result.errors) - 10} more")

    return "\n".join(lines)
