"""
Tests for the GA risk classification engine (core/risk).

Covers:
- Deterministic scoring (same input → same output)
- All risk categories reachable
- Factor traceability
- Input hash reproducibility
- Score clamping (0–100)
- Protected branch detection
- Destructive command detection
- File scope sensitivity
- Environment awareness
"""

from __future__ import annotations

from atlasbridge.core.risk import (
    RiskCategory,
    RiskClassifier,
    RiskFactor,
    RiskInput,
    score_to_category,
)

# ---------------------------------------------------------------------------
# score_to_category mapping
# ---------------------------------------------------------------------------


class TestScoreToCategory:
    def test_low_range(self):
        assert score_to_category(0) == RiskCategory.LOW
        assert score_to_category(25) == RiskCategory.LOW

    def test_medium_range(self):
        assert score_to_category(26) == RiskCategory.MEDIUM
        assert score_to_category(50) == RiskCategory.MEDIUM

    def test_high_range(self):
        assert score_to_category(51) == RiskCategory.HIGH
        assert score_to_category(75) == RiskCategory.HIGH

    def test_critical_range(self):
        assert score_to_category(76) == RiskCategory.CRITICAL
        assert score_to_category(100) == RiskCategory.CRITICAL

    def test_clamped_above_100(self):
        assert score_to_category(150) == RiskCategory.CRITICAL

    def test_clamped_below_0(self):
        assert score_to_category(-5) == RiskCategory.LOW


# ---------------------------------------------------------------------------
# RiskInput
# ---------------------------------------------------------------------------


class TestRiskInput:
    def test_frozen(self):
        import pytest

        inp = RiskInput(prompt_type="yes_no", action_type="auto_reply", confidence="high")
        with pytest.raises(AttributeError):
            inp.prompt_type = "free_text"  # type: ignore[misc]

    def test_input_hash_deterministic(self):
        inp = RiskInput(prompt_type="yes_no", action_type="auto_reply", confidence="high")
        assert inp.input_hash() == inp.input_hash()

    def test_input_hash_changes_with_input(self):
        inp1 = RiskInput(prompt_type="yes_no", action_type="auto_reply", confidence="high")
        inp2 = RiskInput(prompt_type="free_text", action_type="auto_reply", confidence="high")
        assert inp1.input_hash() != inp2.input_hash()

    def test_defaults(self):
        inp = RiskInput(prompt_type="yes_no", action_type="auto_reply", confidence="high")
        assert inp.branch == ""
        assert inp.ci_status == ""
        assert inp.file_scope == ""
        assert inp.command_pattern == ""
        assert inp.environment == ""


# ---------------------------------------------------------------------------
# RiskClassifier — determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_identical_input_identical_output(self):
        inp = RiskInput(
            prompt_type="yes_no",
            action_type="auto_reply",
            confidence="high",
            branch="main",
            ci_status="passing",
        )
        results = [RiskClassifier.classify(inp) for _ in range(100)]
        scores = {r.score for r in results}
        cats = {r.category for r in results}
        hashes = {r.input_hash for r in results}
        assert len(scores) == 1
        assert len(cats) == 1
        assert len(hashes) == 1

    def test_determinism_across_all_factor_combinations(self):
        """Run 1000 identical classifications — must all match."""
        inp = RiskInput(
            prompt_type="free_text",
            action_type="auto_reply",
            confidence="low",
            branch="main",
            ci_status="failing",
            file_scope="secrets",
            command_pattern="rm -rf /",
            environment="production",
        )
        first = RiskClassifier.classify(inp)
        for _ in range(999):
            r = RiskClassifier.classify(inp)
            assert r.score == first.score
            assert r.category == first.category
            assert r.input_hash == first.input_hash
            assert len(r.factors) == len(first.factors)


# ---------------------------------------------------------------------------
# RiskClassifier — all categories reachable
# ---------------------------------------------------------------------------


class TestCategoryReachability:
    def test_low_risk(self):
        """require_human + high confidence + no context = LOW."""
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="require_human",
                confidence="high",
            )
        )
        assert r.category == RiskCategory.LOW
        assert r.score <= 25

    def test_medium_risk(self):
        """auto_reply + medium confidence + protected branch = MEDIUM (15+10+15=40)."""
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="medium",
                branch="main",
            )
        )
        assert r.category == RiskCategory.MEDIUM

    def test_high_risk(self):
        """auto_reply + free_text + low confidence + protected branch = HIGH (15+20+15+15=65)."""
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="free_text",
                action_type="auto_reply",
                confidence="low",
                branch="main",
            )
        )
        assert r.category == RiskCategory.HIGH

    def test_critical_risk(self):
        """auto_reply + low conf + protected branch + failing CI + destructive cmd = CRITICAL."""
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="free_text",
                action_type="auto_reply",
                confidence="low",
                branch="main",
                ci_status="failing",
                command_pattern="rm -rf /",
                environment="production",
            )
        )
        assert r.category == RiskCategory.CRITICAL
        assert r.score >= 76


# ---------------------------------------------------------------------------
# Factor traceability
# ---------------------------------------------------------------------------


