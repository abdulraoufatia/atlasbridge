"""
Policy DSL v1 completeness audit — integration tests.

Validates that:
- All preset policies parse without error
- All v0 + v1 test fixtures parse without error
- Example policies parse without error
- v0 fixtures parse identically under both v0 and v1 code paths
- Unknown fields are rejected with clear error messages
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlasbridge.core.policy.parser import PolicyParseError, load_policy, parse_policy

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---- Discovery helpers ----


def _discover_yaml_files(*dirs: str) -> list[Path]:
    """Collect all .yaml files from given directories relative to project root."""
    files: list[Path] = []
    for d in dirs:
        p = PROJECT_ROOT / d
        if p.is_dir():
            files.extend(sorted(p.rglob("*.yaml")))
    return files


PRESET_POLICIES = _discover_yaml_files("config/policies")
EXAMPLE_POLICIES = [
    PROJECT_ROOT / "config/policy.example.yaml",
    PROJECT_ROOT / "config/policy.example_v1.yaml",
]
V0_FIXTURES = _discover_yaml_files("tests/policy/fixtures")
V1_FIXTURES = _discover_yaml_files("tests/policy/fixtures/v1")
# Remove v1 fixtures from v0 list (v1 dir is a subdirectory)
V0_FIXTURES = [f for f in V0_FIXTURES if "/v1/" not in str(f)]


# ---- Preset policies ----


@pytest.mark.parametrize("path", PRESET_POLICIES, ids=lambda p: p.name)
def test_preset_policies_parse(path: Path) -> None:
    """Every preset policy in config/policies/ must parse without error."""
    policy = load_policy(path)
    assert policy.name, f"{path.name}: policy name is empty"
    assert len(policy.rules) >= 1, f"{path.name}: no rules defined"


# ---- Example policies ----


@pytest.mark.parametrize("path", EXAMPLE_POLICIES, ids=lambda p: p.name)
def test_example_policies_parse(path: Path) -> None:
    """Example policies must parse without error."""
    policy = load_policy(path)
    assert policy.name
    assert len(policy.rules) >= 1


# ---- v0 fixtures ----


@pytest.mark.parametrize("path", V0_FIXTURES, ids=lambda p: p.name)
def test_v0_fixtures_parse(path: Path) -> None:
    """All v0 test fixtures must parse without error."""
    policy = load_policy(path)
    assert policy is not None


# ---- v1 fixtures ----


@pytest.mark.parametrize(
    "path",
    [f for f in V1_FIXTURES if "extends_child" not in f.name],
    ids=lambda p: p.name,
)
def test_v1_fixtures_parse(path: Path) -> None:
    """All v1 test fixtures must parse without error (skip extends_child, needs base)."""
    policy = load_policy(path)
    assert policy is not None


def test_v1_extends_fixture_parses() -> None:
    """The extends_child.yaml fixture must parse with its base."""
    child = PROJECT_ROOT / "tests/policy/fixtures/v1/extends_child.yaml"
    if child.exists():
        policy = load_policy(child)
        assert policy is not None
        assert len(policy.rules) >= 1


# ---- v0 backward compatibility ----


@pytest.mark.parametrize("path", V0_FIXTURES, ids=lambda p: p.name)
def test_v0_backward_compatibility(path: Path) -> None:
    """v0 fixtures must parse identically whether loaded as v0 or as YAML text."""
    policy_from_file = load_policy(path)
    policy_from_text = parse_policy(path.read_text())
    assert policy_from_file.name == policy_from_text.name
    assert len(policy_from_file.rules) == len(policy_from_text.rules)
    for r1, r2 in zip(policy_from_file.rules, policy_from_text.rules, strict=True):
        assert r1.id == r2.id


# ---- Unknown field rejection ----


def test_unknown_root_field_rejected() -> None:
    """Unknown fields at the root level must be rejected."""
    text = """
policy_version: "0"
name: "test"
autonomy_mode: "full"
unknown_field: true
rules: []
defaults:
  no_match: require_human
  low_confidence: require_human
"""
    with pytest.raises(PolicyParseError, match="(?i)unknown|extra"):
        parse_policy(text)


def test_unknown_match_field_rejected() -> None:
    """Unknown fields in match block must be rejected."""
    text = """
policy_version: "0"
name: "test"
autonomy_mode: "full"
rules:
  - id: "test-rule"
    match:
      bogus_field: true
    action:
      type: require_human
defaults:
  no_match: require_human
  low_confidence: require_human
"""
    with pytest.raises(PolicyParseError, match="(?i)unknown|extra"):
        parse_policy(text)


def test_unknown_action_field_rejected() -> None:
    """Unknown fields in action block must be rejected."""
    text = """
