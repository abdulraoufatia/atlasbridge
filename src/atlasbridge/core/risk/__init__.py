"""
Deterministic risk classification engine.

Computes a risk score (0–100) from weighted, traceable factors.
Every input signal has an explicit weight; identical inputs always
produce identical output.  No ML, no heuristics, no hidden state.

Risk categories:
    0–25   LOW
    26–50  MEDIUM
    51–75  HIGH
    76–100 CRITICAL

Usage::

    assessment = RiskClassifier.classify(RiskInput(
        prompt_type="free_text",
        action_type="auto_reply",
        confidence="low",
        branch="main",
        ci_status="failing",
        file_scope="infrastructure",
        command_pattern="rm -rf",
        environment="production",
    ))
    assert assessment.score == 100
    assert assessment.category == RiskCategory.CRITICAL
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum


class RiskCategory(StrEnum):
    """Risk category derived from numeric score."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Scoring thresholds — deterministic mapping from score to category
# ---------------------------------------------------------------------------

_THRESHOLDS: list[tuple[int, RiskCategory]] = [
    (76, RiskCategory.CRITICAL),
    (51, RiskCategory.HIGH),
    (26, RiskCategory.MEDIUM),
    (0, RiskCategory.LOW),
]


def score_to_category(score: int) -> RiskCategory:
    """Map a 0–100 score to a risk category.  Deterministic."""
    clamped = max(0, min(100, score))
    for threshold, cat in _THRESHOLDS:
        if clamped >= threshold:
            return cat
    return RiskCategory.LOW  # pragma: no cover — unreachable


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskFactor:
    """A single scored risk factor contributing to the overall assessment."""

    name: str
    weight: int  # contribution to the 0–100 score
    description: str


