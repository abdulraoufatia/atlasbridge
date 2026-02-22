"""
BaseChannel — abstract interface for notification channels.

Concrete implementations:
  TelegramChannel  — python-telegram-bot or httpx polling
  SlackChannel     — Slack Bolt (v0.4.0)
  WhatsAppChannel  — stub (future)
  WebUIChannel     — stub (future)

A channel is responsible for:
  1. Sending prompt events to the human (forward path)
  2. Receiving replies from the human (return path)
  3. Enforcing allowlisted identities
  4. Applying rate limits

Channels must NOT inject replies directly — they enqueue Reply objects
that the PromptRouter delivers to the correct session's PTY supervisor.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import structlog

from atlasbridge.core.exceptions import ChannelUnavailableError
from atlasbridge.core.prompt.models import PromptEvent, Reply

logger = structlog.get_logger()


class ChannelCircuitBreaker:
    """
    Lightweight circuit breaker for channel send operations.

    After *threshold* consecutive failures the circuit opens and
    ``is_open`` returns True.  The circuit auto-closes after
    *recovery_seconds* so the next send attempt is allowed through
    (half-open probe).
    """

    def __init__(self, threshold: int = 3, recovery_seconds: float = 30.0) -> None:
        self.threshold = threshold
        self.recovery_seconds = recovery_seconds
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._failures < self.threshold:
            return False
        # Auto-reset after recovery window (half-open probe)
        if self._opened_at and (time.monotonic() - self._opened_at) >= self.recovery_seconds:
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold and self._opened_at is None:
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit_breaker_opened",
                failures=self._failures,
                threshold=self.threshold,
                recovery_seconds=self.recovery_seconds,
            )

    def reset(self) -> None:
        self._failures = 0
        self._opened_at = None


class BaseChannel(ABC):
    """
    Abstract notification channel.

    One channel instance is shared across all sessions.
    The channel routes prompts and replies by session_id and prompt_id.

    Includes a ``circuit_breaker`` that subclasses should consult before
    sending.  After 3 consecutive send failures the breaker opens for
    30 s, giving the backend time to recover before retrying.
    """

    #: Short identifier used in config and logs (e.g. "telegram")
    channel_name: str = ""

    #: Human-readable name shown in `atlasbridge channel list`
    display_name: str = ""

    @property
    def circuit_breaker(self) -> ChannelCircuitBreaker:
        """Per-instance circuit breaker (lazy-initialised)."""
        cb = getattr(self, "_circuit_breaker", None)
        if cb is None:
            cb = ChannelCircuitBreaker()
            self._circuit_breaker = cb
        return cb

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def start(self) -> None:
        """
        Connect to the channel backend and start receiving messages.

        For long-polling channels (Telegram): start the polling loop.
        For webhook channels (Slack): start the webhook server.
        """

    @abstractmethod
    async def close(self) -> None:
        """Disconnect from the channel backend and stop all background tasks."""

    # ------------------------------------------------------------------
    # Forward path — send prompts to the human
    # ------------------------------------------------------------------

    @abstractmethod
    async def send_prompt(self, event: PromptEvent) -> str:
        """
        Send a prompt notification to all allowlisted users.

        Returns a channel-specific message ID (used to edit/delete the
        message later, e.g. after the prompt is resolved or expires).

        Args:
            event: The PromptEvent to display to the user.

        Returns:
            Channel message ID as a string (e.g. Telegram message_id).
        """

    @abstractmethod
    async def notify(self, message: str, session_id: str = "") -> None:
        """
        Send a plain text notification (not a prompt).

        Used for: session start/end, expiry notices, error alerts.

        Args:
            message:    Text to send.
            session_id: Optional session context for routing.
        """

    @abstractmethod
    async def send_output(self, text: str, session_id: str = "") -> None:
        """
        Send CLI output text as a conversational message (not a prompt).

        Used by the OutputForwarder to stream CLI activity to the human.
        Different from ``notify()`` in that it uses monospace/code formatting
        and may be sent silently (no notification buzz).

        Args:
            text:       Cleaned CLI output text (ANSI-stripped).
            session_id: Session context for routing.
        """

    @abstractmethod
    async def edit_prompt_message(
        self,
        message_id: str,
        new_text: str,
        session_id: str = "",
    ) -> None:
        """
        Edit a previously sent prompt message (e.g. to show "Resolved: y").

        Args:
            message_id: Channel message ID returned by send_prompt().
            new_text:   New message text.
            session_id: Session context for routing.
        """

    # ------------------------------------------------------------------
    # Agent prose — rich formatted text (non-monospace)
    # ------------------------------------------------------------------

    async def send_agent_message(self, text: str, session_id: str = "") -> None:
        """
        Send agent prose as a rich-formatted message (not monospace).

        Default delegates to ``notify()``.  Channels may override for
        richer formatting (HTML on Telegram, mrkdwn on Slack).

        Args:
            text:       Agent-generated prose text (may contain markdown).
            session_id: Session context for routing.
        """
        await self.notify(text, session_id=session_id)

    # ------------------------------------------------------------------
    # Return path — receive replies from the human
    # ------------------------------------------------------------------

    @abstractmethod
    def receive_replies(self) -> AsyncIterator[Reply]:
        """
        Yield Reply objects as the human responds.

        This is an async generator. The PromptRouter consumes it in a loop:

            async for reply in channel.receive_replies():
                await router.handle_reply(reply)

        The generator must never raise; it runs for the lifetime of the daemon.
        """

    # ------------------------------------------------------------------
    # Identity enforcement
    # ------------------------------------------------------------------

    @abstractmethod
    def is_allowed(self, identity: str) -> bool:
        """
        Return True if *identity* is in the allowlist.

        identity format: "<channel>:<id>" e.g. "telegram:123456789"
        """

    # ------------------------------------------------------------------
    # Circuit-breaker guarded send
    # ------------------------------------------------------------------

    async def guarded_send(self, event: PromptEvent) -> str:
        """Send a prompt through the circuit breaker.

        If the circuit is open, raises ``ChannelUnavailableError``.
        On success, records the success. On failure, records the failure
        and re-raises.
        """
        cb = self.circuit_breaker
        if cb.is_open:
            logger.warning(
                "circuit_breaker_rejected",
                channel=self.channel_name,
                failures=cb._failures,
            )
            raise ChannelUnavailableError(
                f"Circuit breaker open for {self.channel_name} "
                f"({cb._failures} consecutive failures)"
            )
        try:
            result = await self.send_prompt(event)
            cb.record_success()
            return result
        except Exception:
            cb.record_failure()
            raise

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def healthcheck(self) -> dict[str, Any]:
        """
        Return health status for this channel.

        Called by `atlasbridge doctor`. Default returns {"status": "ok"}.
        """
        cb = self.circuit_breaker
        status = "degraded" if cb.is_open else "ok"
        return {
            "status": status,
            "channel": self.channel_name,
            "circuit_breaker": {
                "open": cb.is_open,
                "failures": cb._failures,
                "threshold": cb.threshold,
            },
        }
