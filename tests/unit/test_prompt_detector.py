"""Unit tests for atlasbridge.core.prompt.detector — PromptDetector tri-signal detection."""

from __future__ import annotations

import time

import pytest

from atlasbridge.core.prompt.detector import (
    CONTENT_DEDUP_WINDOW_S,
    ECHO_SUPPRESS_MS,
    PromptDetector,
)
from atlasbridge.core.prompt.models import Confidence, PromptType

SESSION = "test-session-abc123"


@pytest.fixture
def detector() -> PromptDetector:
    return PromptDetector(session_id=SESSION)


# ---------------------------------------------------------------------------
# Signal 1 — pattern matching (YES/NO)
# ---------------------------------------------------------------------------


class TestYesNoDetection:
    def test_yn_brackets_detected(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Overwrite existing file? [y/N]")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_YES_NO
        assert event.confidence == Confidence.HIGH

    def test_yes_no_word_detected(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Proceed with installation? (yes/no)")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_YES_NO

    def test_yn_choices_populated(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Delete all files? [y/N]")
        assert event is not None
        assert "y" in event.choices or "n" in event.choices

    def test_no_false_positive_plain_sentence(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Processing 100 items, this may take a while.")
        assert event is None

    def test_no_false_positive_empty(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"")
        assert event is None


# ---------------------------------------------------------------------------
# Signal 1 — CONFIRM ENTER
# ---------------------------------------------------------------------------


class TestConfirmEnterDetection:
    def test_press_enter_to_continue(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Press Enter to continue")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_CONFIRM_ENTER
        assert event.confidence == Confidence.HIGH

    def test_hit_enter(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Hit enter to proceed")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_CONFIRM_ENTER

    def test_press_enter_brackets(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"[Press Enter]")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_CONFIRM_ENTER


# ---------------------------------------------------------------------------
# Signal 1 — MULTIPLE CHOICE
# ---------------------------------------------------------------------------


class TestMultipleChoiceDetection:
    def test_numbered_list(self, detector: PromptDetector) -> None:
        text = b"Choose an option:\n1) Install\n2) Update\n3) Remove"
        event = detector.analyse(text)
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE

    def test_choice_range_brackets(self, detector: PromptDetector) -> None:
        # Just verify no exception — pattern may or may not fire
        detector.analyse(b"Enter your choice [1-3]:")


# ---------------------------------------------------------------------------
# Signal 1 — FREE TEXT
# ---------------------------------------------------------------------------


class TestFreeTextDetection:
    def test_enter_your_name(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Enter your name:")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_FREE_TEXT

    def test_password_prompt(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Password:")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_FREE_TEXT


# ---------------------------------------------------------------------------
# Signal 1 — ANSI stripping
# ---------------------------------------------------------------------------


class TestAnsiStripping:
    def test_strip_color_codes(self, detector: PromptDetector) -> None:
        text = b"\x1b[32mGreen text\x1b[0m"
        event = detector.analyse(text)
        # Plain text without prompt markers — no event expected
        assert event is None

    def test_yn_with_ansi_detected(self, detector: PromptDetector) -> None:
        text = b"\x1b[1mContinue?\x1b[0m (yes/no) "
        event = detector.analyse(text)
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_YES_NO


# ---------------------------------------------------------------------------
# Signal 2 — TTY blocked-on-read
# ---------------------------------------------------------------------------


class TestTTYBlockedSignal:
    def test_tty_blocked_returns_free_text_med(self, detector: PromptDetector) -> None:
        # Non-matching output + tty_blocked=True → Signal 2
        event = detector.analyse(b"some non-matching output", tty_blocked=True)
        assert event is not None
        assert event.confidence == Confidence.MED
        assert event.prompt_type == PromptType.TYPE_FREE_TEXT

    def test_tty_blocked_suppressed_during_echo(self, detector: PromptDetector) -> None:
        detector.mark_injected()
        event = detector.analyse(b"injected echo text", tty_blocked=True)
        assert event is None  # suppressed within echo window


# ---------------------------------------------------------------------------
# Signal 3 — silence threshold
# ---------------------------------------------------------------------------


class TestSilenceFallback:
    def test_no_event_before_threshold(self, detector: PromptDetector) -> None:
        # Threshold is 3.0 s by default; immediately after construction it's below threshold
        event = detector.check_silence(process_running=True)
        assert event is None

    def test_no_event_if_process_dead(self, detector: PromptDetector) -> None:
        # Force silence by manipulating state
        detector._state.last_output_time = time.monotonic() - 100.0
        event = detector.check_silence(process_running=False)
        assert event is None  # process not running → no event

    def test_event_fires_after_threshold(self) -> None:
        d = PromptDetector(session_id="silence-test", silence_threshold_s=0.01)
        # Feed meaningful output first so stable_excerpt is populated
        d.analyse(b"Waiting for your input...")
        d._state.last_output_time = time.monotonic() - 1.0  # well past threshold
        event = d.check_silence(process_running=True)
        assert event is not None
        assert event.confidence == Confidence.LOW

    def test_no_event_when_excerpt_empty(self) -> None:
        d = PromptDetector(session_id="silence-empty", silence_threshold_s=0.01)
        d._state.last_output_time = time.monotonic() - 1.0
        # stable_excerpt is "" (no output fed) → should NOT fire
        event = d.check_silence(process_running=True)
        assert event is None


# ---------------------------------------------------------------------------
# ANSI junk regression — private-mode CSI sequences
# ---------------------------------------------------------------------------


class TestAnsiJunkRegression:
    def test_private_mode_csi_no_event(self, detector: PromptDetector) -> None:
        """Root cause: \\x1b[?1004l was not stripped, polluting stable_excerpt."""
        event = detector.analyse(b"\x1b[?1004l\x1b[?2004l")
        assert event is None

    def test_ansi_junk_does_not_pollute_stable_excerpt(self) -> None:
        d = PromptDetector(session_id="ansi-junk", silence_threshold_s=0.01)
        d.analyse(b"\x1b[?1004l\x1b[?2004l")
        d._state.last_output_time = time.monotonic() - 1.0
        # stable_excerpt should still be empty → Signal 3 should not fire
        event = d.check_silence(process_running=True)
        assert event is None

    def test_real_prompt_after_ansi_junk(self) -> None:
        d = PromptDetector(session_id="junk-then-real")
        d.analyse(b"\x1b[?1004l\x1b[?2004l")
        event = d.analyse(b"Delete all files? [y/N]")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_YES_NO

    def test_mixed_ansi_junk_and_real_text(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"\x1b[?1004l\x1b[?2004l\x1b[32mContinue?\x1b[0m (yes/no)")
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_YES_NO


# ---------------------------------------------------------------------------
# MULTIPLE_CHOICE — choice extraction
# ---------------------------------------------------------------------------


class TestMultipleChoiceChoices:
    def test_numbered_choices_populated(self, detector: PromptDetector) -> None:
        text = b"Choose an option:\n1) Install\n2) Update\n3) Remove"
        event = detector.analyse(text)
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE
        assert event.choices == ["Install", "Update", "Remove"]


# ---------------------------------------------------------------------------
# Echo suppression
# ---------------------------------------------------------------------------


class TestEchoSuppression:
    def test_pattern_match_suppressed_after_inject(self, detector: PromptDetector) -> None:
        detector.mark_injected()
        # Even a clear yes/no prompt should be suppressed immediately after injection
        event = detector.analyse(b"Delete all? [y/N]")
        assert event is None

    def test_detection_resumes_after_window(self) -> None:
        # Use a short-window detector by manipulating injection_time
        d = PromptDetector(session_id="echo-test")
        d._state.injection_time = time.monotonic() - (ECHO_SUPPRESS_MS / 1000.0) - 0.1
        event = d.analyse(b"Delete all? [y/N]")
        assert event is not None

    def test_session_id_in_event(self, detector: PromptDetector) -> None:
        event = detector.analyse(b"Proceed? [y/N]")
        assert event is not None
        assert event.session_id == SESSION


# ---------------------------------------------------------------------------
# Folder trust detection
# ---------------------------------------------------------------------------


class TestFolderTrustDetection:
    """Folder trust prompts from Claude Code should be detected as MULTIPLE_CHOICE."""

    def test_folder_trust_single_chunk(self, detector: PromptDetector) -> None:
        """Full folder trust menu in a single PTY chunk → MULTIPLE_CHOICE."""
        text = (
            b"Do you trust the files in this folder?\n"
            b"1. Yes, trust this folder\n"
            b"2. Yes, but only for this session\n"
            b"3. No, don't trust this folder\n"
        )
        event = detector.analyse(text)
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE
        assert event.confidence == Confidence.HIGH

    def test_folder_trust_split_chunks(self) -> None:
        """Folder trust question + items arrive in separate PTY chunks."""
        d = PromptDetector(session_id="split-test")
        # Chunk 1: just the question
        event1 = d.analyse(b"Do you trust the files in this folder?")
        # Question alone shouldn't match multiple choice
        assert event1 is None or event1.prompt_type != PromptType.TYPE_MULTIPLE_CHOICE

        # Chunk 2: the numbered items
        event2 = d.analyse(
            b"1. Yes, trust this folder\n"
            b"2. Yes, but only for this session\n"
            b"3. No, don't trust this folder\n"
        )
        # Combined buffer should now match
        assert event2 is not None
        assert event2.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE

    def test_folder_trust_with_ansi(self, detector: PromptDetector) -> None:
        """Folder trust prompt with ANSI formatting still detected."""
        text = (
            b"\x1b[1mDo you trust the files in this folder?\x1b[0m\n"
            b"1. Yes, trust this folder\n"
            b"2. No, don't trust\n"
        )
        event = detector.analyse(text)
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE

    def test_folder_trust_dot_format(self, detector: PromptDetector) -> None:
        """Claude Code uses '1.' not '1)' — ensure dot format is matched."""
        text = b"Trust this folder?\n1. Trust\n2. Security guide\n"
        event = detector.analyse(text)
        assert event is not None
        assert event.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE


# ---------------------------------------------------------------------------
# Content dedup — prevents prompt notification spam
# ---------------------------------------------------------------------------


class TestContentDedup:
    """Verifies that identical prompt text within the dedup window is suppressed."""

    def test_same_prompt_suppressed_on_second_analyse(self) -> None:
        d = PromptDetector(session_id="dedup-test")
        text = b"Delete all files? [y/N]"
        e1 = d.analyse(text)
        assert e1 is not None
        e2 = d.analyse(text)
        assert e2 is None  # duplicate within 30s window

    def test_different_prompt_not_suppressed(self) -> None:
        d = PromptDetector(session_id="dedup-diff")
        e1 = d.analyse(b"Delete all files? [y/N]")
        assert e1 is not None
        e2 = d.analyse(b"Overwrite config? [y/N]")
        assert e2 is not None  # different content — allowed

    def test_dedup_window_expires(self) -> None:
        d = PromptDetector(session_id="dedup-expire")
        e1 = d.analyse(b"Delete all? [y/N]")
        assert e1 is not None
        # Simulate window expiry
        d._state.last_emitted_at = time.monotonic() - CONTENT_DEDUP_WINDOW_S - 1.0
        e2 = d.analyse(b"Delete all? [y/N]")
        assert e2 is not None  # window expired — new event emitted

    def test_dedup_resets_after_injection(self) -> None:
        d = PromptDetector(session_id="dedup-inject")
        text = b"Proceed? (yes/no)"
        e1 = d.analyse(text)
        assert e1 is not None

        d.mark_injected()
        # Wait for echo suppression to pass
        d._state.injection_time = time.monotonic() - (ECHO_SUPPRESS_MS / 1000.0) - 0.1

        # Same text re-appears (agent re-asked) — should detect again
        e2 = d.analyse(text)
        assert e2 is not None

    def test_folder_trust_spam_suppressed(self) -> None:
        """Reproduces the P0 bug: folder trust prompt re-detected on every PTY chunk."""
        d = PromptDetector(session_id="trust-spam")
        trust_text = (
            b"Do you trust the files in this folder?\n"
            b"1. Yes, trust this folder\n"
            b"2. Yes, but only for this session\n"
            b"3. No, don't trust this folder\n"
        )
        e1 = d.analyse(trust_text)
        assert e1 is not None
        assert e1.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE

        # Simulate PTY redraw — same text arrives again
        for _ in range(10):
            e = d.analyse(trust_text)
            assert e is None  # all suppressed

    def test_silence_watchdog_dedup(self) -> None:
        """Signal 3 (silence) should also be deduped with same excerpt."""
        d = PromptDetector(session_id="silence-dedup", silence_threshold_s=0.01)
        d.analyse(b"Waiting for input...")
        d._state.last_output_time = time.monotonic() - 1.0
        e1 = d.check_silence(process_running=True)
        assert e1 is not None
        assert e1.confidence == Confidence.LOW

        # Second check with same stable_excerpt — should be deduped
        d._state.last_output_time = time.monotonic() - 1.0
        e2 = d.check_silence(process_running=True)
        assert e2 is None

    def test_injection_clears_stable_excerpt(self) -> None:
        """mark_injected() should clear stable_excerpt to prevent combined buffer re-match."""
        d = PromptDetector(session_id="clear-excerpt")
        d.analyse(b"Do you trust the files in this folder?")
        assert d._state.stable_excerpt != ""
        d.mark_injected()
        assert d._state.stable_excerpt == ""
