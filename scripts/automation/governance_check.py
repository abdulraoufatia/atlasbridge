#!/usr/bin/env python3
"""PR governance gate validation for AtlasBridge project automation.

Validates that pull requests comply with the governance gates defined in
.github/PULL_REQUEST_TEMPLATE.md:
  1. At least one "Type of Change" checkbox is checked
  2. If PR touches core/, os/, channels/, or adapters/ — governance gates
     section must have at least one checkbox checked

Usage:
    python scripts/automation/governance_check.py --pr-number 51
    python scripts/automation/governance_check.py --pr-number 51 --strict
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# Paths that require governance gate acknowledgment
GOVERNED_PATHS = (
    "src/atlasbridge/core/",
    "src/atlasbridge/os/",
    "src/atlasbridge/channels/",
    "src/atlasbridge/adapters/",
)


def fetch_pr(pr_number: int | str) -> dict:
    """Fetch PR body and changed files via `gh pr view`."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "body,files,title",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Failed to fetch PR #{pr_number}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def extract_checked_boxes(text: str, section_header: str) -> tuple[int, int]:
    """Count checked and total checkboxes under a section header.

    Returns (checked_count, total_count).
    """
    # Find the section
    pattern = rf"##\s*{re.escape(section_header)}.*?(?=\n##|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return 0, 0

    section_text = match.group(0)
    total = len(re.findall(r"- \[[ xX]\]", section_text))
    checked = len(re.findall(r"- \[[xX]\]", section_text))
    return checked, total


def touches_governed_paths(files: list[dict]) -> list[str]:
    """Return list of changed files that fall under governed paths."""
    governed = []
    for f in files:
        path = f.get("path", "")
        if any(path.startswith(gp) for gp in GOVERNED_PATHS):
            governed.append(path)
    return governed


def check_governance(pr_number: int | str, *, strict: bool = False) -> bool:
    """Validate PR against governance gates. Returns True if valid."""
    pr = fetch_pr(pr_number)
    body = pr.get("body", "") or ""
    files = pr.get("files", [])
    title = pr.get("title", "")
    passed = True

    print(f"Governance check for PR #{pr_number}: {title}")
    print(f"Changed files: {len(files)}")

    # Check 1: Type of Change
    type_checked, type_total = extract_checked_boxes(body, "Type of Change")
    if type_total == 0:
        print("  WARN: No 'Type of Change' section found in PR body")
        if strict:
            passed = False
    elif type_checked == 0:
        print("  FAIL: No 'Type of Change' checkbox is checked")
        passed = False
    else:
        print(f"  PASS: Type of Change — {type_checked}/{type_total} checked")

    # Check 2: Governance Gates (if governed paths are touched)
    governed_files = touches_governed_paths(files)
    if governed_files:
        print(f"  INFO: PR touches {len(governed_files)} governed files:")
        for gf in governed_files[:5]:
            print(f"    - {gf}")
        if len(governed_files) > 5:
            print(f"    ... and {len(governed_files) - 5} more")

        gov_checked, gov_total = extract_checked_boxes(body, "Governance Gates")
        if gov_total == 0:
            print("  FAIL: No 'Governance Gates' section found but governed paths changed")
            passed = False
        elif gov_checked == 0:
            print("  FAIL: No 'Governance Gates' checkbox is checked")
            passed = False
        else:
            print(f"  PASS: Governance Gates — {gov_checked}/{gov_total} checked")
    else:
        print("  SKIP: No governed paths touched — governance gates not required")

    # Check 3: Testing section (advisory)
    test_checked, test_total = extract_checked_boxes(body, "Testing")
    if test_total > 0 and test_checked == 0:
        print("  WARN: No 'Testing' checkboxes checked")
    elif test_total > 0:
        print(f"  INFO: Testing — {test_checked}/{test_total} checked")

    # Summary
    if passed:
        print("\nResult: PASSED")
    else:
        print("\nResult: FAILED")
        sys.exit(1)

    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate PR governance gates.")
    parser.add_argument("--pr-number", required=True, help="Pull request number")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on missing sections (not just unchecked boxes)",
    )
    args = parser.parse_args()

    check_governance(args.pr_number, strict=args.strict)


if __name__ == "__main__":
    main()
