"""
InteractionClassifier — deterministic refinement of PromptType.

The existing PromptType enum (4 values) stays unchanged.
InteractionClass is a finer-grained classification used by the
interaction engine to choose execution strategy.

Mapping:
  TYPE_YES_NO         → YES_NO
  TYPE_CONFIRM_ENTER  → CONFIRM_ENTER
  TYPE_MULTIPLE_CHOICE→ NUMBERED_CHOICE
  TYPE_FREE_TEXT      → check password patterns → PASSWORD_INPUT or FREE_TEXT
  None (no event)     → CHAT_INPUT
"""

from __future__ import annotations

import re
from enum import StrEnum
from re import Pattern

from atlasbridge.core.prompt.models import PromptEvent, PromptType


class InteractionClass(StrEnum):
    """Fine-grained interaction classification."""

    YES_NO = "yes_no"
    CONFIRM_ENTER = "confirm_enter"
    NUMBERED_CHOICE = "numbered_choice"
    FREE_TEXT = "free_text"
    PASSWORD_INPUT = "password_input"  # noqa: S105
    CHAT_INPUT = "chat_input"


# ---------------------------------------------------------------------------
# Password / credential detection patterns
# ---------------------------------------------------------------------------

_PASSWORD_PATTERNS: list[Pattern[str]] = [
    re.compile(
        r"(?:password|passphrase|passwd)\s*:\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"(?:token|api.?key|secret|credential)\s*:\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"(?:ssh|gpg)\s+(?:key\s+)?(?:passphrase|password)\s*:\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
]


class InteractionClassifier:
    """
    Refines a PromptEvent into an InteractionClass.

    The classifier is stateless and deterministic — same input always
    produces the same output.
    """

    def classify(self, event: PromptEvent | None) -> InteractionClass:
        """
        Classify a PromptEvent into an InteractionClass.

        Args:
            event: A PromptEvent from the detector, or None for chat mode.

        Returns:
            The refined InteractionClass.
        """
        if event is None:
            return InteractionClass.CHAT_INPUT

        match event.prompt_type:
            case PromptType.TYPE_YES_NO:
                return InteractionClass.YES_NO
            case PromptType.TYPE_CONFIRM_ENTER:
                return InteractionClass.CONFIRM_ENTER
            case PromptType.TYPE_MULTIPLE_CHOICE:
                return InteractionClass.NUMBERED_CHOICE
            case PromptType.TYPE_FREE_TEXT:
                return self._refine_free_text(event)
            case _:
                return InteractionClass.FREE_TEXT

    def _refine_free_text(self, event: PromptEvent) -> InteractionClass:
        """Check if a FREE_TEXT prompt is actually a password/credential prompt."""
        text = event.excerpt
        for pat in _PASSWORD_PATTERNS:
            if pat.search(text):
                return InteractionClass.PASSWORD_INPUT
        return InteractionClass.FREE_TEXT
