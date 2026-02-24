"""
Integration test: Agent profile → session_tag → policy evaluation flow.

Verifies the end-to-end path:
  AgentProfile.session_label → Session.label → PromptEvent.session_label → session_tag in evaluate()
"""

from __future__ import annotations

from atlasbridge.core.policy.evaluator import evaluate
from atlasbridge.core.policy.model import AutonomyMode, PolicyDefaults
from atlasbridge.core.policy.model_v1 import MatchCriteriaV1, PolicyRuleV1, PolicyV1
from atlasbridge.core.profile import AgentProfile


def _v1_policy_with_session_tag(tag: str) -> PolicyV1:
    """Create a v1 policy with one rule matching a specific session_tag."""
    return PolicyV1(
        policy_version="1",
        name="profile-test",
        autonomy_mode=AutonomyMode.FULL,
        rules=[
            PolicyRuleV1(
                id="tag-match",
                match=MatchCriteriaV1(
                    session_tag=tag,
                    prompt_type=["yes_no"],
                    min_confidence="high",
                ),
                action={"type": "auto_reply", "value": "y"},
            ),
        ],
        defaults=PolicyDefaults(no_match="require_human"),
    )


class TestProfilePolicyFlow:
    """Verify profiles correctly influence policy evaluation via session_tag."""

    def test_matching_profile_triggers_rule(self):
        """Profile with session_label='ci' should match rule with session_tag='ci'."""
        profile = AgentProfile(name="ci", session_label="ci")
        policy = _v1_policy_with_session_tag("ci")

        decision = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
            session_tag=profile.session_label,  # this is how run passes it
        )

        assert decision.action_type == "auto_reply"
        assert decision.action_value == "y"
        assert decision.matched_rule_id == "tag-match"

    def test_non_matching_profile_falls_through(self):
        """Profile with session_label='dev' should NOT match rule with session_tag='ci'."""
        profile = AgentProfile(name="dev", session_label="dev")
        policy = _v1_policy_with_session_tag("ci")

        decision = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
            session_tag=profile.session_label,
        )

        assert decision.action_type == "require_human"
        assert decision.matched_rule_id is None

    def test_empty_label_does_not_match(self):
        """Profile with no session_label should not match tagged rules."""
        profile = AgentProfile(name="bare")
        policy = _v1_policy_with_session_tag("ci")

        decision = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
            session_tag=profile.session_label,
        )

        assert decision.action_type == "require_human"

    def test_multiple_profiles_distinct_behavior(self):
        """Two profiles should get different policy decisions."""
        policy = PolicyV1(
            policy_version="1",
            name="multi-profile",
            autonomy_mode=AutonomyMode.FULL,
            rules=[
                PolicyRuleV1(
                    id="ci-approve",
                    match=MatchCriteriaV1(
                        session_tag="ci",
                        prompt_type=["yes_no"],
                    ),
                    action={"type": "auto_reply", "value": "y"},
                ),
                PolicyRuleV1(
                    id="review-escalate",
                    match=MatchCriteriaV1(session_tag="code-review"),
                    action={"type": "require_human"},
                ),
            ],
            defaults=PolicyDefaults(no_match="require_human"),
        )

        ci = AgentProfile(name="ci", session_label="ci")
        review = AgentProfile(name="code-review", session_label="code-review")

        d_ci = evaluate(
            policy=policy,
            prompt_text="Continue?",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
            session_tag=ci.session_label,
        )
        assert d_ci.action_type == "auto_reply"
        assert d_ci.matched_rule_id == "ci-approve"

        d_review = evaluate(
            policy=policy,
            prompt_text="Continue?",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p2",
            session_id="s2",
            session_tag=review.session_label,
        )
        assert d_review.action_type == "require_human"
        assert d_review.matched_rule_id == "review-escalate"
