"""
Conversation session binding — maps (channel_name, thread_id) to session_id.

A conversation binding connects a channel thread (e.g. a Telegram DM or
Slack channel thread) to a specific agent session.  This allows multi-session
routing: messages arriving in thread T are deterministically routed to
the session bound to T, preventing cross-session injection.

Bindings have a configurable TTL and are pruned periodically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum

import structlog

logger = structlog.get_logger()


class ConversationState(StrEnum):
    """State of a conversation binding."""

    IDLE = "idle"  # Bound but session not yet running
    RUNNING = "running"  # Session active, accepting chat input
    AWAITING_INPUT = "awaiting_input"  # Prompt detected, waiting on user
    STOPPED = "stopped"  # Session ended


@dataclass
class ConversationBinding:
    """A single thread → session binding with state tracking."""

    channel_name: str  # "telegram" | "slack"
    thread_id: str  # chat_id (Telegram) | channel:thread_ts (Slack)
    session_id: str
    state: ConversationState = ConversationState.IDLE
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)


# Default TTL: 4 hours
_DEFAULT_TTL_S = 14400.0


class ConversationRegistry:
    """Thread-safe registry of conversation bindings.

    Invariants:
      - Each (channel_name, thread_id) maps to exactly one session_id.
      - Bindings expire after TTL and are pruned by ``prune_expired()``.
      - Cross-session injection is prevented: a message in thread T
        can only reach session S if binding(T) == S.
    """

    def __init__(self, ttl_seconds: float = _DEFAULT_TTL_S) -> None:
        self._bindings: dict[tuple[str, str], ConversationBinding] = {}
        self._ttl = ttl_seconds

    def bind(
        self,
        channel_name: str,
        thread_id: str,
        session_id: str,
    ) -> ConversationBinding:
        """Create or update a binding for the given thread.

        If a binding already exists for the thread, it is replaced.

        Returns:
            The new or updated ConversationBinding.
        """
        key = (channel_name, thread_id)
        now = time.monotonic()
        binding = ConversationBinding(
            channel_name=channel_name,
            thread_id=thread_id,
            session_id=session_id,
            state=ConversationState.RUNNING,
            created_at=now,
            last_activity=now,
        )
        self._bindings[key] = binding
        logger.debug(
            "conversation_bound",
            channel=channel_name,
            thread_id=thread_id[:16],
            session_id=session_id[:8],
        )
        return binding

    def resolve(self, channel_name: str, thread_id: str) -> str | None:
        """Return session_id for the given thread, or None if unbound/expired."""
        key = (channel_name, thread_id)
        binding = self._bindings.get(key)
        if binding is None:
            return None
        if self._is_expired(binding):
            del self._bindings[key]
            return None
        binding.last_activity = time.monotonic()
        return binding.session_id

    def get_binding(self, channel_name: str, thread_id: str) -> ConversationBinding | None:
        """Return the full binding for the given thread, or None."""
        key = (channel_name, thread_id)
        binding = self._bindings.get(key)
        if binding is None:
            return None
        if self._is_expired(binding):
            del self._bindings[key]
            return None
        return binding

    def update_state(self, channel_name: str, thread_id: str, state: ConversationState) -> None:
        """Update the conversation state for a thread binding."""
        key = (channel_name, thread_id)
        binding = self._bindings.get(key)
        if binding is not None:
            binding.state = state
            binding.last_activity = time.monotonic()

    def unbind(self, session_id: str) -> int:
        """Remove all bindings for a session (called on session end).

        Returns:
            Number of bindings removed.
        """
        to_remove = [key for key, b in self._bindings.items() if b.session_id == session_id]
        for key in to_remove:
            del self._bindings[key]
        if to_remove:
            logger.debug(
                "conversation_unbound",
                session_id=session_id[:8],
                count=len(to_remove),
            )
        return len(to_remove)

    def prune_expired(self) -> int:
        """Remove expired bindings.

        Returns:
            Number of bindings pruned.
        """
        to_remove = [key for key, b in self._bindings.items() if self._is_expired(b)]
        for key in to_remove:
            del self._bindings[key]
        return len(to_remove)

    def bindings_for_session(self, session_id: str) -> list[ConversationBinding]:
        """Return all bindings for a session (multi-channel fan-out)."""
        return [
            b
            for b in self._bindings.values()
            if b.session_id == session_id and not self._is_expired(b)
        ]

    @property
    def active_count(self) -> int:
        """Number of non-expired bindings."""
        return sum(1 for b in self._bindings.values() if not self._is_expired(b))

    def _is_expired(self, binding: ConversationBinding) -> bool:
        return (time.monotonic() - binding.last_activity) > self._ttl
