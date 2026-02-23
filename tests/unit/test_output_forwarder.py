"""Unit tests for OutputForwarder — batching, ANSI stripping, rate limiting."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.interaction.output_forwarder import (
    BATCH_INTERVAL_S,
    MAX_MESSAGES_PER_MINUTE,
    MAX_OUTPUT_CHARS,
    OutputForwarder,
)


def _make_channel() -> MagicMock:
    ch = MagicMock()
    ch.send_output = AsyncMock()
    return ch


class TestFeed:
    def test_buffers_meaningful_text(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"Hello from the CLI agent\n")
        assert fwd._buffer_chars > 0

    def test_skips_empty_bytes(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"")
        assert fwd._buffer_chars == 0

    def test_strips_ansi_before_buffering(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"\x1b[32mGreen text output here\x1b[0m\n")
        assert fwd._buffer  # Should buffer the stripped text
        assert "\x1b" not in fwd._buffer[0]

    def test_skips_non_meaningful_fragments(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        # Just whitespace after ANSI stripping
        fwd.feed(b"\x1b[0m   \x1b[K")
        assert fwd._buffer_chars == 0

    def test_handles_invalid_utf8(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        # Invalid UTF-8 sequence should not crash
        fwd.feed(b"\xff\xfe some valid text and more\n")
        # Should still buffer (errors="replace")
        assert fwd._buffer_chars > 0


class TestFlush:
    @pytest.mark.asyncio
    async def test_sends_buffered_output(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"Running npm install...\n")
        await fwd._flush()
        ch.send_output.assert_called_once()
        sent_text = ch.send_output.call_args[0][0]
        assert "npm install" in sent_text

    @pytest.mark.asyncio
    async def test_clears_buffer_after_flush(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"Some output from the CLI tool\n")
        await fwd._flush()
        assert fwd._buffer_chars == 0
        assert len(fwd._buffer) == 0

    @pytest.mark.asyncio
    async def test_skips_empty_buffer(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        await fwd._flush()
        ch.send_output.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_tiny_fragments(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        # Feed something meaningful enough to pass is_meaningful() but short after strip
        fwd._buffer.append("hi.")
        fwd._buffer_chars = 3
        await fwd._flush()
        ch.send_output.assert_not_called()


class TestTruncation:
    @pytest.mark.asyncio
    async def test_truncates_long_output(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        long_text = "x" * (MAX_OUTPUT_CHARS + 500) + "\n"
        fwd._buffer.append(long_text)
        fwd._buffer_chars = len(long_text)
        await fwd._flush()
        sent = ch.send_output.call_args[0][0]
        assert len(sent) <= MAX_OUTPUT_CHARS + 50  # +50 for truncation marker
        assert "truncated" in sent


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limits_messages(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")

        # Fill up rate limit
        now = time.monotonic()
        fwd._send_times = [now - i for i in range(MAX_MESSAGES_PER_MINUTE)]

        fwd.feed(b"This should be rate limited text output\n")
        await fwd._flush()
        ch.send_output.assert_not_called()

    def test_can_send_when_under_limit(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        assert fwd._can_send() is True

    def test_cannot_send_when_at_limit(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        now = time.monotonic()
        fwd._send_times = [now - i for i in range(MAX_MESSAGES_PER_MINUTE)]
        assert fwd._can_send() is False

    def test_old_timestamps_pruned(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        # All timestamps are > 60s old
        old = time.monotonic() - 120.0
        fwd._send_times = [old] * MAX_MESSAGES_PER_MINUTE
        assert fwd._can_send() is True


class TestFlushLoop:
    @pytest.mark.asyncio
    async def test_flush_loop_runs_and_cancels(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")

        fwd.feed(b"Output text from the CLI agent running\n")

        task = asyncio.create_task(fwd.flush_loop())
        # Let it run for one flush cycle
        await asyncio.sleep(BATCH_INTERVAL_S + 0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        ch.send_output.assert_called()

    @pytest.mark.asyncio
    async def test_final_flush_on_cancel(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")

        task = asyncio.create_task(fwd.flush_loop())
        await asyncio.sleep(0.1)

        # Feed after loop started but before flush
        fwd.feed(b"Last gasp output from the agent\n")

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Final flush should have sent it
        ch.send_output.assert_called()


class TestSendFailure:
    @pytest.mark.asyncio
    async def test_send_failure_does_not_crash(self) -> None:
        ch = _make_channel()
        ch.send_output.side_effect = RuntimeError("network error")
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"Some substantial output from CLI\n")
        # Should not raise
        await fwd._flush()
        ch.send_output.assert_called_once()
