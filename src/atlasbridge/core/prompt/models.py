"""
Prompt domain models.

PromptEvent  — emitted by the detector when the CLI awaits input.
Reply        — a user's response arriving from a channel.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC
from enum import StrEnum
from typing import Any


class PromptType(StrEnum):
    TYPE_YES_NO = "yes_no"
    TYPE_CONFIRM_ENTER = "confirm_enter"
    TYPE_MULTIPLE_CHOICE = "multiple_choice"
    TYPE_FREE_TEXT = "free_text"


class Confidence(StrEnum):
    HIGH = "high"
    MED = "medium"
    LOW = "low"


class PromptStatus(StrEnum):
    CREATED = "created"
    ROUTED = "routed"
    AWAITING_REPLY = "awaiting_reply"
    REPLY_RECEIVED = "reply_received"
    INJECTED = "injected"
    RESOLVED = "resolved"
    # Terminal states
    EXPIRED = "expired"
    CANCELED = "canceled"
    FAILED = "failed"


@dataclass
class PromptEvent:
    """Emitted by the detector when the CLI is awaiting input."""

    prompt_id: str
    session_id: str
    prompt_type: PromptType
    confidence: Confidence
    excerpt: str  # Redacted/truncated display text for channel
    choices: list[str] = field(default_factory=list)  # For MULTIPLE_CHOICE / YES_NO
    constraints: dict[str, Any] = field(default_factory=dict)  # e.g. {"max_length": 50}
    idempotency_key: str = field(default_factory=lambda: secrets.token_hex(8))
    timestamp: str = ""  # ISO8601 — set on creation
    raw_bytes: bytes = field(
        default=b"", repr=False
    )  # Original terminal bytes (not sent to channel)
    ttl_seconds: int = 300  # Default 5 min TTL

    # Session context — populated by PromptRouter before dispatch
    tool: str = ""  # Adapter name (e.g. "claude", "openai", "gemini")
    cwd: str = ""  # Working directory of the session
    session_label: str = ""  # Optional human label (e.g. git branch name)

    @classmethod
    def create(
        cls,
        session_id: str,
        prompt_type: PromptType,
        confidence: Confidence,
        excerpt: str,
        choices: list[str] | None = None,
        constraints: dict[str, Any] | None = None,
        raw_bytes: bytes = b"",
        ttl_seconds: int = 300,
    ) -> PromptEvent:
        from datetime import datetime

        return cls(
            prompt_id=secrets.token_hex(12),
            session_id=session_id,
            prompt_type=prompt_type,
            confidence=confidence,
            excerpt=excerpt[:200],  # Max 200 chars to channel
            choices=choices or [],
            constraints=constraints or {},
            timestamp=datetime.now(UTC).isoformat(),
            raw_bytes=raw_bytes,
            ttl_seconds=ttl_seconds,
        )


@dataclass
class Reply:
    """A user's response arriving from a channel, ready to inject into the CLI."""

    prompt_id: str
    session_id: str
    value: str  # Normalized value to inject into stdin
    nonce: str  # One-time token; duplicate nonces rejected
    channel_identity: str  # e.g. "telegram:123456789"
    timestamp: str  # ISO8601
    newline_policy: str = "append"  # "append" | "none" | "replace"
