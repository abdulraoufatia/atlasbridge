"""
Gemini CLI adapter.

Wraps the Google Gemini CLI (``gemini`` binary) in a PTY supervisor.
Inherits PTY/injection logic from ClaudeCodeAdapter and adds Gemini-specific
prompt patterns on top of the generic tri-signal detector.

Gemini CLI prompt characteristics:
  - Yes/no confirmations: "Do you want to continue? (y/n)"
  - Approval gates:       "Allow Gemini to execute this? [Yes/No]"
  - Numbered menus:       "Select an option:\n  1) Generate code\n  2) Explain code"
  - Model selection:      "Choose a model:\n  [1] gemini-1.5-pro\n  [2] gemini-1.5-flash"
  - Free-text inputs:     "Enter your prompt:", "Describe the task:"

Registration key: "gemini" (``atlasbridge run gemini``)
"""

from __future__ import annotations

import re
from re import Pattern

from atlasbridge.adapters.base import AdapterRegistry
from atlasbridge.adapters.claude_code import ClaudeCodeAdapter
from atlasbridge.core.prompt.detector import PromptDetector
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType

# ---------------------------------------------------------------------------
# Gemini CLI-specific patterns (supplement generic detector patterns)
# ---------------------------------------------------------------------------

_GEMINI_YES_NO: list[Pattern[str]] = [
    re.compile(r"Do you want to (?:continue|proceed|apply)\? \(y/n\)", re.IGNORECASE),
    re.compile(
        r"Allow Gemini to (?:execute|run|apply) this\? \[(?:Yes|Y)/(?:No|N)\]", re.IGNORECASE
    ),
    re.compile(r"(?:Confirm|Approve) (?:action|change|operation)\? \[y/n\]", re.IGNORECASE),
    re.compile(r"(?:Execute|Apply) this (?:code|change|command)\? \(yes/no\)", re.IGNORECASE),
    re.compile(r"Save (?:this|the) (?:file|output)\? \[y/n\]", re.IGNORECASE),
]

_GEMINI_MULTIPLE_CHOICE: list[Pattern[str]] = [
    re.compile(r"Select an? option:\s*\n\s*1[\)\.]\s+\S", re.IGNORECASE | re.DOTALL),
    re.compile(r"Choose a model:\s*\n\s*\[1\]", re.IGNORECASE | re.DOTALL),
    re.compile(
        r"(?:^|\n)\s*\d+[\)\.]\s+(?:Generate|Explain|Refactor|Debug|Test)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"gemini-\d+\.\d+-(?:pro|flash)\s*\n", re.IGNORECASE),
]

_GEMINI_FREE_TEXT: list[Pattern[str]] = [
    re.compile(
        r"(?:Enter|Describe|Provide)\s+(?:(?:your|the|a|an)\s+)?(?:prompt|task|input|query)\s*:",
        re.IGNORECASE,
    ),
    re.compile(
        r"What (?:would you like|do you want) (?:Gemini|me) to (?:do|generate|write)\?",
        re.IGNORECASE,
    ),
    re.compile(r"Gemini>\s*$", re.MULTILINE),  # interactive REPL prompt
]


class GeminiPromptDetector(PromptDetector):
    """
    PromptDetector extended with Gemini CLI-specific patterns.

    Runs generic patterns first; falls back to Gemini-specific ones if no
    generic match is found.
    """

    def _pattern_match(self, text: str) -> PromptEvent | None:
        # Generic patterns first
        event = super()._pattern_match(text)
        if event:
            return event

        # Gemini-specific yes/no
        for pat in _GEMINI_YES_NO:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_YES_NO,
                    confidence=Confidence.HIGH,
                    excerpt=text[-200:],
                    choices=["y", "n"],
                )

        # Gemini-specific multiple choice
        for pat in _GEMINI_MULTIPLE_CHOICE:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
                    confidence=Confidence.HIGH,
                    excerpt=text[-200:],
                )

        # Gemini-specific free text
        for pat in _GEMINI_FREE_TEXT:
            if pat.search(text):
                return PromptEvent.create(
                    session_id=self.session_id,
                    prompt_type=PromptType.TYPE_FREE_TEXT,
                    confidence=Confidence.MED,
                    excerpt=text[-200:],
                )

        return None


@AdapterRegistry.register("gemini")
class GeminiAdapter(ClaudeCodeAdapter):
    """
    Adapter for the Google Gemini CLI.

    Uses an extended detector with Gemini-specific prompt patterns.
    """

    tool_name = "gemini"
    description = "Google Gemini CLI (gemini)"
    min_tool_version = "1.0.0"

    def _make_detector(self, session_id: str) -> PromptDetector:
        return GeminiPromptDetector(session_id)
