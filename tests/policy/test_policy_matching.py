"""
Unit tests for Policy DSL v0: model, parser, and evaluator.

Covers:
- Model validation (valid / invalid schemas)
- Parser (YAML loading, error messages)
- Evaluator: all match criteria, first-match-wins precedence
- Action constraints (allowed_choices, numeric_only, max_length)
- Default fallbacks (no_match, low_confidence)
- Idempotency key derivation
- Fixture files
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlasbridge.core.policy.evaluator import evaluate
from atlasbridge.core.policy.model import (
    AutonomyMode,
    AutoReplyAction,
    ConfidenceLevel,
    DenyAction,
    MatchCriteria,
    NotifyOnlyAction,
    Policy,
    PolicyDecision,
    PolicyDefaults,
    PolicyRule,
    RequireHumanAction,
    confidence_from_str,
)
from atlasbridge.core.policy.parser import (
    PolicyParseError,
    default_policy,
    load_policy,
    parse_policy,
    validate_policy_file,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


def make_rule(
    rule_id: str, action_type: str = "require_human", **match_kwargs: object
) -> PolicyRule:
    action: object
    if action_type == "auto_reply":
        action = AutoReplyAction(value="y")
    elif action_type == "deny":
        action = DenyAction(reason="test deny")
    elif action_type == "notify_only":
        action = NotifyOnlyAction(message="test notify")
    else:
        action = RequireHumanAction()
    return PolicyRule(id=rule_id, match=MatchCriteria(**match_kwargs), action=action)


def make_policy(*rules: PolicyRule, mode: str = "full") -> Policy:
    return Policy(
        policy_version="0",
        name="test",
        autonomy_mode=AutonomyMode(mode),
        rules=list(rules),
    )


class TestModelValidation:
    def test_valid_policy_version(self) -> None:
        p = make_policy()
        assert p.policy_version == "0"

    def test_invalid_policy_version_raises(self) -> None:
        with pytest.raises(Exception, match="Unsupported policy_version"):
            Policy(policy_version="1", name="x", rules=[])

    def test_duplicate_rule_ids_raises(self) -> None:
        r1 = make_rule("dup")
        r2 = make_rule("dup")
        with pytest.raises(Exception, match="Duplicate rule id"):
            Policy(policy_version="0", name="x", rules=[r1, r2])

    def test_rule_id_pattern(self) -> None:
        with pytest.raises(Exception):
            PolicyRule(id="-invalid", match=MatchCriteria(), action=RequireHumanAction())

    def test_content_hash_is_stable(self) -> None:
        p = make_policy()
        h1 = p.content_hash()
        h2 = p.content_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_content_hash_changes_on_rule_change(self) -> None:
        p1 = make_policy(make_rule("r1", "auto_reply"))
        p2 = make_policy(make_rule("r1", "deny"))
        assert p1.content_hash() != p2.content_hash()

    def test_confidence_ordering(self) -> None:
        assert ConfidenceLevel.HIGH >= ConfidenceLevel.HIGH
        assert ConfidenceLevel.HIGH >= ConfidenceLevel.MED
        assert ConfidenceLevel.HIGH >= ConfidenceLevel.LOW
        assert ConfidenceLevel.MED >= ConfidenceLevel.LOW
        assert not (ConfidenceLevel.LOW >= ConfidenceLevel.MED)
        assert not (ConfidenceLevel.MED >= ConfidenceLevel.HIGH)

    def test_confidence_from_str(self) -> None:
        assert confidence_from_str("high") == ConfidenceLevel.HIGH
        assert confidence_from_str("medium") == ConfidenceLevel.MED
        assert confidence_from_str("med") == ConfidenceLevel.MED
        assert confidence_from_str("low") == ConfidenceLevel.LOW
        assert confidence_from_str("UNKNOWN") == ConfidenceLevel.LOW  # fallback

    def test_auto_reply_constraints_allowed_choices(self) -> None:
        from atlasbridge.core.policy.model import ReplyConstraints

        with pytest.raises(Exception, match="not in allowed_choices"):
            AutoReplyAction(
                value="x",
                constraints=ReplyConstraints(allowed_choices=["y", "n"]),
            )

    def test_auto_reply_constraints_numeric_only(self) -> None:
        from atlasbridge.core.policy.model import ReplyConstraints

        with pytest.raises(Exception, match="not numeric"):
            AutoReplyAction(value="abc", constraints=ReplyConstraints(numeric_only=True))

    def test_auto_reply_constraints_max_length(self) -> None:
        from atlasbridge.core.policy.model import ReplyConstraints

        with pytest.raises(Exception, match="exceeds max_length"):
            AutoReplyAction(value="toolong", constraints=ReplyConstraints(max_length=3))

    def test_contains_empty_string_raises(self) -> None:
        with pytest.raises(Exception, match="must not be empty"):
            MatchCriteria(contains="")

    def test_contains_regex_too_long_raises(self) -> None:
        with pytest.raises(Exception, match="too long"):
            MatchCriteria(contains="a" * 201, contains_is_regex=True)

    def test_contains_invalid_regex_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid regex"):
            MatchCriteria(contains="[invalid", contains_is_regex=True)

    def test_contains_regex_empty_match_raises(self) -> None:
        with pytest.raises(Exception, match="matches empty string"):
            MatchCriteria(contains="a*", contains_is_regex=True)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_parse_valid_yaml(self) -> None:
        yaml_text = """
