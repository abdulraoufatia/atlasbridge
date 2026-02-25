"""Unit tests for TelegramChannel prompt formatting and keyboard building."""

from __future__ import annotations

from atlasbridge.channels.telegram.channel import TelegramChannel
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType

_VALID_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


def _channel() -> TelegramChannel:
    return TelegramChannel(bot_token=_VALID_TOKEN, allowed_user_ids=[12345])


def _event(
    prompt_type: PromptType,
    choices: list[str] | None = None,
    confidence: Confidence = Confidence.HIGH,
    tool: str = "",
    cwd: str = "",
    session_label: str = "",
    ttl_seconds: int = 300,
) -> PromptEvent:
    event = PromptEvent.create(
        session_id="test-session-abc",
        prompt_type=prompt_type,
        confidence=confidence,
        excerpt="Continue? (y/n)",
        choices=choices or [],
        ttl_seconds=ttl_seconds,
    )
    event.tool = tool
    event.cwd = cwd
    event.session_label = session_label
    return event


class TestFormatPrompt:
    def test_contains_session_id(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_YES_NO)
        text = ch._format_prompt(event)
        assert "test-ses" in text  # first 8 chars of session_id

    def test_contains_input_required_header(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_YES_NO)
        text = ch._format_prompt(event)
        assert "Input Required" in text

    def test_yes_no_shows_type_label(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_YES_NO)
        text = ch._format_prompt(event)
        assert "Yes / No" in text

    def test_confirm_enter_shows_label(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_CONFIRM_ENTER)
        text = ch._format_prompt(event)
        assert "Press Enter" in text

    def test_free_text_shows_label(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_FREE_TEXT)
        text = ch._format_prompt(event)
        assert "Free Text" in text

    def test_multiple_choice_shows_label(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_MULTIPLE_CHOICE, choices=["a", "b"])
        text = ch._format_prompt(event)
        assert "Multiple Choice" in text

    def test_excerpt_in_output(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_YES_NO)
        text = ch._format_prompt(event)
        assert "Continue? (y/n)" in text


class TestFormatPromptResponseInstructions:
    def test_yes_no_instruction(self) -> None:
        text = TelegramChannel._format_prompt(_event(PromptType.TYPE_YES_NO))
        assert "Tap <b>Yes</b> or <b>No</b> below" in text

    def test_confirm_enter_instruction(self) -> None:
        text = TelegramChannel._format_prompt(_event(PromptType.TYPE_CONFIRM_ENTER))
        assert "Tap <b>Send Enter</b> below to continue" in text

    def test_multiple_choice_instruction(self) -> None:
        text = TelegramChannel._format_prompt(
            _event(PromptType.TYPE_MULTIPLE_CHOICE, choices=["a", "b"])
        )
        assert "Reply" in text and ("1" in text or "2" in text)
        assert "tap a button" in text

    def test_free_text_instruction(self) -> None:
        text = TelegramChannel._format_prompt(_event(PromptType.TYPE_FREE_TEXT))
        assert "Type your response and send it as a message" in text


class TestFormatPromptTTL:
    def test_default_ttl_5_minutes(self) -> None:
        text = TelegramChannel._format_prompt(_event(PromptType.TYPE_YES_NO))
        assert "5 minutes" in text

    def test_custom_ttl(self) -> None:
        text = TelegramChannel._format_prompt(_event(PromptType.TYPE_YES_NO, ttl_seconds=600))
        assert "10 minutes" in text


class TestFormatPromptContext:
    def test_tool_shown_when_set(self) -> None:
        text = TelegramChannel._format_prompt(_event(PromptType.TYPE_YES_NO, tool="claude"))
        assert "Tool: claude" in text

    def test_tool_absent_when_empty(self) -> None:
        text = TelegramChannel._format_prompt(_event(PromptType.TYPE_YES_NO, tool=""))
        assert "Tool:" not in text

    def test_cwd_shown_when_set(self) -> None:
        text = TelegramChannel._format_prompt(
            _event(PromptType.TYPE_YES_NO, cwd="/Users/ara/projects/my-app")
        )
        assert "/Users/ara/projects/my-app" in text
        assert "Workspace" in text

    def test_cwd_absent_when_empty(self) -> None:
        text = TelegramChannel._format_prompt(_event(PromptType.TYPE_YES_NO, cwd=""))
        assert "Workspace" not in text


class TestFormatPromptConfidence:
    def test_high_confidence(self) -> None:
        text = TelegramChannel._format_prompt(
            _event(PromptType.TYPE_YES_NO, confidence=Confidence.HIGH)
        )
        assert "Confidence: high" in text

    def test_low_confidence_shows_ambiguous(self) -> None:
        text = TelegramChannel._format_prompt(
            _event(PromptType.TYPE_YES_NO, confidence=Confidence.LOW)
        )
        assert "low (ambiguous)" in text


