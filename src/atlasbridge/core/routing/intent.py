"""
Intent router — classifies PromptEvents and dispatches to the correct handler.

Sits between PromptDetector output and PromptRouter/AutopilotEngine:

    PromptEvent
        |
        v
    IntentRouter
        |
        +-- PolicyRouteClassifier.classify(event) -> ClassificationResult
        |
        +-- AUTOPILOT  -> autopilot_handler (or fallthrough)
        +-- HUMAN      -> prompt_router.route_event()
        +-- DENY       -> deny_handler (or fallthrough)
        +-- PASSTHROUGH -> prompt_router.route_event()

With handlers set to None, ALL intents fall through to prompt_router.route_event().
Runtime behavior is identical to the pre-intent-router flow.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

import structlog

if TYPE_CHECKING:
    from atlasbridge.core.prompt.models import PromptEvent, Reply
    from atlasbridge.core.routing.router import PromptRouter

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Route intents
# ---------------------------------------------------------------------------


class RouteIntent(StrEnum):
    """Where to send a classified PromptEvent."""

    AUTOPILOT = "autopilot"
    """Policy says auto_reply or notify_only."""

    HUMAN = "human"
    """Policy says require_human or no-match default."""

    DENY = "deny"
    """Policy says deny."""

    PASSTHROUGH = "passthrough"
    """No classifier configured; legacy behavior."""


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------


class ClassificationResult:
    """Carries intent + metadata from a RouteClassifier."""

    __slots__ = ("intent", "matched_rule_id", "action_type", "action_value", "explanation")

    def __init__(
        self,
        *,
        intent: RouteIntent,
        matched_rule_id: str | None = None,
        action_type: str = "",
        action_value: str = "",
        explanation: str = "",
    ) -> None:
        self.intent = intent
        self.matched_rule_id = matched_rule_id
        self.action_type = action_type
        self.action_value = action_value
        self.explanation = explanation

    def __repr__(self) -> str:
        return (
            f"ClassificationResult(intent={self.intent!r}, "
            f"rule={self.matched_rule_id!r}, action={self.action_type!r})"
        )


# ---------------------------------------------------------------------------
# Classifier protocol + policy implementation
# ---------------------------------------------------------------------------

# Mapping from policy action_type to RouteIntent
_ACTION_TO_INTENT: dict[str, RouteIntent] = {
    "auto_reply": RouteIntent.AUTOPILOT,
    "notify_only": RouteIntent.AUTOPILOT,
    "require_human": RouteIntent.HUMAN,
    "deny": RouteIntent.DENY,
}


class RouteClassifier(Protocol):
    """Protocol for intent classifiers."""

    def classify(self, event: PromptEvent) -> ClassificationResult: ...

    def reload_policy(self, policy: Any) -> None: ...


class PolicyRouteClassifier:
    """Classifies PromptEvents using the policy evaluator."""

    def __init__(self, policy: Any) -> None:
        self._policy = policy

    def classify(self, event: PromptEvent) -> ClassificationResult:
        """Evaluate the policy and map the decision to a RouteIntent."""
        from atlasbridge.core.policy.evaluator import evaluate

        decision = evaluate(
            policy=self._policy,
            prompt_text=event.excerpt,
            prompt_type=(
                event.prompt_type.value
                if hasattr(event.prompt_type, "value")
                else str(event.prompt_type)
            ),
            confidence=(
                event.confidence.value
                if hasattr(event.confidence, "value")
                else str(event.confidence)
            ),
            prompt_id=event.prompt_id,
            session_id=event.session_id,
            tool_id=event.tool or "*",
            repo=event.cwd or "",
        )

        intent = _ACTION_TO_INTENT.get(decision.action_type, RouteIntent.HUMAN)

        return ClassificationResult(
            intent=intent,
            matched_rule_id=decision.matched_rule_id,
            action_type=decision.action_type,
            action_value=decision.action_value,
            explanation=decision.explanation,
        )

    def reload_policy(self, policy: Any) -> None:
        """Hot-swap the policy used for classification."""
        self._policy = policy


# ---------------------------------------------------------------------------
# Intent router
# ---------------------------------------------------------------------------

# Handler type: async callable(event, classification_result) -> None
IntentHandler = Any  # Callable[[PromptEvent, ClassificationResult], Awaitable[None]]


class IntentRouter:
    """
    Wraps PromptRouter with intent-based dispatch.

    When autopilot_handler or deny_handler is None, those intents fall through
    to prompt_router.route_event() — preserving existing behavior.
    """

    def __init__(
        self,
        prompt_router: PromptRouter,
        classifier: RouteClassifier | None = None,
        autopilot_handler: IntentHandler | None = None,
        deny_handler: IntentHandler | None = None,
    ) -> None:
        self._prompt_router = prompt_router
        self._classifier = classifier
        self._autopilot_handler = autopilot_handler
        self._deny_handler = deny_handler

    async def route_event(self, event: PromptEvent) -> None:
        """Classify the event and dispatch to the appropriate handler."""
        if self._classifier is None:
            await self._prompt_router.route_event(event)
            return

        try:
            result = self._classifier.classify(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "intent_classification_failed",
                prompt_id=event.prompt_id,
                error=str(exc),
            )
            await self._prompt_router.route_event(event)
            return

        logger.debug(
            "intent_classified",
            prompt_id=event.prompt_id,
            intent=result.intent,
            rule=result.matched_rule_id,
            action=result.action_type,
        )

        if result.intent == RouteIntent.AUTOPILOT and self._autopilot_handler is not None:
            await self._autopilot_handler(event, result)
        elif result.intent == RouteIntent.DENY and self._deny_handler is not None:
            await self._deny_handler(event, result)
        else:
            # HUMAN, PASSTHROUGH, or handler not configured — fallthrough
            await self._prompt_router.route_event(event)

    async def handle_reply(self, reply: Reply) -> None:
        """Delegate to the wrapped PromptRouter."""
        await self._prompt_router.handle_reply(reply)

    async def expire_overdue(self) -> None:
        """Delegate to the wrapped PromptRouter."""
        await self._prompt_router.expire_overdue()
