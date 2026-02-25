"""
Tests for GA Policy Explain Mode — full_explain().

Covers:
- All failed rules shown with reasons
- Risk assessment included
- Alternative outcomes computed
- Secret redaction in output
- JSON output structure
- Deterministic output
"""

from __future__ import annotations

import json

from atlasbridge.core.policy.explain import (
    ExplainResult,
    explain_decision,
    full_explain,
)
from atlasbridge.core.policy.model import (
    AutoReplyAction,
    ConfidenceLevel,
    MatchCriteria,
    Policy,
    PolicyDecision,
    PolicyDefaults,
    PolicyRule,
    RequireHumanAction,
)


def _make_policy(rules: list[PolicyRule] | None = None) -> Policy:
    """Create a test policy with standard rules."""
    if rules is None:
        rules = [
            PolicyRule(
                id="auto-yes-no",
                description="Auto-approve yes/no at high confidence",
                match=MatchCriteria(
                    prompt_type=["yes_no"],
                    min_confidence=ConfidenceLevel.HIGH,
                ),
                action=AutoReplyAction(value="y"),
            ),
            PolicyRule(
                id="escalate-free-text",
                description="Escalate free text to human",
                match=MatchCriteria(
                    prompt_type=["free_text"],
                ),
                action=RequireHumanAction(message="Free text requires review"),
            ),
            PolicyRule(
                id="auto-confirm",
                description="Auto-confirm at high confidence",
                match=MatchCriteria(
                    prompt_type=["confirm_enter"],
                    min_confidence=ConfidenceLevel.HIGH,
                ),
                action=AutoReplyAction(value=""),
            ),
        ]
    return Policy(
        policy_version="0",
        name="test-policy",
        rules=rules,
        defaults=PolicyDefaults(no_match="require_human"),
    )


class TestFullExplain:
    def test_returns_explain_result(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert isinstance(result, ExplainResult)

    def test_matched_rule_shown(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert result.matched_rule_id == "auto-yes-no"
        assert result.action_type == "auto_reply"

    def test_all_rules_traced(self):
        """All rules are evaluated (no short-circuit), even after match."""
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert len(result.rule_traces) == 3
        assert result.rule_traces[0].rule_id == "auto-yes-no"
        assert result.rule_traces[0].is_winner is True
        assert result.rule_traces[1].rule_id == "escalate-free-text"
        assert result.rule_traces[1].is_winner is False

    def test_failed_rules_have_reasons(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        # Second rule (escalate-free-text) should fail on prompt_type
        failed = result.rule_traces[1]
        assert not failed.matched
        assert len(failed.reasons) > 0
        # Should have a reason mentioning prompt_type mismatch
        has_prompt_reason = any("prompt_type" in r for r in failed.reasons)
        assert has_prompt_reason

    def test_risk_assessment_included(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert result.risk_score is not None
        assert result.risk_category is not None

    def test_risk_with_context(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            branch="main",
            ci_status="failing",
        )
        assert result.risk_score is not None
        assert result.risk_score > 0
        factor_names = {f["name"] for f in result.risk_factors}
        assert "branch" in factor_names or "ci_status" in factor_names

    def test_alternative_outcomes(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        # Should have 2 alternatives (low and medium)
        assert len(result.alternatives) == 2
        alt_confs = {a.confidence for a in result.alternatives}
        assert alt_confs == {"low", "medium"}

    def test_alternative_shows_different_outcome(self):
        """Low confidence may match a different rule or default."""
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        # At low confidence, auto-yes-no won't match (min_confidence=high)
        low_alt = next(a for a in result.alternatives if a.confidence == "low")
        assert low_alt.matched_rule_id != "auto-yes-no"

    def test_no_match_shows_default(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Enter password:",
            prompt_type="multiple_choice",
            confidence="low",
        )
        assert result.matched_rule_id is None
        assert result.action_type == "require_human"


class TestExplainDecisionGA:
    def test_risk_shown_when_present(self):
        decision = PolicyDecision(
            prompt_id="p1",
            session_id="s1",
            policy_hash="abc123",
            matched_rule_id="test-rule",
            action=AutoReplyAction(value="y"),
            explanation="test",
            confidence="high",
            prompt_type="yes_no",
            autonomy_mode="full",
            risk_score=45,
            risk_category="medium",
            risk_factors=[
                {"name": "branch", "weight": 15, "description": "protected branch"},
                {"name": "action_type", "weight": 15, "description": "auto_reply"},
            ],
        )
        text = explain_decision(decision)
        assert "45/100" in text
        assert "medium" in text
        assert "branch" in text

    def test_risk_not_shown_when_absent(self):
        decision = PolicyDecision(
            prompt_id="p1",
            session_id="s1",
            policy_hash="abc123",
            matched_rule_id="test-rule",
            action=AutoReplyAction(value="y"),
            explanation="test",
            confidence="high",
            prompt_type="yes_no",
            autonomy_mode="full",
        )
        text = explain_decision(decision)
        assert "Risk score" not in text


class TestExplainTextOutput:
    def test_text_contains_sections(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        text = result.to_text()
        assert "POLICY EXPLAIN" in text
        assert "Decision:" in text
        assert "Risk Assessment:" in text
        assert "Rule Evaluation" in text
        assert "Alternative Outcomes:" in text

    def test_text_redacts_secrets(self):
        policy = _make_policy()
        # Include a token-like string in prompt text
        result = full_explain(
            policy=policy,
            prompt_text="Token: xoxb-fake-slack-token-1234567890",
            prompt_type="yes_no",
            confidence="high",
        )
        text = result.to_text()
        assert "xoxb-fake-slack-token-1234567890" not in text


class TestExplainJSONOutput:
    def test_json_valid(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        j = result.to_json()
        parsed = json.loads(j)
        assert "policy" in parsed
        assert "decision" in parsed
        assert "risk" in parsed
        assert "rules" in parsed
        assert "alternatives" in parsed

    def test_json_rules_include_all(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        parsed = json.loads(result.to_json())
        assert len(parsed["rules"]) == 3

    def test_json_redacts_secrets(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Token: xoxb-fake-slack-token-1234567890",
            prompt_type="yes_no",
            confidence="high",
        )
        parsed = json.loads(result.to_json())
        assert "xoxb-fake-slack-token-1234567890" not in parsed["input"]["prompt_text"]

    def test_json_decision_structure(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        parsed = json.loads(result.to_json())
        d = parsed["decision"]
        assert "matched_rule_id" in d
        assert "action_type" in d
        assert "explanation" in d

    def test_json_risk_structure(self):
        policy = _make_policy()
        result = full_explain(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            branch="main",
        )
        parsed = json.loads(result.to_json())
        r = parsed["risk"]
        assert "score" in r
        assert "category" in r
        assert "factors" in r


class TestExplainDeterminism:
    def test_same_input_same_output(self):
        policy = _make_policy()
        results = [
            full_explain(
                policy=policy,
                prompt_text="Continue? [y/n]",
                prompt_type="yes_no",
                confidence="high",
                branch="main",
            )
            for _ in range(50)
        ]
        for r in results[1:]:
            # Compare JSON (excludes timestamps from PolicyDecision)
            assert r.matched_rule_id == results[0].matched_rule_id
            assert r.risk_score == results[0].risk_score
            assert len(r.rule_traces) == len(results[0].rule_traces)
            assert len(r.alternatives) == len(results[0].alternatives)
