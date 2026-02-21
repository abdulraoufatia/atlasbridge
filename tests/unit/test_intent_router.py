"""
Unit tests for atlasbridge.core.routing.intent — IntentRouter and PolicyRouteClassifier.

Test classes:
  TestRouteIntent           — enum values and StrEnum behavior
  TestPolicyRouteClassifier — action_type → RouteIntent mapping
  TestIntentRouter          — dispatch logic, fallthrough, delegation
  TestIntentRouterWithPolicy — end-to-end with real policy + classifier
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.policy.model import (
    AutoReplyAction,
    DenyAction,
    MatchCriteria,
    NotifyOnlyAction,
    Policy,
    PolicyRule,
    RequireHumanAction,
)
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType
from atlasbridge.core.routing.intent import (
    ClassificationResult,
    IntentRouter,
    PolicyRouteClassifier,
    RouteIntent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    session_id: str | None = None,
    prompt_type: PromptType = PromptType.TYPE_YES_NO,
    confidence: Confidence = Confidence.HIGH,
    excerpt: str = "Continue? [y/N]",
) -> PromptEvent:
    return PromptEvent.create(
        session_id=session_id or str(uuid.uuid4()),
        prompt_type=prompt_type,
        confidence=confidence,
        excerpt=excerpt,
    )


def _policy(*rules: PolicyRule) -> Policy:
    return Policy(
        policy_version="0",
        name="test-intent",
        rules=list(rules),
    )


def _auto_reply_rule(rule_id: str = "r-auto", contains: str | None = None) -> PolicyRule:
    match = MatchCriteria(contains=contains) if contains else MatchCriteria()
    return PolicyRule(id=rule_id, match=match, action=AutoReplyAction(value="y"))


def _require_human_rule(rule_id: str = "r-human") -> PolicyRule:
    return PolicyRule(id=rule_id, match=MatchCriteria(), action=RequireHumanAction())


def _deny_rule(rule_id: str = "r-deny") -> PolicyRule:
    return PolicyRule(id=rule_id, match=MatchCriteria(), action=DenyAction(reason="blocked"))


def _notify_only_rule(rule_id: str = "r-notify") -> PolicyRule:
    return PolicyRule(id=rule_id, match=MatchCriteria(), action=NotifyOnlyAction())


# ---------------------------------------------------------------------------
# TestRouteIntent
# ---------------------------------------------------------------------------


class TestRouteIntent:
    def test_enum_values_exist(self) -> None:
        assert RouteIntent.AUTOPILOT == "autopilot"
        assert RouteIntent.HUMAN == "human"
        assert RouteIntent.DENY == "deny"
        assert RouteIntent.PASSTHROUGH == "passthrough"

    def test_values_are_strings(self) -> None:
        for member in RouteIntent:
            assert isinstance(member, str)
            assert member.value == member  # StrEnum identity


# ---------------------------------------------------------------------------
# TestPolicyRouteClassifier
# ---------------------------------------------------------------------------


class TestPolicyRouteClassifier:
    def test_auto_reply_maps_to_autopilot(self) -> None:
        policy = _policy(_auto_reply_rule())
        classifier = PolicyRouteClassifier(policy=policy)
        result = classifier.classify(_event())
        assert result.intent == RouteIntent.AUTOPILOT
        assert result.action_type == "auto_reply"

    def test_require_human_maps_to_human(self) -> None:
        policy = _policy(_require_human_rule())
        classifier = PolicyRouteClassifier(policy=policy)
        result = classifier.classify(_event())
        assert result.intent == RouteIntent.HUMAN
        assert result.action_type == "require_human"

    def test_deny_maps_to_deny(self) -> None:
        policy = _policy(_deny_rule())
        classifier = PolicyRouteClassifier(policy=policy)
        result = classifier.classify(_event())
        assert result.intent == RouteIntent.DENY
        assert result.action_type == "deny"

    def test_notify_only_maps_to_autopilot(self) -> None:
        policy = _policy(_notify_only_rule())
        classifier = PolicyRouteClassifier(policy=policy)
        result = classifier.classify(_event())
        assert result.intent == RouteIntent.AUTOPILOT
        assert result.action_type == "notify_only"

    def test_no_matching_rule_defaults_to_human(self) -> None:
        # Rule only matches "blocked" substring, event says "Continue?"
        policy = _policy(_auto_reply_rule(contains="blocked"))
        classifier = PolicyRouteClassifier(policy=policy)
        result = classifier.classify(_event(excerpt="Continue? [y/N]"))
        assert result.intent == RouteIntent.HUMAN
        assert result.matched_rule_id is None

    def test_result_carries_rule_metadata(self) -> None:
        policy = _policy(_auto_reply_rule(rule_id="my-rule"))
        classifier = PolicyRouteClassifier(policy=policy)
        result = classifier.classify(_event())
        assert result.matched_rule_id == "my-rule"
        assert result.action_value == "y"
        assert result.explanation != ""

    def test_reload_policy_swaps_policy(self) -> None:
        policy1 = _policy(_auto_reply_rule())
        policy2 = _policy(_deny_rule())
        classifier = PolicyRouteClassifier(policy=policy1)

        result1 = classifier.classify(_event())
        assert result1.intent == RouteIntent.AUTOPILOT

        classifier.reload_policy(policy2)
        result2 = classifier.classify(_event())
        assert result2.intent == RouteIntent.DENY


# ---------------------------------------------------------------------------
# TestIntentRouter
# ---------------------------------------------------------------------------


class TestIntentRouter:
    @pytest.mark.asyncio
    async def test_no_classifier_passthrough(self) -> None:
        mock_router = AsyncMock()
        intent_router = IntentRouter(prompt_router=mock_router, classifier=None)
        event = _event()
        await intent_router.route_event(event)
        mock_router.route_event.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_human_intent_routes_to_prompt_router(self) -> None:
        mock_router = AsyncMock()
        classifier = MagicMock()
        classifier.classify.return_value = ClassificationResult(intent=RouteIntent.HUMAN)
        intent_router = IntentRouter(prompt_router=mock_router, classifier=classifier)
        event = _event()
        await intent_router.route_event(event)
        mock_router.route_event.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_autopilot_intent_with_handler(self) -> None:
        mock_router = AsyncMock()
        handler = AsyncMock()
        classifier = MagicMock()
        result = ClassificationResult(intent=RouteIntent.AUTOPILOT, action_type="auto_reply")
        classifier.classify.return_value = result
        intent_router = IntentRouter(
            prompt_router=mock_router, classifier=classifier, autopilot_handler=handler
        )
        event = _event()
        await intent_router.route_event(event)
        handler.assert_awaited_once_with(event, result)
        mock_router.route_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_autopilot_intent_no_handler_fallthrough(self) -> None:
        mock_router = AsyncMock()
        classifier = MagicMock()
        classifier.classify.return_value = ClassificationResult(intent=RouteIntent.AUTOPILOT)
        intent_router = IntentRouter(
            prompt_router=mock_router, classifier=classifier, autopilot_handler=None
        )
        event = _event()
        await intent_router.route_event(event)
        mock_router.route_event.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_deny_intent_with_handler(self) -> None:
        mock_router = AsyncMock()
        handler = AsyncMock()
        classifier = MagicMock()
        result = ClassificationResult(intent=RouteIntent.DENY, action_type="deny")
        classifier.classify.return_value = result
        intent_router = IntentRouter(
            prompt_router=mock_router, classifier=classifier, deny_handler=handler
        )
        event = _event()
        await intent_router.route_event(event)
        handler.assert_awaited_once_with(event, result)
        mock_router.route_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deny_intent_no_handler_fallthrough(self) -> None:
        mock_router = AsyncMock()
        classifier = MagicMock()
        classifier.classify.return_value = ClassificationResult(intent=RouteIntent.DENY)
        intent_router = IntentRouter(
            prompt_router=mock_router, classifier=classifier, deny_handler=None
        )
        event = _event()
        await intent_router.route_event(event)
        mock_router.route_event.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_classification_failure_fallback(self) -> None:
        mock_router = AsyncMock()
        classifier = MagicMock()
        classifier.classify.side_effect = RuntimeError("policy boom")
        intent_router = IntentRouter(prompt_router=mock_router, classifier=classifier)
        event = _event()
        await intent_router.route_event(event)
        # Should fall through to prompt_router despite error
        mock_router.route_event.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_handle_reply_delegates(self) -> None:
        mock_router = AsyncMock()
        intent_router = IntentRouter(prompt_router=mock_router)
        reply = MagicMock()
        await intent_router.handle_reply(reply)
        mock_router.handle_reply.assert_awaited_once_with(reply)

    @pytest.mark.asyncio
    async def test_expire_overdue_delegates(self) -> None:
        mock_router = AsyncMock()
        intent_router = IntentRouter(prompt_router=mock_router)
        await intent_router.expire_overdue()
        mock_router.expire_overdue.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestIntentRouterWithPolicy — end-to-end with real policy
# ---------------------------------------------------------------------------


class TestIntentRouterWithPolicy:
    @pytest.mark.asyncio
    async def test_real_policy_dispatches_to_handler(self) -> None:
        """End-to-end: real policy + classifier → autopilot handler called."""
        mock_router = AsyncMock()
        handler = AsyncMock()
        policy = _policy(_auto_reply_rule())
        classifier = PolicyRouteClassifier(policy=policy)
        intent_router = IntentRouter(
            prompt_router=mock_router, classifier=classifier, autopilot_handler=handler
        )
        event = _event()
        await intent_router.route_event(event)
        handler.assert_awaited_once()
        mock_router.route_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_matching_rule_falls_through_to_channel(self) -> None:
        """End-to-end: no matching rule → prompt_router.route_event() called."""
        mock_router = AsyncMock()
        handler = AsyncMock()
        # Rule requires "blocked" substring, which won't match our event
        policy = _policy(_auto_reply_rule(contains="blocked"))
        classifier = PolicyRouteClassifier(policy=policy)
        intent_router = IntentRouter(
            prompt_router=mock_router, classifier=classifier, autopilot_handler=handler
        )
        event = _event(excerpt="Continue? [y/N]")
        await intent_router.route_event(event)
        handler.assert_not_awaited()
        mock_router.route_event.assert_awaited_once_with(event)
