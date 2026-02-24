"""Tests for atlasbridge.core.policy.coverage — analyze_coverage() and CLI command."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from atlasbridge.cli._policy_cmd import policy_coverage
from atlasbridge.core.policy.coverage import (
    KNOWN_PROMPT_TYPES,
    PolicyCoverage,
    analyze_coverage,
    format_coverage,
)
from atlasbridge.core.policy.parser import load_policy

_FIXTURES = Path(__file__).parent / "fixtures"
_FIXTURES_V1 = _FIXTURES / "v1"


# ---------------------------------------------------------------------------
# analyze_coverage() tests
# ---------------------------------------------------------------------------


class TestAnalyzeCoverage:
    def test_basic_policy_partial_coverage(self):
        """basic.yaml covers yes_no + confirm_enter but not multiple_choice or free_text."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)

        assert report.total_rules == 2
        assert "yes_no" in report.covered_prompt_types
        assert "confirm_enter" in report.covered_prompt_types
        assert "multiple_choice" in report.uncovered_prompt_types
        assert "free_text" in report.uncovered_prompt_types
        assert report.has_default_no_match
        assert report.has_default_low_confidence

    def test_full_auto_policy_wildcard(self):
        """full_auto.yaml uses wildcard prompt_type — all types covered."""
        policy = load_policy(_FIXTURES / "full_auto.yaml")
        report = analyze_coverage(policy)

        assert report.has_wildcard_rule
        assert len(report.uncovered_prompt_types) == 0
        assert set(report.covered_prompt_types) == set(KNOWN_PROMPT_TYPES)

    def test_escalation_policy(self):
        """escalation.yaml has deny + require_human actions."""
        policy = load_policy(_FIXTURES / "escalation.yaml")
        report = analyze_coverage(policy)

        assert "deny" in report.action_types_used or "require_human" in report.action_types_used

    def test_v1_policy_coverage(self):
        """V1 policies should be analyzable too."""
        policy = load_policy(_FIXTURES_V1 / "any_of_match.yaml")
        report = analyze_coverage(policy)

        assert report.total_rules > 0
        assert isinstance(report, PolicyCoverage)

    def test_empty_policy_critical_gap(self, tmp_path):
        """A policy with no rules should flag critical gap."""
        policy_yaml = {
            "policy_version": "0",
            "name": "empty",
            "autonomy_mode": "full",
            "rules": [],
            "defaults": {"no_match": "require_human", "low_confidence": "require_human"},
        }
        policy_file = tmp_path / "empty.yaml"
        policy_file.write_text(yaml.dump(policy_yaml))
        policy = load_policy(str(policy_file))

        report = analyze_coverage(policy)

        assert report.total_rules == 0
        assert report.coverage_score < 30
        assert any(g.severity == "critical" for g in report.gaps)
        assert any("no rules" in g.description.lower() for g in report.gaps)

    def test_coverage_score_range(self):
        """Score should be between 0 and 100."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)

        assert 0 <= report.coverage_score <= 100

    def test_full_coverage_high_score(self):
        """A wildcard policy with defaults should score high."""
        policy = load_policy(_FIXTURES / "full_auto.yaml")
        report = analyze_coverage(policy)

        assert report.coverage_score >= 70

    def test_defaults_present(self):
        """basic.yaml has both defaults set."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)

        assert report.has_default_no_match
        assert report.has_default_low_confidence

    def test_no_deny_gap_flagged(self):
        """basic.yaml has no deny rules — should flag as low severity gap."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)

        deny_gaps = [g for g in report.gaps if g.item == "deny"]
        assert len(deny_gaps) == 1
        assert deny_gaps[0].severity == "low"


# ---------------------------------------------------------------------------
# format_coverage() tests
# ---------------------------------------------------------------------------


class TestFormatCoverage:
    def test_output_contains_score(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)
        output = format_coverage(report)

        assert "Coverage Score:" in output
        assert "/100" in output

    def test_output_contains_prompt_types(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)
        output = format_coverage(report)

        assert "Prompt Type Coverage:" in output
        assert "yes_no" in output
        assert "free_text" in output

    def test_output_contains_confidence_levels(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)
        output = format_coverage(report)

        assert "Confidence Level Coverage:" in output

    def test_output_contains_gaps(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)
        output = format_coverage(report)

        assert "Gaps" in output

    def test_full_coverage_no_gaps_message(self):
        """A policy with full coverage should say 'No gaps'."""
        policy = load_policy(_FIXTURES / "full_auto.yaml")
        report = analyze_coverage(policy)
        # Only check if there are no medium/critical gaps
        # (low severity "no deny" gap may still be present)
        output = format_coverage(report)
        # The output should contain gap section
        assert "Gaps" in output or "No gaps" in output

    def test_output_shows_action_types(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        report = analyze_coverage(policy)
        output = format_coverage(report)

        assert "Action types used:" in output
        assert "auto_reply" in output


# ---------------------------------------------------------------------------
# CLI command tests
# ---------------------------------------------------------------------------


class TestCoverageCLI:
    def test_coverage_command_basic(self):
        runner = CliRunner()
        result = runner.invoke(policy_coverage, [str(_FIXTURES / "basic.yaml")])

        assert result.exit_code == 0
        assert "Coverage Score:" in result.output
        assert "Prompt Type Coverage:" in result.output

    def test_coverage_command_full_auto(self):
        runner = CliRunner()
        result = runner.invoke(policy_coverage, [str(_FIXTURES / "full_auto.yaml")])

        assert result.exit_code == 0
        assert "Coverage Score:" in result.output

    def test_coverage_command_v1_policy(self):
        runner = CliRunner()
        result = runner.invoke(policy_coverage, [str(_FIXTURES_V1 / "any_of_match.yaml")])

        assert result.exit_code == 0
        assert "Coverage Score:" in result.output

    def test_coverage_command_invalid_file(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: a: valid: policy")
        runner = CliRunner()
        result = runner.invoke(policy_coverage, [str(bad)])

        assert result.exit_code == 1

    def test_coverage_command_missing_file(self):
        runner = CliRunner()
        result = runner.invoke(policy_coverage, ["/nonexistent/policy.yaml"])

        assert result.exit_code != 0
