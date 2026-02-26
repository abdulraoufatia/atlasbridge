"""Safety guard: Policy DSL schema must not drift."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlasbridge.core.policy.model import (
    AutonomyMode,
    AutoReplyAction,
    ConfidenceLevel,
    DenyAction,
    MatchCriteria,
    NotifyOnlyAction,
    Policy,
    PolicyDefaults,
    PolicyRule,
    PromptTypeFilter,
    RequireHumanAction,
)

# --- Enum stability ---


def test_autonomy_mode_members():
    """AutonomyMode must have exactly OFF, ASSIST, FULL."""
    expected = {"OFF", "ASSIST", "FULL"}
    actual = {m.name for m in AutonomyMode}
    assert actual == expected, f"AutonomyMode members changed: {actual}"


def test_prompt_type_filter_members():
    """PromptTypeFilter must have exactly 6 members."""
    expected = {"YES_NO", "CONFIRM_ENTER", "MULTIPLE_CHOICE", "FREE_TEXT", "TOOL_USE", "ANY"}
    actual = {m.name for m in PromptTypeFilter}
    assert actual == expected, f"PromptTypeFilter members changed: {actual}"


def test_confidence_level_members():
    """ConfidenceLevel must have exactly LOW, MED, HIGH."""
    expected = {"LOW", "MED", "HIGH"}
    actual = {m.name for m in ConfidenceLevel}
    assert actual == expected, f"ConfidenceLevel members changed: {actual}"


# --- Action type stability ---


def test_four_action_types_exist():
    """All 4 action types must exist."""
    assert AutoReplyAction is not None
    assert RequireHumanAction is not None
    assert DenyAction is not None
    assert NotifyOnlyAction is not None


def test_auto_reply_action_has_value_field():
    """AutoReplyAction must have a 'value' field."""
    action = AutoReplyAction(type="auto_reply", value="y")
    assert action.value == "y"


# --- PolicyDefaults safety ---


def test_defaults_no_match_is_require_human():
    """PolicyDefaults.no_match must default to 'require_human'."""
    defaults = PolicyDefaults()
    assert defaults.no_match == "require_human", (
        f"SAFETY VIOLATION: no_match default changed to '{defaults.no_match}'"
    )


def test_defaults_low_confidence_is_require_human():
    """PolicyDefaults.low_confidence must default to 'require_human'."""
    defaults = PolicyDefaults()
    assert defaults.low_confidence == "require_human", (
        f"SAFETY VIOLATION: low_confidence default changed to '{defaults.low_confidence}'"
    )


def test_defaults_no_match_rejects_auto_reply():
    """PolicyDefaults.no_match must NOT accept 'auto_reply'."""
    with pytest.raises(ValidationError):
        PolicyDefaults(no_match="auto_reply")


def test_defaults_low_confidence_rejects_auto_reply():
    """PolicyDefaults.low_confidence must NOT accept 'auto_reply'."""
    with pytest.raises(ValidationError):
        PolicyDefaults(low_confidence="auto_reply")


# --- Policy model stability ---


def test_policy_version_zero_accepted():
    """Policy must accept policy_version '0'."""
    p = Policy(
        policy_version="0",
        name="test",
        rules=[],
    )
    assert p.policy_version == "0"


def test_policy_has_content_hash():
    """Policy must have a content_hash() method."""
    p = Policy(policy_version="0", name="test", rules=[])
    h = p.content_hash()
    assert isinstance(h, str)
    assert len(h) == 16  # SHA-256 first 16 hex chars


def test_policy_rule_fields():
    """PolicyRule must have id, description, match, action fields."""
    rule = PolicyRule(
        id="test-rule",
        description="A test rule",
        match=MatchCriteria(),
        action=RequireHumanAction(type="require_human"),
    )
    assert rule.id == "test-rule"
    assert rule.description == "A test rule"
    assert rule.match is not None
    assert rule.action is not None


def test_policy_extra_fields_forbidden():
    """Policy models must reject unknown fields (extra='forbid')."""
    with pytest.raises(ValidationError):
        PolicyDefaults(no_match="require_human", unknown_field="bad")
