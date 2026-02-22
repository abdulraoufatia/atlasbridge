"""
Sanitization utilities for dashboard display.

Strips ANSI escape codes, redacts tokens/secrets, and prepares text
for safe HTML rendering. Jinja2 autoescape handles HTML escaping;
this module handles content-level sanitization.
"""

from __future__ import annotations

import ipaddress
import re

# ---------------------------------------------------------------------------
# ANSI stripping — reuse pattern from core.prompt.sanitize
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI sequences
    r"|\x1b\][^\x07]*(?:\x07|\x1b\\)"  # OSC sequences
    r"|\x1b[()][A-Z0-9]"  # Charset designators
    r"|\x1b[ -/]*[@-~]"  # Other ESC sequences
    r"|\r"  # Carriage returns
)


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape codes and carriage returns."""
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# Token redaction
# ---------------------------------------------------------------------------

# Each pattern: (compiled regex, replacement label)
_TOKEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Telegram bot tokens: 123456:ABC-DEF...
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35,}\b"), "[REDACTED:telegram-token]"),
    # Slack bot/user tokens: xoxb-..., xoxp-..., xoxs-...
    (re.compile(r"\bxox[bpsar]-[A-Za-z0-9-]{10,}\b"), "[REDACTED:slack-token]"),
    # Generic API keys: sk-..., ak-..., key-...
    (re.compile(r"\b(?:sk|ak|key)-[A-Za-z0-9]{20,}\b"), "[REDACTED:api-key]"),
    # GitHub PATs: ghp_, gho_, ghu_, ghs_, ghr_
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "[REDACTED:github-pat]"),
    # AWS access keys: AKIA...
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "[REDACTED:aws-key]"),
    # Generic long hex secrets (64+ hex chars, like SHA-256 hashes used as secrets)
    (re.compile(r"\b[0-9a-f]{64,}\b"), "[REDACTED:hex-secret]"),
]


def redact_tokens(text: str) -> str:
    """Replace known token patterns with redaction labels."""
    for pattern, label in _TOKEN_PATTERNS:
        text = pattern.sub(label, text)
    return text


# ---------------------------------------------------------------------------
# Combined sanitization
# ---------------------------------------------------------------------------

MAX_DISPLAY_LENGTH = 4096


def is_loopback(host: str) -> bool:
    """Check if a host string resolves to a loopback address.

    This function lives in sanitize (not app) so it can be imported
    without fastapi installed — safety tests depend on it.
    """
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_loopback
    except ValueError:
        return False


def sanitize_for_display(text: str, max_length: int = MAX_DISPLAY_LENGTH) -> str:
    """Apply full sanitization pipeline: ANSI strip → token redaction → truncate.

    HTML escaping is handled by Jinja2 autoescape, not here.
    """
    text = strip_ansi(text)
    text = redact_tokens(text)
    if len(text) > max_length:
        text = text[:max_length] + "\n... [truncated]"
    return text
