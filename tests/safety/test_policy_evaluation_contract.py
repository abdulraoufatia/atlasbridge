"""
Contract tests for policy evaluation — freeze GA evaluation semantics.

These tests pin the exact behavior of the policy evaluator for known inputs.
If any test breaks, it means the evaluation contract has changed, which requires
explicit review before shipping.

IMPORTANT: Do NOT update these expected values casually. Changes to evaluation
semantics are breaking changes that affect all deployed policies.
"""

from __future__ import annotations

from pathlib import Path

from atlasbridge.core.policy.evaluator import evaluate
from atlasbridge.core.policy.model import ConfidenceLevel, Policy
from atlasbridge.core.policy.parser import load_policy

_FIXTURES = Path(__file__).parents[1] / "policy" / "fixtures"
_FIXTURES_V1 = _FIXTURES / "v1"


# ---------------------------------------------------------------------------
# Pinned evaluation vectors — v0
# ---------------------------------------------------------------------------


class TestV0EvaluationContract:
    """Pinned evaluation results for v0 policies. Do not change without review."""

    def test_basic_yes_no_high_confidence_auto_reply(self):
        """basic.yaml + yes_no + high → auto_reply 'y' via rule 'yes-no-auto-yes'."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="pin-1",
            session_id="pin-sess",
        )
        assert decision.action_type == "auto_reply"
        assert decision.action_value == "y"
        assert decision.matched_rule_id == "yes-no-auto-yes"

    def test_basic_confirm_enter_auto_reply(self):
        """basic.yaml + confirm_enter + high → auto_reply '\\n' via 'confirm-enter-auto'."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="Press Enter to continue",
            prompt_type="confirm_enter",
            confidence="high",
            prompt_id="pin-2",
            session_id="pin-sess",
        )
        assert decision.action_type == "auto_reply"
        assert decision.action_value == "\n"
        assert decision.matched_rule_id == "confirm-enter-auto"

    def test_basic_free_text_no_match_default(self):
        """basic.yaml + free_text + high → no match → require_human default."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="What file?",
            prompt_type="free_text",
            confidence="high",
            prompt_id="pin-3",
            session_id="pin-sess",
        )
        assert decision.action_type == "require_human"
        assert decision.matched_rule_id is None

    def test_basic_low_confidence_default(self):
        """basic.yaml + yes_no + low → no match (min_confidence: medium) → default."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="low",
            prompt_id="pin-4",
            session_id="pin-sess",
        )
        assert decision.action_type == "require_human"
        assert decision.matched_rule_id is None

    def test_escalation_deny_destructive(self):
        """escalation.yaml + destructive prompt → deny via 'deny-destructive'."""
        policy = load_policy(_FIXTURES / "escalation.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="Are you sure you want to rm -rf /?",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="pin-5",
            session_id="pin-sess",
        )
        assert decision.action_type == "deny"
        assert decision.matched_rule_id == "deny-destructive"


# ---------------------------------------------------------------------------
# Pinned evaluation vectors — v1
# ---------------------------------------------------------------------------


class TestV1EvaluationContract:
    """Pinned evaluation results for v1 policies. Do not change without review."""

    def test_any_of_yes_no_match(self):
        """any_of_match.yaml + yes_no + high → match via any_of."""
        policy = load_policy(_FIXTURES_V1 / "any_of_match.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="Continue?",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="pin-v1-1",
            session_id="pin-sess",
        )
        assert decision.action_type == "auto_reply"
        assert decision.matched_rule_id == "any-of-rule"

    def test_none_of_excludes_destructive(self):
        """none_of_match.yaml + 'destroy' in text → first rule excluded by none_of."""
        policy = load_policy(_FIXTURES_V1 / "none_of_match.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="destroy all data? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="pin-v1-2",
            session_id="pin-sess",
        )
        # First rule excluded, catch-all should match
        assert decision.matched_rule_id != "safe-auto-reply"

    def test_session_tag_routing(self):
        """session_tag_match.yaml + tag='ci' → ci-auto-reply rule."""
        policy = load_policy(_FIXTURES_V1 / "session_tag_match.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="pin-v1-3",
            session_id="pin-sess",
            session_tag="ci",
        )
        assert decision.matched_rule_id == "ci-auto-reply"

    def test_session_tag_mismatch_fallthrough(self):
        """session_tag_match.yaml + tag='dev' → ci rule skipped, catch-all matches."""
        policy = load_policy(_FIXTURES_V1 / "session_tag_match.yaml")
        decision = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="pin-v1-4",
            session_id="pin-sess",
            session_tag="dev",
        )
        assert decision.matched_rule_id != "ci-auto-reply"


