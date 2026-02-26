"""
Safety test: GA risk classification determinism.

Ensures identical inputs ALWAYS produce identical risk assessments.
This is a contract test — if it fails, risk classification is non-deterministic
and the GA requirement is broken.
"""

from __future__ import annotations

import pytest

from atlasbridge.core.risk import RiskClassifier, RiskInput

_DETERMINISM_ITERATIONS = 1000


@pytest.fixture(
    params=[
        # LOW
        {"prompt_type": "yes_no", "action_type": "require_human", "confidence": "high"},
        # MEDIUM
        {"prompt_type": "yes_no", "action_type": "auto_reply", "confidence": "medium"},
        # HIGH
        {
            "prompt_type": "free_text",
            "action_type": "auto_reply",
            "confidence": "low",
        },
        # CRITICAL
        {
            "prompt_type": "free_text",
            "action_type": "auto_reply",
            "confidence": "low",
            "branch": "main",
            "ci_status": "failing",
            "file_scope": "secrets",
            "command_pattern": "rm -rf /",
            "environment": "production",
        },
        # Edge: deny action
        {"prompt_type": "yes_no", "action_type": "deny", "confidence": "high"},
        # Edge: all context, human review
        {
            "prompt_type": "confirm_enter",
            "action_type": "require_human",
            "confidence": "medium",
            "branch": "release/1.0",
            "ci_status": "passing",
            "file_scope": "config",
            "environment": "staging",
        },
    ],
    ids=["low", "medium", "high", "critical", "deny", "human-with-context"],
)
def risk_input(request: pytest.FixtureRequest) -> RiskInput:
    return RiskInput(**request.param)


def test_deterministic_risk_classification(risk_input: RiskInput) -> None:
    """Same input must produce identical output across N iterations."""
    first = RiskClassifier.classify(risk_input)
    for _ in range(_DETERMINISM_ITERATIONS):
        result = RiskClassifier.classify(risk_input)
        assert result.score == first.score, f"Score diverged: {result.score} != {first.score}"
        assert result.category == first.category
        assert result.input_hash == first.input_hash
        assert len(result.factors) == len(first.factors)


def test_input_hash_reproducibility(risk_input: RiskInput) -> None:
    """Input hash must be identical across classifications."""
    hashes = {RiskClassifier.classify(risk_input).input_hash for _ in range(100)}
    assert len(hashes) == 1


def test_score_within_bounds(risk_input: RiskInput) -> None:
    """Score must always be 0–100."""
    result = RiskClassifier.classify(risk_input)
    assert 0 <= result.score <= 100


def test_category_matches_score(risk_input: RiskInput) -> None:
    """Category must match the score threshold."""
    result = RiskClassifier.classify(risk_input)
    if result.score <= 25:
        assert result.category == "low"
    elif result.score <= 50:
        assert result.category == "medium"
    elif result.score <= 75:
        assert result.category == "high"
    else:
        assert result.category == "critical"


def test_factor_weights_sum_correctly(risk_input: RiskInput) -> None:
    """Factor weights must sum to at most the score (clamped at 100)."""
    result = RiskClassifier.classify(risk_input)
    total = sum(f.weight for f in result.factors)
    assert result.score == min(100, total)
