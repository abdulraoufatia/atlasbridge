"""
Policy coverage analyzer — identify rule gaps and compute coverage scores.

Usage::

    report = analyze_coverage(policy)
    print(format_coverage(report))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from atlasbridge.core.policy.model import (
    ConfidenceLevel,
    Policy,
    PromptTypeFilter,
)

if TYPE_CHECKING:
    from atlasbridge.core.policy.model_v1 import PolicyV1

# ---------------------------------------------------------------------------
# Known taxonomy — the universe of prompt types and confidence levels
# ---------------------------------------------------------------------------

# Concrete prompt types that rules should cover (excludes ANY wildcard)
KNOWN_PROMPT_TYPES: list[str] = [
    PromptTypeFilter.YES_NO.value,
    PromptTypeFilter.CONFIRM_ENTER.value,
    PromptTypeFilter.MULTIPLE_CHOICE.value,
    PromptTypeFilter.FREE_TEXT.value,
]

KNOWN_CONFIDENCE_LEVELS: list[str] = [
    ConfidenceLevel.LOW.value,
    ConfidenceLevel.MED.value,
    ConfidenceLevel.HIGH.value,
]

KNOWN_ACTION_TYPES: list[str] = [
    "auto_reply",
    "require_human",
    "deny",
    "notify_only",
]


# ---------------------------------------------------------------------------
# Coverage model
# ---------------------------------------------------------------------------


@dataclass
class CoverageGap:
    """A single identified gap in policy coverage."""

    category: str  # "prompt_type", "confidence", "default", "action"
    item: str  # e.g. "free_text", "low", "no_match_default"
    severity: str  # "critical", "medium", "low"
    description: str


@dataclass
class PolicyCoverage:
    """Result of analyzing a policy's rule coverage."""

    total_rules: int
    covered_prompt_types: list[str] = field(default_factory=list)
    uncovered_prompt_types: list[str] = field(default_factory=list)
    covered_confidence_levels: list[str] = field(default_factory=list)
    uncovered_confidence_levels: list[str] = field(default_factory=list)
    action_types_used: list[str] = field(default_factory=list)
    has_wildcard_rule: bool = False
    has_default_no_match: bool = False
    has_default_low_confidence: bool = False
    gaps: list[CoverageGap] = field(default_factory=list)
    coverage_score: int = 0  # 0-100


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_coverage(policy: Policy | PolicyV1) -> PolicyCoverage:
    """
    Analyze a policy's rules and compute coverage against the known taxonomy.

    Returns a PolicyCoverage with:
    - Which prompt types are covered (directly or via wildcard)
    - Which confidence levels have explicit min_confidence handling
    - Which action types are used
    - Gap list with severity and description
    - Coverage score (0-100)
    """
    from atlasbridge.core.policy.model_v1 import PolicyV1

    report = PolicyCoverage(total_rules=len(policy.rules))

    # Collect covered prompt types and confidence levels across all rules
    covered_types: set[str] = set()
    covered_conf: set[str] = set()
    action_types: set[str] = set()
    has_wildcard = False

    for rule in policy.rules:
        action_types.add(rule.action.type)

        if isinstance(policy, PolicyV1):
            _analyze_v1_rule(rule, covered_types, covered_conf, has_wildcard_set=None)
            # Check any_of branches for wildcards and types
            m = rule.match
            if m.any_of is not None:  # type: ignore[union-attr]
                for sub in m.any_of:  # type: ignore[union-attr]
                    _collect_criteria(sub, covered_types, covered_conf)
                    if sub.prompt_type and PromptTypeFilter.ANY in sub.prompt_type:
                        has_wildcard = True
            else:
                _collect_criteria(m, covered_types, covered_conf)
                if m.prompt_type and PromptTypeFilter.ANY in m.prompt_type:
                    has_wildcard = True
        else:
            m = rule.match
            _collect_criteria(m, covered_types, covered_conf)
            if m.prompt_type and PromptTypeFilter.ANY in m.prompt_type:
                has_wildcard = True

    # If any rule uses wildcard, all prompt types are covered
    if has_wildcard:
        covered_types = set(KNOWN_PROMPT_TYPES)

    report.has_wildcard_rule = has_wildcard
    report.covered_prompt_types = sorted(covered_types & set(KNOWN_PROMPT_TYPES))
    report.uncovered_prompt_types = sorted(set(KNOWN_PROMPT_TYPES) - covered_types)
    report.covered_confidence_levels = sorted(covered_conf & set(KNOWN_CONFIDENCE_LEVELS))
    report.uncovered_confidence_levels = sorted(set(KNOWN_CONFIDENCE_LEVELS) - covered_conf)
    report.action_types_used = sorted(action_types)

    # Defaults
    report.has_default_no_match = policy.defaults.no_match in ("require_human", "deny")
    report.has_default_low_confidence = policy.defaults.low_confidence in ("require_human", "deny")

    # Compute gaps
    _compute_gaps(report)

    # Compute score
    report.coverage_score = _compute_score(report)

    return report


