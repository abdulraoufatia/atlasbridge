"""Tests for dashboard sanitization utilities."""

from __future__ import annotations

from atlasbridge.dashboard.sanitize import (
    redact_tokens,
    sanitize_for_display,
    strip_ansi,
)


class TestStripAnsi:
    def test_removes_color_codes(self):
        assert strip_ansi("\x1b[31mred\x1b[0m") == "red"

    def test_removes_osc_sequences(self):
        assert strip_ansi("\x1b]0;title\x07text") == "text"

    def test_removes_carriage_returns(self):
        assert strip_ansi("hello\rworld") == "helloworld"

    def test_preserves_plain_text(self):
        assert strip_ansi("hello world") == "hello world"

    def test_handles_empty_string(self):
        assert strip_ansi("") == ""


class TestRedactTokens:
    def test_redacts_telegram_token(self):
        text = "token is 1234567890:ABCdef_ghijklmnop-1234567890ABCDEfg"
        result = redact_tokens(text)
        assert "[REDACTED:telegram-token]" in result
        assert "1234567890:ABC" not in result

    def test_redacts_slack_token(self):
        text = "xoxb-FAKE00000000-FAKE00000000-abcdefghijklmnop"
        result = redact_tokens(text)
        assert "[REDACTED:slack-token]" in result
        assert "xoxb-" not in result

    def test_redacts_api_key(self):
        text = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
        result = redact_tokens(text)
        assert "[REDACTED:api-key]" in result
        assert "sk-abc" not in result

    def test_redacts_github_pat(self):
        text = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij1234"
        result = redact_tokens(text)
        assert "[REDACTED:github-pat]" in result
        assert "ghp_" not in result

    def test_redacts_aws_key(self):
        text = "AKIAIOSFODNN7EXAMPLE"
        result = redact_tokens(text)
        assert "[REDACTED:aws-key]" in result

    def test_preserves_normal_text(self):
        text = "This is a normal sentence with no secrets."
        assert redact_tokens(text) == text


class TestSanitizeForDisplay:
    def test_strips_ansi_and_redacts(self):
        text = "\x1b[31mtoken: sk-abcdefghijklmnopqrstuvwxyz1234567890\x1b[0m"
        result = sanitize_for_display(text)
        assert "\x1b[" not in result
        assert "[REDACTED:api-key]" in result

    def test_truncates_long_text(self):
        text = "x" * 5000
        result = sanitize_for_display(text, max_length=100)
        assert len(result) < 5000
        assert result.endswith("... [truncated]")

    def test_short_text_not_truncated(self):
        text = "hello"
        assert sanitize_for_display(text) == "hello"
