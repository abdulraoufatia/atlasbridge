"""Shared constants and GraphQL helpers for AtlasBridge project automation.

All field IDs and option IDs come from the GitHub Projects v2 GraphQL API
for the "AtlasBridge — Master Roadmap" project (number 17).

Usage:
    from project_fields import (
        PROJECT_ID, STATUS, PHASE, PRIORITY, EDITION,
        graphql_query, graphql_mutation, add_item_to_project, set_field_value,
    )
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Project identity
# ---------------------------------------------------------------------------

PROJECT_ID = "PVT_kwHOBHKkbc4BP12z"

# ---------------------------------------------------------------------------
# Field IDs
# ---------------------------------------------------------------------------

STATUS_FIELD_ID = "PVTSSF_lAHOBHKkbc4BP12zzg-Ii4A"
PHASE_FIELD_ID = "PVTSSF_lAHOBHKkbc4BP12zzg-IjQk"
PRIORITY_FIELD_ID = "PVTSSF_lAHOBHKkbc4BP12zzg-IjgY"
CATEGORY_FIELD_ID = "PVTSSF_lAHOBHKkbc4BP12zzg-Ijhs"
RISK_LEVEL_FIELD_ID = "PVTSSF_lAHOBHKkbc4BP12zzg-Ijm0"
EFFORT_FIELD_ID = "PVTSSF_lAHOBHKkbc4BP12zzg-IjrU"
IMPACT_FIELD_ID = "PVTSSF_lAHOBHKkbc4BP12zzg-Ijto"
SPRINT_FIELD_ID = "PVTF_lAHOBHKkbc4BP12zzg-IjpY"
BLOCKED_BY_FIELD_ID = "PVTF_lAHOBHKkbc4BP12zzg-IjvA"
TARGET_DATE_FIELD_ID = "PVTF_lAHOBHKkbc4BP12zzg-MsT4"
EDITION_FIELD_ID = "PVTSSF_lAHOBHKkbc4BP12zzg-MsV4"


# ---------------------------------------------------------------------------
# Option ID lookups  (single-select fields)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldOptions:
    """Maps human-readable option names to their GitHub option IDs."""

    field_id: str
    options: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.options[key]

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.options.get(key, default)


STATUS = FieldOptions(
    field_id=STATUS_FIELD_ID,
    options={
        "Backlog": "8967f04f",
        "Planned": "7d0ac164",
        "In Progress": "18c0a3c8",
        "Blocked": "f3c5bb13",
        "Done": "7a15a729",
    },
)

PHASE = FieldOptions(
    field_id=PHASE_FIELD_ID,
    options={
        "A": "59450c8c",
        "B": "da43e009",
        "C": "2aae8075",
        "D": "c73593c0",
        "E": "8cfab998",
        "F": "04c26123",
        "G": "ce46bb70",
        "H": "d8741409",
    },
)

PRIORITY = FieldOptions(
    field_id=PRIORITY_FIELD_ID,
    options={
        "P0": "6f5b2bda",
        "P1": "da71189a",
        "P2": "b8549d9d",
        "P3": "291c5078",
    },
)

CATEGORY = FieldOptions(
    field_id=CATEGORY_FIELD_ID,
    options={
        "Core": "539bc0d6",
        "Hardening": "f2b4611e",
        "Security": "dedef3a5",
        "Governance": "143404df",
        "UX": "4aab1fa0",
        "SaaS": "d9836495",
        "Docs": "6f912729",
    },
)

RISK_LEVEL = FieldOptions(
    field_id=RISK_LEVEL_FIELD_ID,
    options={
        "Low": "c9903d13",
        "Medium": "c8f63fc9",
        "High": "b7677831",
        "Critical": "47cc58df",
    },
)

EFFORT = FieldOptions(
    field_id=EFFORT_FIELD_ID,
    options={
        "XS": "d6668cba",
        "S": "700963a8",
        "M": "83f5274d",
        "L": "106e9496",
        "XL": "6f6d240e",
    },
)

IMPACT = FieldOptions(
    field_id=IMPACT_FIELD_ID,
    options={
        "Stability": "db6379c7",
        "UX": "1bca2126",
        "Governance": "5038bbba",
        "Revenue Path": "3403edf6",
        "Risk Reduction": "6f53b253",
    },
)

EDITION = FieldOptions(
    field_id=EDITION_FIELD_ID,
    options={
        "Community": "ea9177c5",
        "Pro": "9edb2417",
        "Enterprise": "c2cd6c57",
    },
)


# ---------------------------------------------------------------------------
# Secret redaction (reuses patterns from src/atlasbridge/cli/_debug.py)
# ---------------------------------------------------------------------------

_TOKEN_PATTERNS = [
    re.compile(r"\d{8,12}:[A-Za-z0-9_-]{35,}"),  # Telegram bot tokens
    re.compile(r"xoxb-[A-Za-z0-9-]+"),  # Slack bot tokens
    re.compile(r"xapp-[A-Za-z0-9-]+"),  # Slack app tokens
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # API keys
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),  # GitHub PATs
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),  # Fine-grained PATs
]


def redact_for_logging(text: str) -> str:
    """Replace known secret patterns with <REDACTED>."""
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub("<REDACTED>", text)
    return text


# ---------------------------------------------------------------------------
# GraphQL helpers
# ---------------------------------------------------------------------------

_RATE_LIMIT_DELAY = 1.0  # seconds between mutations


def graphql_query(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a read-only GraphQL query via `gh api graphql`."""
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if variables:
        for key, value in variables.items():
            cmd.extend(["-f", f"{key}={value}"])

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = redact_for_logging(result.stderr)
        print(f"GraphQL query failed: {stderr}", file=sys.stderr)
        sys.exit(1)

    return json.loads(result.stdout)


