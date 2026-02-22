#!/usr/bin/env python3
"""Deterministic issue classification for AtlasBridge project automation.

Uses first-match-wins rules (mirrors the Policy DSL evaluator pattern) to
classify issues by Phase, Priority, Category, Risk Level, and Status.

Usage:
    python scripts/automation/triage.py --issue-number 60 --dry-run
    python scripts/automation/triage.py --issue-number 60
    python scripts/automation/triage.py --issue-number 60 --set-status "In Progress"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

# Sibling import — scripts/automation/ is not a package install,
# so we adjust sys.path for direct execution.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from project_fields import (
    CATEGORY,
    PHASE,
    PRIORITY,
    RISK_LEVEL,
    STATUS,
    add_item_to_project,
    get_issue_node_id,
    set_single_select_field,
)

# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------


@dataclass
class Classification:
    """Accumulated field assignments from rule evaluation."""

    status: str | None = None
    phase: str | None = None
    priority: str | None = None
    category: str | None = None
    risk_level: str | None = None
    matched_rules: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Classification rules — first-match-wins per field
# ---------------------------------------------------------------------------


def classify(title: str, labels: list[str]) -> Classification:
    """Apply deterministic, first-match-wins rules to classify an issue.

    Each field is assigned independently. The first rule that matches for a
    given field wins; subsequent rules for that field are skipped.
    """
    c = Classification()
    title_lower = title.lower()
    label_set = {lb.lower() for lb in labels}

    # --- Phase (from labels first, then title) ---
    for phase_key in ("a", "b", "c", "d", "e", "f", "g"):
        if f"phase:{phase_key}" in label_set and c.phase is None:
            c.phase = phase_key.upper()
            c.matched_rules.append(f"label:phase:{phase_key} -> Phase {c.phase}")

    if c.phase is None:
        phase_title_rules: list[tuple[list[str], str]] = [
            (["conpty", "windows"], "E"),
            (["websocket", "heartbeat", "cloud sync", "audit stream"], "F"),
            (["dashboard", "sso", "governance api", "saml", "oauth"], "G"),
            (["adapter", "pty", "detector", "prompt detection"], "E"),
            (["policy", "dsl", "autopilot"], "E"),
        ]
        for keywords, phase in phase_title_rules:
            if any(kw in title_lower for kw in keywords) and c.phase is None:
                c.phase = phase
                c.matched_rules.append(f"title contains {keywords} -> Phase {phase}")

    # --- Priority (from labels first, then title) ---
    for prio in ("p0", "p1", "p2", "p3"):
        if f"priority:{prio}" in label_set and c.priority is None:
            c.priority = prio.upper()
            c.matched_rules.append(f"label:priority:{prio} -> Priority {c.priority}")

    if c.priority is None:
        if any(kw in title_lower for kw in ("security", "secret", "cve", "vulnerability")):
            c.priority = "P1"
            c.matched_rules.append("title contains security keyword -> Priority P1")
        elif any(kw in title_lower for kw in ("crash", "data loss", "corruption")):
            c.priority = "P0"
            c.matched_rules.append("title contains critical keyword -> Priority P0")

    # --- Category (from labels first, then title) ---
    for cat_label, cat_value in [
        ("category:core", "Core"),
        ("category:hardening", "Hardening"),
        ("category:security", "Security"),
        ("category:governance", "Governance"),
        ("category:ux", "UX"),
        ("category:saas", "SaaS"),
        ("category:docs", "Docs"),
    ]:
        if cat_label in label_set and c.category is None:
            c.category = cat_value
            c.matched_rules.append(f"label:{cat_label} -> Category {cat_value}")

    if c.category is None:
        category_title_rules: list[tuple[list[str], str]] = [
            (["security", "secret", "cve", "vulnerability", "scan"], "Security"),
            (["policy", "dsl", "governance", "audit"], "Governance"),
            (["adapter", "pty", "detector", "prompt", "session", "daemon"], "Core"),
            (["docs", "readme", "guide", "changelog"], "Docs"),
            (["tui", "ux", "wizard", "dashboard", "ui"], "UX"),
            (["websocket", "heartbeat", "cloud", "saas"], "SaaS"),
            (["test", "coverage", "ci", "lint", "mypy"], "Hardening"),
        ]
        for keywords, cat in category_title_rules:
            if any(kw in title_lower for kw in keywords) and c.category is None:
                c.category = cat
                c.matched_rules.append(f"title contains {keywords} -> Category {cat}")

    # --- Risk Level (from title keywords) ---
    if any(kw in title_lower for kw in ("security", "secret", "cve", "auth")):
        c.risk_level = "High"
        c.matched_rules.append("title contains security keyword -> Risk High")
    elif any(kw in title_lower for kw in ("refactor", "migration", "breaking")):
        c.risk_level = "Medium"
        c.matched_rules.append("title contains refactor keyword -> Risk Medium")

    # --- Defaults for unset fields ---
    if c.status is None:
        c.status = "Backlog"
    if c.priority is None:
        c.priority = "P2"
        c.matched_rules.append("default -> Priority P2")
    if c.risk_level is None:
        c.risk_level = "Low"
        c.matched_rules.append("default -> Risk Low")

    return c


# ---------------------------------------------------------------------------
# Issue fetching
# ---------------------------------------------------------------------------


def fetch_issue(issue_number: int | str) -> dict[str, Any]:
    """Fetch issue title and labels via `gh issue view`."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--json",
            "title,labels,id",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Failed to fetch issue #{issue_number}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Apply classification to project
