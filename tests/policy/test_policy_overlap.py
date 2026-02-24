"""Tests for atlasbridge.core.policy.overlap — overlapping rule detection."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from atlasbridge.cli._policy_cmd import policy_validate
from atlasbridge.core.policy.model import (
    AutoReplyAction,
    ConfidenceLevel,
    MatchCriteria,
    Policy,
    PolicyRule,
    PromptTypeFilter,
    RequireHumanAction,
)
from atlasbridge.core.policy.overlap import detect_overlaps
from atlasbridge.core.policy.parser import load_policy

_FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule(
    rule_id: str,
    prompt_types: list[str] | None = None,
    min_confidence: str = "low",
    tool_id: str = "*",
    repo: str | None = None,
    action_type: str = "auto_reply",
    value: str = "y",
) -> PolicyRule:
    pt = [PromptTypeFilter(t) for t in prompt_types] if prompt_types else None
    action = AutoReplyAction(value=value) if action_type == "auto_reply" else RequireHumanAction()
    return PolicyRule(
        id=rule_id,
        match=MatchCriteria(
            prompt_type=pt,
            min_confidence=ConfidenceLevel(min_confidence),
            tool_id=tool_id,
            repo=repo,
        ),
        action=action,
    )


def _policy(*rules: PolicyRule) -> Policy:
    return Policy(
        policy_version="0",
        name="test",
        rules=list(rules),
    )


# ---------------------------------------------------------------------------
# detect_overlaps() tests
# ---------------------------------------------------------------------------


class TestDetectOverlaps:
    def test_no_overlap_different_types(self):
        """Rules matching different prompt types don't overlap."""
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"]),
            _rule("r2", prompt_types=["free_text"]),
        )
        warnings = detect_overlaps(policy)
        assert len(warnings) == 0

    def test_overlap_same_type(self):
        """Two rules matching the same prompt type overlap."""
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"]),
            _rule("r2", prompt_types=["yes_no"]),
        )
        warnings = detect_overlaps(policy)
        assert len(warnings) == 1
        assert "r1" in warnings[0].rule_a_id
        assert "r2" in warnings[0].rule_b_id

    def test_overlap_wildcard_type(self):
        """A wildcard rule overlaps with any typed rule."""
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"]),
            _rule("r2", prompt_types=["*"]),
        )
        warnings = detect_overlaps(policy)
        assert len(warnings) == 1

    def test_overlap_none_type_matches_all(self):
        """A rule with no prompt_type (None) matches everything — overlaps."""
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"]),
            _rule("r2", prompt_types=None),
        )
        warnings = detect_overlaps(policy)
        assert len(warnings) == 1

    def test_no_overlap_different_tools(self):
        """Rules for different tools don't overlap."""
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"], tool_id="claude_code"),
            _rule("r2", prompt_types=["yes_no"], tool_id="openai_cli"),
        )
        warnings = detect_overlaps(policy)
        assert len(warnings) == 0

    def test_no_overlap_non_overlapping_confidence(self):
        """Rules with non-overlapping confidence ranges don't overlap."""
        # This requires v1 with max_confidence — for v0, min_confidence only means
        # [min, HIGH], so two rules with different min still overlap if ranges intersect
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"], min_confidence="high"),
            _rule("r2", prompt_types=["yes_no"], min_confidence="low"),
        )
        warnings = detect_overlaps(policy)
        # r1=[high,high], r2=[low,high] — they overlap at high
        assert len(warnings) == 1

    def test_no_overlap_different_repos(self):
        """Rules with non-overlapping repo prefixes don't overlap."""
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"], repo="/home/alice"),
            _rule("r2", prompt_types=["yes_no"], repo="/home/bob"),
        )
        warnings = detect_overlaps(policy)
        assert len(warnings) == 0

    def test_overlap_nested_repos(self):
        """Nested repo prefixes overlap (/home and /home/alice)."""
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"], repo="/home"),
            _rule("r2", prompt_types=["yes_no"], repo="/home/alice"),
        )
        warnings = detect_overlaps(policy)
        assert len(warnings) == 1

    def test_fixture_basic_has_no_overlap(self):
        """basic.yaml should have no overlapping rules."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        warnings = detect_overlaps(policy)
        assert len(warnings) == 0

    def test_warning_str_format(self):
        """OverlapWarning.__str__ produces readable output."""
        policy = _policy(
            _rule("r1", prompt_types=["yes_no"]),
            _rule("r2", prompt_types=["yes_no"]),
        )
        warnings = detect_overlaps(policy)
        s = str(warnings[0])
        assert "r1" in s
        assert "r2" in s
        assert "overlap" in s.lower() or "shared" in s.lower()

    def test_single_rule_no_overlap(self):
        """A policy with one rule has no overlaps."""
        policy = _policy(_rule("r1", prompt_types=["yes_no"]))
        warnings = detect_overlaps(policy)
        assert len(warnings) == 0

    def test_empty_policy_no_overlap(self):
        """An empty policy has no overlaps."""
        policy = _policy()
        warnings = detect_overlaps(policy)
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# CLI --check-overlaps tests
# ---------------------------------------------------------------------------


class TestCheckOverlapsCLI:
    def test_check_overlaps_clean(self):
        runner = CliRunner()
        result = runner.invoke(
            policy_validate,
            [str(_FIXTURES / "basic.yaml"), "--check-overlaps"],
        )
        assert result.exit_code == 0
        assert "No overlapping rules" in result.output

    def test_check_overlaps_not_shown_by_default(self):
        """Without --check-overlaps, overlap info should not appear."""
        runner = CliRunner()
        result = runner.invoke(policy_validate, [str(_FIXTURES / "basic.yaml")])
        assert result.exit_code == 0
        assert "overlap" not in result.output.lower()
