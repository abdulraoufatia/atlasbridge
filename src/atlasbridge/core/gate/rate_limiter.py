"""Token-bucket rate limiter for incoming channel messages.

Per-user, per-channel rate limiting. In-memory only — resets on daemon
restart. No database or network dependencies.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Absolute minimum rate — policy can raise but never lower below this.
_FLOOR_PER_MINUTE: int = 1


@dataclass
class _TokenBucket:
    """Single token bucket with refill."""

    rate: float  # tokens per minute
    burst: int  # max tokens
    tokens: float = 0.0
    last_refill: float = 0.0

    def __post_init__(self) -> None:
        if self.last_refill == 0.0:
            self.last_refill = time.monotonic()
        # Start with full burst allowance.
        if self.tokens == 0.0:
            self.tokens = float(self.burst)

    def consume(self) -> bool:
        """Try to consume one token. Return True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * (self.rate / 60.0))
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


@dataclass
class ChannelRateLimiter:
    """Rate limiter for incoming channel messages.

    Args:
        max_per_minute: Maximum sustained messages per minute. Enforced
            floor of 1/min — cannot be disabled.
        burst: Maximum burst size (messages allowed in rapid succession).
    """

    max_per_minute: int = 10
    burst: int = 3
    _buckets: dict[str, _TokenBucket] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # Enforce floor — policy can raise but never disable.
        if self.max_per_minute < _FLOOR_PER_MINUTE:
            self.max_per_minute = _FLOOR_PER_MINUTE
        if self.burst < 1:
            self.burst = 1

    def check(self, channel: str, user_id: str) -> bool:
        """Return True if the message is allowed, False if rate-limited."""
        key = f"{channel}:{user_id}"
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _TokenBucket(
                rate=float(self.max_per_minute),
                burst=self.burst,
            )
            self._buckets[key] = bucket
        return bucket.consume()

    def reset(self) -> None:
        """Clear all buckets (e.g., on daemon restart)."""
        self._buckets.clear()
