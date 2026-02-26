"""
Terminal output sanitization and choice extraction.

Provides shared utilities for cleaning ANSI escape sequences and
extracting structured choices from terminal prompt text.

Used by:
  - PromptDetector (strip ANSI, gate meaningful output, extract choices)
  - Tests and Prompt Lab scenarios
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Comprehensive ANSI escape sequence regex
# ---------------------------------------------------------------------------
# Matches:
#   CSI sequences   \x1b[ ... final_byte  (including private mode ? > !)
#   OSC sequences   \x1b] ... BEL  or  \x1b] ... ST
#   Charset desig.  \x1b( or \x1b) followed by designator
#   Other ESC seqs  \x1b + intermediate + final
#   Carriage return  \r
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI: e.g. \x1b[31m, \x1b[?1004l, \x1b[?2004h
    r"|\x1b\][^\x07]*(?:\x07|\x1b\\)"  # OSC: e.g. \x1b]0;title\x07
    r"|\x1b[()][A-Z0-9]"  # Charset designators: \x1b(B
    r"|\x1b[ -/]*[@-~]"  # Other ESC sequences: \x1b=, \x1b>
    r"|\r"  # Carriage returns
)

# ---------------------------------------------------------------------------
# Choice extraction patterns
# ---------------------------------------------------------------------------

# Numbered choices: "1) Fast", "2. Balanced", "3: Thorough"
# Also handles Unicode bullets/arrows before digits: "❯ 1. Yes, I trust this folder"
_NUMBERED_CHOICE_RE = re.compile(
    r"^\s*\S?\s*(\d+)\s*[).\]:]\s+(.+?)$",
    re.MULTILINE,
)

# Lettered choices: "a) Option", "A. Option", "b: Option"
_LETTERED_CHOICE_RE = re.compile(
    r"^\s*([A-Za-z])\s*[).\]:]\s+(.+?)$",
    re.MULTILINE,
)

# Inline slash-separated in brackets/parens: [Y/n], (yes/No/cancel)
_INLINE_CHOICE_RE = re.compile(
    r"[\[\(]\s*([A-Za-z][A-Za-z]*(?:\s*/\s*[A-Za-z][A-Za-z]*){1,5})\s*[\]\)]"
)


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape codes and carriage returns from terminal output."""
    return _ANSI_RE.sub("", text)


def is_meaningful(text: str) -> bool:
    """Return True if text contains meaningful content (not just ANSI junk remnants).

    Requires at least 3 non-whitespace characters and at least 1 alphanumeric.
    """
    stripped = strip_ansi(text).strip()
    non_ws = re.sub(r"\s", "", stripped)
    if len(non_ws) < 3:
        return False
    return bool(re.search(r"[A-Za-z0-9]", non_ws))


def sanitize_terminal_output(text: str) -> str:
    """Strip ANSI codes and rebuild lines overwritten by carriage returns.

    When a terminal writes ``prefix\\rfull_line``, only ``full_line``
    should remain. This handles that before stripping remaining ANSI.
    """
    # First handle CR-based line overwriting (before stripping ANSI)
    lines = text.split("\n")
    rebuilt: list[str] = []
    for line in lines:
        # If line contains \r, take everything after the last \r
        if "\r" in line:
            parts = line.split("\r")
            line = parts[-1]
        rebuilt.append(line)
    joined = "\n".join(rebuilt)
    return strip_ansi(joined)


# ---------------------------------------------------------------------------
# Terminal hint phrases (keyboard shortcuts, IDE references, navigation)
# ---------------------------------------------------------------------------
# These are terminal-only UI hints that are meaningless on mobile (Telegram/Slack).
# Used by strip_terminal_hints() to clean output before channel delivery.
_TERMINAL_HINT_PHRASES: tuple[str, ...] = (
    # Confirmation / navigation
    "enter to confirm",
    "press enter",
    "esc to cancel",
    "escape to cancel",
    "use the arrow keys",
    "use arrow keys",
    "use ↑/↓",
    "↑ ↓ to navigate",
    "↑/↓",
    # Tab / space
    "tab to cycle",
    "shift+tab",
    "space to select",
    "space to toggle",
    # Ctrl shortcuts
    "ctrl+g",
    "ctrl+c to cancel",
    "ctrl+d to submit",
    "ctrl+a to select",
    # IDE / editor references
    "vs code",
    "vscode",
    "open in editor",
    "edit in vs",
    # Vim-style
    "use j/k",
    "press q to quit",
    # Filter / search
    "type to filter",
    "type to search",
)


def strip_terminal_hints(text: str) -> str:
    """Remove terminal-only UI hints from text for phone-first rendering.

    Strips entire lines that contain terminal-specific hints (keyboard shortcuts,
    editor references, navigation instructions) that are meaningless on mobile.
    Preserves all other content including blank lines for readability.
    """
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue
        lower = stripped.lower()
        if any(phrase in lower for phrase in _TERMINAL_HINT_PHRASES):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_choices(text: str) -> list[str]:
    """Extract structured choices from prompt text.

    Supports:
      - Numbered lists: ``1) Fast``, ``2. Balanced``
      - Lettered lists: ``a) Alpha``, ``B. Bravo``
      - Inline bracket/paren: ``[Y/n]``, ``(yes/No/cancel)``

    Returns an empty list if no structured choices are found.
    Simple yes/no bracket patterns (exactly 2 single-letter items where
    the letters are y and n) are excluded — those are handled by
    TYPE_YES_NO detection.
    """
    cleaned = strip_ansi(text)

    # Try numbered choices first
    numbered = _NUMBERED_CHOICE_RE.findall(cleaned)
    if len(numbered) >= 2:
        # Verify consecutive numbering starting from 1
        nums = [int(n) for n, _ in numbered]
        if nums == list(range(1, len(nums) + 1)):
            return [label.strip() for _, label in numbered]

    # Try lettered choices
    lettered = _LETTERED_CHOICE_RE.findall(cleaned)
    if len(lettered) >= 2:
        letters = [ch.upper() for ch, _ in lettered]
        expected = [chr(ord("A") + i) for i in range(len(letters))]
        if letters == expected:
            return [label.strip() for _, label in lettered]

    # Try inline bracket/paren choices
    match = _INLINE_CHOICE_RE.search(cleaned)
    if match:
        items = [s.strip() for s in match.group(1).split("/")]
        # Exclude simple y/n — that's TYPE_YES_NO territory
        if len(items) == 2 and {i.lower() for i in items} == {"y", "n"}:
            return []
        if len(items) >= 2:
            return items

    return []
