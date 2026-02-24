"""Tests for policy debug mode — debug_policy() and --debug CLI flag."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from atlasbridge.cli._policy_cmd import policy_test
from atlasbridge.core.policy.evaluator import _evaluate_rule, _evaluate_rule_v1
from atlasbridge.core.policy.explain import debug_policy
from atlasbridge.core.policy.parser import load_policy

_FIXTURES = Path(__file__).parent / "fixtures"
_FIXTURES_V1 = _FIXTURES / "v1"


# ---------------------------------------------------------------------------
# short_circuit=False evaluator tests
# ---------------------------------------------------------------------------


class TestShortCircuitDisabled:
    """Verify that short_circuit=False causes all criteria to be evaluated."""

    def test_v0_all_criteria_shown_on_mismatch(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        rule = policy.rules[0]  # yes-no-auto-yes

        # With short_circuit=True and wrong prompt_type, should stop early
        result_sc = _evaluate_rule(
            rule=rule,
            prompt_type="free_text",
            confidence="low",
            excerpt="anything",
            tool_id="*",
            repo="",
            short_circuit=True,
        )
        # With short_circuit=False, all criteria shown
        result_full = _evaluate_rule(
            rule=rule,
            prompt_type="free_text",
            confidence="low",
            excerpt="anything",
            tool_id="*",
            repo="",
            short_circuit=False,
        )

        # Both should not match
        assert not result_sc.matched
        assert not result_full.matched

        # Full trace should have more reasons (all criteria evaluated)
        assert len(result_full.reasons) >= len(result_sc.reasons)
        # Full trace should include confidence check even though prompt_type failed
        assert any("min_confidence" in r for r in result_full.reasons)

    def test_v1_all_criteria_shown_on_mismatch(self):
        policy = load_policy(_FIXTURES_V1 / "session_tag_match.yaml")
        rule = policy.rules[0]  # ci-auto-reply

        # Short-circuit: stops at first failure
        result_sc = _evaluate_rule_v1(
            rule=rule,
            prompt_type="free_text",
            confidence="low",
            excerpt="test",
            tool_id="wrong-tool",
            repo="/wrong/repo",
            session_tag="wrong-tag",
            short_circuit=True,
        )
        # Full: evaluates all criteria
        result_full = _evaluate_rule_v1(
            rule=rule,
            prompt_type="free_text",
            confidence="low",
            excerpt="test",
            tool_id="wrong-tool",
            repo="/wrong/repo",
            session_tag="wrong-tag",
            short_circuit=False,
        )

        assert not result_sc.matched
        assert not result_full.matched
        assert len(result_full.reasons) >= len(result_sc.reasons)

    def test_v0_match_unchanged_with_short_circuit_off(self):
        """short_circuit=False should not change the match/miss result."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        rule = policy.rules[0]  # yes-no-auto-yes

        result_sc = _evaluate_rule(
            rule=rule,
            prompt_type="yes_no",
            confidence="high",
            excerpt="Continue? [y/n]",
            tool_id="*",
            repo="",
            short_circuit=True,
        )
        result_full = _evaluate_rule(
            rule=rule,
            prompt_type="yes_no",
            confidence="high",
            excerpt="Continue? [y/n]",
            tool_id="*",
            repo="",
            short_circuit=False,
        )

        assert result_sc.matched
        assert result_full.matched


# ---------------------------------------------------------------------------
# debug_policy() output tests
# ---------------------------------------------------------------------------


class TestDebugPolicy:
    def test_header_and_footer_present(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        output = debug_policy(
            policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert "POLICY DEBUG TRACE" in output
        assert "END DEBUG TRACE" in output

    def test_all_rules_evaluated(self):
        """Unlike explain_policy, debug_policy shows ALL rules — no early exit."""
        policy = load_policy(_FIXTURES / "basic.yaml")
        output = debug_policy(
            policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        # basic.yaml has 2 rules: yes-no-auto-yes and confirm-enter-auto
        # Both should appear in the output (explain_policy would stop after first match)
        assert "yes-no-auto-yes" in output
        assert "confirm-enter-auto" in output

    def test_winner_marked(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        output = debug_policy(
            policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert "WINNER" in output
        assert "first-match-wins" in output.lower() or "first match" in output.lower()

    def test_summary_shows_match_count(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        output = debug_policy(
            policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert "Summary:" in output
        # At least 1 rule should match (yes-no-auto-yes)
        assert "1/" in output or "2/" in output

    def test_no_match_shows_default(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        output = debug_policy(
            policy,
            prompt_text="What file?",
            prompt_type="free_text",
            confidence="high",
        )
        assert "(none)" in output
        assert "require_human" in output

    def test_prompt_text_shown_in_header(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        output = debug_policy(
            policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert "Continue? [y/n]" in output

    def test_final_decision_section(self):
        policy = load_policy(_FIXTURES / "basic.yaml")
        output = debug_policy(
            policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert "Final decision:" in output
        assert "Action:" in output
        assert "AUTO_REPLY" in output

    def test_v1_debug_all_rules_traced(self):
        policy = load_policy(_FIXTURES_V1 / "none_of_match.yaml")
        output = debug_policy(
            policy,
            prompt_text="Continue? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert "POLICY DEBUG TRACE" in output
        # Should show all rules in the v1 policy
        assert "safe-auto-reply" in output
        assert "catch-all" in output

    def test_v1_none_of_criteria_shown(self):
        policy = load_policy(_FIXTURES_V1 / "none_of_match.yaml")
        output = debug_policy(
            policy,
            prompt_text="destroy all data? [y/n]",
            prompt_type="yes_no",
            confidence="high",
        )
        assert "none_of" in output


# ---------------------------------------------------------------------------
# CLI --debug flag tests
# ---------------------------------------------------------------------------


class TestDebugCLIFlag:
    def test_debug_flag_invokes_debug_policy(self):
        runner = CliRunner()
        result = runner.invoke(
            policy_test,
            [
                str(_FIXTURES / "basic.yaml"),
                "--prompt",
                "Continue? [y/n]",
                "--type",
                "yes_no",
                "--debug",
            ],
        )
        assert result.exit_code == 0
        assert "POLICY DEBUG TRACE" in result.output
        assert "END DEBUG TRACE" in result.output

    def test_debug_shows_all_rules(self):
        runner = CliRunner()
        result = runner.invoke(
            policy_test,
            [
                str(_FIXTURES / "basic.yaml"),
                "--prompt",
                "Continue? [y/n]",
                "--type",
                "yes_no",
                "--debug",
            ],
        )
        assert result.exit_code == 0
        assert "yes-no-auto-yes" in result.output
        assert "confirm-enter-auto" in result.output

    def test_explain_still_works(self):
        """--explain should still show first-match-wins behavior."""
        runner = CliRunner()
        result = runner.invoke(
            policy_test,
            [
                str(_FIXTURES / "basic.yaml"),
                "--prompt",
                "Continue? [y/n]",
                "--type",
                "yes_no",
                "--explain",
            ],
        )
        assert result.exit_code == 0
        assert "first match wins" in result.output.lower()

    def test_debug_without_explain_works(self):
        """--debug should work on its own without --explain."""
        runner = CliRunner()
        result = runner.invoke(
            policy_test,
            [
                str(_FIXTURES / "basic.yaml"),
                "--prompt",
                "Continue? [y/n]",
                "--type",
                "yes_no",
                "--debug",
            ],
        )
        assert result.exit_code == 0
        assert "POLICY DEBUG TRACE" in result.output
