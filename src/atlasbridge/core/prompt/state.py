"""
Prompt lifecycle state machine.

  CREATED → ROUTED → AWAITING_REPLY → REPLY_RECEIVED → INJECTED → RESOLVED
                                                               ↓
                                              EXPIRED / CANCELED / FAILED

Rules:
  - Only one ACTIVE prompt per session at a time.
  - Subsequent prompts are queued until the active prompt reaches a terminal state.
  - All transitions are logged to the audit store.
  - Expired prompts refuse further replies.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from atlasbridge.core.prompt.models import PromptEvent, PromptStatus

VALID_TRANSITIONS: dict[PromptStatus, set[PromptStatus]] = {
    PromptStatus.CREATED: {PromptStatus.ROUTED, PromptStatus.FAILED, PromptStatus.CANCELED},
    PromptStatus.ROUTED: {PromptStatus.AWAITING_REPLY, PromptStatus.EXPIRED, PromptStatus.FAILED},
    PromptStatus.AWAITING_REPLY: {
        PromptStatus.REPLY_RECEIVED,
        PromptStatus.EXPIRED,
        PromptStatus.CANCELED,
        PromptStatus.FAILED,
    },
    PromptStatus.REPLY_RECEIVED: {PromptStatus.INJECTED, PromptStatus.FAILED},
    PromptStatus.INJECTED: {PromptStatus.RESOLVED, PromptStatus.FAILED},
    # Terminal — no outgoing transitions
    PromptStatus.RESOLVED: set(),
    PromptStatus.EXPIRED: set(),
    PromptStatus.CANCELED: set(),
    PromptStatus.FAILED: set(),
}

TERMINAL_STATES = {
    PromptStatus.RESOLVED,
    PromptStatus.EXPIRED,
    PromptStatus.CANCELED,
    PromptStatus.FAILED,
}


@dataclass
class PromptStateMachine:
    """Tracks state for a single prompt."""

    event: PromptEvent
    status: PromptStatus = PromptStatus.CREATED
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    history: list[tuple[PromptStatus, str]] = field(default_factory=list)
    on_transition: Callable[[PromptStatus, PromptStatus], None] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        from datetime import timedelta

        self.expires_at = datetime.now(UTC) + timedelta(seconds=self.event.ttl_seconds)
        self.created_at = datetime.now(UTC)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    @property
    def latency_ms(self) -> float | None:
        """Milliseconds from creation to resolution, or None if not yet resolved."""
        if self.resolved_at is None:
            return None
        return (self.resolved_at - self.created_at).total_seconds() * 1000

    def transition(self, new_status: PromptStatus, reason: str = "") -> None:
        """Advance state; raise ValueError on invalid transition."""
        if new_status not in VALID_TRANSITIONS.get(self.status, set()):
            raise ValueError(
                f"Invalid transition {self.status!r} → {new_status!r} "
                f"for prompt {self.event.prompt_id}"
            )
        old = self.status
        self.status = new_status
        self.history.append((new_status, reason or f"{old} → {new_status}"))
        if new_status == PromptStatus.RESOLVED:
            self.resolved_at = datetime.now(UTC)
        if self.on_transition:
            self.on_transition(old, new_status)

    def expire_if_due(self) -> bool:
        """Check TTL and transition to EXPIRED if overdue. Returns True if expired."""
        if not self.is_terminal and self.is_expired:
            # Force-expire even if not in AWAITING_REPLY (handle edge cases)
            try:
                self.transition(PromptStatus.EXPIRED, "TTL elapsed")
            except ValueError:
                self.status = PromptStatus.EXPIRED
                self.history.append((PromptStatus.EXPIRED, "TTL elapsed (forced)"))
            return True
        return False