def _collect_criteria(
    match: object,
    covered_types: set[str],
    covered_conf: set[str],
) -> None:
    """Extract prompt types and confidence levels from a match criteria block."""
    prompt_type = getattr(match, "prompt_type", None)
    min_confidence = getattr(match, "min_confidence", None)
    max_confidence = getattr(match, "max_confidence", None)

    if prompt_type:
        for pt in prompt_type:
            if pt == PromptTypeFilter.ANY:
                covered_types.update(KNOWN_PROMPT_TYPES)
            else:
                covered_types.add(pt.value if hasattr(pt, "value") else str(pt))

    # Determine which confidence levels this rule covers
    if min_confidence is not None:
        min_val = min_confidence
        max_val = max_confidence if max_confidence is not None else ConfidenceLevel.HIGH
        order = [ConfidenceLevel.LOW, ConfidenceLevel.MED, ConfidenceLevel.HIGH]
        for level in order:
            if level >= min_val and level <= max_val:
                covered_conf.add(level.value)


def _analyze_v1_rule(
    rule: object,
    covered_types: set[str],
    covered_conf: set[str],
    has_wildcard_set: set[str] | None,
) -> None:
    """Analyze a v1 rule's match criteria (handles any_of)."""
    # Already handled in the caller — this is a placeholder for future extension
    pass


def _compute_gaps(report: PolicyCoverage) -> None:
    """Identify gaps and add them to the report."""
    # No rules at all
    if report.total_rules == 0:
        report.gaps.append(
            CoverageGap(
                category="rules",
                item="empty_policy",
                severity="critical",
                description="Policy has no rules — all prompts will use defaults",
            )
        )

    # Uncovered prompt types
    for pt in report.uncovered_prompt_types:
        report.gaps.append(
            CoverageGap(
                category="prompt_type",
                item=pt,
                severity="medium",
                description=f"No rule covers prompt type '{pt}'",
            )
        )

    # Low confidence not explicitly handled
    if "low" not in report.covered_confidence_levels and not report.has_wildcard_rule:
        report.gaps.append(
            CoverageGap(
                category="confidence",
                item="low",
                severity="medium",
                description="No rule explicitly handles low-confidence prompts "
                "(defaults.low_confidence will apply)",
            )
        )

    # No deny rules (may be intentional, but worth flagging)
    if "deny" not in report.action_types_used:
        report.gaps.append(
            CoverageGap(
                category="action",
                item="deny",
                severity="low",
                description="No deny rules — consider adding rules for destructive prompts",
            )
        )


def _compute_score(report: PolicyCoverage) -> int:
    """
    Compute a coverage score from 0-100.

    Scoring:
    - Prompt type coverage:   40 points (10 per type)
    - Confidence coverage:    30 points (10 per level)
    - Has default no_match:   10 points
    - Has default low_conf:   10 points
    - Has at least 1 rule:    10 points
    """
    score = 0

    # Prompt types: 40 points total
    n_types = len(KNOWN_PROMPT_TYPES)
    n_covered = len(report.covered_prompt_types)
    score += int(40 * n_covered / n_types) if n_types > 0 else 40

    # Confidence: 30 points total
    n_conf = len(KNOWN_CONFIDENCE_LEVELS)
    n_conf_covered = len(report.covered_confidence_levels)
    score += int(30 * n_conf_covered / n_conf) if n_conf > 0 else 30

    # Defaults
    if report.has_default_no_match:
        score += 10
    if report.has_default_low_confidence:
        score += 10

    # At least one rule
    if report.total_rules > 0:
        score += 10

    return min(score, 100)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_coverage(report: PolicyCoverage) -> str:
    """Format a PolicyCoverage report as human-readable text for CLI output."""
    lines: list[str] = []

    # Score header
    label = _score_label(report.coverage_score)
    lines.append(f"Coverage Score: {report.coverage_score}/100 ({label})")
    lines.append("")

    # Summary
    lines.append(f"Total rules: {report.total_rules}")
    if report.has_wildcard_rule:
        lines.append("Wildcard rule: yes (matches all prompt types)")
    lines.append("")

    # Prompt type table
    lines.append("Prompt Type Coverage:")
    for pt in KNOWN_PROMPT_TYPES:
        status = "covered" if pt in report.covered_prompt_types else "MISSING"
        marker = "  [+]" if pt in report.covered_prompt_types else "  [-]"
        lines.append(f"{marker} {pt:25s} {status}")
    lines.append("")

    # Confidence level table
    lines.append("Confidence Level Coverage:")
    for cl in KNOWN_CONFIDENCE_LEVELS:
        status = "covered" if cl in report.covered_confidence_levels else "MISSING"
        marker = "  [+]" if cl in report.covered_confidence_levels else "  [-]"
        lines.append(f"{marker} {cl:25s} {status}")
    lines.append("")

    # Action types
    lines.append(f"Action types used: {', '.join(report.action_types_used) or '(none)'}")
    lines.append(f"Default no-match: {report.has_default_no_match}")
    lines.append(f"Default low-confidence: {report.has_default_low_confidence}")
    lines.append("")

    # Gaps
    if report.gaps:
        lines.append(f"Gaps ({len(report.gaps)}):")
        for gap in report.gaps:
            sev = gap.severity.upper()
            lines.append(f"  [{sev}] {gap.description}")
    else:
        lines.append("No gaps identified — full coverage.")

    return "\n".join(lines)


def _score_label(score: int) -> str:
    """Map coverage score to a qualitative label."""
    if score >= 90:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    if score >= 30:
        return "Poor"
    return "Critical"