policy_version: "0"
name: test-policy
autonomy_mode: full
rules:
  - id: r1
    match:
      prompt_type: [yes_no]
    action:
      type: auto_reply
      value: "y"
defaults:
  no_match: require_human
"""
        policy = parse_policy(yaml_text)
        assert policy.name == "test-policy"
        assert len(policy.rules) == 1

    def test_parse_invalid_yaml_syntax(self) -> None:
        with pytest.raises(PolicyParseError, match="YAML syntax"):
            parse_policy("{invalid: yaml: nested:")

    def test_parse_invalid_schema(self) -> None:
        with pytest.raises(PolicyParseError, match="unsupported policy_version"):
            parse_policy('policy_version: "99"\nname: x\n')

    def test_parse_non_mapping_raises(self) -> None:
        with pytest.raises(PolicyParseError, match="must be a YAML mapping"):
            parse_policy("- item1\n- item2\n")

    def test_default_policy(self) -> None:
        p = default_policy()
        assert p.name == "safe-default"
        assert len(p.rules) == 1
        assert p.rules[0].action.type == "require_human"  # type: ignore[union-attr]

    def test_load_policy_missing_file(self) -> None:
        with pytest.raises(PolicyParseError, match="not found"):
            load_policy("/nonexistent/policy.yaml")

    def test_load_policy_fixture_basic(self) -> None:
        policy = load_policy(FIXTURES_DIR / "basic.yaml")
        assert policy.name == "basic"
        assert len(policy.rules) == 2

    def test_load_policy_fixture_escalation(self) -> None:
        policy = load_policy(FIXTURES_DIR / "escalation.yaml")
        assert policy.name == "escalation"
        assert policy.autonomy_mode == AutonomyMode.ASSIST

    def test_load_policy_fixture_full_auto(self) -> None:
        policy = load_policy(FIXTURES_DIR / "full_auto.yaml")
        assert policy.name == "full-auto"
        assert len(policy.rules) == 4

    def test_validate_policy_file_valid(self) -> None:
        errors = validate_policy_file(FIXTURES_DIR / "basic.yaml")
        assert errors == []

    def test_validate_policy_file_invalid(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text('policy_version: "99"\nname: bad\n')
        errors = validate_policy_file(bad)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Evaluator: first-match-wins
# ---------------------------------------------------------------------------


def _eval(
    policy: Policy,
    prompt_type: str = "yes_no",
    confidence: str = "high",
    prompt_text: str = "Continue? [y/n]",
    tool_id: str = "*",
    repo: str = "",
) -> PolicyDecision:
    return evaluate(
        policy=policy,
        prompt_text=prompt_text,
        prompt_type=prompt_type,
        confidence=confidence,
        prompt_id="p1",
        session_id="s1",
        tool_id=tool_id,
        repo=repo,
    )


class TestEvaluator:
    def test_first_matching_rule_wins(self) -> None:
        r1 = make_rule("r1", "auto_reply", prompt_type=["yes_no"])
        r2 = make_rule("r2", "deny", prompt_type=["yes_no"])
        p = make_policy(r1, r2)
        d = _eval(p, prompt_type="yes_no")
        assert d.matched_rule_id == "r1"
        assert d.action_type == "auto_reply"

    def test_no_match_uses_default_require_human(self) -> None:
        r1 = make_rule("r1", "auto_reply", prompt_type=["multiple_choice"])
        p = make_policy(r1)
        d = _eval(p, prompt_type="yes_no")
        assert d.matched_rule_id is None
        assert d.action_type == "require_human"

    def test_no_match_uses_default_deny(self) -> None:
        p = Policy(
            policy_version="0",
            name="test",
            rules=[],
            defaults=PolicyDefaults(no_match="deny"),
        )
        d = _eval(p)
        assert d.action_type == "deny"

    def test_low_confidence_default(self) -> None:
        p = Policy(
            policy_version="0",
            name="test",
            rules=[make_rule("r1", "auto_reply", prompt_type=["yes_no"])],
            defaults=PolicyDefaults(no_match="require_human", low_confidence="require_human"),
        )
        # Rule requires min_confidence=low (default), but no_match default should not trigger
        d = _eval(p, confidence="low")
        # LOW confidence still matches since default min_confidence is LOW
        assert d.matched_rule_id == "r1"

    def test_low_confidence_fallback_when_min_is_medium(self) -> None:
        r1 = make_rule(
            "r1", "auto_reply", prompt_type=["yes_no"], min_confidence=ConfidenceLevel.MED
        )
        p = make_policy(r1)
        p_with_low_default = Policy(
            policy_version="0",
            name="test",
            rules=[r1],
            defaults=PolicyDefaults(low_confidence="deny"),
        )
        d = _eval(p_with_low_default, confidence="low")
        assert d.action_type == "deny"
        assert d.matched_rule_id is None

    def test_tool_id_wildcard_matches_any(self) -> None:
        r1 = make_rule("r1", "auto_reply", tool_id="*")
        p = make_policy(r1)
        d = _eval(p, tool_id="claude_code")
        assert d.matched_rule_id == "r1"

    def test_tool_id_exact_match(self) -> None:
        r1 = make_rule("r1", "auto_reply", tool_id="claude_code")
        p = make_policy(r1)
        d = _eval(p, tool_id="openai_cli")
        assert d.matched_rule_id is None  # no match

    def test_repo_prefix_match(self) -> None:
        r1 = make_rule("r1", "auto_reply", repo="/home/user")
        p = make_policy(r1)
        d = _eval(p, repo="/home/user/project/sub")
        assert d.matched_rule_id == "r1"

    def test_repo_prefix_no_match(self) -> None:
        r1 = make_rule("r1", "auto_reply", repo="/home/user")
        p = make_policy(r1)
        d = _eval(p, repo="/home/other/project")
        assert d.matched_rule_id is None

    def test_contains_substring_match(self) -> None:
        r1 = make_rule("r1", "auto_reply", contains="continue")
        p = make_policy(r1)
        d = _eval(p, prompt_text="Do you want to Continue? [y/n]")
        assert d.matched_rule_id == "r1"

    def test_contains_substring_case_insensitive(self) -> None:
        r1 = make_rule("r1", "auto_reply", contains="CONTINUE")
        p = make_policy(r1)
        d = _eval(p, prompt_text="Do you want to continue?")
        assert d.matched_rule_id == "r1"

    def test_contains_regex_match(self) -> None:
        r1 = make_rule("r1", "deny", contains=r"rm\s+-rf", contains_is_regex=True)
        p = make_policy(r1)
        d = _eval(p, prompt_text="Run: rm -rf /tmp/test?")
        assert d.matched_rule_id == "r1"
        assert d.action_type == "deny"

    def test_contains_regex_no_match(self) -> None:
        r1 = make_rule("r1", "deny", contains=r"rm\s+-rf", contains_is_regex=True)
        p = make_policy(r1)
        d = _eval(p, prompt_text="Delete this file?")
        assert d.matched_rule_id is None

    def test_min_confidence_met(self) -> None:
        r1 = make_rule("r1", "auto_reply", min_confidence=ConfidenceLevel.MED)
        p = make_policy(r1)
        d = _eval(p, confidence="high")
        assert d.matched_rule_id == "r1"

    def test_min_confidence_not_met(self) -> None:
        r1 = make_rule("r1", "auto_reply", min_confidence=ConfidenceLevel.HIGH)
        p = make_policy(r1)
        d = _eval(p, confidence="medium")
        assert d.matched_rule_id is None

    def test_prompt_type_any_wildcard(self) -> None:
        r1 = make_rule("r1", "auto_reply", prompt_type=["*"])
        p = make_policy(r1)
        d = _eval(p, prompt_type="free_text")
        assert d.matched_rule_id == "r1"

    def test_idempotency_key_is_deterministic(self) -> None:
        p = make_policy(make_rule("r1"))
        d1 = evaluate(
            policy=p,
            prompt_text="x",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="pid",
            session_id="sid",
        )
        d2 = evaluate(
            policy=p,
            prompt_text="different text",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="pid",
            session_id="sid",
        )
        # Same policy_hash + prompt_id + session_id → same idempotency key
        assert d1.idempotency_key == d2.idempotency_key

    def test_idempotency_key_changes_with_prompt_id(self) -> None:
        p = make_policy(make_rule("r1"))
        d1 = evaluate(
            policy=p,
            prompt_text="x",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
        )
        d2 = evaluate(
            policy=p,
            prompt_text="x",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p2",
            session_id="s1",
        )
        assert d1.idempotency_key != d2.idempotency_key

    def test_decision_to_dict_has_required_keys(self) -> None:
        p = make_policy(make_rule("r1"))
        d = _eval(p)
        dct = d.to_dict()
        for key in (
            "timestamp",
            "idempotency_key",
            "prompt_id",
            "session_id",
            "policy_hash",
            "matched_rule_id",
            "action_type",
            "action_value",
            "confidence",
            "prompt_type",
            "autonomy_mode",
            "explanation",
        ):
            assert key in dct, f"missing key: {key}"

    def test_decision_to_json_parses(self) -> None:
        import json

        p = make_policy(make_rule("r1"))
        d = _eval(p)
        parsed = json.loads(d.to_json())
        assert parsed["action_type"] in ("auto_reply", "require_human", "deny", "notify_only")

    def test_fixture_basic_policy_yes_no_auto_y(self) -> None:
        policy = load_policy(FIXTURES_DIR / "basic.yaml")
        d = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
        )
        assert d.action_type == "auto_reply"
        assert d.action_value == "y"

    def test_fixture_basic_policy_low_confidence_escalates(self) -> None:
        policy = load_policy(FIXTURES_DIR / "basic.yaml")
        d = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="low",
            prompt_id="p1",
            session_id="s1",
        )
        # Rule requires min_confidence=medium; LOW doesn't satisfy → no match → require_human
        assert d.action_type == "require_human"

    def test_fixture_escalation_deny_destructive(self) -> None:
        policy = load_policy(FIXTURES_DIR / "escalation.yaml")
        d = evaluate(
            policy=policy,
            prompt_text="Run rm -rf /var?",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
        )
        assert d.action_type == "deny"

    def test_fixture_full_auto_tool_id_mismatch(self) -> None:
        policy = load_policy(FIXTURES_DIR / "full_auto.yaml")
        d = evaluate(
            policy=policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
            prompt_id="p1",
            session_id="s1",
            tool_id="openai_cli",  # claude_code rule won't match
        )
        # Falls through to catch-all-human
        assert d.action_type == "require_human"
        assert d.matched_rule_id == "catch-all-human"
