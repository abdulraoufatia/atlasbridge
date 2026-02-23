"""Reply normalizer for binary semantic numbered menus.

Detects when a numbered menu has exactly two options with yes/no semantics,
and maps natural language replies (yes, no, allow, deny, etc.) to the
correct option number.

Deterministic rules only — no ML. Explicit word lists, version-controlled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Semantic synonym sets — explicit, version-controlled
# ---------------------------------------------------------------------------

YES_SYNONYMS: frozenset[str] = frozenset(
    {
        "yes",
        "y",
        "ok",
        "allow",
        "approve",
        "trust",
        "continue",
        "accept",
        "confirm",
    }
)

NO_SYNONYMS: frozenset[str] = frozenset(
    {
        "no",
        "n",
        "exit",
        "deny",
        "cancel",
        "abort",
        "reject",
        "quit",
        "stop",
    }
)

# All known semantic tokens (for option label matching)
_YES_TOKENS = YES_SYNONYMS
_NO_TOKENS = NO_SYNONYMS

# ---------------------------------------------------------------------------
# Binary menu detection — pattern matches "1. Allow" / "2. Deny" etc.
# ---------------------------------------------------------------------------

# Matches numbered options in various formats:
# "1. Allow", "1) Allow", "1 - Allow", "1: Allow", "[1] Allow"
_OPTION_PATTERN = re.compile(
    r"^\s*\[?\s*(\d+|[a-zA-Z])\s*\]?\s*[.)\-:]?\s+(.+?)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class BinaryMenu:
    """A detected binary semantic menu."""

    yes_option: str  # option key for yes-like label (e.g., "1")
    no_option: str  # option key for no-like label (e.g., "2")
    yes_label: str  # original label text (e.g., "Allow")
    no_label: str  # original label text (e.g., "Deny")


def detect_binary_menu(prompt_text: str) -> BinaryMenu | None:
    """Detect a binary semantic menu from prompt text.

    Returns a BinaryMenu if the prompt contains exactly two numbered/lettered
    options where one is semantically yes and the other is semantically no.
    Returns None otherwise.
    """
    matches = _OPTION_PATTERN.findall(prompt_text)
    if len(matches) != 2:
        return None

    key_a, label_a = matches[0]
    key_b, label_b = matches[1]

    sem_a = _classify_label(label_a)
    sem_b = _classify_label(label_b)

    if sem_a == "yes" and sem_b == "no":
        return BinaryMenu(
            yes_option=key_a,
            no_option=key_b,
            yes_label=label_a,
            no_label=label_b,
        )
    if sem_a == "no" and sem_b == "yes":
        return BinaryMenu(
            yes_option=key_b,
            no_option=key_a,
            yes_label=label_b,
            no_label=label_a,
        )

    return None


def normalize_reply(menu: BinaryMenu, reply: str) -> str | None:
    """Map a natural language reply to the correct option key.

    Returns the option key (e.g., "1") if the reply maps to an option,
    or None if the reply is ambiguous (caller should request clarification).
    Digit/letter replies that match an option key pass through unchanged.
    """
    stripped = reply.strip().lower()

    # Already a valid option key?
    if stripped == menu.yes_option.lower():
        return menu.yes_option
    if stripped == menu.no_option.lower():
        return menu.no_option

    # Semantic synonym match
    if stripped in YES_SYNONYMS:
        return menu.yes_option
    if stripped in NO_SYNONYMS:
        return menu.no_option

    return None


def _classify_label(label: str) -> str | None:
    """Classify a menu option label as 'yes', 'no', or None (unknown)."""
    tokens = set(label.lower().split())
    if tokens & _YES_TOKENS:
        return "yes"
    if tokens & _NO_TOKENS:
        return "no"
    return None
