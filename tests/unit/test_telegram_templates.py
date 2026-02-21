"""Unit tests for aegis.channels.telegram.templates."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from aegis.channels.telegram.templates import (
    format_prompt,
    parse_callback_data,
)
from aegis.core.constants import PromptType
from aegis.store.models import PromptRecord


def _prompt(input_type: str, choices: list[str] | None = None) -> PromptRecord:
    p = PromptRecord(
        id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        input_type=input_type,
        excerpt="Continue? (y/n)",
        confidence=0.9,
        nonce=secrets.token_hex(16),
        expires_at=(datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
        safe_default="n",
    )
    if choices:
        p.choices = choices
    return p


class TestFormatPrompt:
    def test_yes_no_has_yes_button(self) -> None:
        p = _prompt(PromptType.YES_NO)
        text, kb = format_prompt(p)
        assert kb is not None
        buttons = [b["text"] for row in kb["inline_keyboard"] for b in row]
        assert any("Yes" in b for b in buttons)
        assert any("No" in b for b in buttons)

    def test_yes_no_callback_contains_nonce(self) -> None:
        p = _prompt(PromptType.YES_NO)
        _, kb = format_prompt(p)
        all_data = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
        assert any(p.nonce in d for d in all_data)

    def test_confirm_enter_has_enter_button(self) -> None:
        p = _prompt(PromptType.CONFIRM_ENTER)
        _, kb = format_prompt(p)
        buttons = [b["text"] for row in kb["inline_keyboard"] for b in row]
        assert any("Enter" in b for b in buttons)

    def test_multiple_choice_renders_choices(self) -> None:
        p = _prompt(PromptType.MULTIPLE_CHOICE, choices=["Alpha", "Beta", "Gamma"])
        _, kb = format_prompt(p)
        buttons = [b["text"] for row in kb["inline_keyboard"] for b in row]
        assert any("Alpha" in b for b in buttons)
        assert any("Beta" in b for b in buttons)

    def test_free_text_instructions_in_text(self) -> None:
        p = _prompt(PromptType.FREE_TEXT)
        text, _ = format_prompt(p)
        assert "Reply" in text or "reply" in text

    def test_unknown_type_has_buttons(self) -> None:
        p = _prompt(PromptType.UNKNOWN)
        _, kb = format_prompt(p)
        assert kb is not None
        assert len(kb["inline_keyboard"]) > 0


class TestParseCallbackData:
    def test_valid_parse(self) -> None:
        pid = str(uuid.uuid4())
        nonce = secrets.token_hex(16)
        data = f"ans:{pid}:{nonce}:y"
        result = parse_callback_data(data)
        assert result is not None
        assert result == (pid, nonce, "y")

    def test_invalid_prefix(self) -> None:
        assert parse_callback_data("bad:a:b:c") is None

    def test_too_few_parts(self) -> None:
        assert parse_callback_data("ans:a:b") is None

    def test_empty_string(self) -> None:
        assert parse_callback_data("") is None

    def test_default_value(self) -> None:
        pid = str(uuid.uuid4())
        nonce = secrets.token_hex(16)
        result = parse_callback_data(f"ans:{pid}:{nonce}:default")
        assert result is not None
        assert result[2] == "default"
