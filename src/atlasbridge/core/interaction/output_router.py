"""
OutputRouter — classifies PTY output as agent prose, CLI output, or noise.

Used by OutputForwarder to decide how to render messages:
  - AGENT_MESSAGE: prose text from the agent (markdown, complete sentences)
  - CLI_OUTPUT: raw command output, stack traces, build logs
  - NOISE: too short or only whitespace/ANSI remnants — discard

When ``show_raw_output=True`` the router bypasses classification and
treats everything as CLI_OUTPUT (useful for debugging).
"""

from __future__ import annotations

import re
from enum import StrEnum

import structlog

logger = structlog.get_logger()


class OutputKind(StrEnum):
    """Classification of a PTY output chunk."""

    AGENT_MESSAGE = "agent_message"
    CLI_OUTPUT = "cli_output"
    NOISE = "noise"


# Minimum meaningful characters (after strip) to avoid classifying as NOISE
_MIN_MEANINGFUL_CHARS: int = 10

# Patterns that indicate CLI/command output (not agent prose)
_CLI_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*\$\s"),  # $ command prefix
    re.compile(r"^\s*>\s"),  # > command prefix
    re.compile(r"^(Traceback|File \"|  File \")"),  # Python stack traces
    re.compile(r"^\s*(npm |yarn |pip |cargo |go |make |gcc |clang )"),  # Build tools
    re.compile(r"^(error|warning|Error|Warning|ERROR|WARNING)\b"),  # Error lines
    re.compile(r"^\s*at\s+\S+\s+\("),  # JS stack frames
    re.compile(r"^[/\w.-]+\.\w+:\d+"),  # file:line references
    re.compile(r"^\s*\d+\s+(passing|failing|pending)"),  # Test summaries
    re.compile(r"^(PASS|FAIL|ok|---)\s"),  # Test results
    re.compile(r"^\s*#\s*(include|define|pragma)"),  # C preprocessor
]

# Patterns that indicate agent prose (markdown, structured text)
_PROSE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^#+\s"),  # Markdown headings
    re.compile(r"^\s*[-*]\s\w"),  # Markdown lists
    re.compile(r"^\s*\d+\.\s\w"),  # Numbered lists
    re.compile(r"```"),  # Code fences (agent wraps code)
    re.compile(r"\*\*\w"),  # Bold text
    re.compile(r"^I('m| will| can| have|'ll)\s", re.IGNORECASE),  # Agent self-ref
    re.compile(r"^(Let me|Here's|This is|The |Now |Next )\s", re.IGNORECASE),
    re.compile(r"^(Sure|Done|Updated|Created|Fixed|Added)\b", re.IGNORECASE),
]


class OutputRouter:
    """
    Classifies PTY output into agent prose, CLI output, or noise.

    Args:
        show_raw_output: When True, all non-noise output is treated as
            CLI_OUTPUT (bypass classification). Default False.
    """

    def __init__(self, show_raw_output: bool = False) -> None:
        self._show_raw = show_raw_output

    def classify(self, text: str) -> OutputKind:
        """Classify a text chunk into AGENT_MESSAGE, CLI_OUTPUT, or NOISE."""
        stripped = text.strip()

        # Too short → noise
        if len(stripped) < _MIN_MEANINGFUL_CHARS:
            return OutputKind.NOISE

        # Bypass mode → everything is CLI output
        if self._show_raw:
            return OutputKind.CLI_OUTPUT

        lines = stripped.splitlines()

        cli_score = 0
        prose_score = 0

        for line in lines[:20]:  # Cap to avoid scanning huge outputs
            for pat in _CLI_PATTERNS:
                if pat.search(line):
                    cli_score += 1
                    break
            for pat in _PROSE_PATTERNS:
                if pat.search(line):
                    prose_score += 1
                    break

        # Heuristic: if more than half of lines match CLI patterns
        if cli_score > prose_score:
            return OutputKind.CLI_OUTPUT

        if prose_score > 0:
            return OutputKind.AGENT_MESSAGE

        # Default: CLI output (safer than misclassifying as agent prose)
        return OutputKind.CLI_OUTPUT
