#!/usr/bin/env python3
"""Sprint rotation and auto-chain for AtlasBridge project automation.

Sprint model:
  - Sprint names: S1, S2, S3, ... (text field)
  - Current sprint: highest SN with at least one non-Done item
  - Auto-chain: when all items in SN are Done, populate S(N+1) from Backlog

Usage:
    python scripts/automation/sprint_rotate.py --check
    python scripts/automation/sprint_rotate.py --rotate
    python scripts/automation/sprint_rotate.py --rotate --dry-run
    python scripts/automation/sprint_rotate.py --check --trigger-if-complete
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from project_fields import (
    SPRINT_FIELD_ID,
    STATUS,
    GraphQLError,
    get_project_items,
    set_single_select_field,
    set_text_field,
)

# Priority sort order (P0 first)
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, None: 99}


def parse_sprint_number(sprint: str | None) -> int | None:
    """Extract the numeric part from a sprint name like 'S3'."""
    if not sprint:
        return None
    match = re.match(r"^S(\d+)$", sprint.strip(), re.IGNORECASE)
    return int(match.group(1)) if match else None


def find_current_sprint(items: list[dict]) -> tuple[str | None, int | None]:
    """Find the current sprint: highest SN with at least one non-Done item.

    Returns (sprint_name, sprint_number) or (None, None) if no active sprint.
    """
    sprints: dict[int, list[dict]] = defaultdict(list)

    for item in items:
        num = parse_sprint_number(item.get("sprint"))
        if num is not None:
            sprints[num].append(item)

    if not sprints:
        return None, None

    # Find highest sprint with at least one non-Done item
    for sprint_num in sorted(sprints.keys(), reverse=True):
        sprint_items = sprints[sprint_num]
        if any(it.get("status") != "Done" for it in sprint_items):
            return f"S{sprint_num}", sprint_num

    # All sprints complete — return the highest one as "just completed"
    highest = max(sprints.keys())
    return f"S{highest}", highest


def is_sprint_complete(items: list[dict], sprint_name: str) -> bool:
    """Check if all items in a sprint are Done."""
    sprint_items = [it for it in items if it.get("sprint") == sprint_name]
    if not sprint_items:
        return False
    return all(it.get("status") == "Done" for it in sprint_items)


def get_backlog_candidates(items: list[dict]) -> list[dict]:
    """Get Backlog items with no sprint assigned, ordered by priority."""
    candidates = [it for it in items if it.get("status") == "Backlog" and not it.get("sprint")]
    candidates.sort(key=lambda it: PRIORITY_ORDER.get(it.get("priority"), 99))
    return candidates


def check_sprint_status(items: list[dict]) -> dict:
    """Report on current sprint status."""
    current_name, current_num = find_current_sprint(items)

    if current_name is None:
        return {
            "current_sprint": None,
            "status": "no_active_sprint",
            "items_total": 0,
            "items_done": 0,
            "is_complete": False,
            "backlog_count": len(get_backlog_candidates(items)),
        }

    sprint_items = [it for it in items if it.get("sprint") == current_name]
    done_items = [it for it in sprint_items if it.get("status") == "Done"]
    complete = len(sprint_items) > 0 and len(done_items) == len(sprint_items)

    return {
        "current_sprint": current_name,
        "sprint_number": current_num,
        "status": "complete" if complete else "in_progress",
        "items_total": len(sprint_items),
        "items_done": len(done_items),
        "is_complete": complete,
        "backlog_count": len(get_backlog_candidates(items)),
    }


def rotate_sprint(
    items: list[dict],
    *,
    max_items: int = 8,
    dry_run: bool = False,
) -> dict:
    """Execute sprint rotation: if current sprint is complete, populate next.

    Returns a summary dict.
    """
    status = check_sprint_status(items)

    if not status["is_complete"]:
        print(f"Sprint {status['current_sprint'] or '(none)'} is not complete.")
        print(f"  {status['items_done']}/{status['items_total']} items done.")
        return {"action": "none", "reason": "sprint_not_complete", **status}

    current_num = status.get("sprint_number", 0) or 0
    next_sprint = f"S{current_num + 1}"

    print(f"Sprint {status['current_sprint']} is COMPLETE!")
    print(f"Rotating to {next_sprint}...")

    candidates = get_backlog_candidates(items)
    selected = candidates[:max_items]

    if not selected:
        print(f"No backlog items to pull into {next_sprint}.")
        return {
            "action": "complete_no_backlog",
            "next_sprint": next_sprint,
            "selected_count": 0,
            **status,
        }

    print(f"Pulling {len(selected)} items into {next_sprint}:")
    for item in selected:
        title = item.get("title", "(untitled)")[:60]
        prio = item.get("priority", "?")
        print(f"  [{prio}] {title}")

        try:
            # Set Sprint = next_sprint
            set_text_field(item["id"], SPRINT_FIELD_ID, next_sprint, dry_run=dry_run)

            # Set Status = Planned
            set_single_select_field(item["id"], STATUS, "Planned", dry_run=dry_run)
        except GraphQLError as exc:
            print(f"  ERROR: failed to update item: {exc}", file=sys.stderr)
            sys.exit(1)

    return {
        "action": "rotated",
        "completed_sprint": status["current_sprint"],
        "next_sprint": next_sprint,
        "selected_count": len(selected),
        "selected_titles": [it.get("title", "") for it in selected],
    }


def trigger_rotation_workflow() -> None:
    """Trigger the sprint-rotation workflow via workflow_dispatch."""
    result = subprocess.run(
        [
            "gh",
            "workflow",
            "run",
            "sprint-rotation.yml",
            "-f",
            "dry_run=false",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        print("Triggered sprint-rotation workflow.")
    else:
        print(f"Failed to trigger workflow: {result.stderr}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Sprint rotation and auto-chain.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Report sprint status")
    group.add_argument("--rotate", action="store_true", help="Execute sprint rotation")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument(
        "--max-items",
        type=int,
        default=8,
        help="Max items to pull into next sprint (default: 8)",
    )
    parser.add_argument(
        "--trigger-if-complete",
        action="store_true",
        help="If sprint is complete, trigger the rotation workflow",
    )
    args = parser.parse_args()

    print("Fetching project items...")
    items = get_project_items()
    print(f"Found {len(items)} items.")

    if args.check:
        status = check_sprint_status(items)
        print("\nSprint Status:")
        print(f"  Current: {status['current_sprint'] or '(none)'}")
        print(f"  Status:  {status['status']}")
        print(f"  Items:   {status['items_done']}/{status['items_total']} done")
        print(f"  Backlog: {status['backlog_count']} items available")

        if args.trigger_if_complete and status["is_complete"]:
            print("\nSprint complete! Triggering rotation workflow...")
            trigger_rotation_workflow()

    elif args.rotate:
        result = rotate_sprint(items, max_items=args.max_items, dry_run=args.dry_run)
        if result["action"] == "rotated":
            print(f"\nRotation complete: {result['completed_sprint']} -> {result['next_sprint']}")
            print(f"Pulled {result['selected_count']} items.")
        elif result["action"] == "complete_no_backlog":
            print("\nSprint complete but no backlog items to pull.")
        else:
            print("\nNo rotation needed.")


if __name__ == "__main__":
    main()
