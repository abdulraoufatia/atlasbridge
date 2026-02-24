"""
OutputForwarder — batches PTY output and forwards to channel as messages.

In Chat Mode, the human sees CLI activity as conversational messages in
their Telegram/Slack chat.  The forwarder receives raw PTY bytes via
``feed()``, strips ANSI codes, batches meaningful text for 2 seconds,
then flushes to the channel via ``send_output()``.

Rate limiting prevents flooding: max 15 messages per minute.
Tiny fragments (< 10 meaningful chars) are silently dropped.

Optional features (when ``StreamingConfig`` is provided):
  - Secret redaction: token patterns stripped before sending
  - Message editing: re-use last message ID for streaming updates
  - State transitions: STREAMING on output, RUNNING after idle cycles
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from atlasbridge.core.prompt.sanitize import is_meaningful, strip_ansi
from atlasbridge.core.security.redactor import redact as _redact_secrets

if TYPE_CHECKING:
    from atlasbridge.channels.base import BaseChannel
    from atlasbridge.core.config import StreamingConfig
    from atlasbridge.core.conversation.session_binding import ConversationRegistry
    from atlasbridge.core.interaction.output_router import OutputRouter
    from atlasbridge.core.interaction.streaming import StreamingManager

logger = structlog.get_logger()

# Tuning constants (used as defaults when no StreamingConfig is provided)
BATCH_INTERVAL_S: float = 2.0
"""Seconds to collect output before sending a message."""

MAX_OUTPUT_CHARS: int = 2000
"""Truncate output messages beyond this length."""

MAX_MESSAGES_PER_MINUTE: int = 15
"""Rate limit: don't send more than N messages per minute."""

MIN_MEANINGFUL_CHARS: int = 10
"""Skip fragments shorter than this (after ANSI stripping)."""

# Number of consecutive idle flush cycles before transitioning from STREAMING → RUNNING
_IDLE_CYCLES_BEFORE_RUNNING = 2


