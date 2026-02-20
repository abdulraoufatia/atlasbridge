"""
Aegis prompt detector — three-layer classification of terminal output.

Layer 1 (confidence 1.0): Structured JSON event from the tool
Layer 2 (confidence 0.65–0.95): Regex pattern matching on terminal text
Layer 3 (confidence 0.60): Blocking heuristic — no output for N seconds

Only Layer 2 is implemented here; the blocking heuristic is signalled
by the PTY supervisor when it detects stdin stall. Layer 1 is handled
by the adapter if the tool emits machine-readable events.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from aegis.core.constants import PromptType


# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------


@dataclass
class DetectionResult:
    """Output of the detector for one terminal chunk."""

    detected: bool
    prompt_type: PromptType = PromptType.UNKNOWN
    confidence: float = 0.0
    excerpt: str = ""
    choices: list[str] = field(default_factory=list)
    method: str = "text_pattern"

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.65


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# YES/NO patterns — "Do you want to…? (y/n)" etc.
_YES_NO_PATTERNS: list[re.Pattern[str]] = [
    # (Y/n), (y/N), [y/n], [Y/N], (yes/no)
    re.compile(r"\(\s*[Yy]\s*/\s*[Nn]\s*\)", re.IGNORECASE),
    re.compile(r"\[\s*[Yy]\s*/\s*[Nn]\s*\]", re.IGNORECASE),
    re.compile(r"\(\s*yes\s*/\s*no\s*\)", re.IGNORECASE),
    # Trailing "? [y/n]" or "? (y/n)"
    re.compile(r"\?\s*[\[\(]\s*[yYnN]\s*/\s*[yYnN]\s*[\]\)]"),
    # "Proceed? y/n" or "Continue? (y/n):"
    re.compile(r"(?:proceed|continue|confirm|allow|accept|approve|delete|remove|overwrite|install|update|upgrade|reset|clear|flush|terminate|kill|stop|disable|enable)\b.*\?\s*[\[\(]?[Yy]\s*/\s*[Nn][\]\)]?", re.IGNORECASE),
    # "Press y to continue, n to abort"
    re.compile(r"press\s+['\"]?[yY]['\"]?\s+to\s+\w+", re.IGNORECASE),
    # "Enter y or n" / "Type y/n"
    re.compile(r"(?:enter|type)\s+['\"]?[yY]['\"]?\s+or\s+['\"]?[nN]", re.IGNORECASE),
]

# CONFIRM ENTER patterns — "Press Enter to continue", blank line with cursor
_CONFIRM_ENTER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"press\s+(?:enter|return|<enter>|<return>)\s+to\s+(?:continue|proceed|confirm|accept|start|begin)", re.IGNORECASE),
    re.compile(r"hit\s+(?:enter|return)\s+to\s+(?:continue|proceed)", re.IGNORECASE),
    re.compile(r"\[Press\s+Enter\]", re.IGNORECASE),
    re.compile(r"--\s*(?:More|Press\s+Enter\s+to\s+continue)\s*--", re.IGNORECASE),
    # Minimal "press enter" without further context
    re.compile(r"\bpress\s+enter\b", re.IGNORECASE),
]

# MULTIPLE CHOICE patterns — numbered lists with a "choose" prompt
_MULTIPLE_CHOICE_PATTERNS: list[re.Pattern[str]] = [
    # "Enter your choice [1-4]:" or "Select an option (1-3):"
    re.compile(r"(?:enter|select|choose|pick)\s+(?:your\s+)?(?:choice|option|selection)\s*[\(\[]\s*\d+\s*[-–]\s*\d+\s*[\)\]]", re.IGNORECASE),
    # "Enter choice:" alone is weak; require digit list context
    re.compile(r"(?:enter|select|choose)\s+(?:an?\s+)?(?:choice|option):\s*$", re.IGNORECASE | re.MULTILINE),
    # List of items: "1) ...\n2) ...\n"
    re.compile(r"(?:^|\n)\s*1[\)\.]\s+\S.+\n\s*2[\)\.]\s+\S", re.DOTALL),
    # Bracketed number prompt at EOL: "Choice [1/2/3]:"
    re.compile(r"[\(\[]\s*1\s*/\s*2", re.IGNORECASE),
    # "Which ... do you want?"
    re.compile(r"\bwhich\b.{1,60}\bdo\s+you\s+(?:want|prefer|choose)\b", re.IGNORECASE),
]

# FREE TEXT patterns — open-ended input prompts
_FREE_TEXT_PATTERNS: list[re.Pattern[str]] = [
    # "Enter <something>:" at line end
    re.compile(r"\benter\b.{1,40}:\s*$", re.IGNORECASE | re.MULTILINE),
    # "Type your message:" / "Provide a description:"
    re.compile(r"(?:type|provide|input|give|write)\b.{1,40}:\s*$", re.IGNORECASE | re.MULTILINE),
    # Password / secret prompts
    re.compile(r"(?:password|passphrase|secret|token|key|api.?key|auth.?token)\s*:\s*$", re.IGNORECASE | re.MULTILINE),
    # "Name:" / "Email:" bare field prompts
    re.compile(r"^(?:name|email|username|user|host|url|path|file|directory|comment|message|description)\s*:\s*$", re.IGNORECASE | re.MULTILINE),
    # Generic input prompt with terminal cursor indicator
    re.compile(r">\s*$"),
]


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class PromptDetector:
    """
    Classify terminal output chunks into prompt types with confidence scores.

    Usage::

        detector = PromptDetector(threshold=0.65)
        result = detector.detect(chunk)
        if result.detected:
            ...
    """

    def __init__(self, threshold: float = 0.65) -> None:
        self.threshold = threshold

    def detect(self, text: str) -> DetectionResult:
        """Run all pattern layers and return the best match."""
        if not text or not text.strip():
            return DetectionResult(detected=False)

        # Normalise: strip ANSI escape sequences before matching
        clean = _strip_ansi(text)

        # Try each type in priority order
        for prompt_type, patterns, base_confidence in _LAYERS:
            result = _match_patterns(clean, patterns, prompt_type, base_confidence)
            if result and result.confidence >= self.threshold:
                result.excerpt = _extract_excerpt(clean)
                if prompt_type == PromptType.MULTIPLE_CHOICE:
                    result.choices = _extract_choices(clean)
                return result

        return DetectionResult(detected=False)

    def detect_structured(
        self,
        prompt_type_str: str,
        excerpt: str,
        choices: list[str] | None = None,
    ) -> DetectionResult:
        """
        Layer 1: accept a structured event from the tool itself (confidence 1.0).
        """
        try:
            pt = PromptType(prompt_type_str)
        except ValueError:
            pt = PromptType.UNKNOWN
        return DetectionResult(
            detected=True,
            prompt_type=pt,
            confidence=1.0,
            excerpt=excerpt,
            choices=choices or [],
            method="structured",
        )

    def detect_blocking(self, last_text: str) -> DetectionResult:
        """
        Layer 3: heuristic — process is blocked on stdin (no output for N seconds).
        Returns UNKNOWN with confidence 0.60.
        """
        return DetectionResult(
            detected=True,
            prompt_type=PromptType.UNKNOWN,
            confidence=0.60,
            excerpt=_extract_excerpt(_strip_ansi(last_text)) if last_text else "",
            method="blocking_heuristic",
        )


# ---------------------------------------------------------------------------
# Pattern matching helpers
# ---------------------------------------------------------------------------

_LAYERS: list[tuple[PromptType, list[re.Pattern[str]], float]] = [
    (PromptType.YES_NO, _YES_NO_PATTERNS, 0.85),
    (PromptType.CONFIRM_ENTER, _CONFIRM_ENTER_PATTERNS, 0.80),
    (PromptType.MULTIPLE_CHOICE, _MULTIPLE_CHOICE_PATTERNS, 0.75),
    (PromptType.FREE_TEXT, _FREE_TEXT_PATTERNS, 0.65),
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]|\x1b[c-z]|\x1b\[[0-9]*[A-D]|\x0d|\x08")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _match_patterns(
    text: str,
    patterns: list[re.Pattern[str]],
    prompt_type: PromptType,
    base_confidence: float,
) -> DetectionResult | None:
    matches = sum(1 for p in patterns if p.search(text))
    if matches == 0:
        return None
    # Confidence scales slightly with number of matching patterns
    confidence = min(0.99, base_confidence + (matches - 1) * 0.05)
    return DetectionResult(
        detected=True,
        prompt_type=prompt_type,
        confidence=confidence,
    )


def _extract_excerpt(text: str, max_chars: int = 200) -> str:
    """Return the last non-empty lines of text, up to max_chars."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    excerpt = " | ".join(lines[-3:])  # up to 3 trailing lines
    return excerpt[:max_chars]


def _extract_choices(text: str) -> list[str]:
    """
    Extract numbered options like "1) Foo\\n2) Bar" from text.
    Returns a list of option labels (without leading number).
    """
    pattern = re.compile(r"^\s*(\d+)[)\.]\s+(.+)$", re.MULTILINE)
    matches = pattern.findall(text)
    if not matches:
        return []
    # Sort by number; cap at 9
    numbered = sorted(matches, key=lambda m: int(m[0]))[:9]
    return [label.strip() for _, label in numbered]
