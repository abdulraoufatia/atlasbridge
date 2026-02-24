"""Unit tests for OutputForwarder — batching, ANSI stripping, rate limiting, redaction."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.config import StreamingConfig
from atlasbridge.core.interaction.output_forwarder import (
    BATCH_INTERVAL_S,
    MAX_MESSAGES_PER_MINUTE,
    MAX_OUTPUT_CHARS,
    OutputForwarder,
)
from atlasbridge.core.security.redactor import SecretRedactor


def _make_channel() -> MagicMock:
    ch = MagicMock()
    ch.send_output = AsyncMock()
    ch.send_output_editable = AsyncMock(return_value="")
    ch.send_agent_message = AsyncMock()
    ch.edit_prompt_message = AsyncMock()
    ch.notify = AsyncMock()
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

    def test_feed_resets_idle_counter(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd._idle_cycles = 5
        fwd.feed(b"Hello from the CLI agent\n")
        assert fwd._idle_cycles == 0


class TestFlush:
    @pytest.mark.asyncio
    async def test_sends_buffered_output(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"Running npm install...\n")
        await fwd._flush()
        ch.send_output_editable.assert_called_once()
        sent_text = ch.send_output_editable.call_args[0][0]
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
        ch.send_output_editable.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_tiny_fragments(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        # Feed something meaningful enough to pass is_meaningful() but short after strip
        fwd._buffer.append("hi.")
        fwd._buffer_chars = 3
        await fwd._flush()
        ch.send_output_editable.assert_not_called()


class TestTruncation:
    @pytest.mark.asyncio
    async def test_truncates_long_output(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        long_text = "x" * (MAX_OUTPUT_CHARS + 500) + "\n"
        fwd._buffer.append(long_text)
        fwd._buffer_chars = len(long_text)
        await fwd._flush()
        sent = ch.send_output_editable.call_args[0][0]
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
        ch.send_output_editable.assert_not_called()

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

        ch.send_output_editable.assert_called()

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
        ch.send_output_editable.assert_called()


class TestSendFailure:
    @pytest.mark.asyncio
    async def test_send_failure_does_not_crash(self) -> None:
        ch = _make_channel()
        ch.send_output_editable.side_effect = RuntimeError("network error")
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"Some substantial output from CLI\n")
        # Should not raise
        await fwd._flush()
        ch.send_output_editable.assert_called_once()


# -----------------------------------------------------------------------
# New tests for Commit 2: StreamingConfig, redaction, editing, state
# -----------------------------------------------------------------------


class TestConfigDefaults:
    def test_config_defaults_match_constants(self) -> None:
        """Without StreamingConfig, forwarder uses module-level constants."""
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        assert fwd._batch_interval == BATCH_INTERVAL_S
        assert fwd._max_output_chars == MAX_OUTPUT_CHARS
        assert fwd._max_messages_per_minute == MAX_MESSAGES_PER_MINUTE

    def test_custom_batch_interval(self) -> None:
        ch = _make_channel()
        cfg = StreamingConfig(batch_interval_s=5.0)
        fwd = OutputForwarder(ch, "sess-001", streaming_config=cfg)
        assert fwd._batch_interval == 5.0

    def test_custom_rate_limit(self) -> None:
        ch = _make_channel()
        cfg = StreamingConfig(max_messages_per_minute=30)
        fwd = OutputForwarder(ch, "sess-001", streaming_config=cfg)
        assert fwd._max_messages_per_minute == 30

    def test_custom_max_output_chars(self) -> None:
        ch = _make_channel()
        cfg = StreamingConfig(max_output_chars=500)
        fwd = OutputForwarder(ch, "sess-001", streaming_config=cfg)
        assert fwd._max_output_chars == 500


class TestSecretRedaction:
    def test_redact_telegram_token(self) -> None:
        text = "Found token: 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ_1234567890ab"
        result = OutputForwarder._redact(text)
        assert "[REDACTED]" in result
        assert "1234567890:ABC" not in result

    def test_redact_slack_bot_token(self) -> None:
        text = "Bot token: xoxb-FAKE000-FAKE000-FAKETOKEN0000"
        result = OutputForwarder._redact(text)
        assert "[REDACTED]" in result
        assert "xoxb-" not in result

    def test_redact_slack_app_token(self) -> None:
        text = "App token: xapp-1-ABCDEFGHIJ-1234567890-abcdefghij"
        result = OutputForwarder._redact(text)
        assert "[REDACTED]" in result
        assert "xapp-" not in result

    def test_redact_openai_api_key(self) -> None:
        text = "Key: sk-ABCDEFGHIJKLMNOPQRSTuvwxyz1234567890abcdef"
        result = OutputForwarder._redact(text)
        assert "[REDACTED]" in result
        assert "sk-ABCD" not in result

    def test_redact_github_pat(self) -> None:
        text = "Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        result = OutputForwarder._redact(text)
        assert "[REDACTED]" in result
        assert "ghp_" not in result

    def test_redact_aws_key(self) -> None:
        text = "Key: AKIAIOSFODNN7EXAMPLE"
        result = OutputForwarder._redact(text)
        assert "[REDACTED]" in result
        assert "AKIA" not in result

    def test_no_redact_normal_text(self) -> None:
        text = "This is normal CLI output with no secrets"
        result = OutputForwarder._redact(text)
        assert result == text

    @pytest.mark.asyncio
    async def test_redaction_applied_in_flush(self) -> None:
        """Secret redaction is applied before sending to channel."""
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"Token: sk-ABCDEFGHIJKLMNOPQRSTuvwxyz1234567890xx\n")
        await fwd._flush()
        sent = ch.send_output_editable.call_args[0][0]
        assert "[REDACTED]" in sent
        assert "sk-ABCD" not in sent

    @pytest.mark.asyncio
    async def test_redaction_disabled_via_config(self) -> None:
        """When redact_secrets=False, secrets pass through."""
        ch = _make_channel()
        cfg = StreamingConfig(redact_secrets=False)
        fwd = OutputForwarder(ch, "sess-001", streaming_config=cfg)
        fwd.feed(b"Token: sk-ABCDEFGHIJKLMNOPQRSTuvwxyz1234567890xx\n")
        await fwd._flush()
        sent = ch.send_output_editable.call_args[0][0]
        assert "sk-ABCD" in sent


class TestMessageEditing:
    @pytest.mark.asyncio
    async def test_first_send_uses_editable(self) -> None:
        ch = _make_channel()
        ch.send_output_editable.return_value = "msg-123"
        fwd = OutputForwarder(ch, "sess-001")
        fwd.feed(b"First output from the CLI agent\n")
        await fwd._flush()
        ch.send_output_editable.assert_called_once()
        assert fwd._last_message_id == "msg-123"

    @pytest.mark.asyncio
    async def test_second_send_edits_last_message(self) -> None:
        ch = _make_channel()
        ch.send_output_editable.return_value = "msg-123"
        fwd = OutputForwarder(ch, "sess-001")
        fwd._last_message_id = "msg-123"
        fwd.feed(b"Second output from the CLI agent\n")
        await fwd._flush()
        ch.edit_prompt_message.assert_called_once()
        edit_args = ch.edit_prompt_message.call_args
        assert edit_args[0][0] == "msg-123"

    @pytest.mark.asyncio
    async def test_edit_failure_falls_back_to_new_message(self) -> None:
        ch = _make_channel()
        ch.edit_prompt_message.side_effect = RuntimeError("edit failed")
        ch.send_output_editable.return_value = "msg-456"
        fwd = OutputForwarder(ch, "sess-001")
        fwd._last_message_id = "msg-old"
        fwd.feed(b"Output after edit failure in channel\n")
        await fwd._flush()
        ch.send_output_editable.assert_called_once()
        assert fwd._last_message_id == "msg-456"

    @pytest.mark.asyncio
    async def test_editing_disabled_via_config(self) -> None:
        ch = _make_channel()
        ch.send_output_editable.return_value = "msg-123"
        cfg = StreamingConfig(edit_last_message=False)
        fwd = OutputForwarder(ch, "sess-001", streaming_config=cfg)
        fwd._last_message_id = "msg-old"
        fwd.feed(b"Output when editing is disabled completely\n")
        await fwd._flush()
        # Should send new message, not edit
        ch.edit_prompt_message.assert_not_called()
        ch.send_output_editable.assert_called_once()


class TestIdleCycleTransition:
    @pytest.mark.asyncio
    async def test_idle_cycles_increment_on_empty_flush(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        await fwd._flush()
        assert fwd._idle_cycles == 1
        await fwd._flush()
        assert fwd._idle_cycles == 2

    @pytest.mark.asyncio
    async def test_idle_cycles_reset_on_feed(self) -> None:
        ch = _make_channel()
        fwd = OutputForwarder(ch, "sess-001")
        await fwd._flush()
        await fwd._flush()
        assert fwd._idle_cycles == 2
        fwd.feed(b"New output from the CLI agent\n")
        assert fwd._idle_cycles == 0


class TestSecretPatterns:
    """Verify centralized secret redactor has patterns loaded."""

    def test_all_patterns_compile(self) -> None:
        r = SecretRedactor()
        assert r.pattern_count >= 6
