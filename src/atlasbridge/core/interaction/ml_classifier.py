"""
Optional ML-based interaction classifier — local-only, never authoritative.

Defines the ``MLClassifier`` protocol and a ``NullMLClassifier`` default
that returns None for all inputs.  The fuser (``fuser.py``) combines
ML output with the deterministic classifier using strict safety rules.

ML classifiers must be:
  - Local-only (no network calls)
  - Deterministic for the same input
  - Fast (< 10ms per classification)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable


class MLClassification(StrEnum):
    """ML classifier output — may include types the deterministic classifier cannot produce."""

    YES_NO = "yes_no"
    CONFIRM_ENTER = "confirm_enter"
    NUMBERED_CHOICE = "numbered_choice"
    FREE_TEXT = "free_text"
    PASSWORD_INPUT = "password_input"  # noqa: S105
    CHAT_INPUT = "chat_input"
    FOLDER_TRUST = "folder_trust"  # "Trust this folder?" special-case
    RAW_TERMINAL = "raw_terminal"  # Unparsable interactive prompts
    UNKNOWN = "unknown"  # ML is uncertain


@runtime_checkable
class MLClassifier(Protocol):
    """Protocol for optional ML-based interaction classifiers.

    Implementations must be local-only (no network calls), deterministic
    for the same input, and fast (< 10ms per classification).
    """

    def classify(self, text: str, prompt_type: str) -> MLClassification | None:
        """Return a classification or None if the ML model has no opinion."""
        ...


class NullMLClassifier:
    """Default no-op ML classifier.  Always returns None.

    Used when no ML model is configured.  The fuser treats None
    as "no ML opinion" and uses the deterministic classifier alone.
    """

    def classify(self, text: str, prompt_type: str) -> MLClassification | None:
        return None
