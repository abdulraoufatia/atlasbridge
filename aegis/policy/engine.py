"""
Aegis prompt router — decides how to handle a detected prompt.

For v0.x the router is simple:
  - Route all prompts to the user via Telegram (ROUTE_TO_USER).
  - Exception: TYPE_FREE_TEXT when disabled in config → auto-inject empty string.

The engine is synchronous; the async PTY supervisor calls it after detection.
"""

from __future__ import annotations

from dataclasses import dataclass

from aegis.core.constants import PolicyAction, PromptType
from aegis.policy.detector import DetectionResult


@dataclass
class PolicyDecision:
    action: PolicyAction
    reason: str
    # If AUTO_INJECT, the value to inject
    inject_value: str | None = None


class PolicyEngine:
    """
    Route a detected prompt to the appropriate handler.

    Parameters
    ----------
    free_text_enabled:
        Whether TYPE_FREE_TEXT prompts are forwarded to the user via Telegram.
        If False, the safe default (empty string) is injected immediately.
    """

    def __init__(self, free_text_enabled: bool = False) -> None:
        self.free_text_enabled = free_text_enabled

    def evaluate(self, result: DetectionResult) -> PolicyDecision:
        """Return a PolicyDecision for a detected prompt."""

        # TYPE_FREE_TEXT: only route if explicitly enabled
        if result.prompt_type == PromptType.FREE_TEXT and not self.free_text_enabled:
            return PolicyDecision(
                action=PolicyAction.AUTO_INJECT,
                reason="free_text disabled in config; using safe default",
                inject_value="",
            )

        # All other detected prompts go to the user
        return PolicyDecision(
            action=PolicyAction.ROUTE_TO_USER,
            reason="default policy: route all prompts to user",
        )