@dataclass(frozen=True)
class RiskInput:
    """All inputs to the risk classifier.  Every field is deterministic."""

    prompt_type: str  # yes_no, confirm_enter, multiple_choice, free_text
    action_type: str  # auto_reply, require_human, deny, notify_only
    confidence: str  # high, medium, low

    branch: str = ""
    ci_status: str = ""  # passing, failing, unknown, ""
    file_scope: str = ""  # general, config, infrastructure, secrets
    command_pattern: str = ""  # destructive command text (or "")
    environment: str = ""  # dev, staging, production, ""

    def input_hash(self) -> str:
        """SHA-256 hash of all input fields for reproducibility verification."""
        data = json.dumps(
            {
                "prompt_type": self.prompt_type,
                "action_type": self.action_type,
                "confidence": self.confidence,
                "branch": self.branch,
                "ci_status": self.ci_status,
                "file_scope": self.file_scope,
                "command_pattern": self.command_pattern,
                "environment": self.environment,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class RiskAssessment:
    """Output of the risk classifier — fully traceable."""

    score: int  # 0–100
    category: RiskCategory
    factors: tuple[RiskFactor, ...]
    explanation: str
    input_hash: str

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "category": self.category.value,
            "factors": [
                {"name": f.name, "weight": f.weight, "description": f.description}
                for f in self.factors
            ],
            "explanation": self.explanation,
            "input_hash": self.input_hash,
        }


# ---------------------------------------------------------------------------
# Factor scoring functions — each returns (weight, RiskFactor | None)
# ---------------------------------------------------------------------------

# Protected branch patterns
_PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master", "release", "production", "prod"})

# Destructive command patterns (lowercase substrings)
_DESTRUCTIVE_PATTERNS: tuple[str, ...] = (
    "rm -rf",
    "rm -r",
    "drop table",
    "drop database",
    "truncate",
    "delete from",
    "force-push",
    "--force",
    "git push -f",
    "git reset --hard",
    "git clean -f",
    "format c:",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    "kill -9",
    "pkill",
    "> /dev/",
)


def _is_protected_branch(branch: str) -> bool:
    if not branch:
        return False
    normalized = branch.strip().lower()
    if normalized in _PROTECTED_BRANCHES:
        return True
    return normalized.startswith("release/")


def _factor_action_type(inp: RiskInput) -> RiskFactor | None:
    """Action type risk: auto_reply is riskier than require_human."""
    if inp.action_type == "auto_reply":
        return RiskFactor(
            name="action_type",
            weight=15,
            description="auto_reply — autonomous execution without human review",
        )
    if inp.action_type == "deny":
        return RiskFactor(
            name="action_type",
            weight=0,
            description="deny — action blocked, no risk",
        )
    return None  # require_human, notify_only — no weight


def _factor_confidence(inp: RiskInput) -> RiskFactor | None:
    """Lower confidence = higher risk."""
    if inp.confidence == "low":
        return RiskFactor(
            name="confidence",
            weight=20,
            description="low confidence — prompt detection uncertain",
        )
    if inp.confidence == "medium":
        return RiskFactor(
            name="confidence",
            weight=10,
            description="medium confidence — partial signal match",
        )
    return None  # high confidence — no additional risk


def _factor_prompt_type(inp: RiskInput) -> RiskFactor | None:
    """Free-text prompts are inherently riskier (unbounded input)."""
    if inp.prompt_type == "free_text":
        return RiskFactor(
            name="prompt_type",
            weight=15,
            description="free_text — unbounded input, higher injection risk",
        )
    if inp.prompt_type == "multiple_choice":
        return RiskFactor(
            name="prompt_type",
            weight=5,
            description="multiple_choice — bounded but multi-option",
        )
    return None  # yes_no, confirm_enter — low inherent risk


def _factor_branch(inp: RiskInput) -> RiskFactor | None:
    """Protected branches carry higher risk."""
    if _is_protected_branch(inp.branch):
        return RiskFactor(
            name="branch",
            weight=15,
            description=f"protected branch '{inp.branch}' — changes affect production",
        )
    return None


def _factor_ci_status(inp: RiskInput) -> RiskFactor | None:
    """Failing CI increases risk."""
    if inp.ci_status == "failing":
        return RiskFactor(
            name="ci_status",
            weight=15,
            description="CI failing — deploying may introduce regressions",
        )
    if inp.ci_status == "unknown":
        return RiskFactor(
            name="ci_status",
            weight=5,
            description="CI status unknown — cannot verify safety",
        )
    return None  # passing or empty — no extra risk


def _factor_file_scope(inp: RiskInput) -> RiskFactor | None:
    """Operations on sensitive files carry more risk."""
    scope = inp.file_scope.lower()
    if scope == "secrets":
        return RiskFactor(
            name="file_scope",
            weight=20,
            description="secrets scope — operations on credential/secret files",
        )
    if scope == "infrastructure":
        return RiskFactor(
            name="file_scope",
            weight=15,
            description="infrastructure scope — operations on infra/deployment files",
        )
    if scope == "config":
        return RiskFactor(
            name="file_scope",
            weight=10,
            description="config scope — operations on configuration files",
        )
    return None  # general or empty — no extra risk


def _factor_command_pattern(inp: RiskInput) -> RiskFactor | None:
    """Destructive command patterns increase risk."""
    if not inp.command_pattern:
        return None
    lower = inp.command_pattern.lower()
    for pattern in _DESTRUCTIVE_PATTERNS:
        if pattern in lower:
            return RiskFactor(
                name="command_pattern",
                weight=20,
                description=f"destructive command detected: '{pattern}'",
            )
    return None


def _factor_environment(inp: RiskInput) -> RiskFactor | None:
    """Production environments carry the highest risk."""
    env = inp.environment.lower()
    if env in ("production", "prod"):
        return RiskFactor(
            name="environment",
            weight=15,
            description="production environment — direct impact on live systems",
        )
    if env == "staging":
        return RiskFactor(
            name="environment",
            weight=5,
            description="staging environment — pre-production risk",
        )
    return None  # dev or empty — no extra risk


# Ordered list of all factor functions
_FACTOR_FUNCTIONS = (
    _factor_action_type,
    _factor_confidence,
    _factor_prompt_type,
    _factor_branch,
    _factor_ci_status,
    _factor_file_scope,
    _factor_command_pattern,
    _factor_environment,
)


# ---------------------------------------------------------------------------
# Risk classifier
# ---------------------------------------------------------------------------


class RiskClassifier:
    """Deterministic weighted risk classifier.

    Every assessment is:
    - Deterministic — identical inputs produce identical output
    - Traceable — every factor is named, weighted, and described
    - Reproducible — input_hash allows verification
    - Bounded — score is clamped to 0–100
    """

    @classmethod
    def classify(cls, inp: RiskInput) -> RiskAssessment:
        """Classify risk for a given input context.

        Pure function — no side effects, no I/O, no state.
        """
        factors: list[RiskFactor] = []
        total = 0

        for fn in _FACTOR_FUNCTIONS:
            factor = fn(inp)
            if factor is not None and factor.weight > 0:
                factors.append(factor)
                total += factor.weight

        score = max(0, min(100, total))
        category = score_to_category(score)

        if factors:
            factor_strs = [f"{f.name}(+{f.weight})" for f in factors]
            explanation = f"Risk score {score}/100 ({category.value}): " + ", ".join(factor_strs)
        else:
            explanation = f"Risk score {score}/100 ({category.value}): no risk factors detected"

        return RiskAssessment(
            score=score,
            category=category,
            factors=tuple(factors),
            explanation=explanation,
            input_hash=inp.input_hash(),
        )
