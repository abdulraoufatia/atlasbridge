"""
Sanitization utilities for dashboard display.

Strips ANSI escape codes, redacts tokens/secrets, and prepares text
for safe HTML rendering. Jinja2 autoescape handles HTML escaping;
this module handles content-level sanitization.
"""

from __future__ import annotations

import ipaddress
import re

from atlasbridge.core.security.redactor import get_redactor as _get_redactor

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
# Token redaction — delegates to centralized SecretRedactor
# ---------------------------------------------------------------------------


def redact_tokens(text: str) -> str:
    """Replace known token patterns with labeled redaction placeholders."""
    return _get_redactor().redact_labeled(text)


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


def redact_query_params(query_string: str) -> str:
    """Redact sensitive values from a URL query string for logging.

    Preserves parameter names but replaces values that look like tokens
    or secrets with ``[REDACTED]``.  Non-sensitive values pass through.
    """
    if not query_string:
        return query_string
    from urllib.parse import parse_qsl, urlencode

    pairs = parse_qsl(query_string, keep_blank_values=True)
    safe: list[tuple[str, str]] = []
    for key, value in pairs:
        redacted = redact_tokens(value)
        if redacted != value:
            safe.append((key, "[REDACTED]"))
        else:
            safe.append((key, value))
    return urlencode(safe)


def sanitize_for_display(text: str, max_length: int = MAX_DISPLAY_LENGTH) -> str:
    """Apply full sanitization pipeline: ANSI strip → token redaction → truncate.

    HTML escaping is handled by Jinja2 autoescape, not here.
    """
    text = strip_ansi(text)
    text = redact_tokens(text)
    if len(text) > max_length:
        text = text[:max_length] + "\n... [truncated]"
    return text
