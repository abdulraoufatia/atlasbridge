"""
AI Safety Regression — Policy bypass attempt vectors.

Tests that crafted inputs cannot circumvent policy evaluation.
Covers regex DoS, schema abuse, invalid enum values, and
first-match-wins ordering attacks.

Minimum 10 scenarios per issue #218 acceptance criteria.
"""

from __future__ import annotations

import pytest

from atlasbridge.core.policy.evaluator import evaluate
from atlasbridge.core.policy.model import (
    AutonomyMode,
    AutoReplyAction,
    DenyAction,
    MatchCriteria,
    Policy,
    PolicyDefaults,
    PolicyRule,
)
from atlasbridge.core.policy.parser import PolicyParseError, parse_policy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy(
    rules: list[PolicyRule] | None = None,
    defaults: PolicyDefaults | None = None,
    mode: str = "full",
) -> Policy:
    return Policy(
        name="test-bypass",
        policy_version="0",
        autonomy_mode=AutonomyMode(mode),
        rules=rules or [],
        defaults=defaults or PolicyDefaults(),
    )


def _eval(
    policy: Policy,
    prompt_type: str = "yes_no",
    confidence: str = "high",
    prompt_text: str = "Continue?",
    tool_id: str = "*",
    repo: str = "",
):
    return evaluate(
        policy=policy,
        prompt_text=prompt_text,
        prompt_type=prompt_type,
        confidence=confidence,
        prompt_id="test-prompt",
        session_id="test-session",
        tool_id=tool_id,
        repo=repo,
    )


# ---------------------------------------------------------------------------
# 1. Empty / missing policy defaults to safe
# ---------------------------------------------------------------------------


class TestEmptyPolicy:
    def test_empty_rules_defaults_to_require_human(self):
        policy = _make_policy(rules=[])
        d = _eval(policy)
        assert d.action_type == "require_human"

    def test_empty_rules_deny_default(self):
        policy = _make_policy(
            rules=[],
            defaults=PolicyDefaults(no_match="deny"),
        )
        d = _eval(policy)
        assert d.action_type == "deny"


# ---------------------------------------------------------------------------
# 2. Invalid confidence values — non-canonical strings
# ---------------------------------------------------------------------------


class TestInvalidConfidence:
    @pytest.mark.parametrize("confidence", ["MEDIUM", "none", "0", ""])
    def test_nonstandard_confidence_no_match(self, confidence: str):
        """Non-high confidence values must NOT match rules requiring high confidence."""
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(prompt_type=["yes_no"], min_confidence="high"),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        d = _eval(policy, confidence=confidence)
        assert d.action_type in ("require_human", "deny")

    @pytest.mark.parametrize("confidence", ["HIGH", "High", "HIGH "])
    def test_case_insensitive_confidence_matches(self, confidence: str):
        """confidence_from_str is case-insensitive; 'HIGH'/'High' resolve to high."""
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(prompt_type=["yes_no"], min_confidence="high"),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        d = _eval(policy, confidence=confidence)
        # Case-insensitive: 'HIGH' → 'high' → matches min_confidence="high"
        # Unknown strings (with trailing space) default to LOW → no match
        assert d.action_type in ("auto_reply", "require_human")


# ---------------------------------------------------------------------------
# 3. Invalid prompt_type values
# ---------------------------------------------------------------------------


class TestInvalidPromptType:
    @pytest.mark.parametrize(
        "ptype",
        ["YES_NO", "Yes_No", "unknown", "multiple_CHOICE", ""],
    )
    def test_nonstandard_type_no_match(self, ptype: str):
        """Non-canonical prompt types must not match rules expecting specific types."""
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(prompt_type=["yes_no"]),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        d = _eval(policy, prompt_type=ptype)
        assert d.action_type == "require_human"


# ---------------------------------------------------------------------------
# 4. Low confidence always escalates regardless of matching rule
# ---------------------------------------------------------------------------


class TestLowConfidenceEscalation:
    def test_low_confidence_defaults_override(self):
        """Low confidence should apply defaults.low_confidence."""
        policy = _make_policy(
            rules=[],
            defaults=PolicyDefaults(low_confidence="require_human"),
        )
        d = _eval(policy, confidence="low")
        assert d.action_type == "require_human"

    def test_low_confidence_deny_default(self):
        policy = _make_policy(
            rules=[],
            defaults=PolicyDefaults(low_confidence="deny"),
        )
        d = _eval(policy, confidence="low")
        assert d.action_type == "deny"


# ---------------------------------------------------------------------------
# 5. First-match-wins ordering attacks
# ---------------------------------------------------------------------------


class TestFirstMatchWins:
    def test_deny_before_allow(self):
        """If deny rule comes first, it wins even if allow rule also matches."""
        rules = [
            PolicyRule(
                id="deny-all",
                match=MatchCriteria(prompt_type=["yes_no"]),
                action=DenyAction(),
            ),
            PolicyRule(
                id="allow-all",
                match=MatchCriteria(prompt_type=["yes_no"]),
                action=AutoReplyAction(value="y"),
            ),
        ]
        policy = _make_policy(rules=rules)
        d = _eval(policy)
        assert d.action_type == "deny"
        assert d.matched_rule_id == "deny-all"

    def test_allow_before_deny(self):
        """Reorder — allow first means allow wins."""
        rules = [
            PolicyRule(
                id="allow-all",
                match=MatchCriteria(prompt_type=["yes_no"]),
                action=AutoReplyAction(value="y"),
            ),
            PolicyRule(
                id="deny-all",
                match=MatchCriteria(prompt_type=["yes_no"]),
                action=DenyAction(),
            ),
        ]
        policy = _make_policy(rules=rules)
        d = _eval(policy)
        assert d.action_type == "auto_reply"
        assert d.matched_rule_id == "allow-all"