def graphql_mutation(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Execute a GraphQL mutation via `gh api graphql`.

    With dry_run=True, prints the mutation but does not execute.
    Rate-limits to 1 mutation per second.
    """
    if dry_run:
        safe_query = redact_for_logging(query)
        safe_vars = redact_for_logging(json.dumps(variables or {}))
        print("[DRY RUN] Would execute mutation:")
        print(f"  Query: {safe_query[:200]}...")
        print(f"  Variables: {safe_vars}")
        return None

    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if variables:
        for key, value in variables.items():
            cmd.extend(["-f", f"{key}={value}"])

    time.sleep(_RATE_LIMIT_DELAY)

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = redact_for_logging(result.stderr)
        print(f"GraphQL mutation failed: {stderr}", file=sys.stderr)
        sys.exit(1)

    return json.loads(result.stdout)


def get_issue_node_id(issue_number: int | str) -> str:
    """Get the global node ID for a repo issue."""
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "id", "-q", ".id"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print(f"Failed to get node ID for issue #{issue_number}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def add_item_to_project(content_id: str, *, dry_run: bool = False) -> str | None:
    """Add an issue/PR to the project. Returns the project item ID."""
    query = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item { id }
      }
    }
    """
    result = graphql_mutation(
        query,
        {"projectId": PROJECT_ID, "contentId": content_id},
        dry_run=dry_run,
    )
    if result is None:
        return None
    return result["data"]["addProjectV2ItemById"]["item"]["id"]


def set_single_select_field(
    item_id: str,
    field: FieldOptions,
    option_name: str,
    *,
    dry_run: bool = False,
) -> None:
    """Set a single-select field on a project item."""
    option_id = field[option_name]
    query = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId
        itemId: $itemId
        fieldId: $fieldId
        value: {singleSelectOptionId: $optionId}
      }) {
        projectV2Item { id }
      }
    }
    """
    graphql_mutation(
        query,
        {
            "projectId": PROJECT_ID,
            "itemId": item_id,
            "fieldId": field.field_id,
            "optionId": option_id,
        },
        dry_run=dry_run,
    )
    print(f"  Set {field.field_id[-4:]}... = {option_name}")


def set_text_field(
    item_id: str,
    field_id: str,
    value: str,
    *,
    dry_run: bool = False,
) -> None:
    """Set a text field on a project item."""
    query = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId
        itemId: $itemId
        fieldId: $fieldId
        value: {text: $value}
      }) {
        projectV2Item { id }
      }
    }
    """
    graphql_mutation(
        query,
        {
            "projectId": PROJECT_ID,
            "itemId": item_id,
            "fieldId": field_id,
            "value": value,
        },
        dry_run=dry_run,
    )
    print(f"  Set text field {field_id[-4:]}... = {value}")


def get_project_items() -> list[dict[str, Any]]:
    """Fetch all items from the project with their field values.

    Returns a list of dicts with keys: id, title, status, sprint, priority,
    content_type, content_number.
    """
    items: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        after_clause = f', after: "{cursor}"' if cursor else ""
        query = f"""
        {{
          node(id: "{PROJECT_ID}") {{
            ... on ProjectV2 {{
              items(first: 100{after_clause}) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                  id
                  content {{
                    ... on Issue {{
                      title
                      number
                      __typename
                    }}
                    ... on PullRequest {{
                      title
                      number
                      __typename
                    }}
                  }}
                  fieldValues(first: 20) {{
                    nodes {{
                      ... on ProjectV2ItemFieldSingleSelectValue {{
                        field {{ ... on ProjectV2SingleSelectField {{ id }} }}
                        name
                        optionId
                      }}
                      ... on ProjectV2ItemFieldTextValue {{
                        field {{ ... on ProjectV2Field {{ id }} }}
                        text
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        data = graphql_query(query)
        project_items = data["data"]["node"]["items"]

        for node in project_items["nodes"]:
            content = node.get("content") or {}
            item: dict[str, Any] = {
                "id": node["id"],
                "title": content.get("title", ""),
                "content_type": content.get("__typename", ""),
                "content_number": content.get("number"),
                "status": None,
                "sprint": None,
                "priority": None,
            }

            for fv in node.get("fieldValues", {}).get("nodes", []):
                field_info = fv.get("field", {})
                field_id = field_info.get("id", "")

                if field_id == STATUS_FIELD_ID:
                    item["status"] = fv.get("name")
                elif field_id == SPRINT_FIELD_ID:
                    item["sprint"] = fv.get("text")
                elif field_id == PRIORITY_FIELD_ID:
                    item["priority"] = fv.get("name")

            items.append(item)

        if project_items["pageInfo"]["hasNextPage"]:
            cursor = project_items["pageInfo"]["endCursor"]
        else:
            break

    return items
