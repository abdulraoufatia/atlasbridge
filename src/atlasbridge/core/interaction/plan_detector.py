"""
Plan detection in agent output.

Detects structured plan blocks (numbered steps with action verbs) in
PTY output text.  This is a pure function — no side effects, no state.

Detection strategies:
  1. Header + numbered steps: a plan header ("Plan:", "## Plan", etc.)
     followed by ≥2 numbered steps.
  2. Headerless numbered steps: ≥3 consecutive numbered steps where
     ≥60% begin with an action verb.

Conservative: false negatives are preferred over false positives.
Numbered shell output (e.g. line counts, test results) should never
be misidentified as a plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Plan header patterns (case-insensitive)
_PLAN_HEADERS: list[re.Pattern[str]] = [
    re.compile(r"^#+\s*Plan\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Plan\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Here(?:'s| is) (?:my |the )?plan\b", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"^I(?:'ll| will) (?:follow |use )?(?:this|the following) plan\b",
        re.IGNORECASE | re.MULTILINE,
    ),
]

# Numbered step pattern: "1. Do something" or "1) Do something"
_STEP_PATTERN = re.compile(r"^\s*(\d+)[.)]\s+(.+)", re.MULTILINE)

# Action verbs that commonly start plan steps
_ACTION_VERBS: frozenset[str] = frozenset(
    {
        "add",
        "build",
        "check",
        "clean",
        "configure",
        "copy",
        "create",
        "debug",
        "define",
        "delete",
        "deploy",
        "design",
        "ensure",
        "execute",
        "extend",
        "extract",
        "fix",
        "generate",
        "identify",
        "implement",
        "import",
        "initialize",
        "install",
        "integrate",
        "investigate",
        "merge",
        "migrate",
        "modify",
        "move",
        "optimize",
        "parse",
        "read",
        "refactor",
        "remove",
        "rename",
        "replace",
        "resolve",
        "restructure",
        "review",
        "rewrite",
        "run",
        "search",
        "set",
        "setup",
        "start",
        "test",
        "update",
        "upgrade",
        "use",
        "validate",
        "verify",
        "wire",
        "wrap",
        "write",
    }
)


@dataclass(frozen=True)
class DetectedPlan:
    """A detected plan block in agent output."""

    title: str
    steps: list[str]
    raw_text: str
    start_offset: int
    end_offset: int


def detect_plan(text: str) -> DetectedPlan | None:
    """
    Detect a plan in the given text.

    Returns a DetectedPlan if a valid plan is found, None otherwise.
    """
    # Strategy 1: header + numbered steps
    for header_pat in _PLAN_HEADERS:
        match = header_pat.search(text)
        if match:
            plan = _extract_plan_after(text, match.start(), match.group().strip())
            if plan is not None:
                return plan

    # Strategy 2: headerless consecutive numbered steps with action verbs
    return _detect_headerless_plan(text)


def _extract_plan_after(
    text: str,
    header_start: int,
    title: str,
) -> DetectedPlan | None:
    """Extract a plan starting from a header position."""
    # Look for numbered steps after the header
    remaining = text[header_start:]
    steps: list[str] = []
    last_end = 0

    for m in _STEP_PATTERN.finditer(remaining):
        steps.append(m.group(2).strip())
        last_end = m.end()

    if len(steps) < 2:
        return None

    end_offset = header_start + last_end
    raw = text[header_start:end_offset]

    return DetectedPlan(
        title=title,
        steps=steps,
        raw_text=raw,
        start_offset=header_start,
        end_offset=end_offset,
    )


def _detect_headerless_plan(text: str) -> DetectedPlan | None:
    """Detect a plan from consecutive numbered steps without a header."""
    matches = list(_STEP_PATTERN.finditer(text))
    if len(matches) < 3:
        return None

    # Find longest consecutive run
    best_run: list[re.Match[str]] = []
    current_run: list[re.Match[str]] = []
    prev_num = 0

    for m in matches:
        num = int(m.group(1))
        if num == prev_num + 1:
            current_run.append(m)
        else:
            if len(current_run) > len(best_run):
                best_run = current_run
            current_run = [m]
        prev_num = num

    if len(current_run) > len(best_run):
        best_run = current_run

    if len(best_run) < 3:
        return None

    # Check action verb density (≥60%)
    steps = [m.group(2).strip() for m in best_run]
    verb_count = sum(1 for s in steps if _starts_with_action_verb(s))
    if verb_count / len(steps) < 0.6:
        return None

    start_offset = best_run[0].start()
    end_offset = best_run[-1].end()

    return DetectedPlan(
        title="Plan",
        steps=steps,
        raw_text=text[start_offset:end_offset],
        start_offset=start_offset,
        end_offset=end_offset,
    )


def _starts_with_action_verb(step: str) -> bool:
    """Check if a step starts with a recognized action verb."""
    first_word = step.split(None, 1)[0].lower().rstrip(".,;:") if step.strip() else ""
    return first_word in _ACTION_VERBS
