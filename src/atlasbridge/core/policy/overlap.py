"""
Policy overlap detector — identify rules with overlapping match criteria.

When multiple rules can match the same input, the first-match-wins semantics
mean that later rules are shadowed. This module detects such overlaps and
produces warnings for policy authors.

Usage::

    warnings = detect_overlaps(policy)
    for w in warnings:
        print(w)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from atlasbridge.core.policy.model import (
    ConfidenceLevel,
    Policy,
    PromptTypeFilter,
)

if TYPE_CHECKING:
    from atlasbridge.core.policy.model_v1 import PolicyV1


@dataclass
class OverlapWarning:
    """Warning about two rules with overlapping match criteria."""

    rule_a_id: str
    rule_b_id: str
    overlap_reason: str

    def __str__(self) -> str:
        return f"Rules {self.rule_a_id!r} and {self.rule_b_id!r} may overlap: {self.overlap_reason}"


def detect_overlaps(policy: Policy | PolicyV1) -> list[OverlapWarning]:
    """
    Detect pairs of rules with overlapping match criteria.

    Checks for prompt_type + confidence level overlap. Returns a list of
    warnings; empty list means no overlaps detected.

    Only considers flat (non-any_of) criteria for overlap detection.
    """
    warnings: list[OverlapWarning] = []
    rules = policy.rules

    for i in range(len(rules)):
        for j in range(i + 1, len(rules)):
            rule_a = rules[i]
            rule_b = rules[j]

            match_a = rule_a.match
            match_b = rule_b.match

            # Skip v1 any_of rules — too complex for static overlap analysis
            if hasattr(match_a, "any_of") and match_a.any_of is not None:
                continue
            if hasattr(match_b, "any_of") and match_b.any_of is not None:
                continue

            overlap = _check_criteria_overlap(match_a, match_b)
            if overlap:
                warnings.append(
                    OverlapWarning(
                        rule_a_id=rule_a.id,
                        rule_b_id=rule_b.id,
                        overlap_reason=overlap,
                    )
                )

    return warnings


def _check_criteria_overlap(match_a: object, match_b: object) -> str | None:
    """
    Check if two match criteria blocks overlap.

    Returns a description of the overlap, or None if no overlap.
    """
    # Extract prompt_type lists
    pt_a = getattr(match_a, "prompt_type", None)
    pt_b = getattr(match_b, "prompt_type", None)

    # Check tool_id overlap
    tool_a = getattr(match_a, "tool_id", "*")
    tool_b = getattr(match_b, "tool_id", "*")
    if tool_a != "*" and tool_b != "*" and tool_a != tool_b:
        return None  # Different tools — no overlap

    # Check prompt_type overlap
    if not _prompt_types_overlap(pt_a, pt_b):
        return None

    # Check confidence overlap
    min_a = getattr(match_a, "min_confidence", ConfidenceLevel.LOW)
    min_b = getattr(match_b, "min_confidence", ConfidenceLevel.LOW)
    max_a = getattr(match_a, "max_confidence", None) or ConfidenceLevel.HIGH
    max_b = getattr(match_b, "max_confidence", None) or ConfidenceLevel.HIGH

    if not _confidence_ranges_overlap(min_a, max_a, min_b, max_b):
        return None

    # Check repo overlap
    repo_a = getattr(match_a, "repo", None)
    repo_b = getattr(match_b, "repo", None)
    if repo_a is not None and repo_b is not None:
        if not repo_a.startswith(repo_b) and not repo_b.startswith(repo_a):
            return None  # Non-overlapping repo prefixes

    # Build overlap description
    parts = []
    parts.append(_describe_type_overlap(pt_a, pt_b))
    parts.append(_describe_conf_overlap(min_a, max_a, min_b, max_b))
    return "; ".join(p for p in parts if p)


def _prompt_types_overlap(
    pt_a: list[PromptTypeFilter] | None,
    pt_b: list[PromptTypeFilter] | None,
) -> bool:
    """Check if two prompt_type filter lists overlap."""
    # None means "match any"
    if pt_a is None or pt_b is None:
        return True
    if PromptTypeFilter.ANY in pt_a or PromptTypeFilter.ANY in pt_b:
        return True
    set_a = {f.value for f in pt_a}
    set_b = {f.value for f in pt_b}
    return bool(set_a & set_b)


def _confidence_ranges_overlap(
    min_a: ConfidenceLevel,
    max_a: ConfidenceLevel,
    min_b: ConfidenceLevel,
    max_b: ConfidenceLevel,
) -> bool:
    """Check if two confidence ranges [min, max] overlap."""
    return min_a <= max_b and min_b <= max_a


def _describe_type_overlap(
    pt_a: list[PromptTypeFilter] | None,
    pt_b: list[PromptTypeFilter] | None,
) -> str:
    if pt_a is None and pt_b is None:
        return "both match any prompt type"
    if pt_a is None or (pt_a and PromptTypeFilter.ANY in pt_a):
        return "first rule matches any prompt type"
    if pt_b is None or (pt_b and PromptTypeFilter.ANY in pt_b):
        return "second rule matches any prompt type"
    set_a = {f.value for f in pt_a}
    set_b = {f.value for f in pt_b}
    common = sorted(set_a & set_b)
    return f"shared prompt types: {common}"


def _describe_conf_overlap(
    min_a: ConfidenceLevel,
    max_a: ConfidenceLevel,
    min_b: ConfidenceLevel,
    max_b: ConfidenceLevel,
) -> str:
    return f"confidence ranges overlap: [{min_a.value}..{max_a.value}] and [{min_b.value}..{max_b.value}]"
