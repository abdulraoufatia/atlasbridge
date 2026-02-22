"""
OutputForwarder — batches PTY output and forwards to channel as messages.

In Chat Mode, the human sees CLI activity as conversational messages in
their Telegram/Slack chat.  The forwarder receives raw PTY bytes via
``feed()``, strips ANSI codes, batches meaningful text for 2 seconds,
then flushes to the channel via ``send_output()``.

Rate limiting prevents flooding: max 15 messages per minute.
Tiny fragments (< 10 meaningful chars) are silently dropped.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from atlasbridge.core.prompt.sanitize import is_meaningful, strip_ansi

if TYPE_CHECKING:
    from atlasbridge.channels.base import BaseChannel
    from atlasbridge.core.interaction.output_router import OutputRouter

logger = structlog.get_logger()

# Tuning constants
BATCH_INTERVAL_S: float = 2.0
"""Seconds to collect output before sending a message."""

MAX_OUTPUT_CHARS: int = 2000
"""Truncate output messages beyond this length."""

MAX_MESSAGES_PER_MINUTE: int = 15
"""Rate limit: don't send more than N messages per minute."""

MIN_MEANINGFUL_CHARS: int = 10
"""Skip fragments shorter than this (after ANSI stripping)."""


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
    ) -> None:
        self._channel = channel
        self._session_id = session_id
        self._output_router = output_router
        self._buffer: list[str] = []
        self._buffer_chars = 0
        self._lock = asyncio.Lock()
        # Rate limiting: ring of send timestamps
        self._send_times: list[float] = []

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

    async def flush_loop(self) -> None:
        """
        Background loop that flushes the buffer every BATCH_INTERVAL_S seconds.

        Run this as a task in the session's TaskGroup. It runs until cancelled.
        """
        try:
            while True:
                await asyncio.sleep(BATCH_INTERVAL_S)
                await self._flush()
        except asyncio.CancelledError:
            # Final flush on shutdown
            await self._flush()
            raise

    async def _flush(self) -> None:
        """Drain the buffer and send to channel (if non-trivial)."""
        async with self._lock:
            if not self._buffer:
                return

            merged = "".join(self._buffer)
            self._buffer.clear()
            self._buffer_chars = 0

        # Drop tiny fragments
        stripped = merged.strip()
        if len(stripped) < MIN_MEANINGFUL_CHARS:
            return

        # Truncate
        if len(stripped) > MAX_OUTPUT_CHARS:
            stripped = stripped[:MAX_OUTPUT_CHARS] + "\n...(truncated)"

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

    async def _send_classified(self, text: str) -> None:
        """Route text through OutputRouter or send as CLI output."""
        if self._output_router is None:
            await self._channel.send_output(text, session_id=self._session_id)
            return

        from atlasbridge.core.interaction.output_router import OutputKind

        kind = self._output_router.classify(text)
        if kind == OutputKind.NOISE:
            return
        if kind == OutputKind.AGENT_MESSAGE:
            await self._channel.send_agent_message(text, session_id=self._session_id)
        else:
            await self._channel.send_output(text, session_id=self._session_id)

    def _can_send(self) -> bool:
        """Return True if we haven't exceeded MAX_MESSAGES_PER_MINUTE."""
        now = time.monotonic()
        # Prune old timestamps
        cutoff = now - 60.0
        self._send_times = [t for t in self._send_times if t > cutoff]
        return len(self._send_times) < MAX_MESSAGES_PER_MINUTE

    def _record_send(self) -> None:
        """Record a send timestamp for rate limiting."""
        self._send_times.append(time.monotonic())
