"""Unit tests for binary semantic menu normalizer."""

from __future__ import annotations

import pytest

from atlasbridge.core.interaction.normalizer import (
    NO_SYNONYMS,
    YES_SYNONYMS,
    BinaryMenu,
    detect_binary_menu,
    normalize_reply,
)


class TestDetectBinaryMenu:
    """Detect binary semantic menus from prompt text."""

    def test_numbered_dot_format(self):
        menu = detect_binary_menu("1. Yes\n2. No")
        assert menu is not None
        assert menu.yes_option == "1"
        assert menu.no_option == "2"

    def test_numbered_paren_format(self):
        menu = detect_binary_menu("1) Allow\n2) Deny")
        assert menu is not None
        assert menu.yes_option == "1"
        assert menu.no_option == "2"
        assert menu.yes_label == "Allow"
        assert menu.no_label == "Deny"

    def test_numbered_dash_format(self):
        menu = detect_binary_menu("1 - Continue\n2 - Exit")
        assert menu is not None
        assert menu.yes_option == "1"
        assert menu.no_option == "2"

    def test_reversed_order(self):
        """No-like option first, yes-like second."""
        menu = detect_binary_menu("1. No\n2. Yes")
        assert menu is not None
        assert menu.yes_option == "2"
        assert menu.no_option == "1"

    def test_deny_allow_order(self):
        menu = detect_binary_menu("1. Deny\n2. Allow")
        assert menu is not None
        assert menu.yes_option == "2"
        assert menu.no_option == "1"

    def test_trust_reject(self):
        menu = detect_binary_menu("1. Trust\n2. Reject")
        assert menu is not None
        assert menu.yes_option == "1"
        assert menu.no_option == "2"

    def test_non_semantic_menu_returns_none(self):
        """Non-semantic options should not be detected."""
        menu = detect_binary_menu("1. Option A\n2. Option B")
        assert menu is None

    def test_three_options_returns_none(self):
        """More than 2 options should not be detected."""
        menu = detect_binary_menu("1. Yes\n2. No\n3. Maybe")
        assert menu is None

    def test_single_option_returns_none(self):
        menu = detect_binary_menu("1. Yes")
        assert menu is None

    def test_no_numbered_options(self):
        menu = detect_binary_menu("Do you want to continue?")
        assert menu is None

    def test_lettered_options(self):
        menu = detect_binary_menu("a. Accept\nb. Cancel")
        assert menu is not None
        assert menu.yes_option == "a"
        assert menu.no_option == "b"

    def test_bracketed_numbers(self):
        menu = detect_binary_menu("[1] Allow\n[2] Deny")
        assert menu is not None
        assert menu.yes_option == "1"
        assert menu.no_option == "2"

    def test_with_surrounding_text(self):
        prompt = "Choose an option:\n1. Allow\n2. Deny\nEnter your choice:"
        menu = detect_binary_menu(prompt)
        assert menu is not None
        assert menu.yes_option == "1"

    def test_confirm_abort(self):
        menu = detect_binary_menu("1. Confirm\n2. Abort")
        assert menu is not None
        assert menu.yes_option == "1"
        assert menu.no_option == "2"


class TestNormalizeReply:
    """Map natural language replies to option keys."""

    @pytest.fixture
    def menu(self) -> BinaryMenu:
        return BinaryMenu(
            yes_option="1",
            no_option="2",
            yes_label="Allow",
            no_label="Deny",
        )

    def test_digit_passthrough(self, menu):
        assert normalize_reply(menu, "1") == "1"
        assert normalize_reply(menu, "2") == "2"

    def test_yes_synonym(self, menu):
        assert normalize_reply(menu, "yes") == "1"
        assert normalize_reply(menu, "y") == "1"
        assert normalize_reply(menu, "ok") == "1"

    def test_no_synonym(self, menu):
        assert normalize_reply(menu, "no") == "2"
        assert normalize_reply(menu, "n") == "2"
        assert normalize_reply(menu, "deny") == "2"

    def test_case_insensitive(self, menu):
        assert normalize_reply(menu, "YES") == "1"
        assert normalize_reply(menu, "No") == "2"
        assert normalize_reply(menu, "ALLOW") == "1"

    def test_whitespace_stripped(self, menu):
        assert normalize_reply(menu, "  yes  ") == "1"
        assert normalize_reply(menu, "\tno\n") == "2"

    def test_ambiguous_returns_none(self, menu):
        assert normalize_reply(menu, "maybe") is None
        assert normalize_reply(menu, "hello") is None
        assert normalize_reply(menu, "3") is None

    @pytest.mark.parametrize("synonym", sorted(YES_SYNONYMS))
    def test_all_yes_synonyms(self, menu, synonym):
        assert normalize_reply(menu, synonym) == "1"

    @pytest.mark.parametrize("synonym", sorted(NO_SYNONYMS))
    def test_all_no_synonyms(self, menu, synonym):
        assert normalize_reply(menu, synonym) == "2"

    def test_reversed_menu(self):
        """When yes is option 2, synonyms map to 2."""
        menu = BinaryMenu(yes_option="2", no_option="1", yes_label="Accept", no_label="Reject")
        assert normalize_reply(menu, "yes") == "2"
        assert normalize_reply(menu, "no") == "1"

    def test_lettered_options(self):
        menu = BinaryMenu(yes_option="a", no_option="b", yes_label="Allow", no_label="Deny")
        assert normalize_reply(menu, "a") == "a"
        assert normalize_reply(menu, "yes") == "a"
        assert normalize_reply(menu, "no") == "b"


class TestSynonymSets:
    """Verify synonym set properties."""

    def test_no_overlap(self):
        """YES and NO synonyms must not overlap."""
        overlap = YES_SYNONYMS & NO_SYNONYMS
        assert overlap == set(), f"Overlapping synonyms: {overlap}"

    def test_all_lowercase(self):
        for s in YES_SYNONYMS:
            assert s == s.lower(), f"YES synonym not lowercase: {s}"
        for s in NO_SYNONYMS:
            assert s == s.lower(), f"NO synonym not lowercase: {s}"

    def test_minimum_synonyms(self):
        assert len(YES_SYNONYMS) >= 5
        assert len(NO_SYNONYMS) >= 5

    def test_core_synonyms_present(self):
        assert "yes" in YES_SYNONYMS
        assert "y" in YES_SYNONYMS
        assert "no" in NO_SYNONYMS
        assert "n" in NO_SYNONYMS
