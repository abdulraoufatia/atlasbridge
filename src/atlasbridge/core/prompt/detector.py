"""
Tri-signal prompt detector.

Signal 1 — Pattern match (regex/signatures)        → Confidence HIGH/MED
Signal 2 — TTY blocked-on-read inference           → Confidence MED
Signal 3 — Time-based fallback (no output, N secs) → Confidence LOW

Output: PromptEvent | None

Combination rules:
  HIGH signal                   → route immediately
  MED + TTY blocked             → route
  LOW alone                     → ambiguity protocol (SEND_ENTER/CANCEL/SHOW_LAST_OUTPUT)
  No signal                     → None (not a prompt)

Echo suppression:
  After injection, suppress detection for ECHO_SUPPRESS_MS milliseconds
  to prevent the echoed input text from triggering a new prompt event.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from re import Pattern

from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType
from atlasbridge.core.prompt.sanitize import extract_choices, is_meaningful, strip_ansi

# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------

# YES/NO patterns — high confidence
_YES_NO_PATTERNS: list[Pattern[str]] = [
    re.compile(
        r"(?:delete|remove|destroy|overwrite|replace|reset|drop|purge|"
        r"install|update|upgrade|enable|disable|kill|stop|terminate)\b"
        r".{0,60}?\[\s*[Yy]\s*/\s*[Nn]\s*\]",
        re.IGNORECASE,
    ),
    re.compile(r"\(\s*[Yy]es\s*/\s*[Nn]o\s*\)", re.IGNORECASE),
    re.compile(r"\[\s*[Yy]\s*/\s*[Nn]\s*\]\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"(?:^|\n)\s*[Yy]/[Nn]\s*[>:]\s*$", re.MULTILINE),
    re.compile(r"Do you want to (?:proceed|continue|overwrite)\?", re.IGNORECASE),
]

# CONFIRM ENTER patterns
_CONFIRM_ENTER_PATTERNS: list[Pattern[str]] = [
    re.compile(
        r"press\s+(?:enter|return|<enter>|<return>)\s+to\s+"
        r"(?:continue|proceed|confirm|accept|start|begin)",
        re.IGNORECASE,
    ),
    re.compile(r"hit\s+(?:enter|return)\s+to\s+(?:continue|proceed)", re.IGNORECASE),
    re.compile(r"\[Press\s+Enter\]", re.IGNORECASE),
    re.compile(r"--More--", re.IGNORECASE),
]

# MULTIPLE CHOICE patterns
_MULTIPLE_CHOICE_PATTERNS: list[Pattern[str]] = [
    re.compile(
        r"(?:select|choose|pick|enter)\s+(?:an?\s+)?(?:option|choice|number)\s*"
        r"[\(\[]\s*\d+\s*[-–]\s*\d+\s*[\)\]]",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|\n)\s*1[\)\.]\s+\S.+\n\s*2[\)\.]\s+\S", re.DOTALL),
    re.compile(r"(?:^|\n)\s*\[A\].+\[B\]", re.DOTALL | re.IGNORECASE),
    # Folder trust prompt — "trust ... folder" followed by numbered items
    re.compile(
        r"trust.{0,80}folder.{0,200}?\n\s*1[\)\.]\s+",
        re.DOTALL | re.IGNORECASE,
    ),
]

# FREE TEXT patterns
_FREE_TEXT_PATTERNS: list[Pattern[str]] = [
    re.compile(r"(?:enter|type|provide|input)\b.{1,40}:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"(?:name|email|username|branch|message|description)\s*:\s*$", re.IGNORECASE | re.MULTILINE
    ),
    re.compile(r"(?:password|token|api.?key)\s*:\s*$", re.IGNORECASE | re.MULTILINE),
]

ECHO_SUPPRESS_MS = 500  # ms to suppress detection after injection


@dataclass
class DetectorState:
    """Mutable state carried across successive buffer chunks for one session."""

    last_output_time: float = field(default_factory=time.monotonic)
    injection_time: float = 0.0  # monotonic timestamp of last injection
    stable_excerpt: str = ""  # Last stable text before ANSI redraws
    silence_threshold_s: float = 3.0  # Signal 3 threshold


class PromptDetector:
    """
    Analyses terminal output bytes and infers whether the CLI is awaiting input.

    Usage::

        detector = PromptDetector(session_id="abc123")
        event = detector.analyse(chunk_bytes)
        if event:
            await router.route(event)
        # After inject:
        detector.mark_injected()
    """

    def __init__(self, session_id: str, silence_threshold_s: float = 3.0) -> None:
        self.session_id = session_id
        self._state = DetectorState(silence_threshold_s=silence_threshold_s)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, raw: bytes, tty_blocked: bool = False) -> PromptEvent | None:
        """
        Analyse a new chunk of terminal output.

        Args:
            raw:         Raw bytes from PTY master.
            tty_blocked: True if the OS-level read-block signal is active (Signal 2).

        Returns:
            PromptEvent if a prompt is detected, else None.
        """
        if self._in_echo_suppress_window():
            return None

        text = strip_ansi(raw.decode("utf-8", errors="replace"))
        self._state.last_output_time = time.monotonic()

        # Only update stable_excerpt with meaningful content (not ANSI junk remnants)
        if text.strip() and is_meaningful(text):
            self._state.stable_excerpt = text

        # Signal 1 — pattern match
        event = self._pattern_match(text)
        if event:
            return event

        # Signal 2 — TTY blocked-on-read
        if tty_blocked:
            return PromptEvent.create(
                session_id=self.session_id,
                prompt_type=PromptType.TYPE_FREE_TEXT,
                confidence=Confidence.MED,
                excerpt=self._state.stable_excerpt[-200:],
            )

        return None

    def check_silence(self, process_running: bool) -> PromptEvent | None:
        """
        Signal 3 — time-based fallback. Call periodically from the stall watchdog.
        Returns a LOW-confidence PromptEvent if silence threshold exceeded.
        """
        if not process_running or self._in_echo_suppress_window():
            return None
        elapsed = time.monotonic() - self._state.last_output_time
        if elapsed >= self._state.silence_threshold_s:
            excerpt = self._state.stable_excerpt[-200:]
            # Guard: don't fire Signal 3 if stable_excerpt is empty or not meaningful
            if not excerpt or not is_meaningful(excerpt):
                return None
            return PromptEvent.create(
                session_id=self.session_id,
                prompt_type=PromptType.TYPE_FREE_TEXT,
                confidence=Confidence.LOW,
                excerpt=excerpt,
            )
        return None

    @property
    def last_output_time(self) -> float:
        """Monotonic timestamp of the last PTY output received."""
        return self._state.last_output_time

    def mark_injected(self) -> None:
        """Call immediately after injecting a reply — starts echo suppression window."""
        self._state.injection_time = time.monotonic()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _in_echo_suppress_window(self) -> bool:
        elapsed_ms = (time.monotonic() - self._state.injection_time) * 1000
        return elapsed_ms < ECHO_SUPPRESS_MS

    def _pattern_match(self, text: str) -> PromptEvent | None:
        for pat in _YES_NO_PATTERNS:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_YES_NO,
                    confidence=Confidence.HIGH,
                    excerpt=text[-200:],
                    choices=["y", "n"],
                )
        for pat in _CONFIRM_ENTER_PATTERNS:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_CONFIRM_ENTER,
                    confidence=Confidence.HIGH,
                    excerpt=text[-200:],
                    choices=["\n"],
                )
        # For MULTIPLE_CHOICE, also try combined buffer (handles multi-chunk menus
        # like folder trust prompts where the question and items arrive separately).
        combined = (self._state.stable_excerpt + "\n" + text)[-2000:]
        for pat in _MULTIPLE_CHOICE_PATTERNS:
            matched_text = text
            if not pat.search(text) and not pat.search(combined):
                continue
            if not pat.search(text):
                matched_text = combined
            choices = extract_choices(matched_text)
            return PromptEvent.create(
                session_id=self.session_id,
                prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
                confidence=Confidence.HIGH,
                excerpt=matched_text[-200:],
                choices=choices,
            )
        for pat in _FREE_TEXT_PATTERNS:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_FREE_TEXT,
                    confidence=Confidence.MED,
                    excerpt=text[-200:],
                )
        return None
