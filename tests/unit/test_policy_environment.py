"""Unit tests for policy environment matching."""

from __future__ import annotations

from atlasbridge.core.policy.evaluator import _match_environment


class TestMatchEnvironment:
    def test_none_always_matches(self) -> None:
        ok, _ = _match_environment(None, "production")
        assert ok is True

    def test_exact_match(self) -> None:
        ok, _ = _match_environment("production", "production")
        assert ok is True

    def test_mismatch(self) -> None:
        ok, _ = _match_environment("production", "dev")
        assert ok is False

    def test_empty_environment(self) -> None:
        ok, _ = _match_environment("production", "")
        assert ok is False

    def test_none_criterion_matches_empty(self) -> None:
        ok, _ = _match_environment(None, "")
        assert ok is True


class TestPolicyEvaluationWithEnvironment:
    def test_v1_rule_matches_environment(self) -> None:
        from atlasbridge.core.policy.evaluator import evaluate
        from atlasbridge.core.policy.model import AutonomyMode, DenyAction
        from atlasbridge.core.policy.model_v1 import (
            MatchCriteriaV1,
            PolicyRuleV1,
            PolicyV1,
        )

        rule = PolicyRuleV1(
            id="prod-deny",
            description="Deny in production",
            match=MatchCriteriaV1(environment="production"),
            action=DenyAction(type="deny", reason="Blocked in production"),
        )
        policy = PolicyV1(
            policy_version="1",
            autonomy_mode=AutonomyMode.FULL,
            rules=[rule],
        )

        decision = evaluate(
            policy=policy,
            prompt_text="run command",
            prompt_type="tool_use",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
            environment="production",
        )
        assert decision.matched_rule_id == "prod-deny"
        assert decision.action.type == "deny"

    def test_v1_rule_skips_wrong_environment(self) -> None:
        from atlasbridge.core.policy.evaluator import evaluate
        from atlasbridge.core.policy.model import AutonomyMode, DenyAction
        from atlasbridge.core.policy.model_v1 import (
            MatchCriteriaV1,
            PolicyRuleV1,
            PolicyV1,
        )

        rule = PolicyRuleV1(
            id="prod-deny",
            description="Deny in production",
            match=MatchCriteriaV1(environment="production"),
            action=DenyAction(type="deny", reason="Blocked in production"),
        )
        policy = PolicyV1(
            policy_version="1",
            autonomy_mode=AutonomyMode.FULL,
            rules=[rule],
        )

        decision = evaluate(
            policy=policy,
            prompt_text="run command",
            prompt_type="tool_use",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
            environment="dev",
        )
        # Rule should not match — falls through to default escalation
        assert decision.matched_rule_id is None
