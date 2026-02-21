"""
OpenAI Codex CLI adapter.

Wraps the OpenAI Codex CLI (``codex`` binary) in a PTY supervisor.
Inherits PTY/injection logic from ClaudeCodeAdapter and adds Codex-specific
prompt patterns on top of the generic tri-signal detector.

Codex CLI prompt characteristics:
  - Yes/no confirmations: "Apply changes? [y/n]", "Run command? [y/n]"
  - Approval gates:       "Approve this action? (yes/no)"
  - Numbered menus:       "Select action:\n  1. Apply\n  2. Skip\n  3. Abort"
  - Model selection:      "Choose model: [1] gpt-4o  [2] gpt-4-turbo"
  - Free-text inputs:     "Enter a description:", "Provide context:"

Registration key: "openai" (``atlasbridge run openai``)
"""

from __future__ import annotations

import re
from re import Pattern

from atlasbridge.adapters.base import AdapterRegistry
from atlasbridge.adapters.claude_code import ClaudeCodeAdapter
from atlasbridge.core.prompt.detector import PromptDetector
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType

# ---------------------------------------------------------------------------
# Codex CLI-specific patterns (supplement generic detector patterns)
# ---------------------------------------------------------------------------

_CODEX_YES_NO: list[Pattern[str]] = [
    re.compile(r"Apply (?:these )?changes\? \[y/n\]", re.IGNORECASE),
    re.compile(r"Run (?:this )?command\? \[y/n\]", re.IGNORECASE),
    re.compile(r"Approve this action\? \(yes/no\)", re.IGNORECASE),
    re.compile(
        r"(?:Proceed|Continue|Confirm) with (?:this|the) (?:change|action|operation)\?",
        re.IGNORECASE,
    ),
    re.compile(r"Allow Codex to .+\? \[y/n\]", re.IGNORECASE),
]

_CODEX_MULTIPLE_CHOICE: list[Pattern[str]] = [
    re.compile(r"Select action:\s*\n\s*1\.", re.IGNORECASE | re.DOTALL),
    re.compile(r"Choose model:\s*\[1\]", re.IGNORECASE),
    re.compile(
        r"(?:^|\n)\s*\d+\.\s+(?:Apply|Skip|Abort|Cancel|Retry)\b", re.IGNORECASE | re.MULTILINE
    ),
]

_CODEX_FREE_TEXT: list[Pattern[str]] = [
    re.compile(
        r"(?:Enter|Provide|Type)\s+(?:a\s+)?(?:description|context|message|name)\s*:", re.IGNORECASE
    ),
    re.compile(r"What (?:do you want|should Codex) (?:to do|change)\?", re.IGNORECASE),
]


class OpenAIPromptDetector(PromptDetector):
    """
    PromptDetector extended with Codex CLI-specific patterns.

    Runs generic patterns first; falls back to Codex-specific ones if no
    generic match is found.
    """

    def _pattern_match(self, text: str) -> PromptEvent | None:
        # Generic patterns first
        event = super()._pattern_match(text)
        if event:
            return event

        # Codex-specific yes/no
        for pat in _CODEX_YES_NO:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_YES_NO,
                    confidence=Confidence.HIGH,
                    excerpt=text[-200:],
                    choices=["y", "n"],
                )

        # Codex-specific multiple choice
        for pat in _CODEX_MULTIPLE_CHOICE:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
                    confidence=Confidence.HIGH,
                    excerpt=text[-200:],
                )

        # Codex-specific free text
        for pat in _CODEX_FREE_TEXT:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_FREE_TEXT,
                    confidence=Confidence.MED,
                    excerpt=text[-200:],
                )

        return None


@AdapterRegistry.register("openai")
class OpenAIAdapter(ClaudeCodeAdapter):
    """
    Adapter for the OpenAI Codex CLI.

    Uses an extended detector with Codex-specific prompt patterns.
    """

    tool_name = "openai"
    description = "OpenAI Codex CLI (codex)"
    min_tool_version = "1.0.0"

    def _make_detector(self, session_id: str) -> PromptDetector:
        return OpenAIPromptDetector(session_id)


@AdapterRegistry.register("custom")
class CustomCLIAdapter(ClaudeCodeAdapter):
    """
    Generic adapter for any interactive CLI tool.

    Uses the generic tri-signal detector without tool-specific patterns.
    Suitable for any interactive CLI that produces text prompts.
    """

    tool_name = "custom"
    description = "Generic interactive CLI (any tool)"
    min_tool_version = ""