class OutputForwarder:
    """
    Buffers PTY output and periodically flushes it to a channel.

    Usage::

        forwarder = OutputForwarder(channel, session_id)
        # In the read loop:
        forwarder.feed(raw_bytes)
        # In a TaskGroup:
        await forwarder.flush_loop()
    """

    def __init__(
        self,
        channel: BaseChannel,
        session_id: str,
        output_router: OutputRouter | None = None,
        streaming_config: StreamingConfig | None = None,
        conversation_registry: ConversationRegistry | None = None,
        streaming_manager: StreamingManager | None = None,
    ) -> None:
        self._channel = channel
        self._session_id = session_id
        self._output_router = output_router
        self._conversation_registry = conversation_registry
        self._streaming_manager = streaming_manager
        self._buffer: list[str] = []
        self._buffer_chars = 0
        self._lock = asyncio.Lock()
        # Rate limiting: ring of send timestamps
        self._send_times: list[float] = []

        # Config-driven parameters (fallback to module constants)
        if streaming_config is not None:
            self._batch_interval = streaming_config.batch_interval_s
            self._max_output_chars = streaming_config.max_output_chars
            self._max_messages_per_minute = streaming_config.max_messages_per_minute
            self._min_meaningful_chars = streaming_config.min_meaningful_chars
            self._edit_last_message = streaming_config.edit_last_message
            self._redact_secrets = streaming_config.redact_secrets
        else:
            self._batch_interval = BATCH_INTERVAL_S
            self._max_output_chars = MAX_OUTPUT_CHARS
            self._max_messages_per_minute = MAX_MESSAGES_PER_MINUTE
            self._min_meaningful_chars = MIN_MEANINGFUL_CHARS
            self._edit_last_message = True
            self._redact_secrets = True

        # Message editing state
        self._last_message_id: str = ""

        # Idle cycle counter for STREAMING → RUNNING transition
        self._idle_cycles = 0

    def feed(self, raw: bytes) -> None:
        """
        Accept raw PTY bytes, strip ANSI, and buffer meaningful text.

        This is called synchronously from the read loop. The buffer is
        drained asynchronously by ``flush_loop()``.
        """
        try:
            text = strip_ansi(raw.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            return

        if not text or not is_meaningful(text):
            return

        self._buffer.append(text)
        self._buffer_chars += len(text)

        # Reset idle counter — output is flowing
        self._idle_cycles = 0

    async def flush_loop(self) -> None:
        """
        Background loop that flushes the buffer every batch_interval seconds.

        Run this as a task in the session's TaskGroup. It runs until cancelled.
        """
        try:
            while True:
                await asyncio.sleep(self._batch_interval)
                await self._flush()
        except asyncio.CancelledError:
            # Final flush on shutdown
            await self._flush()
            raise

    async def _flush(self) -> None:
        """Drain the buffer and send to channel (if non-trivial)."""
        async with self._lock:
            if not self._buffer:
                # Buffer empty — track idle cycles for state transition
                self._idle_cycles += 1
                if self._idle_cycles >= _IDLE_CYCLES_BEFORE_RUNNING:
                    await self._transition_to_running()
                return

            merged = "".join(self._buffer)
            self._buffer.clear()
            self._buffer_chars = 0

        # Transition to STREAMING when output is flowing
        self._transition_to_streaming()

        # Drop tiny fragments
        stripped = merged.strip()
        if len(stripped) < self._min_meaningful_chars:
            return

        # Secret redaction
        if self._redact_secrets:
            stripped = self._redact(stripped)

        # Truncate
        if len(stripped) > self._max_output_chars:
            stripped = stripped[: self._max_output_chars] + "\n...(truncated)"

        # Rate limit
        if not self._can_send():
            logger.debug(
                "output_forwarder_rate_limited",
                session_id=self._session_id[:8],
                dropped_chars=len(stripped),
            )
            return

        try:
            await self._send_classified(stripped)
            self._record_send()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "output_forwarder_send_failed",
                session_id=self._session_id[:8],
                error=str(exc),
            )

    @staticmethod
    def _redact(text: str) -> str:
        """Replace secret patterns with [REDACTED]."""
        return _redact_secrets(text)

    async def _send_classified(self, text: str) -> None:
        """Route text through OutputRouter or send as CLI output."""
        # Feed to streaming manager for plan detection (regardless of router)
        if self._streaming_manager is not None:
            plan = self._streaming_manager.accumulate(text)
            if plan is not None:
                await self._streaming_manager.present_plan(plan)
                self._last_message_id = ""
                return

        if self._output_router is None:
            await self._send_output(text)
            return

        from atlasbridge.core.interaction.output_router import OutputKind

        kind = self._output_router.classify(text)
        if kind == OutputKind.NOISE:
            return
        if kind == OutputKind.PLAN_OUTPUT:
            # Plan-like output is sent as agent prose (plan detection
            # already handled above by StreamingManager if available)
            await self._channel.send_agent_message(text, session_id=self._session_id)
            self._last_message_id = ""
        elif kind == OutputKind.AGENT_MESSAGE:
            await self._channel.send_agent_message(text, session_id=self._session_id)
            # Agent messages are not editable; reset last message ID
            self._last_message_id = ""
        else:
            await self._send_output(text)

    async def _send_output(self, text: str) -> None:
        """Send CLI output, optionally editing the last message."""
        if self._edit_last_message and self._last_message_id:
            try:
                await self._channel.edit_prompt_message(
                    self._last_message_id, text, session_id=self._session_id
                )
                return
            except Exception:  # noqa: BLE001
                # Edit failed — fall through to send new message
                self._last_message_id = ""

        msg_id = await self._channel.send_output_editable(text, session_id=self._session_id)
        if msg_id:
            self._last_message_id = msg_id

    def _can_send(self) -> bool:
        """Return True if we haven't exceeded the rate limit."""
        now = time.monotonic()
        # Prune old timestamps
        cutoff = now - 60.0
        self._send_times = [t for t in self._send_times if t > cutoff]
        return len(self._send_times) < self._max_messages_per_minute

    def _record_send(self) -> None:
        """Record a send timestamp for rate limiting."""
        self._send_times.append(time.monotonic())

    # ------------------------------------------------------------------
    # Conversation state transitions
    # ------------------------------------------------------------------

    def _transition_to_streaming(self) -> None:
        """Mark the session as STREAMING in the conversation registry."""
        if self._conversation_registry is None:
            return

        from atlasbridge.core.conversation.session_binding import ConversationState

        for binding in self._conversation_registry.bindings_for_session(self._session_id):
            if binding.state != ConversationState.STREAMING:
                self._conversation_registry.transition_state(
                    binding.channel_name,
                    binding.thread_id,
                    ConversationState.STREAMING,
                )

    async def _transition_to_running(self) -> None:
        """Transition from STREAMING → RUNNING."""
        if self._conversation_registry is None:
            return

        from atlasbridge.core.conversation.session_binding import ConversationState

        for binding in self._conversation_registry.bindings_for_session(self._session_id):
            if binding.state == ConversationState.STREAMING:
                self._conversation_registry.transition_state(
                    binding.channel_name,
                    binding.thread_id,
                    ConversationState.RUNNING,
                )