# ---------------------------------------------------------------------------
# Idempotency contract — same input MUST produce same output
# ---------------------------------------------------------------------------


class TestEvaluationIdempotency:
    """Verify that policy evaluation is deterministic — same input = same output."""

    def test_repeated_evaluation_identical(self):
        """Evaluating the same input 100 times must produce identical decisions."""
        policy = load_policy(_FIXTURES / "basic.yaml")

        decisions = []
        for i in range(100):
            d = evaluate(
                policy=policy,
                prompt_text="Continue? [y/n]",
                prompt_type="yes_no",
                confidence="high",
                prompt_id=f"idem-{i}",
                session_id="idem-sess",
            )
            decisions.append(d)

        # All decisions must have the same action, rule, and type
        first = decisions[0]
        for d in decisions[1:]:
            assert d.action_type == first.action_type
            assert d.action_value == first.action_value
            assert d.matched_rule_id == first.matched_rule_id
            assert d.confidence == first.confidence
            assert d.prompt_type == first.prompt_type

    def test_idempotency_key_deterministic(self):
        """Same prompt_id + session_id + policy_hash = same idempotency key."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        d1 = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="same-prompt",
            session_id="same-session",
        )
        d2 = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="same-prompt",
            session_id="same-session",
        )
        assert d1.idempotency_key == d2.idempotency_key

    def test_different_prompt_id_different_key(self):
        """Different prompt_id must produce different idempotency key."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        d1 = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="prompt-a",
            session_id="same-session",
        )
        d2 = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="prompt-b",
            session_id="same-session",
        )
        assert d1.idempotency_key != d2.idempotency_key

    def test_content_hash_stable_across_evaluations(self):
        """Policy content_hash must be stable across evaluation calls."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        hash1 = policy.content_hash()
        # Evaluate to ensure no mutation
        evaluate(
            policy=policy,
            prompt_text="test",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="hash-test",
            session_id="hash-sess",
        )
        hash2 = policy.content_hash()
        assert hash1 == hash2


# ---------------------------------------------------------------------------
# First-match-wins contract
# ---------------------------------------------------------------------------


class TestFirstMatchWinsContract:
    """Verify first-match-wins semantics are preserved."""

    def test_earlier_rule_takes_precedence(self):
        """When two rules match, the one declared first wins."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        # basic.yaml: rule 1 = yes-no-auto-yes, rule 2 = confirm-enter-auto
        # yes_no should match rule 1, not fall through
        d = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="fmw-1",
            session_id="fmw-sess",
        )
        assert d.matched_rule_id == "yes-no-auto-yes"

    def test_rule_order_matters(self):
        """Reordering rules changes which one wins."""
        # Create a policy with two rules that both match yes_no
        policy = Policy(
            policy_version="0",
            name="order-test",
            rules=[
                _make_rule("rule-a", "yes_no", "auto_reply", "y", ConfidenceLevel.LOW),
                _make_rule("rule-b", "yes_no", "auto_reply", "n", ConfidenceLevel.LOW),
            ],
        )
        d = evaluate(
            policy=policy,
            prompt_text="test",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="order-1",
            session_id="order-sess",
        )
        assert d.matched_rule_id == "rule-a"
        assert d.action_value == "y"


def _make_rule(rule_id, prompt_type, action_type, value, min_confidence):
    """Helper to create a PolicyRule for testing."""
    from atlasbridge.core.policy.model import (
        AutoReplyAction,
        MatchCriteria,
        PolicyRule,
        PromptTypeFilter,
    )

    return PolicyRule(
        id=rule_id,
        match=MatchCriteria(
            prompt_type=[PromptTypeFilter(prompt_type)],
            min_confidence=min_confidence,
        ),
        action=AutoReplyAction(type="auto_reply", value=value),
    )
