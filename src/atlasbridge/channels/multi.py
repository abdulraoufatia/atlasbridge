"""
MultiChannel — fan-out channel that wraps multiple BaseChannel instances.

Forward path: send_prompt() is broadcast to all active channels in parallel.
Return path:  receive_replies() merges asyncio streams from all channels.

Message IDs returned by send_prompt() are channel-prefixed so that
edit_prompt_message() can dispatch to the correct sub-channel:
  "{channel_name}:{channel_specific_id}"
  e.g. "telegram:12345" or "slack:D12345:1234567890.123456"
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog

from atlasbridge.channels.base import BaseChannel
from atlasbridge.core.prompt.models import PromptEvent, Reply

logger = structlog.get_logger()


class MultiChannel(BaseChannel):
    """
    Fan-out channel that broadcasts prompts to multiple sub-channels
    and merges their reply streams into a single stream.

    Usage::

        telegram = TelegramChannel(...)
        slack = SlackChannel(...)
        channel = MultiChannel([telegram, slack])
        await channel.start()
    """

    channel_name = "multi"
    display_name = "Multi-Channel"

    def __init__(self, channels: list[BaseChannel]) -> None:
        if not channels:
            raise ValueError("MultiChannel requires at least one sub-channel")
        self._channels = channels

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all sub-channels. Errors are logged but do not abort startup."""
        for ch in self._channels:
            try:
                await ch.start()
                logger.info("channel_started", channel=ch.channel_name)
            except Exception as exc:  # noqa: BLE001
                logger.error("channel_start_failed", channel=ch.channel_name, error=str(exc))

    async def close(self) -> None:
        """Close all sub-channels."""
        for ch in self._channels:
            try:
                await ch.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("channel_close_error", channel=ch.channel_name, error=str(exc))

    # ------------------------------------------------------------------
    # Forward path
    # ------------------------------------------------------------------

    async def send_prompt(self, event: PromptEvent) -> str:
        """
        Broadcast the prompt to all sub-channels in parallel.

        Returns the first successful channel-prefixed message ID, e.g.
        ``"telegram:12345"`` or ``"slack:D12345:1234567890.123456"``.
        """
        results = await asyncio.gather(
            *[ch.send_prompt(event) for ch in self._channels],
            return_exceptions=True,
        )
        for ch, result in zip(self._channels, results, strict=False):
            if isinstance(result, Exception):
                logger.warning("send_prompt_failed", channel=ch.channel_name, error=str(result))
            elif result:
                return f"{ch.channel_name}:{result}"
        return ""

    async def notify(self, message: str, session_id: str = "") -> None:
        """Send a plain-text notification to all sub-channels."""
        await asyncio.gather(
            *[ch.notify(message, session_id) for ch in self._channels],
            return_exceptions=True,
        )

    async def send_output(self, text: str, session_id: str = "") -> None:
        """Broadcast CLI output to all sub-channels."""
        await asyncio.gather(
            *[ch.send_output(text, session_id) for ch in self._channels],
            return_exceptions=True,
        )

    async def send_output_editable(self, text: str, session_id: str = "") -> str:
        """Broadcast CLI output and return first successful message ID."""
        results = await asyncio.gather(
            *[ch.send_output_editable(text, session_id) for ch in self._channels],
            return_exceptions=True,
        )
        for ch, result in zip(self._channels, results, strict=False):
            if isinstance(result, str) and result:
                return f"{ch.channel_name}:{result}"
        return ""

    async def send_agent_message(self, text: str, session_id: str = "") -> None:
        """Broadcast agent prose to all sub-channels."""
        await asyncio.gather(
            *[ch.send_agent_message(text, session_id) for ch in self._channels],
            return_exceptions=True,
        )

    async def send_plan(self, plan: Any, session_id: str = "") -> str:
        """Broadcast plan to all sub-channels and return first message ID."""
        results = await asyncio.gather(
            *[ch.send_plan(plan, session_id) for ch in self._channels],
            return_exceptions=True,
        )
        for ch, result in zip(self._channels, results, strict=False):
            if isinstance(result, str) and result:
                return f"{ch.channel_name}:{result}"
        return ""

    async def edit_prompt_message(
        self,
        message_id: str,
        new_text: str,
        session_id: str = "",
    ) -> None:
        """
        Edit a previously sent message.

        Dispatches to the sub-channel identified by the channel-name prefix
        in *message_id* (``"{channel_name}:{inner_id}"``).
        """
        try:
            ch_name, inner_id = message_id.split(":", 1)
        except ValueError:
            logger.warning("edit_prompt_bad_message_id", message_id=message_id)
            return
        for ch in self._channels:
            if ch.channel_name == ch_name:
                await ch.edit_prompt_message(inner_id, new_text, session_id)
                return
        logger.warning("edit_prompt_unknown_channel", channel=ch_name)

    # ------------------------------------------------------------------
    # Return path
    # ------------------------------------------------------------------

    async def receive_replies(self) -> AsyncIterator[Reply]:
        """
        Merge reply streams from all sub-channels into one async iterator.

        Starts one background task per sub-channel that drains that channel's
        receive_replies() generator and enqueues replies into a shared queue.
        """
        queue: asyncio.Queue[Reply] = asyncio.Queue()

        async def _drain(ch: BaseChannel) -> None:
            try:
                async for reply in ch.receive_replies():
                    await queue.put(reply)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("receive_replies_error", channel=ch.channel_name, error=str(exc))

        tasks = [
            asyncio.create_task(_drain(ch), name=f"recv_{ch.channel_name}") for ch in self._channels
        ]
        try:
            while True:
                reply = await queue.get()
                yield reply
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Identity enforcement
    # ------------------------------------------------------------------

    def is_allowed(self, identity: str) -> bool:
        """Return True if *identity* is allowed by any sub-channel."""
        return any(ch.is_allowed(identity) for ch in self._channels)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def healthcheck(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "channel": self.channel_name,
            "sub_channels": [ch.healthcheck() for ch in self._channels],
        }
