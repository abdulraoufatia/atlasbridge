"""
Enterprise policy lifecycle — pinning, validation, and session binding.

Provides:
  - PolicyPin — session-level policy hash binding
  - PolicyPinManager — tracks pinned policies per session

Maturity: Experimental (Phase A scaffolding)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()


@dataclass
class PolicyPin:
    """A session-level policy pin.

    Captures the policy hash at session start.  If the policy changes
    mid-session, the pin detects the drift.
    """

    session_id: str
    policy_hash: str
    policy_version: str
    pinned_at: str  # ISO8601

    def is_valid(self, current_hash: str) -> bool:
        """Check if the current policy hash matches the pin."""
        return self.policy_hash == current_hash


class PolicyPinManager:
    """Manages policy pins for active sessions.

    At session start, the current policy hash is captured and stored.
    On each policy evaluation, the manager checks for drift.

    This is a local-only, in-memory registry.  Pins are not persisted
    across daemon restarts (they are re-captured on session start).
    """

    def __init__(self) -> None:
        self._pins: dict[str, PolicyPin] = {}

    def pin(self, session_id: str, policy_hash: str, policy_version: str) -> PolicyPin:
        """Pin the current policy for a session."""
        pin = PolicyPin(
            session_id=session_id,
            policy_hash=policy_hash,
            policy_version=policy_version,
            pinned_at=datetime.now(UTC).isoformat(),
        )
        self._pins[session_id] = pin
        logger.info(
            "policy_pinned",
            session_id=session_id[:8],
            policy_hash=policy_hash[:12],
        )
        return pin

    def check(self, session_id: str, current_hash: str) -> bool | None:
        """Check if the current policy matches the session pin.

        Returns:
            True  — pin matches (no drift)
            False — pin does NOT match (policy changed mid-session)
            None  — no pin exists for this session
        """
        pin = self._pins.get(session_id)
        if pin is None:
            return None
        return pin.is_valid(current_hash)

    def unpin(self, session_id: str) -> None:
        """Remove the pin for a session (e.g. on session end)."""
        self._pins.pop(session_id, None)

    def get(self, session_id: str) -> PolicyPin | None:
        """Get the pin for a session, if any."""
        return self._pins.get(session_id)
