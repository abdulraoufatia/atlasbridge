"""
Unit tests for SlackChannel and MultiChannel.

These tests cover formatting and logic that is testable without a live
Slack connection or Socket Mode dependency.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.channels.slack.channel import SlackChannel
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    prompt_type: PromptType = PromptType.TYPE_YES_NO,
    excerpt: str = "Continue? [y/n]",
    choices: list[str] | None = None,
    confidence: Confidence = Confidence.HIGH,
) -> PromptEvent:
    return PromptEvent(
        prompt_id="aabbccdd112233",
        session_id="sess-1234-5678-abcd-efab",
        prompt_type=prompt_type,
        excerpt=excerpt,
        choices=choices or [],
        confidence=confidence,
        idempotency_key="nonce123",
    )


# ---------------------------------------------------------------------------
# _format_prompt (static — no network)
# ---------------------------------------------------------------------------


class TestFormatPrompt:
    def test_yes_no_label(self) -> None:
        event = _make_event(PromptType.TYPE_YES_NO)
        text = SlackChannel._format_prompt(event)
        assert "Yes / No" in text
        assert event.excerpt[:30] in text

    def test_confirm_enter_label(self) -> None:
        event = _make_event(PromptType.TYPE_CONFIRM_ENTER, excerpt="Press Enter to continue")
        text = SlackChannel._format_prompt(event)
        assert "Press Enter" in text

    def test_multiple_choice_label(self) -> None:
        event = _make_event(
            PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt="Choose: 1) foo  2) bar",
            choices=["foo", "bar"],
        )
        text = SlackChannel._format_prompt(event)
        assert "Multiple Choice" in text

    def test_free_text_label(self) -> None:
        event = _make_event(PromptType.TYPE_FREE_TEXT, excerpt="Enter your message:")
        text = SlackChannel._format_prompt(event)
        assert "Free Text" in text

    def test_session_prefix(self) -> None:
        event = _make_event()
        text = SlackChannel._format_prompt(event)
        assert event.session_id[:8] in text

    def test_excerpt_truncated_at_120(self) -> None:
        # _format_prompt slices excerpt to [:120] — full 200-char text must not appear
        long_text = "X" * 120 + "Z" * 80  # unique suffix 'Z's beyond 120 chars
        event = _make_event(excerpt=long_text)
        text = SlackChannel._format_prompt(event)
        assert "Z" not in text, "Excerpt beyond 120 chars should be truncated"


# ---------------------------------------------------------------------------
# _build_blocks (static — no network)
# ---------------------------------------------------------------------------


class TestBuildBlocks:
    def test_yes_no_has_two_buttons(self) -> None:
        event = _make_event(PromptType.TYPE_YES_NO)
        blocks = SlackChannel._build_blocks(event)
        assert len(blocks) == 2  # section + actions
        actions = blocks[1]
        assert actions["type"] == "actions"
        elements = actions["elements"]
        assert len(elements) == 2
        values = [e["value"] for e in elements]
        assert any(v.endswith(":y") for v in values)
        assert any(v.endswith(":n") for v in values)

    def test_yes_no_button_styles(self) -> None:
        event = _make_event(PromptType.TYPE_YES_NO)
        blocks = SlackChannel._build_blocks(event)
        elements = blocks[1]["elements"]
        styles = {e["text"]["text"]: e.get("style") for e in elements}
        assert styles["Yes"] == "primary"
        assert styles["No"] == "danger"

    def test_confirm_enter_has_two_buttons(self) -> None:
        event = _make_event(PromptType.TYPE_CONFIRM_ENTER)
        blocks = SlackChannel._build_blocks(event)
        elements = blocks[1]["elements"]
        assert len(elements) == 2
        labels = [e["text"]["text"] for e in elements]
        assert "Send Enter" in labels
        assert "Cancel" in labels

    def test_confirm_enter_value(self) -> None:
        event = _make_event(PromptType.TYPE_CONFIRM_ENTER)
        blocks = SlackChannel._build_blocks(event)
        values = [e["value"] for e in blocks[1]["elements"]]
        assert any(v.endswith(":enter") for v in values)
        assert any(v.endswith(":cancel") for v in values)

    def test_multiple_choice_button_count(self) -> None:
        event = _make_event(PromptType.TYPE_MULTIPLE_CHOICE, choices=["alpha", "beta", "gamma"])
        blocks = SlackChannel._build_blocks(event)
        elements = blocks[1]["elements"]
        assert len(elements) == 3
        labels = [e["text"]["text"] for e in elements]
        assert labels == ["1", "2", "3"]

    def test_free_text_has_no_actions_block(self) -> None:
        event = _make_event(PromptType.TYPE_FREE_TEXT, excerpt="Describe the task:")
        blocks = SlackChannel._build_blocks(event)
        # Free text has no interactive buttons — only the section block
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"

    def test_callback_value_format(self) -> None:
        event = _make_event(PromptType.TYPE_YES_NO)
        blocks = SlackChannel._build_blocks(event)
        value = blocks[1]["elements"][0]["value"]
        # Should be: ans:{prompt_id}:{session_id}:{idempotency_key}:{choice}
        parts = value.split(":")
        assert parts[0] == "ans"
        assert parts[1] == event.prompt_id
        assert parts[2] == event.session_id
        assert parts[3] == event.idempotency_key

    def test_section_contains_mrkdwn(self) -> None:
        event = _make_event()
        blocks = SlackChannel._build_blocks(event)
        section = blocks[0]
        assert section["type"] == "section"
        assert section["text"]["type"] == "mrkdwn"

    def test_section_excerpt_in_text(self) -> None:
        event = _make_event(excerpt="Do you want to proceed?")
        blocks = SlackChannel._build_blocks(event)
        assert "Do you want to proceed?" in blocks[0]["text"]["text"]


# ---------------------------------------------------------------------------
# is_allowed
# ---------------------------------------------------------------------------


class TestIsAllowed:
    def _make_channel(self, allowed: list[str]) -> SlackChannel:
        return SlackChannel(
            bot_token="xoxb-fake",
            app_token="xapp-fake",
            allowed_user_ids=allowed,
        )

    def test_allowed_user(self) -> None:
        ch = self._make_channel(["U1234567890"])
        assert ch.is_allowed("slack:U1234567890") is True

    def test_rejected_user(self) -> None:
        ch = self._make_channel(["U1234567890"])
        assert ch.is_allowed("slack:U9999999999") is False

    def test_telegram_identity_rejected(self) -> None:
        # Slack allowed_user_ids use U... format; a Telegram numeric ID won't match
        ch = self._make_channel(["U1234567890"])
        assert ch.is_allowed("telegram:12345678") is False

    def test_malformed_identity(self) -> None:
        ch = self._make_channel(["U1234567890"])
        assert ch.is_allowed("") is False
        assert ch.is_allowed("nocolon") is False


# ---------------------------------------------------------------------------
# _handle_action (internal — parses callback value, enqueues Reply)
# ---------------------------------------------------------------------------


class TestHandleAction:
    @pytest.mark.asyncio
    async def test_valid_action_enqueued(self) -> None:
        ch = SlackChannel(
            bot_token="xoxb-fake",
            app_token="xapp-fake",
            allowed_user_ids=["U1234567890"],
        )
        value = "ans:promptid:sessid:nonce01:y"
        await ch._handle_action(value, "U1234567890")
        assert not ch._reply_queue.empty()
        reply = ch._reply_queue.get_nowait()
        assert reply.value == "y"
        assert reply.prompt_id == "promptid"
        assert reply.session_id == "sessid"
        assert reply.nonce == "nonce01"
        assert reply.channel_identity == "slack:U1234567890"

    @pytest.mark.asyncio
    async def test_rejected_non_allowlisted(self) -> None:
        ch = SlackChannel(
            bot_token="xoxb-fake",
            app_token="xapp-fake",
            allowed_user_ids=["U1234567890"],
        )
        await ch._handle_action("ans:p:s:n:y", "USTRANGER1")
        assert ch._reply_queue.empty()

    @pytest.mark.asyncio
    async def test_malformed_value_ignored(self) -> None:
        ch = SlackChannel(
            bot_token="xoxb-fake",
            app_token="xapp-fake",
            allowed_user_ids=["U1234567890"],
        )
        await ch._handle_action("badvalue", "U1234567890")
        assert ch._reply_queue.empty()

    @pytest.mark.asyncio
    async def test_wrong_prefix_ignored(self) -> None:
        ch = SlackChannel(
            bot_token="xoxb-fake",
            app_token="xapp-fake",
            allowed_user_ids=["U1234567890"],
        )
        await ch._handle_action("cmd:p:s:n:y", "U1234567890")
        assert ch._reply_queue.empty()


# ---------------------------------------------------------------------------
# MultiChannel
# ---------------------------------------------------------------------------


class TestMultiChannel:
    def _make_multi(self) -> tuple:
        from atlasbridge.channels.multi import MultiChannel

        ch1 = MagicMock()
        ch1.channel_name = "telegram"
        ch1.send_prompt = AsyncMock(return_value="42")
        ch1.notify = AsyncMock()
        ch1.edit_prompt_message = AsyncMock()
        ch1.is_allowed = MagicMock(return_value=False)
        ch1.healthcheck = MagicMock(return_value={"status": "ok", "channel": "telegram"})

        ch2 = MagicMock()
        ch2.channel_name = "slack"
        ch2.send_prompt = AsyncMock(return_value="D12345:1234567890.123456")
        ch2.notify = AsyncMock()
        ch2.edit_prompt_message = AsyncMock()
        ch2.is_allowed = MagicMock(return_value=True)
        ch2.healthcheck = MagicMock(return_value={"status": "ok", "channel": "slack"})

        multi = MultiChannel([ch1, ch2])
        return multi, ch1, ch2

    def test_requires_at_least_one_channel(self) -> None:
        from atlasbridge.channels.multi import MultiChannel

        with pytest.raises(ValueError, match="at least one"):
            MultiChannel([])

    @pytest.mark.asyncio
    async def test_send_prompt_returns_first_success_prefixed(self) -> None:
        multi, ch1, ch2 = self._make_multi()
        event = _make_event()
        result = await multi.send_prompt(event)
        # First channel (telegram) returns "42" → prefixed as "telegram:42"
        assert result == "telegram:42"
        ch1.send_prompt.assert_called_once_with(event)
        ch2.send_prompt.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_send_prompt_falls_back_on_empty(self) -> None:
        from atlasbridge.channels.multi import MultiChannel

        ch1 = MagicMock()
        ch1.channel_name = "telegram"
        ch1.send_prompt = AsyncMock(return_value="")  # returns empty

        ch2 = MagicMock()
        ch2.channel_name = "slack"
        ch2.send_prompt = AsyncMock(return_value="D1:ts1")

        multi = MultiChannel([ch1, ch2])
        result = await multi.send_prompt(_make_event())
        assert result == "slack:D1:ts1"

    @pytest.mark.asyncio
    async def test_edit_dispatches_to_correct_channel(self) -> None:
        multi, ch1, ch2 = self._make_multi()
        await multi.edit_prompt_message("slack:D12345:ts1", "Resolved", "sess1")
        ch2.edit_prompt_message.assert_called_once_with("D12345:ts1", "Resolved", "sess1")
        ch1.edit_prompt_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_telegram_dispatches_correctly(self) -> None:
        multi, ch1, ch2 = self._make_multi()
        await multi.edit_prompt_message("telegram:42", "Done")
        ch1.edit_prompt_message.assert_called_once_with("42", "Done", "")
        ch2.edit_prompt_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_broadcast(self) -> None:
        multi, ch1, ch2 = self._make_multi()
        await multi.notify("hello", "sess1")
        ch1.notify.assert_called_once_with("hello", "sess1")
        ch2.notify.assert_called_once_with("hello", "sess1")

    def test_is_allowed_delegates(self) -> None:
        multi, ch1, ch2 = self._make_multi()
        # ch2.is_allowed returns True
        assert multi.is_allowed("slack:U1234567890") is True

    def test_is_allowed_all_reject(self) -> None:
        multi, ch1, ch2 = self._make_multi()
        ch2.is_allowed.return_value = False
        assert multi.is_allowed("unknown:xyz") is False

    def test_healthcheck_includes_sub_channels(self) -> None:
        multi, ch1, ch2 = self._make_multi()
        hc = multi.healthcheck()
        assert hc["channel"] == "multi"
        assert len(hc["sub_channels"]) == 2