# ---------------------------------------------------------------------------


def apply_classification(
    issue_number: int | str,
    classification: Classification,
    *,
    dry_run: bool = False,
    status_override: str | None = None,
) -> None:
    """Add issue to project and set all classified fields."""
    node_id = get_issue_node_id(issue_number)
    print(f"Issue #{issue_number} (node: {node_id[:12]}...)")

    # Add to project
    item_id = add_item_to_project(node_id, dry_run=dry_run)
    if dry_run:
        print("  [DRY RUN] Would add to project and set fields:")
        print(f"    Status: {status_override or classification.status}")
        print(f"    Phase: {classification.phase or '(not set)'}")
        print(f"    Priority: {classification.priority}")
        print(f"    Category: {classification.category or '(not set)'}")
        print(f"    Risk Level: {classification.risk_level}")
        print("  Matched rules:")
        for rule in classification.matched_rules:
            print(f"    - {rule}")
        return

    if item_id is None:
        print("  Failed to add item to project", file=sys.stderr)
        sys.exit(1)

    # Set Status
    effective_status = status_override or classification.status or "Backlog"
    if STATUS.get(effective_status):
        set_single_select_field(item_id, STATUS, effective_status, dry_run=dry_run)

    # Set Phase
    if classification.phase and PHASE.get(classification.phase):
        set_single_select_field(item_id, PHASE, classification.phase, dry_run=dry_run)

    # Set Priority
    if classification.priority and PRIORITY.get(classification.priority):
        set_single_select_field(item_id, PRIORITY, classification.priority, dry_run=dry_run)

    # Set Category
    if classification.category and CATEGORY.get(classification.category):
        set_single_select_field(item_id, CATEGORY, classification.category, dry_run=dry_run)

    # Set Risk Level
    if classification.risk_level and RISK_LEVEL.get(classification.risk_level):
        set_single_select_field(item_id, RISK_LEVEL, classification.risk_level, dry_run=dry_run)

    print(f"  Classification complete. {len(classification.matched_rules)} rules matched.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify an issue and set project fields.")
    parser.add_argument("--issue-number", required=True, help="GitHub issue number")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument(
        "--set-status",
        help="Override status (e.g., 'In Progress', 'Done')",
    )
    args = parser.parse_args()

    issue = fetch_issue(args.issue_number)
    title = issue["title"]
    labels = [lb["name"] for lb in issue.get("labels", [])]

    print(f"Classifying: {title}")
    print(f"Labels: {labels}")

    classification = classify(title, labels)

    print("Classification result:")
    for rule in classification.matched_rules:
        print(f"  - {rule}")

    apply_classification(
        args.issue_number,
        classification,
        dry_run=args.dry_run,
        status_override=args.set_status,
    )


if __name__ == "__main__":
    main()
