"""Unit tests for terminal hint stripping in sanitize.py."""

from __future__ import annotations

from atlasbridge.core.prompt.sanitize import strip_terminal_hints


class TestStripTerminalHints:
    def test_strips_enter_to_confirm(self) -> None:
        text = "Choose an option:\nPress Enter to confirm\nOption 1"
        result = strip_terminal_hints(text)
        assert "Enter to confirm" not in result
        assert "Choose an option:" in result
        assert "Option 1" in result

    def test_strips_ctrl_g_hint(self) -> None:
        text = "Edit file?\nctrl+g to edit in VS Code\ny/n"
        result = strip_terminal_hints(text)
        assert "ctrl+g" not in result
        assert "Edit file?" in result
        assert "y/n" in result

    def test_strips_vs_code_reference(self) -> None:
        text = "Select mode:\nOpen in VS Code\nFast"
        result = strip_terminal_hints(text)
        assert "VS Code" not in result
        assert "Select mode:" in result
        assert "Fast" in result

    def test_strips_arrow_keys(self) -> None:
        text = "Pick one:\nUse the arrow keys to navigate\n1. Alpha"
        result = strip_terminal_hints(text)
        assert "arrow keys" not in result
        assert "Pick one:" in result
        assert "1. Alpha" in result

    def test_strips_esc_to_cancel(self) -> None:
        text = "Continue?\nEsc to cancel\nYes"
        result = strip_terminal_hints(text)
        assert "Esc to cancel" not in result
        assert "Continue?" in result

    def test_strips_space_to_select(self) -> None:
        text = "Features:\nSpace to select\na) Lint\nb) Format"
        result = strip_terminal_hints(text)
        assert "Space to select" not in result
        assert "a) Lint" in result

    def test_strips_vscode_lowercase(self) -> None:
        text = "Open in vscode?\nYes"
        result = strip_terminal_hints(text)
        assert "vscode" not in result
        assert "Yes" in result

    def test_preserves_question_text(self) -> None:
        text = "Do you want to continue?\nThis is an important decision."
        result = strip_terminal_hints(text)
        assert result == text

    def test_preserves_blank_lines(self) -> None:
        text = "Line one\n\nLine three"
        result = strip_terminal_hints(text)
        assert result == text

    def test_case_insensitive(self) -> None:
        text = "PRESS ENTER to confirm\nOk"
        result = strip_terminal_hints(text)
        assert "PRESS ENTER" not in result
        assert "Ok" in result

    def test_empty_input(self) -> None:
        assert strip_terminal_hints("") == ""

    def test_only_hints_returns_empty(self) -> None:
        text = "Press Enter to confirm\nUse the arrow keys\nctrl+g"
        result = strip_terminal_hints(text)
        assert result.strip() == ""

    def test_tab_to_cycle(self) -> None:
        text = "Select:\nTab to cycle options\n1. Fast"
        result = strip_terminal_hints(text)
        assert "Tab to cycle" not in result
        assert "1. Fast" in result

    def test_type_to_filter(self) -> None:
        text = "Search:\nType to filter results\na) Foo"
        result = strip_terminal_hints(text)
        assert "Type to filter" not in result
        assert "a) Foo" in result