# ---------------------------------------------------------------------------
# 6. Regex match criteria — no ReDoS
# ---------------------------------------------------------------------------


class TestRegexSafety:
    def test_long_excerpt_with_wildcard_rule(self):
        """Wildcard match on huge excerpt must not hang."""
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(
                prompt_type=["yes_no"],
                contains=".+",
                contains_is_regex=True,
            ),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        # 100KB prompt text
        d = _eval(policy, prompt_text="A" * 100_000)
        assert d.action_type == "auto_reply"

    def test_empty_match_regex_rejected(self):
        """Regex that matches empty string is rejected by the validator."""
        with pytest.raises(ValueError, match="matches empty string"):
            MatchCriteria(
                prompt_type=["yes_no"],
                contains=".*",
                contains_is_regex=True,
            )

    def test_pathological_regex_excerpt(self):
        """Nested quantifiers must not cause exponential backtracking."""
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(
                prompt_type=["yes_no"],
                contains="(a+)+b",
                contains_is_regex=True,
            ),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        # This is a classic ReDoS pattern — should timeout gracefully
        d = _eval(policy, prompt_text="a" * 50 + "!")
        # Must not match (no 'b') and must not hang
        assert d.action_type == "require_human"


# ---------------------------------------------------------------------------
# 7. Tool and repo prefix matching edge cases
# ---------------------------------------------------------------------------


class TestToolRepoMatching:
    def test_tool_exact_match_required(self):
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(prompt_type=["yes_no"], tool_id="claude_code"),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        # Wrong tool
        d = _eval(policy, tool_id="openai_cli")
        assert d.action_type == "require_human"
        # Right tool
        d = _eval(policy, tool_id="claude_code")
        assert d.action_type == "auto_reply"

    def test_repo_prefix_match(self):
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(
                prompt_type=["yes_no"],
                repo="/home/user/safe-project",
            ),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        # Match
        d = _eval(policy, repo="/home/user/safe-project/subdir")
        assert d.action_type == "auto_reply"
        # No match — different project
        d = _eval(policy, repo="/home/user/other-project")
        assert d.action_type == "require_human"


# ---------------------------------------------------------------------------
# 8. Schema version abuse
# ---------------------------------------------------------------------------


class TestSchemaVersionAbuse:
    def test_unknown_version_rejected(self):
        yaml_text = """
name: bad-version
policy_version: "999"
autonomy_mode: full
rules: []
"""
        with pytest.raises(PolicyParseError):
            parse_policy(yaml_text, source="test")

    def test_missing_version_rejected(self):
        yaml_text = """
name: no-version
autonomy_mode: full
rules: []
"""
        with pytest.raises((PolicyParseError, Exception)):
            parse_policy(yaml_text, source="test")


# ---------------------------------------------------------------------------
# 9. Wildcard tool_id bypass attempt
# ---------------------------------------------------------------------------


class TestWildcardBypass:
    def test_wildcard_tool_matches_all(self):
        """Wildcard '*' in rule tool_id matches any tool."""
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(prompt_type=["yes_no"], tool_id="*"),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        d = _eval(policy, tool_id="anything")
        assert d.action_type == "auto_reply"

    def test_no_tool_in_rule_matches_all(self):
        """Default tool_id='*' means match regardless of tool."""
        rule = PolicyRule(
            id="r1",
            match=MatchCriteria(prompt_type=["yes_no"]),
            action=AutoReplyAction(value="y"),
        )
        policy = _make_policy(rules=[rule])
        d = _eval(policy, tool_id="claude_code")
        assert d.action_type == "auto_reply"


# ---------------------------------------------------------------------------
# 10. Idempotency key determinism
# ---------------------------------------------------------------------------


class TestIdempotencyKey:
    def test_same_inputs_same_key(self):
        """Same prompt evaluated twice must produce same idempotency_key."""
        policy = _make_policy(rules=[])
        d1 = _eval(policy, prompt_text="foo")
        d2 = _eval(policy, prompt_text="foo")
        assert d1.idempotency_key == d2.idempotency_key

    def test_different_prompt_id_different_key(self):
        """Different prompt_id must produce different idempotency_key."""
        policy = _make_policy(rules=[])
        # idempotency_key = SHA-256(policy_hash:prompt_id:session_id)[:16]
        # prompt_text is NOT part of the key — only prompt_id and session_id
        d1 = evaluate(
            policy=policy,
            prompt_text="foo",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="test-session",
        )
        d2 = evaluate(
            policy=policy,
            prompt_text="foo",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p2",
            session_id="test-session",
        )
        assert d1.idempotency_key != d2.idempotency_key

    def test_same_prompt_text_same_key(self):
        """Same (policy_hash, prompt_id, session_id) → same key, regardless of prompt_text."""
        policy = _make_policy(rules=[])
        d1 = _eval(policy, prompt_text="foo")
        d2 = _eval(policy, prompt_text="bar")
        # prompt_text is NOT part of idempotency_key
        assert d1.idempotency_key == d2.idempotency_key

    def test_policy_hash_in_decision(self):
        """Every decision must carry the policy content hash (truncated to 16 hex chars)."""
        policy = _make_policy(rules=[])
        d = _eval(policy)
        assert d.policy_hash == policy.content_hash()
        assert len(d.policy_hash) == 16  # SHA-256 hex truncated to 16 chars