class TestFactorTraceability:
    def test_factors_have_names_and_weights(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="free_text",
                action_type="auto_reply",
                confidence="low",
                branch="main",
            )
        )
        assert len(r.factors) > 0
        for f in r.factors:
            assert isinstance(f, RiskFactor)
            assert f.name
            assert f.weight > 0
            assert f.description

    def test_factor_weights_sum_to_score(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="free_text",
                action_type="auto_reply",
                confidence="low",
                branch="main",
                ci_status="failing",
            )
        )
        total = sum(f.weight for f in r.factors)
        assert r.score == min(100, total)

    def test_no_factors_for_safe_decision(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="require_human",
                confidence="high",
            )
        )
        assert len(r.factors) == 0
        assert r.score == 0

    def test_explanation_includes_factor_names(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="free_text",
                action_type="auto_reply",
                confidence="low",
            )
        )
        assert "action_type" in r.explanation
        assert "confidence" in r.explanation
        assert "prompt_type" in r.explanation


# ---------------------------------------------------------------------------
# Protected branch detection
# ---------------------------------------------------------------------------


class TestProtectedBranch:
    def test_main_is_protected(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                branch="main",
            )
        )
        factor_names = {f.name for f in r.factors}
        assert "branch" in factor_names

    def test_release_prefix_is_protected(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                branch="release/1.0",
            )
        )
        factor_names = {f.name for f in r.factors}
        assert "branch" in factor_names

    def test_feature_branch_not_protected(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                branch="feature/my-feature",
            )
        )
        factor_names = {f.name for f in r.factors}
        assert "branch" not in factor_names


# ---------------------------------------------------------------------------
# Destructive command detection
# ---------------------------------------------------------------------------


class TestDestructiveCommands:
    def test_rm_rf_detected(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                command_pattern="rm -rf /tmp/data",
            )
        )
        factor_names = {f.name for f in r.factors}
        assert "command_pattern" in factor_names

    def test_force_push_detected(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                command_pattern="git push -f origin main",
            )
        )
        factor_names = {f.name for f in r.factors}
        assert "command_pattern" in factor_names

    def test_safe_command_not_flagged(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                command_pattern="git status",
            )
        )
        factor_names = {f.name for f in r.factors}
        assert "command_pattern" not in factor_names


# ---------------------------------------------------------------------------
# File scope sensitivity
# ---------------------------------------------------------------------------


class TestFileScope:
    def test_secrets_scope_highest_weight(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                file_scope="secrets",
            )
        )
        factor = next(f for f in r.factors if f.name == "file_scope")
        assert factor.weight == 20

    def test_infrastructure_scope(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                file_scope="infrastructure",
            )
        )
        factor = next(f for f in r.factors if f.name == "file_scope")
        assert factor.weight == 15

    def test_config_scope(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                file_scope="config",
            )
        )
        factor = next(f for f in r.factors if f.name == "file_scope")
        assert factor.weight == 10

    def test_general_scope_no_factor(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                file_scope="general",
            )
        )
        factor_names = {f.name for f in r.factors}
        assert "file_scope" not in factor_names


# ---------------------------------------------------------------------------
# Environment awareness
# ---------------------------------------------------------------------------


class TestEnvironment:
    def test_production_highest_weight(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                environment="production",
            )
        )
        factor = next(f for f in r.factors if f.name == "environment")
        assert factor.weight == 15

    def test_staging_medium_weight(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                environment="staging",
            )
        )
        factor = next(f for f in r.factors if f.name == "environment")
        assert factor.weight == 5

    def test_dev_no_factor(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="auto_reply",
                confidence="high",
                environment="dev",
            )
        )
        factor_names = {f.name for f in r.factors}
        assert "environment" not in factor_names


# ---------------------------------------------------------------------------
# RiskAssessment.to_dict()
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_structure(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="free_text",
                action_type="auto_reply",
                confidence="low",
                branch="main",
            )
        )
        d = r.to_dict()
        assert "score" in d
        assert "category" in d
        assert "factors" in d
        assert "explanation" in d
        assert "input_hash" in d
        assert isinstance(d["factors"], list)
        for f in d["factors"]:
            assert "name" in f
            assert "weight" in f
            assert "description" in f


# ---------------------------------------------------------------------------
# Score clamping
# ---------------------------------------------------------------------------


class TestScoreClamping:
    def test_maximum_factors_clamped_to_100(self):
        """Stack every possible factor — score must not exceed 100."""
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="free_text",
                action_type="auto_reply",
                confidence="low",
                branch="main",
                ci_status="failing",
                file_scope="secrets",
                command_pattern="rm -rf /",
                environment="production",
            )
        )
        assert r.score <= 100
        assert r.score >= 76  # must be CRITICAL
        assert r.category == RiskCategory.CRITICAL

    def test_minimum_score_is_zero(self):
        r = RiskClassifier.classify(
            RiskInput(
                prompt_type="yes_no",
                action_type="deny",
                confidence="high",
            )
        )
        assert r.score == 0
        assert r.category == RiskCategory.LOW