class TestBuildKeyboard:
    def test_yes_no_has_yes_and_no(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_YES_NO)
        kb = ch._build_keyboard(event)
        assert len(kb) == 1
        texts = [b["text"] for b in kb[0]]
        assert "Yes" in texts
        assert "No" in texts

    def test_yes_no_callback_contains_prompt_id(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_YES_NO)
        kb = ch._build_keyboard(event)
        all_data = [b["callback_data"] for b in kb[0]]
        assert all(event.prompt_id in d for d in all_data)

    def test_confirm_enter_has_send_enter(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_CONFIRM_ENTER)
        kb = ch._build_keyboard(event)
        texts = [b["text"] for b in kb[0]]
        assert any("Enter" in t for t in texts)

    def test_multiple_choice_one_button_per_choice(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_MULTIPLE_CHOICE, choices=["Alpha", "Beta", "Gamma"])
        kb = ch._build_keyboard(event)
        assert len(kb[0]) == 3
        labels = [b["text"] for b in kb[0]]
        assert labels == ["1. Alpha", "2. Beta", "3. Gamma"]

    def test_free_text_no_buttons(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_FREE_TEXT)
        kb = ch._build_keyboard(event)
        assert kb == []


class TestCallbackDataSizing:
    """All generated callback_data must fit in Telegram's 64-byte limit."""

    def test_yes_no_within_64_bytes(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_YES_NO)
        kb = ch._build_keyboard(event)
        for btn in kb[0]:
            assert len(btn["callback_data"].encode()) <= 64

    def test_confirm_enter_within_64_bytes(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_CONFIRM_ENTER)
        kb = ch._build_keyboard(event)
        for btn in kb[0]:
            assert len(btn["callback_data"].encode()) <= 64

    def test_multiple_choice_within_64_bytes(self) -> None:
        ch = _channel()
        event = _event(PromptType.TYPE_MULTIPLE_CHOICE, choices=["A", "B", "C", "D"])
        kb = ch._build_keyboard(event)
        for btn in kb[0]:
            assert len(btn["callback_data"].encode()) <= 64


class TestCallbackRefFallback:
    """When full callback data exceeds 64 bytes, ref format is used."""

    def test_ref_format_used_when_too_long(self) -> None:
        ch = _channel()
        # Use a very long session_id to force ref fallback
        event = _event(PromptType.TYPE_YES_NO)
        event.session_id = "a" * 80  # Much longer than normal UUID
        kb = ch._build_keyboard(event)
        # At least one button should use ref: format
        data_values = [btn["callback_data"] for btn in kb[0]]
        assert any(d.startswith("ref:") for d in data_values)

    def test_ref_roundtrip(self) -> None:
        ch = _channel()
        pid = "abcdef1234567890abcdef12"
        sid = "12345678-1234-1234-1234-123456789abc"
        nonce = "deadbeef01234567"
        value = "y"

        data = ch._make_callback_data(pid, sid, nonce, value)

        # Parse the callback data back
        if data.startswith("ref:"):
            parts = data.split(":", 2)
            assert len(parts) == 3
            ref_key = parts[1]
            parsed_value = parts[2]
            assert parsed_value == value
            ref = ch._callback_refs.get(ref_key)
            assert ref is not None
            ref_data, _ = ref
            assert ref_data["prompt_id"] == pid
            assert ref_data["session_id"] == sid
            assert ref_data["nonce"] == nonce
        else:
            # Full format — verify it parses
            assert data.startswith("ans:")
            _, parsed_pid, parsed_sid, parsed_nonce, parsed_value = data.split(":", 4)
            assert parsed_pid == pid
            assert parsed_sid == sid
            assert parsed_nonce == nonce
            assert parsed_value == value

    def test_ref_within_64_bytes(self) -> None:
        ch = _channel()
        # Force ref format with long IDs
        data = ch._make_callback_data("a" * 30, "b" * 40, "c" * 20, "y")
        assert len(data.encode()) <= 64


class TestReplyAliases:
    """Common reply aliases are normalized before creating Reply."""

    def test_yes_normalizes_to_y(self) -> None:
        from atlasbridge.channels.telegram.channel import _REPLY_ALIASES

        assert _REPLY_ALIASES["yes"] == "y"

    def test_nope_normalizes_to_n(self) -> None:
        from atlasbridge.channels.telegram.channel import _REPLY_ALIASES

        assert _REPLY_ALIASES["nope"] == "n"

    def test_yeah_normalizes_to_y(self) -> None:
        from atlasbridge.channels.telegram.channel import _REPLY_ALIASES

        assert _REPLY_ALIASES["yeah"] == "y"

    def test_nah_normalizes_to_n(self) -> None:
        from atlasbridge.channels.telegram.channel import _REPLY_ALIASES

        assert _REPLY_ALIASES["nah"] == "n"

    def test_non_alias_not_in_map(self) -> None:
        from atlasbridge.channels.telegram.channel import _REPLY_ALIASES

        assert "maybe" not in _REPLY_ALIASES


class TestGetAllowedIdentities:
    def test_returns_formatted_identities(self) -> None:
        ch = _channel()
        ids = ch.get_allowed_identities()
        assert ids == ["telegram:12345"]

    def test_multiple_users(self) -> None:
        ch = TelegramChannel(bot_token=_VALID_TOKEN, allowed_user_ids=[999, 111, 555])
        ids = ch.get_allowed_identities()
        assert ids == ["telegram:111", "telegram:555", "telegram:999"]
