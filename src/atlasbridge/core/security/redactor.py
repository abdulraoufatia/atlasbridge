"""
Centralized secret redaction for AtlasBridge.

All secret pattern matching and redaction flows through this module.
Consumer sites (audit writer, dashboard sanitize, output forwarder)
import from here instead of maintaining their own pattern lists.

Patterns are intentionally broad — false positives (over-redaction)
are preferred over false negatives (leaked secrets).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Built-in patterns — superset of all previously scattered pattern lists
# ---------------------------------------------------------------------------

# Each entry: (compiled regex, human-readable label)
_BUILTIN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Telegram bot tokens: 123456789:ABC-DEF...
    (re.compile(r"\b\d{8,12}:[A-Za-z0-9_\-]{35,}\b"), "telegram-token"),
    # Slack tokens: xoxb-, xoxp-, xoxs-, xoxa-, xoxr-, xapp-
    (re.compile(r"\bxox[bpsar]-[A-Za-z0-9\-]{10,}\b"), "slack-token"),
    (re.compile(r"\bxapp-[A-Za-z0-9\-]{20,}\b"), "slack-app-token"),
    # OpenAI / generic API keys: sk-...
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "api-key"),
    # GitHub PATs: ghp_, gho_, ghu_, ghs_, ghr_
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "github-pat"),
    # AWS access keys: AKIA...
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "aws-key"),
    # AWS secret keys (40 base64 chars after known prefixes)
    (re.compile(r"(?<=AWS_SECRET_ACCESS_KEY[=: ])[A-Za-z0-9/+=]{40}"), "aws-secret"),
    # Google API keys
    (re.compile(r"\bAIza[A-Za-z0-9_\-]{35}\b"), "google-api-key"),
    # Anthropic API keys: sk-ant-...
    (re.compile(r"\bsk-ant-[A-Za-z0-9\-]{20,}\b"), "anthropic-key"),
    # Generic long hex secrets (64+ hex chars)
    (re.compile(r"\b[0-9a-f]{64,}\b"), "hex-secret"),
    # Bearer tokens in headers
    (re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"), "bearer-token"),
    # Generic key=value for common env var names
    (
        re.compile(
            r"(?i)(?:api_key|api_secret|secret_key|access_token|auth_token"
            r"|password|passwd|token)"
            r"[=:]\s*['\"]?([A-Za-z0-9\-._~+/]{8,})['\"]?"
        ),
        "env-secret",
    ),
]

REDACTION_PLACEHOLDER = "[REDACTED]"


class SecretRedactor:
    """Centralized secret detection and redaction.

    Usage::

        redactor = SecretRedactor()
        safe = redactor.redact("my token is sk-abc123...")
        has_secret = redactor.contains_secret(text)

    Custom patterns can be added at construction or later::

        redactor = SecretRedactor(custom_patterns=["my-corp-[a-z]{20}"])
        redactor.add_pattern(r"internal-\\d{10}")
    """

    def __init__(self, custom_patterns: list[str] | None = None) -> None:
        self._patterns: list[tuple[re.Pattern[str], str]] = list(_BUILTIN_PATTERNS)
        for p in custom_patterns or []:
            self.add_pattern(p)

    def add_pattern(self, pattern: str, label: str = "custom") -> None:
        """Add a custom regex pattern for secret detection."""
        self._patterns.append((re.compile(pattern), label))

    def redact(self, text: str, placeholder: str = REDACTION_PLACEHOLDER) -> str:
        """Replace all detected secrets with a redaction placeholder."""
        for regex, _label in self._patterns:
            text = regex.sub(placeholder, text)
        return text

    def redact_labeled(self, text: str) -> str:
        """Replace secrets with labeled placeholders like ``[REDACTED:api-key]``."""
        for regex, label in self._patterns:
            text = regex.sub(f"[REDACTED:{label}]", text)
        return text

    def contains_secret(self, text: str) -> bool:
        """Return True if text contains any known secret pattern."""
        for regex, _ in self._patterns:
            if regex.search(text):
                return True
        return False

    @property
    def pattern_count(self) -> int:
        """Number of active patterns (built-in + custom)."""
        return len(self._patterns)


# ---------------------------------------------------------------------------
# Module-level singleton for simple import
# ---------------------------------------------------------------------------

_default_redactor: SecretRedactor | None = None


def get_redactor(custom_patterns: list[str] | None = None) -> SecretRedactor:
    """Return the module-level redactor singleton.

    On first call, creates the instance. If ``custom_patterns`` are
    provided, they are added to the existing instance.
    """
    global _default_redactor  # noqa: PLW0603
    if _default_redactor is None:
        _default_redactor = SecretRedactor(custom_patterns=custom_patterns)
    elif custom_patterns:
        for p in custom_patterns:
            _default_redactor.add_pattern(p)
    return _default_redactor


def redact(text: str) -> str:
    """Convenience: redact using the default singleton."""
    return get_redactor().redact(text)


def contains_secret(text: str) -> bool:
    """Convenience: check using the default singleton."""
    return get_redactor().contains_secret(text)
