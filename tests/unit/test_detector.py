"""Unit tests for aegis.policy.detector — PromptDetector."""

from __future__ import annotations

import pytest

from aegis.core.constants import PromptType
from aegis.policy.detector import PromptDetector, _strip_ansi


@pytest.fixture
def detector() -> PromptDetector:
    return PromptDetector(threshold=0.65)


# ---------------------------------------------------------------------------
# YES/NO detection
# ---------------------------------------------------------------------------


class TestYesNoDetection:
    def test_yn_parentheses(self, detector: PromptDetector) -> None:
        result = detector.detect("Do you want to continue? (y/n)")
        assert result.detected
        assert result.prompt_type == PromptType.YES_NO
        assert result.confidence >= 0.65

    def test_yn_brackets(self, detector: PromptDetector) -> None:
        result = detector.detect("Overwrite existing file? [y/N]")
        assert result.detected
        assert result.prompt_type == PromptType.YES_NO

    def test_yes_no_word(self, detector: PromptDetector) -> None:
        result = detector.detect("Proceed with installation? (yes/no)")
        assert result.detected
        assert result.prompt_type == PromptType.YES_NO

    def test_delete_yn(self, detector: PromptDetector) -> None:
        result = detector.detect("Delete all files? (y/n)")
        assert result.detected
        assert result.prompt_type == PromptType.YES_NO

    def test_no_false_positive_plain_sentence(self, detector: PromptDetector) -> None:
        result = detector.detect("Processing 100 items, this may take a while.")
        assert not result.detected

    def test_no_false_positive_empty(self, detector: PromptDetector) -> None:
        result = detector.detect("")
        assert not result.detected


# ---------------------------------------------------------------------------
# CONFIRM ENTER detection
# ---------------------------------------------------------------------------


class TestConfirmEnterDetection:
    def test_press_enter(self, detector: PromptDetector) -> None:
        result = detector.detect("Press Enter to continue")
        assert result.detected
        assert result.prompt_type == PromptType.CONFIRM_ENTER

    def test_press_enter_brackets(self, detector: PromptDetector) -> None:
        result = detector.detect("[Press Enter]")
        assert result.detected
        assert result.prompt_type == PromptType.CONFIRM_ENTER

    def test_hit_enter(self, detector: PromptDetector) -> None:
        result = detector.detect("Hit enter to proceed")
        assert result.detected
        assert result.prompt_type == PromptType.CONFIRM_ENTER

    def test_press_return(self, detector: PromptDetector) -> None:
        result = detector.detect("Press Return to start")
        assert result.detected
        assert result.prompt_type == PromptType.CONFIRM_ENTER


# ---------------------------------------------------------------------------
# MULTIPLE CHOICE detection
# ---------------------------------------------------------------------------


class TestMultipleChoiceDetection:
    def test_numbered_list(self, detector: PromptDetector) -> None:
        text = "Choose an option:\n1) Install\n2) Update\n3) Remove"
        result = detector.detect(text)
        assert result.detected
        assert result.prompt_type == PromptType.MULTIPLE_CHOICE

    def test_choices_extracted(self, detector: PromptDetector) -> None:
        text = "1) Option A\n2) Option B\n3) Option C\nEnter choice [1-3]:"
        result = detector.detect(text)
        assert result.detected
        assert result.prompt_type == PromptType.MULTIPLE_CHOICE
        assert len(result.choices) >= 2

    def test_enter_choice_range(self, detector: PromptDetector) -> None:
        result = detector.detect("Enter your choice [1-4]:")
        assert result.detected
        assert result.prompt_type == PromptType.MULTIPLE_CHOICE

    def test_which_do_you_want(self, detector: PromptDetector) -> None:
        result = detector.detect("Which package manager do you want to use?")
        assert result.detected
        assert result.prompt_type == PromptType.MULTIPLE_CHOICE


# ---------------------------------------------------------------------------
# FREE TEXT detection
# ---------------------------------------------------------------------------


class TestFreeTextDetection:
    def test_enter_name(self, detector: PromptDetector) -> None:
        result = detector.detect("Enter your name:")
        assert result.detected
        assert result.prompt_type == PromptType.FREE_TEXT

    def test_password_prompt(self, detector: PromptDetector) -> None:
        result = detector.detect("Password:")
        assert result.detected
        assert result.prompt_type == PromptType.FREE_TEXT

    def test_api_key_prompt(self, detector: PromptDetector) -> None:
        result = detector.detect("Enter your API key:")
        assert result.detected
        assert result.prompt_type == PromptType.FREE_TEXT


# ---------------------------------------------------------------------------
# ANSI stripping
# ---------------------------------------------------------------------------


class TestAnsiStripping:
    def test_strip_color_codes(self) -> None:
        text = "\x1b[32mGreen text\x1b[0m"
        assert _strip_ansi(text) == "Green text"

    def test_yn_with_ansi(self, detector: PromptDetector) -> None:
        text = "\x1b[1mContinue?\x1b[0m (y/n) "
        result = detector.detect(text)
        assert result.detected
        assert result.prompt_type == PromptType.YES_NO


# ---------------------------------------------------------------------------
# Structured / blocking heuristic
# ---------------------------------------------------------------------------


class TestSpecialDetectionModes:
    def test_structured_yes_no(self, detector: PromptDetector) -> None:
        result = detector.detect_structured("TYPE_YES_NO", "Proceed? (y/n)")
        assert result.detected
        assert result.prompt_type == PromptType.YES_NO
        assert result.confidence == 1.0
        assert result.method == "structured"

    def test_structured_unknown_type(self, detector: PromptDetector) -> None:
        result = detector.detect_structured("TYPE_WHATEVER", "some prompt")
        assert result.detected
        assert result.prompt_type == PromptType.UNKNOWN

    def test_blocking_heuristic(self, detector: PromptDetector) -> None:
        result = detector.detect_blocking("$ ")
        assert result.detected
        assert result.prompt_type == PromptType.UNKNOWN
        assert result.confidence == 0.60
        assert result.method == "blocking_heuristic"


# ---------------------------------------------------------------------------
# Threshold gating
# ---------------------------------------------------------------------------


class TestThreshold:
    def test_high_threshold_rejects_weak_match(self) -> None:
        d = PromptDetector(threshold=0.99)
        # A single "> " alone shouldn't pass a 0.99 threshold
        result = d.detect("> ")
        # Either not detected or below threshold
        assert not result.detected or result.confidence < 0.99

    def test_low_threshold_passes_all(self) -> None:
        d = PromptDetector(threshold=0.0)
        result = d.detect("Do you want to continue? (y/n)")
        assert result.detected