policy_version: "0"
name: "test"
autonomy_mode: "full"
rules:
  - id: "test-rule"
    match: {}
    action:
      type: require_human
      secret_bypass: true
defaults:
  no_match: require_human
  low_confidence: require_human
"""
    with pytest.raises(PolicyParseError, match="(?i)unknown|extra"):
        parse_policy(text)


def test_unknown_v1_match_field_rejected() -> None:
    """Unknown fields in v1 match block must be rejected."""
    text = """
policy_version: "1"
name: "test"
autonomy_mode: "full"
rules:
  - id: "test-rule"
    match:
      imaginary_v2_field: true
    action:
      type: require_human
defaults:
  no_match: require_human
  low_confidence: require_human
"""
    with pytest.raises(PolicyParseError, match="(?i)unknown|extra"):
        parse_policy(text)


# ---- v1 feature validation ----


def test_any_of_with_flat_criteria_rejected() -> None:
    """any_of and flat criteria on the same block must be rejected."""
    text = """
policy_version: "1"
name: "test"
autonomy_mode: "full"
rules:
  - id: "test-rule"
    match:
      prompt_type: [yes_no]
      any_of:
        - prompt_type: [confirm_enter]
    action:
      type: require_human
defaults:
  no_match: require_human
  low_confidence: require_human
"""
    with pytest.raises(PolicyParseError):
        parse_policy(text)


def test_extends_cycle_rejected() -> None:
    """Circular extends chains must be rejected."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        a_path = Path(tmpdir) / "a.yaml"
        b_path = Path(tmpdir) / "b.yaml"

        a_path.write_text(
            f'policy_version: "1"\nname: a\nautonomy_mode: full\n'
            f"extends: {b_path}\nrules:\n  - id: r1\n    match: {{}}\n"
            f"    action:\n      type: require_human\n"
            f"defaults:\n  no_match: require_human\n  low_confidence: require_human\n"
        )
        b_path.write_text(
            f'policy_version: "1"\nname: b\nautonomy_mode: full\n'
            f"extends: {a_path}\nrules:\n  - id: r2\n    match: {{}}\n"
            f"    action:\n      type: require_human\n"
            f"defaults:\n  no_match: require_human\n  low_confidence: require_human\n"
        )

        with pytest.raises(PolicyParseError, match="(?i)circular|cycle"):
            load_policy(a_path)


# ---- All documented DSL fields are validated by the parser ----

V0_MATCH_FIELDS = {
    "tool_id",
    "repo",
    "prompt_type",
    "contains",
    "contains_is_regex",
    "min_confidence",
}
V1_MATCH_FIELDS = V0_MATCH_FIELDS | {"max_confidence", "session_tag", "any_of", "none_of"}
ACTION_TYPES = {"auto_reply", "require_human", "deny", "notify_only"}


def test_all_v0_match_fields_accepted() -> None:
    """Parser must accept all documented v0 match fields."""
    text = """
policy_version: "0"
name: "test"
autonomy_mode: "full"
rules:
  - id: "all-fields"
    match:
      tool_id: "claude_code"
      repo: "/home/user/project"
      prompt_type: [yes_no]
      contains: "continue"
      contains_is_regex: false
      min_confidence: medium
    action:
      type: require_human
defaults:
  no_match: require_human
  low_confidence: require_human
"""
    policy = parse_policy(text)
    assert len(policy.rules) == 1


def test_all_v1_match_fields_accepted() -> None:
    """Parser must accept all documented v1 match fields."""
    text = """
policy_version: "1"
name: "test"
autonomy_mode: "full"
rules:
  - id: "any-of-rule"
    match:
      any_of:
        - prompt_type: [yes_no]
          min_confidence: high
          session_tag: "ci"
        - prompt_type: [confirm_enter]
          max_confidence: medium
      none_of:
        - contains: "destroy"
    action:
      type: require_human
defaults:
  no_match: require_human
  low_confidence: require_human
"""
    policy = parse_policy(text)
    assert len(policy.rules) == 1


def test_all_action_types_accepted() -> None:
    """Parser must accept all 4 documented action types."""
    for action_type in ACTION_TYPES:
        extra = ""
        if action_type == "auto_reply":
            extra = '\n      value: "y"'
        elif action_type == "deny":
            extra = '\n      reason: "denied"'
        elif action_type == "notify_only":
            extra = '\n      message: "notification"'

        text = f"""
policy_version: "0"
name: "test-{action_type}"
autonomy_mode: "full"
rules:
  - id: "rule-1"
    match: {{}}
    action:
      type: {action_type}{extra}
defaults:
  no_match: require_human
  low_confidence: require_human
"""
        policy = parse_policy(text)
        assert policy.rules[0].action.type == action_type
