#!/usr/bin/env python3
"""Create 37 structured GitHub issues for AtlasBridge feature backlog.

Usage:
    python scripts/automation/create_feature_issues.py --dry-run   # preview
    python scripts/automation/create_feature_issues.py              # create all
    python scripts/automation/create_feature_issues.py --batch 1    # just epic children
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field

# Reuse project board helpers
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from project_fields import (
    CATEGORY,
    EDITION,
    EFFORT,
    PHASE,
    PRIORITY,
    RISK_LEVEL,
    STATUS,
    TARGET_DATE_FIELD_ID,
    add_item_to_project,
    get_issue_node_id,
    set_single_select_field,
)

# ---------------------------------------------------------------------------
# Prohibited terms — hard constraint
# ---------------------------------------------------------------------------

PROHIBITED = re.compile(r"\b(revenue|income|money|monetiz|pricing|price|cost)\b", re.IGNORECASE)


def check_prohibited(text: str, context: str) -> None:
    match = PROHIBITED.search(text)
    if match:
        print(f"PROHIBITED TERM '{match.group()}' found in {context}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Issue data model
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    id: str  # internal reference like A1, B2, etc.
    title: str
    body: str
    labels: list[str]
    phase: str  # E, F, G, H
    priority: str  # P0, P1, P2, P3
    category: str  # Core, Security, Governance, etc.
    effort: str  # XS, S, M, L, XL
    edition: str  # Community, Pro, Enterprise
    risk_level: str  # Low, Medium, High, Critical
    target_date: str  # e.g. "v1.0.0" or "v1.1.0"
    batch: int  # 1=epic children, 2=epics, 3-6=standalone
    epic_children: list[str] = field(default_factory=list)  # child IDs for epics
    gh_number: int | None = None  # filled after creation


# ---------------------------------------------------------------------------
# Body builder
# ---------------------------------------------------------------------------


def build_body(
    *,
    phase: str,
    priority: str,
    category: str,
    effort: str,
    edition: str,
    issue_type: str,
    market_segment: str,
    complexity: str,
    recommended_phase: str,
    problem: str,
    solution: str,
    architecture: str,
    safety: str,
    acceptance: str,
    tests: str,
    dependencies: str,
    milestone: str,
) -> str:
    return f"""**Phase:** {phase} | **Priority:** {priority} | **Category:** {category} | **Effort:** {effort}
**Edition:** {edition}

## Type
{issue_type}

## Market Segment
{market_segment}

## Engineering Complexity
{complexity}

## Recommended Phase
{recommended_phase}

## Problem Statement
{problem}

## Proposed Solution
{solution}

## Architectural Considerations
{architecture}

## Safety Considerations
{safety}

## Acceptance Criteria
{acceptance}

## Test Requirements
{tests}

## Dependencies
{dependencies}

## Milestone Suggestion
{milestone}"""


# ---------------------------------------------------------------------------
# Phase E issues (10: 3 epic children + 1 epic + 6 standalone)
# ---------------------------------------------------------------------------


def phase_e_issues() -> list[Issue]:
    issues: list[Issue] = []

    # --- A1 epic children (batch 1) ---
    issues.append(
        Issue(
            id="A1a",
            title="feat(config): Agent profile schema + storage",
            body=build_body(
                phase="E",
                priority="P1",
                category="Core",
                effort="M",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="2/5 — Pydantic schema + YAML persistence, well-understood patterns",
                recommended_phase="E — foundational for profile-aware policy evaluation",
                problem=(
                    "AtlasBridge treats all agents identically regardless of their capabilities, "
                    "risk profile, or typical interaction patterns. Users running Claude Code for "
                    "safe refactoring tasks get the same policy defaults as users running an agent "
                    "that executes shell commands. There is no way to encode agent-specific "
                    "behavior expectations."
                ),
                solution=(
                    "Define a Pydantic v2 `AgentProfile` model with fields: name, adapter, "
                    "default_autonomy, allowed_actions, risk_ceiling, and custom metadata.\n\n"
                    "```python\n"
                    "class AgentProfile(BaseModel):\n"
                    "    name: str\n"
                    "    adapter: str  # e.g. 'claude_code', 'openai_cli'\n"
                    "    default_autonomy: Literal['off', 'assist', 'full']\n"
                    "    allowed_actions: list[str]\n"
                    "    risk_ceiling: Literal['low', 'medium', 'high']\n"
                    "    tags: dict[str, str] = {}\n"
                    "```\n\n"
                    "Store profiles in `~/.config/atlasbridge/profiles/` as YAML files. "
                    "Provide `load_profile()` and `save_profile()` helpers."
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/config/profiles.py`\n"
                    "- Schema: Pydantic v2 model with YAML serialization\n"
                    "- Storage: per-profile YAML in config dir `profiles/` subdirectory\n"
                    "- No CLI changes in this issue (see A1b)\n"
                    "- Backward compatible — profiles are optional"
                ),
                safety=(
                    "- No injection impact — profiles are read-only config\n"
                    "- `risk_ceiling` constrains policy evaluation (see A1c)\n"
                    "- Audit log records which profile was active at decision time"
                ),
                acceptance=(
                    "- [ ] `AgentProfile` Pydantic model defined with validation\n"
                    "- [ ] `load_profile(name)` reads from YAML, returns model\n"
                    "- [ ] `save_profile(profile)` writes to YAML\n"
                    "- [ ] `list_profiles()` returns available profile names\n"
                    "- [ ] Default profile created on first run if none exist\n"
                    "- [ ] Unit tests cover schema validation and round-trip serialization"
                ),
                tests=(
                    "- Unit: schema validation, YAML round-trip, default profile creation\n"
                    "- Integration: profile storage in temp config dir"
                ),
                dependencies=(
                    "- Prerequisite: None\n- Blocks: A1b (CLI), A1c (policy integration)"
                ),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Core",
            effort="M",
            edition="Community",
            risk_level="Low",
            target_date="v1.0.0",
            batch=1,
        )
    )

    issues.append(
        Issue(
            id="A1b",
            title="feat(config): Profile selection CLI",
            body=build_body(
                phase="E",
                priority="P1",
                category="Core",
                effort="S",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="1/5 — thin CLI layer over existing profile module",
                recommended_phase="E — needed for profile UX before GA",
                problem=(
                    "Users need a way to create, list, select, and manage agent profiles from "
                    "the command line. Without CLI commands, profiles would require manual YAML editing."
                ),
                solution=(
                    "Add `atlasbridge profile` subcommand group:\n\n"
                    "```bash\n"
                    "atlasbridge profile list              # show all profiles\n"
                    "atlasbridge profile show <name>       # display profile details\n"
                    "atlasbridge profile create <name>     # interactive creation\n"
                    "atlasbridge profile set-default <name> # set active profile\n"
                    "atlasbridge run claude --profile safe-refactor  # override per-run\n"
                    "```"
                ),
                architecture=(
                    "- New CLI module: `src/atlasbridge/cli/_profile.py`\n"
                    "- Registers under main Click group\n"
                    "- Uses `core/config/profiles.py` from A1a\n"
                    "- `--profile` flag added to `run` command\n"
                    "- Backward compatible — no profile flag = default profile"
                ),
                safety=(
                    "- No injection impact — CLI reads/writes local config only\n"
                    "- Profile selection recorded in audit log\n"
                    "- Invalid profile names rejected with clear error"
                ),
                acceptance=(
                    "- [ ] `atlasbridge profile list` shows available profiles\n"
                    "- [ ] `atlasbridge profile show` displays profile YAML\n"
                    "- [ ] `atlasbridge profile create` creates new profile interactively\n"
                    "- [ ] `atlasbridge profile set-default` sets active profile\n"
                    "- [ ] `atlasbridge run --profile` overrides default for single run\n"
                    "- [ ] CLI smoke test updated to include profile subcommand"
                ),
                tests=(
                    "- Unit: CLI argument parsing, profile resolution logic\n"
                    "- Integration: end-to-end profile create → list → select flow"
                ),
                dependencies=(
                    "- Prerequisite: A1a (profile schema)\n- Blocks: A1c (policy integration)"
                ),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Core",
            effort="S",
            edition="Community",
            risk_level="Low",
            target_date="v1.0.0",
            batch=1,
        )
    )

    issues.append(
        Issue(
            id="A1c",
            title="feat(config): Profile-aware policy evaluation",
            body=build_body(
                phase="E",
                priority="P1",
                category="Governance",
                effort="S",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="2/5 — extends evaluator context with profile data",
                recommended_phase="E — completes the profile feature set for GA",
                problem=(
                    "Policy rules cannot currently reference agent profile attributes. A rule like "
                    "'allow all yes/no prompts when running the safe-refactor profile' is impossible. "
                    "This limits policy expressiveness and forces users to write separate policy "
                    "files for each agent configuration."
                ),
                solution=(
                    "Extend the policy evaluation context to include active profile data:\n\n"
                    "```yaml\n"
                    "# policy.yaml\n"
                    "rules:\n"
                    "  - name: allow-safe-profiles\n"
                    "    match:\n"
                    "      profile_tag: safe\n"
                    "      prompt_type: yes_no\n"
                    "    action: auto_respond\n"
                    "    params:\n"
                    "      response: 'y'\n"
                    "```\n\n"
                    "Add `profile`, `profile_tag`, and `profile_risk` match criteria to the DSL."
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/policy/evaluator.py` — accept profile in context\n"
                    "- Modify: `src/atlasbridge/core/policy/model.py` — add profile match criteria\n"
                    "- Modify: `src/atlasbridge/core/autopilot/engine.py` — pass profile to evaluator\n"
                    "- DSL additions: `profile`, `profile_tag`, `profile_risk` match keys\n"
                    "- Backward compatible — missing profile = match always"
                ),
                safety=(
                    "- Policy evaluation logic changes — requires safety tests\n"
                    "- Profile mismatch must never silently skip rules\n"
                    "- Audit log records profile context for every decision"
                ),
                acceptance=(
                    "- [ ] `profile`, `profile_tag`, `profile_risk` match criteria in DSL\n"
                    "- [ ] Evaluator receives profile context from engine\n"
                    "- [ ] Rules with profile criteria skip when profile doesn't match\n"
                    "- [ ] Rules without profile criteria behave unchanged\n"
                    "- [ ] Policy test command supports `--profile` flag\n"
                    "- [ ] Safety tests verify no bypass when profile is missing"
                ),
                tests=(
                    "- Unit: evaluator with profile context, match/no-match scenarios\n"
                    "- Safety: profile mismatch never auto-executes\n"
                    "- Integration: full policy test with profile flag"
                ),
                dependencies=("- Prerequisite: A1a (schema), A1b (CLI)\n- Blocks: None"),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "governance", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Governance",
            effort="S",
            edition="Community",
            risk_level="Medium",
            target_date="v1.0.0",
            batch=1,
        )
    )

    # --- A1 epic (batch 2) ---
    issues.append(
        Issue(
            id="A1",
            title="epic(config): Smart Agent Profiles",
            body=build_body(
                phase="E",
                priority="P1",
                category="Core",
                effort="L",
                edition="Community",
                issue_type="Epic",
                market_segment="Developer tooling",
                complexity="2/5 — three well-scoped sub-tasks, no novel patterns",
                recommended_phase="E — agent profiles improve GA onboarding experience",
                problem=(
                    "AtlasBridge currently has no concept of agent-specific configuration. All agents "
                    "use the same policy rules and autonomy settings regardless of their capabilities "
                    "or risk profile. This forces users to either over-restrict capable agents or "
                    "under-restrict risky ones."
                ),
                solution=(
                    "Implement agent profiles as a three-part feature:\n"
                    "1. **Profile schema + storage** — Pydantic model, YAML persistence\n"
                    "2. **Profile CLI** — create, list, select, per-run override\n"
                    "3. **Policy integration** — profile-aware match criteria in DSL\n\n"
                    "## Child Issues\n"
                    "- {A1a} — Agent profile schema + storage\n"
                    "- {A1b} — Profile selection CLI\n"
                    "- {A1c} — Profile-aware policy evaluation"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/config/profiles.py`\n"
                    "- New CLI: `src/atlasbridge/cli/_profile.py`\n"
                    "- Modified: policy evaluator, model, autopilot engine\n"
                    "- Storage: `~/.config/atlasbridge/profiles/*.yaml`"
                ),
                safety=(
                    "- Profile mismatch must default to most restrictive behavior\n"
                    "- No profile = existing behavior (backward compatible)\n"
                    "- Audit log captures profile context"
                ),
                acceptance=(
                    "- [ ] All three child issues completed\n"
                    "- [ ] End-to-end: create profile → run with profile → policy uses profile data\n"
                    "- [ ] Documentation updated in policy authoring guide"
                ),
                tests="- See child issues for detailed test requirements",
                dependencies=("- Prerequisite: None\n- Blocks: None (standalone feature)"),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "epic", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Core",
            effort="L",
            edition="Community",
            risk_level="Low",
            target_date="v1.0.0",
            batch=2,
            epic_children=["A1a", "A1b", "A1c"],
        )
    )

    # --- Phase E standalone (batch 3) ---
    issues.append(
        Issue(
            id="A8",
            title="feat(runtime): Deterministic dry run mode",
            body=build_body(
                phase="E",
                priority="P0",
                category="Core",
                effort="M",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="2/5 — wraps existing execution path with output-only mode",
                recommended_phase="E — essential for safe testing before GA",
                problem=(
                    "There is no way to test AtlasBridge policy + runtime behavior without actually "
                    "executing agent commands. Users cannot preview what would happen for a given "
                    "prompt without risking side effects. This makes policy development error-prone "
                    "and slows adoption."
                ),
                solution=(
                    "Add `--dry-run` flag to `atlasbridge run` that processes prompts through the "
                    "full pipeline (detect → classify → evaluate policy → plan) but stops before "
                    "execution. All decisions are logged to stdout and audit log with a `dry_run=true` "
                    "marker.\n\n"
                    "```bash\n"
                    "atlasbridge run claude --dry-run\n"
                    "# Shows: prompt detected → classified as yes_no → policy rule 'auto-yes' matched\n"
                    "#        → would inject 'y' → DRY RUN, no injection performed\n"
                    "```"
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/daemon/manager.py` — accept dry_run flag\n"
                    "- Modify: `src/atlasbridge/core/interaction/executor.py` — skip injection in dry mode\n"
                    "- Modify: `src/atlasbridge/cli/_run.py` — add `--dry-run` option\n"
                    "- Audit events tagged with `dry_run: true`\n"
                    "- No database schema changes"
                ),
                safety=(
                    "- Dry run must NEVER inject into PTY — critical safety invariant\n"
                    "- Audit log must clearly distinguish dry run from real decisions\n"
                    "- Channel messages suppressed in dry run mode"
                ),
                acceptance=(
                    "- [ ] `atlasbridge run claude --dry-run` processes prompts without injection\n"
                    "- [ ] Full pipeline executes: detect → classify → policy → plan → STOP\n"
                    "- [ ] Decisions logged to stdout with clear dry-run indicator\n"
                    "- [ ] Audit log entries tagged `dry_run: true`\n"
                    "- [ ] Channel messages suppressed during dry run\n"
                    "- [ ] Safety test: verify no PTY injection occurs in dry run mode"
                ),
                tests=(
                    "- Unit: executor skips injection when dry_run=True\n"
                    "- Safety: no PTY writes in dry run mode (critical)\n"
                    "- Integration: full pipeline dry run with mocked PTY"
                ),
                dependencies=(
                    "- Prerequisite: None\n- Blocks: C1 (replay engine uses dry run infrastructure)"
                ),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "phase:E-ga"],
            phase="E",
            priority="P0",
            category="Core",
            effort="M",
            edition="Community",
            risk_level="Low",
            target_date="v1.0.0",
            batch=3,
        )
    )

    issues.append(
        Issue(
            id="B12",
            title="feat(security): Secret handling hardening",
            body=build_body(
                phase="E",
                priority="P0",
                category="Security",
                effort="M",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="3/5 — touches multiple subsystems, regex patterns, audit pipeline",
                recommended_phase="E — must ship before GA for baseline safety",
                problem=(
                    "AtlasBridge handles secrets (API keys, tokens) in multiple places: config loading, "
                    "channel initialization, debug output, and audit logging. The current redaction "
                    "patterns cover known formats but lack systematic coverage. A leaked secret in "
                    "audit logs or dashboard output would undermine trust."
                ),
                solution=(
                    "Centralize secret handling into a dedicated module with:\n"
                    "1. Expanded regex patterns for all known secret formats\n"
                    "2. Configurable custom patterns via policy DSL\n"
                    "3. Mandatory redaction pass on all audit log entries\n"
                    "4. Redaction pass on all dashboard/channel output\n"
                    "5. Secret detection in PTY output (warn, never auto-forward)\n\n"
                    "```python\n"
                    "# src/atlasbridge/core/security/redactor.py\n"
                    "class SecretRedactor:\n"
                    "    def __init__(self, custom_patterns: list[str] = None): ...\n"
                    "    def redact(self, text: str) -> str: ...\n"
                    "    def contains_secret(self, text: str) -> bool: ...\n"
                    "```"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/security/redactor.py`\n"
                    "- Modify: `src/atlasbridge/core/audit/writer.py` — mandatory redaction\n"
                    "- Modify: `src/atlasbridge/dashboard/sanitize.py` — use shared redactor\n"
                    "- Modify: `src/atlasbridge/core/interaction/output_forwarder.py` — redact before send\n"
                    "- Config: optional `secret_patterns` in policy YAML\n"
                    "- Backward compatible — default patterns match current behavior"
                ),
                safety=(
                    "- This IS the safety feature — prevents secret leakage\n"
                    "- False positives (over-redaction) preferred over false negatives\n"
                    "- Audit log must never contain raw secrets\n"
                    "- Redaction must not break prompt detection patterns"
                ),
                acceptance=(
                    "- [ ] `SecretRedactor` class with expanded pattern set\n"
                    "- [ ] All audit log writes pass through redactor\n"
                    "- [ ] Dashboard output uses shared redactor\n"
                    "- [ ] Channel output uses shared redactor\n"
                    "- [ ] PTY output scanned for secrets with warning\n"
                    "- [ ] Custom patterns configurable via policy YAML\n"
                    "- [ ] No known secret format passes through unredacted"
                ),
                tests=(
                    "- Unit: pattern matching for all secret formats\n"
                    "- Safety: audit log entries never contain test secrets\n"
                    "- Integration: end-to-end secret in PTY → redacted in channel output"
                ),
                dependencies=(
                    "- Prerequisite: None\n"
                    "- Blocks: B5 (compliance mode requires verified redaction)"
                ),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "security", "phase:E-ga"],
            phase="E",
            priority="P0",
            category="Security",
            effort="M",
            edition="Community",
            risk_level="Medium",
            target_date="v1.0.0",
            batch=3,
        )
    )

    issues.append(
        Issue(
            id="C5",
            title="test(safety): AI safety regression suite",
            body=build_body(
                phase="E",
                priority="P0",
                category="Hardening",
                effort="M",
                edition="Community",
                issue_type="Enhancement",
                market_segment="Cross-market safety",
                complexity="2/5 — test infrastructure, no production code changes",
                recommended_phase="E — safety test coverage must exist before GA",
                problem=(
                    "AtlasBridge has 25 safety test files covering core invariants, but lacks a "
                    "dedicated AI safety regression suite that tests adversarial prompt patterns, "
                    "policy bypass attempts, and edge cases in the interaction pipeline. As the "
                    "system gains autonomy features, regression coverage for safety-critical paths "
                    "must grow proportionally."
                ),
                solution=(
                    "Create `tests/safety/` directory with structured regression tests:\n\n"
                    "1. **Prompt injection tests** — adversarial patterns that should never auto-execute\n"
                    "2. **Policy bypass tests** — crafted inputs that attempt to skip evaluation\n"
                    "3. **Escalation guarantee tests** — verify escalation on no-match and low-confidence\n"
                    "4. **Audit integrity tests** — verify hash chain, no gaps, no tampering\n"
                    "5. **Boundary tests** — max prompt length, unicode edge cases, empty inputs\n\n"
                    "Each category gets a fixture file with test vectors and expected outcomes."
                ),
                architecture=(
                    "- New directory: `tests/safety/`\n"
                    "- New fixtures: `tests/safety/fixtures/` with adversarial test vectors\n"
                    "- CI: safety tests run in dedicated job (must pass for merge)\n"
                    "- No production code changes — test-only"
                ),
                safety=(
                    "- This IS the safety infrastructure\n"
                    "- Tests must be deterministic — no flaky safety tests\n"
                    "- Failure in any safety test blocks merge (CI gate)"
                ),
                acceptance=(
                    "- [ ] `tests/safety/` directory with categorized test modules\n"
                    "- [ ] Prompt injection test vectors (minimum 20 patterns)\n"
                    "- [ ] Policy bypass attempt tests (minimum 10 scenarios)\n"
                    "- [ ] Escalation guarantee tests for all autonomy modes\n"
                    "- [ ] Audit integrity verification tests\n"
                    "- [ ] Boundary/edge case tests (unicode, length, empty)\n"
                    "- [ ] CI job runs safety suite as merge gate"
                ),
                tests=(
                    "- This issue IS tests — all deliverables are test files\n"
                    "- Minimum 50 new test cases across all categories\n"
                    "- All tests must be deterministic (no network, no randomness)"
                ),
                dependencies=(
                    "- Prerequisite: None\n- Blocks: None (but informs all future safety work)"
                ),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "hardening", "phase:E-ga"],
            phase="E",
            priority="P0",
            category="Hardening",
            effort="M",
            edition="Community",
            risk_level="Low",
            target_date="v1.0.0",
            batch=3,
        )
    )

    issues.append(
        Issue(
            id="A6",
            title="feat(policy): Policy debug mode",
            body=build_body(
                phase="E",
                priority="P1",
                category="Governance",
                effort="S",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="2/5 — extends existing policy test command with verbose trace",
                recommended_phase="E — improves policy authoring experience for GA",
                problem=(
                    "When a policy rule doesn't match as expected, users have limited visibility "
                    "into why. The `policy test --explain` flag shows the final decision but not "
                    "the step-by-step evaluation trace. Debugging complex policies with multiple "
                    "rules, any_of/none_of criteria, and confidence thresholds requires guesswork."
                ),
                solution=(
                    "Add `--debug` flag to `atlasbridge policy test` and a runtime debug mode:\n\n"
                    "```bash\n"
                    "atlasbridge policy test policy.yaml --prompt '...' --debug\n"
                    "# Output:\n"
                    "# Rule 1 'auto-yes': checking match criteria...\n"
                    "#   prompt_type: yes_no == yes_no ✓\n"
                    "#   confidence: high >= medium ✓\n"
                    "#   rate_limit: 3/5 in window ✓\n"
                    "#   → MATCH, action: auto_respond(y)\n"
                    "```\n\n"
                    "Runtime debug mode: `atlasbridge run claude --policy-debug` logs evaluation "
                    "trace for every prompt to a debug log file."
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/policy/evaluator.py` — emit trace events\n"
                    "- Modify: `src/atlasbridge/core/policy/explain.py` — format trace for CLI\n"
                    "- Modify: `src/atlasbridge/cli/_policy_cmd.py` — add `--debug` flag\n"
                    "- Modify: `src/atlasbridge/cli/_run.py` — add `--policy-debug` flag\n"
                    "- New: debug trace log file in config directory"
                ),
                safety=(
                    "- Debug output may contain prompt content — redact secrets\n"
                    "- Debug mode is read-only — does not affect evaluation results\n"
                    "- Debug log file should not be world-readable"
                ),
                acceptance=(
                    "- [ ] `policy test --debug` shows step-by-step evaluation trace\n"
                    "- [ ] Each rule shows match/skip reason for every criterion\n"
                    "- [ ] Rate limit state shown in trace\n"
                    "- [ ] `run --policy-debug` writes trace to debug log file\n"
                    "- [ ] Debug output uses secret redaction"
                ),
                tests=(
                    "- Unit: trace output format for match/skip scenarios\n"
                    "- Integration: full policy test with --debug flag"
                ),
                dependencies=("- Prerequisite: None\n- Blocks: None"),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "governance", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Governance",
            effort="S",
            edition="Community",
            risk_level="Low",
            target_date="v1.0.0",
            batch=3,
        )
    )

    issues.append(
        Issue(
            id="A2",
            title="feat(interaction): Plan-Approve-Execute workflow",
            body=build_body(
                phase="E",
                priority="P1",
                category="Core",
                effort="M",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="3/5 — extends interaction pipeline with approval gate",
                recommended_phase="E — key safety workflow for autonomous operation",
                problem=(
                    "When AtlasBridge detects a plan in agent output (via the existing plan detector), "
                    "it can present the plan to the user but lacks a structured approve/reject/modify "
                    "workflow. Users see the plan but must manually decide how to respond. There is no "
                    "policy-driven approval gate that can auto-approve safe plans or escalate risky ones."
                ),
                solution=(
                    "Implement a Plan-Approve-Execute (PAE) workflow:\n\n"
                    "1. **Detect** — existing `plan_detector.py` identifies plan in agent output\n"
                    "2. **Present** — plan sent to channel with structured approve/reject buttons\n"
                    "3. **Evaluate** — policy rules can auto-approve plans matching criteria\n"
                    "4. **Execute** — approved plans proceed; rejected plans send 'no' to agent\n\n"
                    "```yaml\n"
                    "rules:\n"
                    "  - name: auto-approve-safe-plans\n"
                    "    match:\n"
                    "      interaction_class: plan\n"
                    "      plan_risk: low\n"
                    "    action: auto_respond\n"
                    "    params:\n"
                    "      response: 'y'\n"
                    "```"
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/interaction/engine.py` — PAE state in pipeline\n"
                    "- Modify: `src/atlasbridge/core/interaction/plan_detector.py` — risk assessment\n"
                    "- Modify: `src/atlasbridge/core/policy/model.py` — `plan_risk` match criterion\n"
                    "- Modify: channel renderers — approve/reject buttons for plans\n"
                    "- New state: PLAN_PENDING in interaction pipeline"
                ),
                safety=(
                    "- Auto-approval must respect risk ceiling from agent profile\n"
                    "- Plan modification by user must be re-evaluated by policy\n"
                    "- Audit log records plan content + approval decision"
                ),
                acceptance=(
                    "- [ ] Plans detected and presented with approve/reject options\n"
                    "- [ ] Policy rules can match on `interaction_class: plan`\n"
                    "- [ ] `plan_risk` match criterion available in DSL\n"
                    "- [ ] Auto-approved plans proceed to execution\n"
                    "- [ ] Rejected plans send rejection to agent\n"
                    "- [ ] Audit log captures plan content and approval decision"
                ),
                tests=(
                    "- Unit: plan risk assessment, PAE state transitions\n"
                    "- Safety: risky plans never auto-approved without explicit rule\n"
                    "- Integration: full PAE flow with mocked channel"
                ),
                dependencies=(
                    "- Prerequisite: None (builds on existing plan_detector)\n"
                    "- Blocks: C4 (structured planning mode extends PAE)"
                ),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Core",
            effort="M",
            edition="Community",
            risk_level="Medium",
            target_date="v1.0.0",
            batch=3,
        )
    )

    issues.append(
        Issue(
            id="C4",
            title="feat(interaction): Structured planning mode",
            body=build_body(
                phase="E",
                priority="P1",
                category="Core",
                effort="M",
                edition="Community",
                issue_type="Feature",
                market_segment="Cross-market safety",
                complexity="3/5 — extends interaction pipeline with structured plan format",
                recommended_phase="E — improves plan visibility and approval UX",
                problem=(
                    "Agent plans are currently detected as free-text blocks in PTY output. There is no "
                    "structured representation that enables step-by-step approval, partial execution, "
                    "or plan comparison across sessions. Users cannot approve step 1 while rejecting "
                    "step 3 of a multi-step plan."
                ),
                solution=(
                    "Parse detected plans into structured `PlanStep` objects:\n\n"
                    "```python\n"
                    "class PlanStep(BaseModel):\n"
                    "    index: int\n"
                    "    description: str\n"
                    "    risk_level: Literal['low', 'medium', 'high']\n"
                    "    requires_approval: bool\n"
                    "    status: Literal['pending', 'approved', 'rejected', 'executed']\n"
                    "```\n\n"
                    "Channel UX shows each step with individual approve/reject controls. "
                    "Policy rules can gate per-step based on risk level."
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/interaction/plan_detector.py` — structured parsing\n"
                    "- New model: `PlanStep` in `src/atlasbridge/core/interaction/models.py`\n"
                    "- Modify: channel renderers — per-step approval UI\n"
                    "- Modify: policy evaluator — per-step risk gating\n"
                    "- Stored in session state for cross-reference"
                ),
                safety=(
                    "- Per-step approval prevents blanket approval of risky plans\n"
                    "- Step risk assessment must be conservative (default to high)\n"
                    "- Rejected steps must prevent dependent steps from executing"
                ),
                acceptance=(
                    "- [ ] Plans parsed into `PlanStep` objects with risk levels\n"
                    "- [ ] Channel UX shows per-step approve/reject controls\n"
                    "- [ ] Policy rules can gate individual steps by risk\n"
                    "- [ ] Rejected steps block dependent steps\n"
                    "- [ ] Plan state persisted in session for reference\n"
                    "- [ ] Fallback to full-plan approval when parsing fails"
                ),
                tests=(
                    "- Unit: plan parsing, step risk assessment\n"
                    "- Safety: rejected step blocks dependent steps\n"
                    "- Integration: multi-step plan with mixed approval"
                ),
                dependencies=("- Prerequisite: A2 (Plan-Approve-Execute workflow)\n- Blocks: None"),
                milestone="Phase E — v1.0.0",
            ),
            labels=["enhancement", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Core",
            effort="M",
            edition="Community",
            risk_level="Medium",
            target_date="v1.0.0",
            batch=3,
        )
    )

    return issues


# ---------------------------------------------------------------------------
# Phase F issues (5 standalone, batch 4)
# ---------------------------------------------------------------------------


def phase_f_issues() -> list[Issue]:
    issues: list[Issue] = []

    issues.append(
        Issue(
            id="C1",
            title="feat(runtime): Deterministic replay + simulation engine",
            body=build_body(
                phase="F",
                priority="P1",
                category="Core",
                effort="L",
                edition="Community",
                issue_type="Feature",
                market_segment="Cross-market safety",
                complexity="4/5 — requires session capture format, replay runtime, simulation harness",
                recommended_phase="F — builds on dry run mode (A8), not needed for GA",
                problem=(
                    "AtlasBridge sessions are ephemeral — once a session ends, there is no way to "
                    "replay the exact sequence of prompts, decisions, and responses. This prevents "
                    "debugging production issues, regression testing policy changes, and validating "
                    "that a policy update doesn't change behavior for known scenarios."
                ),
                solution=(
                    "Build a replay engine that captures and replays sessions:\n\n"
                    "1. **Capture format** — JSONL session recording with all events\n"
                    "2. **Replay mode** — `atlasbridge replay <recording>` processes events through "
                    "current policy without PTY\n"
                    "3. **Diff mode** — compare replay outcomes against original decisions\n"
                    "4. **Simulation** — synthetic session from YAML scenario definition\n\n"
                    "```bash\n"
                    "atlasbridge session export 12345 > session.jsonl\n"
                    "atlasbridge replay session.jsonl --diff\n"
                    "# Shows: 3 decisions changed, 2 would now escalate\n"
                    "```"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/replay/`\n"
                    "  - `capture.py` — session event recording\n"
                    "  - `engine.py` — replay runtime\n"
                    "  - `diff.py` — decision comparison\n"
                    "- New CLI: `atlasbridge replay` and `atlasbridge session export`\n"
                    "- Uses dry run infrastructure from A8\n"
                    "- No database schema changes (reads existing audit log)"
                ),
                safety=(
                    "- Replay must NEVER inject into any PTY or channel\n"
                    "- Session recordings may contain sensitive prompt content — redact on export\n"
                    "- Replay results are informational only, never trigger actions"
                ),
                acceptance=(
                    "- [ ] Session events captured in JSONL format during normal operation\n"
                    "- [ ] `session export` produces replayable recording\n"
                    "- [ ] `replay` processes recording through current policy\n"
                    "- [ ] `replay --diff` shows decision differences\n"
                    "- [ ] Replay never triggers PTY injection or channel messages\n"
                    "- [ ] Secret redaction on session export"
                ),
                tests=(
                    "- Unit: capture format, replay engine, diff comparison\n"
                    "- Safety: replay never triggers side effects\n"
                    "- Integration: record session → change policy → replay → verify diff"
                ),
                dependencies=(
                    "- Prerequisite: A8 (dry run mode)\n- Blocks: A7 (reproducible session replay)"
                ),
                milestone="Phase F — v1.1.0",
            ),
            labels=["enhancement", "phase:F-ga-freeze"],
            phase="F",
            priority="P1",
            category="Core",
            effort="L",
            edition="Community",
            risk_level="Medium",
            target_date="v1.1.0",
            batch=4,
        )
    )

    issues.append(
        Issue(
            id="C2",
            title="feat(governance): Autonomy confidence metrics",
            body=build_body(
                phase="F",
                priority="P1",
                category="Governance",
                effort="M",
                edition="Community",
                issue_type="Feature",
                market_segment="Cross-market safety",
                complexity="2/5 — aggregation over existing decision data",
                recommended_phase="F — requires stable decision data from GA operation",
                problem=(
                    "Users have no quantitative insight into how well their policy rules are performing. "
                    "Questions like 'what percentage of prompts are auto-handled vs escalated?' or "
                    "'which rules fire most often?' require manual log analysis. Without metrics, "
                    "users cannot tune their autonomy settings effectively."
                ),
                solution=(
                    "Compute and display autonomy confidence metrics:\n\n"
                    "1. **Auto-handle rate** — % of prompts resolved by policy\n"
                    "2. **Escalation rate** — % requiring human intervention\n"
                    "3. **Per-rule hit rate** — how often each rule matches\n"
                    "4. **Confidence distribution** — HIGH/MED/LOW histogram\n"
                    "5. **Trend over time** — rolling 7-day metrics\n\n"
                    "```bash\n"
                    "atlasbridge autopilot metrics\n"
                    "# Auto-handle: 73% | Escalation: 27% | Top rule: auto-yes (45%)\n"
                    "# Confidence: HIGH 52% | MED 31% | LOW 17%\n"
                    "```\n\n"
                    "Dashboard endpoint: `/api/metrics/autonomy`"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/autopilot/metrics.py`\n"
                    "- Modify: `src/atlasbridge/cli/_autopilot.py` — add `metrics` subcommand\n"
                    "- Modify: `src/atlasbridge/dashboard/app.py` — add metrics endpoint\n"
                    "- Reads from existing decision trace JSONL\n"
                    "- No new storage — computed on-demand from existing data"
                ),
                safety=(
                    "- Metrics are read-only — no impact on runtime behavior\n"
                    "- Decision trace data may contain prompt content — aggregate only\n"
                    "- No PII in metric output"
                ),
                acceptance=(
                    "- [ ] `autopilot metrics` CLI command shows key metrics\n"
                    "- [ ] Auto-handle rate, escalation rate, per-rule hit rate computed\n"
                    "- [ ] Confidence distribution histogram\n"
                    "- [ ] Dashboard `/api/metrics/autonomy` endpoint\n"
                    "- [ ] Metrics computed from existing decision trace (no new storage)"
                ),
                tests=(
                    "- Unit: metric computation from sample decision traces\n"
                    "- Integration: CLI metrics command with test data"
                ),
                dependencies=(
                    "- Prerequisite: None (reads existing decision trace)\n"
                    "- Blocks: B6 (enterprise risk engine uses metrics)"
                ),
                milestone="Phase F — v1.1.0",
            ),
            labels=["enhancement", "governance", "phase:F-ga-freeze"],
            phase="F",
            priority="P1",
            category="Governance",
            effort="M",
            edition="Community",
            risk_level="Low",
            target_date="v1.1.0",
            batch=4,
        )
    )

    issues.append(
        Issue(
            id="A7",
            title="feat(session): Reproducible session replay",
            body=build_body(
                phase="F",
                priority="P2",
                category="Core",
                effort="L",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="4/5 — requires deterministic environment snapshot + replay harness",
                recommended_phase="F — depends on replay engine (C1), not needed for GA",
                problem=(
                    "Even with the replay engine (C1), sessions may produce different results if the "
                    "environment has changed (different policy file, different adapter version, different "
                    "OS). True reproducibility requires capturing the full environment state alongside "
                    "session events."
                ),
                solution=(
                    "Extend session recordings with environment snapshots:\n\n"
                    "1. **Environment capture** — policy hash, adapter version, config hash, OS info\n"
                    "2. **Pinned replay** — replay uses captured environment, warns on drift\n"
                    "3. **Reproducibility score** — 0-100% based on environment match\n\n"
                    "```bash\n"
                    "atlasbridge replay session.jsonl --strict\n"
                    "# Environment match: 85% (policy changed, adapter same)\n"
                    "# WARNING: policy hash mismatch — results may differ\n"
                    "```"
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/replay/capture.py` — env snapshot\n"
                    "- Modify: `src/atlasbridge/core/replay/engine.py` — env comparison\n"
                    "- New: `src/atlasbridge/core/replay/environment.py` — snapshot + compare\n"
                    "- No database changes"
                ),
                safety=(
                    "- Environment snapshots may contain file paths — sanitize\n"
                    "- Strict mode refuses to replay on critical env mismatch\n"
                    "- No secret content in environment snapshots"
                ),
                acceptance=(
                    "- [ ] Session recordings include environment snapshot\n"
                    "- [ ] Replay compares environment and reports match score\n"
                    "- [ ] `--strict` mode refuses replay on critical mismatch\n"
                    "- [ ] Warnings for non-critical environment differences\n"
                    "- [ ] Environment snapshot excludes secrets and PII"
                ),
                tests=(
                    "- Unit: environment snapshot, comparison, scoring\n"
                    "- Integration: replay with matched vs mismatched environment"
                ),
                dependencies=("- Prerequisite: C1 (replay engine)\n- Blocks: None"),
                milestone="Phase F — v1.1.0",
            ),
            labels=["enhancement", "phase:F-ga-freeze"],
            phase="F",
            priority="P2",
            category="Core",
            effort="L",
            edition="Community",
            risk_level="Low",
            target_date="v1.1.0",
            batch=4,
        )
    )

    issues.append(
        Issue(
            id="A3",
            title="feat(session): Local agent memory layer",
            body=build_body(
                phase="F",
                priority="P2",
                category="Core",
                effort="L",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="4/5 — persistent memory with session scoping, retrieval, and lifecycle",
                recommended_phase="F — enriches agent sessions but not required for GA",
                problem=(
                    "Agent sessions are stateless across runs — each new session starts fresh with "
                    "no knowledge of past interactions, decisions, or user preferences. Users must "
                    "re-establish context manually. Policy rules cannot reference historical patterns "
                    "(e.g., 'this user always approves refactoring plans')."
                ),
                solution=(
                    "Implement a local memory layer stored in SQLite:\n\n"
                    "1. **Memory entries** — key-value facts with session provenance\n"
                    "2. **Scoped retrieval** — query by session, agent, or global scope\n"
                    "3. **Lifecycle management** — TTL, manual pruning, export\n"
                    "4. **Policy integration** — `memory_tag` match criterion in DSL\n\n"
                    "```python\n"
                    "class MemoryEntry(BaseModel):\n"
                    "    key: str\n"
                    "    value: str\n"
                    "    scope: Literal['session', 'agent', 'global']\n"
                    "    created_at: datetime\n"
                    "    ttl_seconds: int | None = None\n"
                    "    source_session: str\n"
                    "```"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/memory/`\n"
                    "  - `store.py` — SQLite-backed memory storage\n"
                    "  - `models.py` — MemoryEntry, MemoryQuery\n"
                    "  - `manager.py` — CRUD + lifecycle operations\n"
                    "- Modify: `src/atlasbridge/core/store/database.py` — memory table migration\n"
                    "- Modify: `src/atlasbridge/core/policy/model.py` — `memory_tag` criterion\n"
                    "- New CLI: `atlasbridge memory list/get/set/prune`"
                ),
                safety=(
                    "- Memory content may contain sensitive data — encrypt at rest option\n"
                    "- Memory entries must not influence policy evaluation without explicit rules\n"
                    "- TTL prevents unbounded growth\n"
                    "- No cross-user memory in multi-user scenarios"
                ),
                acceptance=(
                    "- [ ] Memory entries stored in SQLite with session provenance\n"
                    "- [ ] Scoped retrieval: session, agent, global\n"
                    "- [ ] TTL-based expiry and manual pruning\n"
                    "- [ ] `memory_tag` criterion available in policy DSL\n"
                    "- [ ] CLI commands for memory management\n"
                    "- [ ] Export/import for memory portability"
                ),
                tests=(
                    "- Unit: memory CRUD, scoping, TTL expiry\n"
                    "- Integration: memory persistence across simulated sessions\n"
                    "- Safety: memory isolation between scopes"
                ),
                dependencies=("- Prerequisite: None\n- Blocks: None"),
                milestone="Phase F — v1.1.0",
            ),
            labels=["enhancement", "phase:F-ga-freeze"],
            phase="F",
            priority="P2",
            category="Core",
            effort="L",
            edition="Community",
            risk_level="Low",
            target_date="v1.1.0",
            batch=4,
        )
    )

    issues.append(
        Issue(
            id="A4",
            title="feat(dashboard): Local risk heatmap",
            body=build_body(
                phase="F",
                priority="P2",
                category="UX",
                effort="M",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="2/5 — dashboard visualization over existing decision data",
                recommended_phase="F — UX enhancement, not blocking GA",
                problem=(
                    "Users cannot visualize where risk concentrates in their AtlasBridge usage. "
                    "Which sessions trigger the most escalations? Which prompt types have the lowest "
                    "confidence? Which policy rules are never matched? This information exists in the "
                    "audit log but is not surfaced visually.\n\n"
                    "Supersedes #88 (risk heat map stub)."
                ),
                solution=(
                    "Add a risk heatmap visualization to the local dashboard:\n\n"
                    "1. **Session risk heatmap** — color-coded grid of sessions by escalation rate\n"
                    "2. **Prompt type distribution** — which types generate most escalations\n"
                    "3. **Rule coverage gaps** — prompt patterns with no matching rules\n"
                    "4. **Time-series view** — risk trends over days/weeks\n\n"
                    "Dashboard route: `/dashboard/risk` with interactive heatmap widget."
                ),
                architecture=(
                    "- New template: `src/atlasbridge/dashboard/templates/risk.html`\n"
                    "- Modify: `src/atlasbridge/dashboard/app.py` — risk route + API endpoint\n"
                    "- Modify: `src/atlasbridge/dashboard/repo.py` — risk aggregation queries\n"
                    "- Frontend: lightweight chart library (Chart.js or similar via CDN)\n"
                    "- No new database tables — computed from existing audit data"
                ),
                safety=(
                    "- Heatmap is read-only visualization — no runtime impact\n"
                    "- Aggregate data only — no individual prompt content exposed\n"
                    "- Dashboard access controls apply"
                ),
                acceptance=(
                    "- [ ] `/dashboard/risk` route renders heatmap visualization\n"
                    "- [ ] Session risk heatmap shows escalation density\n"
                    "- [ ] Prompt type distribution chart\n"
                    "- [ ] Rule coverage gap identification\n"
                    "- [ ] Time-series risk trend view\n"
                    "- [ ] Mobile-responsive layout"
                ),
                tests=(
                    "- Unit: risk aggregation queries\n"
                    "- Integration: dashboard route with test data\n"
                    "- E2E: heatmap renders with sample audit data"
                ),
                dependencies=(
                    "- Prerequisite: None (reads existing audit data)\n"
                    "- Supersedes: #88\n"
                    "- Blocks: B8 (enterprise dashboard extends risk views)"
                ),
                milestone="Phase F — v1.1.0",
            ),
            labels=["enhancement", "ux", "phase:F-ga-freeze"],
            phase="F",
            priority="P2",
            category="UX",
            effort="M",
            edition="Community",
            risk_level="Low",
            target_date="v1.1.0",
            batch=4,
        )
    )

    return issues


# ---------------------------------------------------------------------------
# Phase G issues (10: 3 epic children + 1 epic + 7 standalone)
# ---------------------------------------------------------------------------


def phase_g_issues() -> list[Issue]:
    issues: list[Issue] = []

    # --- A10 epic children (batch 1) ---
    issues.append(
        Issue(
            id="A10a",
            title="feat(adapters): Plugin adapter loading via entry_points",
            body=build_body(
                phase="G",
                priority="P1",
                category="Core",
                effort="M",
                edition="Pro",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="3/5 — entry_points discovery, validation, lifecycle management",
                recommended_phase="G — extends adapter system, not needed for core GA",
                problem=(
                    "AtlasBridge adapters (Claude Code, OpenAI CLI, Gemini CLI) are hard-coded in "
                    "the adapter registry. Adding a new adapter requires modifying source code and "
                    "releasing a new version. Third-party adapter development is impossible without "
                    "forking the project."
                ),
                solution=(
                    "Use Python `entry_points` (PEP 621) for adapter discovery:\n\n"
                    "```toml\n"
                    "# Third-party package pyproject.toml\n"
                    "[project.entry-points.'atlasbridge.adapters']\n"
                    "my_agent = 'my_package:MyAdapter'\n"
                    "```\n\n"
                    "```python\n"
                    "# src/atlasbridge/adapters/plugins.py\n"
                    "def discover_plugin_adapters() -> dict[str, type[BaseAdapter]]:\n"
                    "    adapters = {}\n"
                    "    for ep in importlib.metadata.entry_points(group='atlasbridge.adapters'):\n"
                    "        cls = ep.load()\n"
                    "        if issubclass(cls, BaseAdapter):\n"
                    "            adapters[ep.name] = cls\n"
                    "    return adapters\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/adapters/plugins.py` — entry_points discovery\n"
                    "- Modify: `src/atlasbridge/adapters/base.py` — registry loads plugins\n"
                    "- Entry point group: `atlasbridge.adapters`\n"
                    "- Plugin validation: must subclass BaseAdapter, pass health check\n"
                    "- Backward compatible — built-in adapters unchanged"
                ),
                safety=(
                    "- Plugin code runs with full process permissions — document trust model\n"
                    "- Plugin adapters sandboxed to same PTY isolation as built-in adapters\n"
                    "- Audit log records which adapter (built-in vs plugin) made each decision"
                ),
                acceptance=(
                    "- [ ] `discover_plugin_adapters()` finds entry_points adapters\n"
                    "- [ ] Plugin adapters appear in `atlasbridge adapter list`\n"
                    "- [ ] Plugin adapter can be used with `atlasbridge run <name>`\n"
                    "- [ ] Invalid plugins (wrong base class) rejected with clear error\n"
                    "- [ ] Built-in adapters unaffected by plugin system\n"
                    "- [ ] Documentation for third-party adapter development"
                ),
                tests=(
                    "- Unit: entry_points discovery with mock packages\n"
                    "- Integration: plugin adapter registration and listing\n"
                    "- Safety: invalid plugin rejected gracefully"
                ),
                dependencies=("- Prerequisite: None\n- Blocks: A10 (plugin system epic)"),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Core",
            effort="M",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.2.0",
            batch=1,
        )
    )

    issues.append(
        Issue(
            id="A10b",
            title="feat(channels): Plugin channel loading via entry_points",
            body=build_body(
                phase="G",
                priority="P1",
                category="Core",
                effort="M",
                edition="Pro",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="3/5 — mirrors adapter plugin pattern for channels",
                recommended_phase="G — extends channel system, not needed for core GA",
                problem=(
                    "Like adapters, channels (Telegram, Slack) are hard-coded. Users who want to "
                    "integrate AtlasBridge with Discord, Microsoft Teams, or custom messaging systems "
                    "must fork the project. There is no plugin mechanism for third-party channels."
                ),
                solution=(
                    "Apply the same entry_points pattern used for adapters (A10a) to channels:\n\n"
                    "```toml\n"
                    "[project.entry-points.'atlasbridge.channels']\n"
                    "discord = 'my_package:DiscordChannel'\n"
                    "```\n\n"
                    "Plugin channels must subclass `BaseChannel` and implement the standard interface "
                    "(send, receive, health check)."
                ),
                architecture=(
                    "- New: `src/atlasbridge/channels/plugins.py` — entry_points discovery\n"
                    "- Modify: `src/atlasbridge/channels/multi.py` — load plugin channels\n"
                    "- Entry point group: `atlasbridge.channels`\n"
                    "- Plugin validation: must subclass BaseChannel\n"
                    "- Backward compatible — built-in channels unchanged"
                ),
                safety=(
                    "- Plugin channels handle user messages — trust model must be documented\n"
                    "- Channel plugins sandboxed to BaseChannel interface\n"
                    "- Audit log records which channel handled each interaction"
                ),
                acceptance=(
                    "- [ ] `discover_plugin_channels()` finds entry_points channels\n"
                    "- [ ] Plugin channels available in multi-channel configuration\n"
                    "- [ ] Invalid plugins rejected with clear error\n"
                    "- [ ] Built-in channels unaffected\n"
                    "- [ ] Documentation for third-party channel development"
                ),
                tests=(
                    "- Unit: entry_points discovery with mock packages\n"
                    "- Integration: plugin channel registration\n"
                    "- Safety: invalid plugin rejected gracefully"
                ),
                dependencies=(
                    "- Prerequisite: A10a (adapter plugins establish the pattern)\n"
                    "- Blocks: A10 (plugin system epic)"
                ),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Core",
            effort="M",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.2.0",
            batch=1,
        )
    )

    issues.append(
        Issue(
            id="A10c",
            title="feat(policy): Custom policy rule actions via plugin",
            body=build_body(
                phase="G",
                priority="P1",
                category="Governance",
                effort="M",
                edition="Pro",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="3/5 — extends policy action dispatcher with plugin actions",
                recommended_phase="G — extends policy DSL, not needed for core GA",
                problem=(
                    "The policy DSL supports four built-in actions: auto_respond, escalate, "
                    "require_human, and reject. Users cannot define custom actions (e.g., 'log to "
                    "external system', 'trigger webhook', 'run custom script'). This limits policy "
                    "expressiveness for advanced workflows."
                ),
                solution=(
                    "Allow plugins to register custom policy actions:\n\n"
                    "```toml\n"
                    "[project.entry-points.'atlasbridge.actions']\n"
                    "webhook = 'my_package:WebhookAction'\n"
                    "```\n\n"
                    "```python\n"
                    "class WebhookAction(BaseAction):\n"
                    "    name = 'webhook'\n"
                    "    def execute(self, context: ActionContext) -> ActionResult: ...\n"
                    "```\n\n"
                    "```yaml\n"
                    "rules:\n"
                    "  - name: notify-on-escalation\n"
                    "    match: { confidence: low }\n"
                    "    action: webhook\n"
                    "    params: { url: 'https://hooks.example.com/notify' }\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/core/policy/actions/base.py` — BaseAction ABC\n"
                    "- New: `src/atlasbridge/core/policy/actions/plugins.py` — discovery\n"
                    "- Modify: `src/atlasbridge/core/autopilot/actions.py` — load plugin actions\n"
                    "- Entry point group: `atlasbridge.actions`\n"
                    "- Backward compatible — built-in actions unchanged"
                ),
                safety=(
                    "- Plugin actions execute arbitrary code — critical trust boundary\n"
                    "- Actions must not block the evaluation pipeline (timeout enforced)\n"
                    "- Audit log records plugin action execution and result\n"
                    "- Plugin action failures must not crash the runtime"
                ),
                acceptance=(
                    "- [ ] `BaseAction` ABC defined with execute interface\n"
                    "- [ ] Plugin actions discovered via entry_points\n"
                    "- [ ] Plugin actions usable in policy YAML rules\n"
                    "- [ ] Timeout enforcement on plugin action execution\n"
                    "- [ ] Graceful failure handling for plugin action errors\n"
                    "- [ ] Documentation for custom action development"
                ),
                tests=(
                    "- Unit: action discovery, execution, timeout\n"
                    "- Safety: plugin action failure doesn't crash runtime\n"
                    "- Integration: policy rule with custom action"
                ),
                dependencies=(
                    "- Prerequisite: A10a (establishes plugin pattern)\n"
                    "- Blocks: A10 (plugin system epic)"
                ),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Governance",
            effort="M",
            edition="Pro",
            risk_level="High",
            target_date="v1.2.0",
            batch=1,
        )
    )

    # --- A10 epic (batch 2) ---
    issues.append(
        Issue(
            id="A10",
            title="epic(runtime): Plugin system",
            body=build_body(
                phase="G",
                priority="P1",
                category="Core",
                effort="XL",
                edition="Pro",
                issue_type="Epic",
                market_segment="Developer tooling",
                complexity="5/5 — three extension points, trust model, lifecycle management",
                recommended_phase="G — ecosystem feature for post-GA growth",
                problem=(
                    "AtlasBridge is a closed system — all adapters, channels, and policy actions are "
                    "built-in. Third-party developers cannot extend AtlasBridge without forking. This "
                    "limits ecosystem growth and forces all feature development through the core team."
                ),
                solution=(
                    "Implement a plugin system with three extension points:\n"
                    "1. **Adapter plugins** — custom agent integrations\n"
                    "2. **Channel plugins** — custom messaging integrations\n"
                    "3. **Action plugins** — custom policy rule actions\n\n"
                    "All use Python entry_points (PEP 621) for discovery.\n\n"
                    "## Child Issues\n"
                    "- {A10a} — Plugin adapter loading via entry_points\n"
                    "- {A10b} — Plugin channel loading via entry_points\n"
                    "- {A10c} — Custom policy rule actions via plugin"
                ),
                architecture=(
                    "- New plugin discovery modules in adapters/, channels/, policy/\n"
                    "- Common pattern: entry_points group -> validate base class -> register\n"
                    "- Trust model documented for each extension point\n"
                    "- Plugin health checks and graceful failure handling"
                ),
                safety=(
                    "- Plugins run with full process permissions — trust boundary is installation\n"
                    "- Each extension point has a defined safety contract\n"
                    "- Plugin failures must never crash the core runtime\n"
                    "- Audit log distinguishes built-in vs plugin components"
                ),
                acceptance=(
                    "- [ ] All three child issues completed\n"
                    "- [ ] End-to-end: install plugin package -> discover -> use in policy\n"
                    "- [ ] Plugin developer documentation published\n"
                    "- [ ] Example plugin repository as template"
                ),
                tests="- See child issues for detailed test requirements",
                dependencies=("- Prerequisite: None\n- Blocks: None (enables ecosystem growth)"),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "epic", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Core",
            effort="XL",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.2.0",
            batch=2,
            epic_children=["A10a", "A10b", "A10c"],
        )
    )

    # --- Phase G standalone (batch 5) ---
    issues.append(
        Issue(
            id="B4",
            title="feat(audit): Immutable audit export + hash verification",
            body=build_body(
                phase="G",
                priority="P0",
                category="Governance",
                effort="M",
                edition="Pro",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="2/5 — extends existing hash-chained audit with export + verify",
                recommended_phase="G — governance feature for compliance-conscious users",
                problem=(
                    "AtlasBridge produces a hash-chained audit log, but there is no way to export "
                    "it in a portable format or independently verify the hash chain integrity. "
                    "Compliance workflows require tamper-evident audit trails that can be validated "
                    "by external tools."
                ),
                solution=(
                    "Add audit export and verification commands:\n\n"
                    "```bash\n"
                    "atlasbridge audit export --format jsonl --output audit.jsonl\n"
                    "atlasbridge audit export --format csv --output audit.csv\n"
                    "atlasbridge audit verify audit.jsonl\n"
                    "# Hash chain verified: 1,234 events, no gaps, no tampering detected\n"
                    "```\n\n"
                    "Export includes all fields plus hash chain metadata. Verification recomputes "
                    "hashes and reports any breaks in the chain."
                ),
                architecture=(
                    "- New: `src/atlasbridge/core/audit/export.py` — export to JSONL/CSV\n"
                    "- New: `src/atlasbridge/core/audit/verify.py` — hash chain verification\n"
                    "- New CLI: `atlasbridge audit export` and `atlasbridge audit verify`\n"
                    "- No database changes — reads existing audit table\n"
                    "- Export format documented for external tool integration"
                ),
                safety=(
                    "- Export may contain sensitive prompt content — redaction option\n"
                    "- Verification is read-only — no side effects\n"
                    "- Hash algorithm must match writer.py implementation exactly"
                ),
                acceptance=(
                    "- [ ] `audit export --format jsonl` produces valid JSONL\n"
                    "- [ ] `audit export --format csv` produces valid CSV\n"
                    "- [ ] `audit verify` validates hash chain integrity\n"
                    "- [ ] Verification detects tampered entries\n"
                    "- [ ] Verification detects missing entries (gaps)\n"
                    "- [ ] Export supports `--redact` flag for sensitive content"
                ),
                tests=(
                    "- Unit: export format correctness, hash verification logic\n"
                    "- Safety: tampered audit detected, gap detected\n"
                    "- Integration: write audit -> export -> verify round-trip"
                ),
                dependencies=(
                    "- Prerequisite: None (uses existing audit writer)\n"
                    "- Blocks: B5 (compliance mode requires verified audit)"
                ),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P0",
            category="Governance",
            effort="M",
            edition="Pro",
            risk_level="Low",
            target_date="v1.2.0",
            batch=5,
        )
    )

    issues.append(
        Issue(
            id="B3",
            title="feat(policy): Policy pinning + versioning",
            body=build_body(
                phase="G",
                priority="P1",
                category="Governance",
                effort="M",
                edition="Pro",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — version tracking, diff, pinning with migration path",
                recommended_phase="G — governance maturity feature, not blocking GA",
                problem=(
                    "Policy files can be modified at any time with no version tracking. There is no "
                    "way to pin a session to a specific policy version, diff between versions, or "
                    "roll back to a known-good policy. Hot-reload makes this worse — a policy change "
                    "takes effect immediately for all active sessions."
                ),
                solution=(
                    "Add policy versioning and pinning:\n\n"
                    "1. **Version tracking** — hash-based version on every policy load/reload\n"
                    "2. **Version history** — last N versions stored locally\n"
                    "3. **Pin mode** — `atlasbridge run --policy-version <hash>` locks to version\n"
                    "4. **Diff** — `atlasbridge policy diff <v1> <v2>` shows rule changes\n\n"
                    "```bash\n"
                    "atlasbridge policy versions\n"
                    "# v3 (current) 2024-01-15 abc123  10 rules\n"
                    "# v2           2024-01-10 def456   8 rules\n"
                    "atlasbridge policy diff v2 v3\n"
                    "# + rule: auto-approve-safe-plans (new)\n"
                    "# ~ rule: auto-yes (confidence changed: medium -> high)\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/core/policy/versioning.py` — hash, store, diff\n"
                    "- Modify: `src/atlasbridge/core/policy/parser.py` — version on load\n"
                    "- Modify: `src/atlasbridge/core/autopilot/engine.py` — pin support\n"
                    "- Storage: `~/.config/atlasbridge/policy_versions/` directory\n"
                    "- New CLI: `policy versions`, `policy diff`, `run --policy-version`"
                ),
                safety=(
                    "- Pinned sessions must not receive hot-reloaded policies\n"
                    "- Version history is append-only (no history deletion)\n"
                    "- Audit log records policy version for every decision"
                ),
                acceptance=(
                    "- [ ] Policy files receive hash-based version on load\n"
                    "- [ ] Last 10 versions stored locally with metadata\n"
                    "- [ ] `policy versions` lists version history\n"
                    "- [ ] `policy diff` shows rule-level differences\n"
                    "- [ ] `run --policy-version` pins session to specific version\n"
                    "- [ ] Audit log records policy version per decision"
                ),
                tests=(
                    "- Unit: version hashing, diff computation, pin logic\n"
                    "- Integration: version tracking across policy reloads\n"
                    "- Safety: pinned session ignores hot-reload"
                ),
                dependencies=(
                    "- Prerequisite: None\n- Blocks: B11 (drift detection compares versions)"
                ),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Governance",
            effort="M",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.2.0",
            batch=5,
        )
    )

    issues.append(
        Issue(
            id="B13",
            title="feat(policy): Execution guardrails by environment",
            body=build_body(
                phase="G",
                priority="P1",
                category="Governance",
                effort="M",
                edition="Pro",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — environment detection, policy scoping, guard enforcement",
                recommended_phase="G — governance feature for production deployment safety",
                problem=(
                    "Policy rules apply uniformly regardless of environment (dev, staging, production). "
                    "A rule that auto-approves in development could be dangerous in production. There "
                    "is no way to scope rules by environment or enforce stricter guardrails in "
                    "production contexts."
                ),
                solution=(
                    "Add environment-aware policy evaluation:\n\n"
                    "```yaml\n"
                    "policy:\n"
                    "  environment: production  # or: dev, staging, test\n"
                    "  guardrails:\n"
                    "    production:\n"
                    "      max_autonomy: assist  # never full in prod\n"
                    "      require_approval: [shell_command, file_write]\n"
                    "    dev:\n"
                    "      max_autonomy: full\n"
                    "```\n\n"
                    "Environment detected from: explicit config, `ATLASBRIDGE_ENV` var, or git branch."
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/policy/model.py` — environment config section\n"
                    "- Modify: `src/atlasbridge/core/policy/evaluator.py` — guardrail enforcement\n"
                    "- New: `src/atlasbridge/core/policy/environment.py` — detection logic\n"
                    "- Environment set at daemon startup, immutable for session lifetime\n"
                    "- Backward compatible — no environment = no guardrails (existing behavior)"
                ),
                safety=(
                    "- Production guardrails must be enforced even if rules say otherwise\n"
                    "- Environment detection must not be spoofable by agent output\n"
                    "- Audit log records environment for every decision"
                ),
                acceptance=(
                    "- [ ] `environment` config key in policy YAML\n"
                    "- [ ] `guardrails` section scopes behavior by environment\n"
                    "- [ ] `max_autonomy` enforced as ceiling per environment\n"
                    "- [ ] `require_approval` overrides auto-approve rules per environment\n"
                    "- [ ] Environment detected from config, env var, or git branch\n"
                    "- [ ] Audit log records environment context"
                ),
                tests=(
                    "- Unit: environment detection, guardrail enforcement\n"
                    "- Safety: production guardrails override permissive rules\n"
                    "- Integration: full policy evaluation with environment context"
                ),
                dependencies=("- Prerequisite: None\n- Blocks: None"),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Governance",
            effort="M",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.2.0",
            batch=5,
        )
    )

    issues.append(
        Issue(
            id="B10",
            title="feat(cloud): Cloud observe-only mode",
            body=build_body(
                phase="G",
                priority="P1",
                category="SaaS",
                effort="L",
                edition="Pro",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — telemetry pipeline, cloud API, data minimization",
                recommended_phase="G — first cloud feature, builds on local-first foundation",
                problem=(
                    "AtlasBridge is entirely local — there is no way for teams to aggregate "
                    "visibility across multiple developer workstations. Team leads cannot see "
                    "autonomy metrics, policy compliance, or risk patterns across their organization "
                    "without manual log collection.\n\n"
                    "References design predecessor: #104."
                ),
                solution=(
                    "Add an opt-in cloud observe-only mode that sends anonymized telemetry:\n\n"
                    "1. **Telemetry pipeline** — aggregate metrics (not raw prompts) sent to cloud\n"
                    "2. **Data minimization** — only counts, rates, and hashes sent\n"
                    "3. **Opt-in consent** — explicit enable required, off by default\n"
                    "4. **Local-first guarantee** — all features work without cloud\n\n"
                    "```bash\n"
                    "atlasbridge cloud enable --observe-only\n"
                    "atlasbridge cloud status\n"
                    "# Mode: observe-only | Data: metrics only | Endpoint: api.atlasbridge.dev\n"
                    "```"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/cloud/`\n"
                    "  - `telemetry.py` — metric aggregation and batched send\n"
                    "  - `consent.py` — opt-in/opt-out management\n"
                    "  - `client.py` — HTTPS client for cloud API\n"
                    "- New CLI: `atlasbridge cloud enable/disable/status`\n"
                    "- Config: `cloud:` section in config YAML\n"
                    "- No raw prompt data ever leaves the machine"
                ),
                safety=(
                    "- CRITICAL: no raw prompts, responses, or policy content sent to cloud\n"
                    "- Only aggregate metrics: counts, rates, hashes, timestamps\n"
                    "- Opt-in consent with explicit user action required\n"
                    "- Local functionality unaffected if cloud is unreachable\n"
                    "- Telemetry pipeline must not block runtime operations"
                ),
                acceptance=(
                    "- [ ] `cloud enable --observe-only` enables telemetry\n"
                    "- [ ] Only aggregate metrics sent (no raw data)\n"
                    "- [ ] Opt-in consent required, off by default\n"
                    "- [ ] All local features work without cloud connection\n"
                    "- [ ] Telemetry batched and sent asynchronously\n"
                    "- [ ] `cloud status` shows current mode and data types"
                ),
                tests=(
                    "- Unit: metric aggregation, data minimization verification\n"
                    "- Safety: raw prompt data never appears in telemetry payload\n"
                    "- Integration: telemetry pipeline with mock cloud endpoint"
                ),
                dependencies=(
                    "- Prerequisite: C2 (autonomy confidence metrics as data source)\n"
                    "- Design predecessor: #104\n"
                    "- Blocks: None"
                ),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "saas", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="SaaS",
            effort="L",
            edition="Pro",
            risk_level="High",
            target_date="v1.2.0",
            batch=5,
        )
    )

    issues.append(
        Issue(
            id="C3",
            title="feat(governance): Agent behavior contracts",
            body=build_body(
                phase="G",
                priority="P1",
                category="Governance",
                effort="L",
                edition="Pro",
                issue_type="Feature",
                market_segment="Cross-market safety",
                complexity="3/5 — contract schema, runtime enforcement, violation handling",
                recommended_phase="G — governance maturity feature for post-GA adoption",
                problem=(
                    "Policy rules define what AtlasBridge does for individual prompts, but there is "
                    "no way to define behavioral invariants across a session or agent lifecycle. "
                    "Contracts like 'this agent must never execute more than 10 commands per session' "
                    "or 'escalation rate must stay below 20%' cannot be expressed in the current DSL."
                ),
                solution=(
                    "Define agent behavior contracts as session-level invariants:\n\n"
                    "```yaml\n"
                    "contracts:\n"
                    "  - name: command-limit\n"
                    "    invariant: session.auto_execute_count <= 10\n"
                    "    on_violation: pause_and_escalate\n"
                    "  - name: escalation-rate\n"
                    "    invariant: session.escalation_rate <= 0.20\n"
                    "    on_violation: log_warning\n"
                    "  - name: no-destructive\n"
                    "    invariant: not prompt.contains('rm -rf')\n"
                    "    on_violation: reject\n"
                    "```\n\n"
                    "Contracts evaluated continuously, not just per-prompt."
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/governance/contracts.py`\n"
                    "- New model: `BehaviorContract` with invariant expressions\n"
                    "- Modify: policy YAML schema — `contracts` section\n"
                    "- Modify: autopilot engine — contract evaluation after each decision\n"
                    "- Violation actions: pause_and_escalate, log_warning, reject, kill"
                ),
                safety=(
                    "- Contract violations must trigger immediate response\n"
                    "- Contracts are defense-in-depth — they catch what rules miss\n"
                    "- Invariant expressions must be safe (no arbitrary code execution)\n"
                    "- Audit log records all contract violations"
                ),
                acceptance=(
                    "- [ ] `contracts` section in policy YAML\n"
                    "- [ ] Contracts evaluated after every policy decision\n"
                    "- [ ] Violation triggers configured action\n"
                    "- [ ] Session-level counters (auto_execute_count, escalation_rate)\n"
                    "- [ ] Prompt-level invariants (content matching)\n"
                    "- [ ] Audit log records contract violations"
                ),
                tests=(
                    "- Unit: contract parsing, invariant evaluation, violation actions\n"
                    "- Safety: contract violation always triggers action\n"
                    "- Integration: full session with contract enforcement"
                ),
                dependencies=(
                    "- Prerequisite: None\n- Blocks: B6 (enterprise risk engine uses contract data)"
                ),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Governance",
            effort="L",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.2.0",
            batch=5,
        )
    )

    issues.append(
        Issue(
            id="B11",
            title="feat(governance): Drift detection",
            body=build_body(
                phase="G",
                priority="P2",
                category="Governance",
                effort="M",
                edition="Pro",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — baseline capture, continuous comparison, alert system",
                recommended_phase="G — requires policy versioning (B3) and stable metrics",
                problem=(
                    "Over time, agent behavior can drift from expected patterns — either because "
                    "the agent model changed, the policy was modified, or the environment shifted. "
                    "There is no automated detection of behavioral drift. Users discover problems "
                    "only when something goes visibly wrong."
                ),
                solution=(
                    "Implement drift detection by comparing current behavior against a baseline:\n\n"
                    "1. **Baseline capture** — snapshot of expected behavior metrics\n"
                    "2. **Continuous comparison** — compare rolling metrics against baseline\n"
                    "3. **Drift score** — 0-100 indicating deviation from baseline\n"
                    "4. **Alerting** — notify via channel when drift exceeds threshold\n\n"
                    "```bash\n"
                    "atlasbridge drift baseline --capture  # save current as baseline\n"
                    "atlasbridge drift status\n"
                    "# Drift score: 12/100 (low) — escalation rate +3% from baseline\n"
                    "```"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/governance/drift.py`\n"
                    "- Baseline stored as JSON in config directory\n"
                    "- Rolling metrics computed from recent decision trace\n"
                    "- Drift score algorithm: weighted deviation across key metrics\n"
                    "- Alert threshold configurable in policy YAML"
                ),
                safety=(
                    "- Drift detection is informational — does not change runtime behavior\n"
                    "- High drift score could trigger policy review escalation\n"
                    "- Baseline must be tamper-evident (hash-signed)"
                ),
                acceptance=(
                    "- [ ] `drift baseline --capture` saves behavior snapshot\n"
                    "- [ ] `drift status` shows current drift score\n"
                    "- [ ] Drift score from escalation rate, auto-handle rate, confidence distribution\n"
                    "- [ ] Alert sent via channel when drift exceeds threshold\n"
                    "- [ ] Dashboard shows drift trend over time"
                ),
                tests=(
                    "- Unit: drift score calculation, baseline comparison\n"
                    "- Integration: baseline capture -> simulate drift -> detect"
                ),
                dependencies=(
                    "- Prerequisite: B3 (policy versioning), C2 (autonomy metrics)\n- Blocks: None"
                ),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P2",
            category="Governance",
            effort="M",
            edition="Pro",
            risk_level="Low",
            target_date="v1.2.0",
            batch=5,
        )
    )

    issues.append(
        Issue(
            id="A5",
            title="feat(runtime): Multi-agent coordination",
            body=build_body(
                phase="G",
                priority="P2",
                category="Core",
                effort="XL",
                edition="Pro",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="5/5 — concurrent session management, inter-agent messaging, shared state",
                recommended_phase="G — advanced feature, requires stable single-agent runtime",
                problem=(
                    "AtlasBridge manages one agent session at a time. Modern development workflows "
                    "involve multiple AI agents working concurrently — one for code generation, one "
                    "for testing, one for documentation. There is no coordination mechanism to prevent "
                    "conflicts, share context, or orchestrate multi-agent workflows.\n\n"
                    "Related: #153 (multi-agent design discussion)."
                ),
                solution=(
                    "Implement multi-agent coordination:\n\n"
                    "1. **Concurrent sessions** — multiple PTY sessions managed by daemon\n"
                    "2. **Session registry** — track active agents and their state\n"
                    "3. **Coordination protocol** — prevent conflicting file operations\n"
                    "4. **Shared context** — agents can read (not write) shared memory\n"
                    "5. **Orchestrator mode** — define agent workflows in YAML\n\n"
                    "```bash\n"
                    "atlasbridge run claude --session code-gen &\n"
                    "atlasbridge run claude --session test-runner &\n"
                    "atlasbridge agents list\n"
                    "# code-gen: active (3 prompts handled)\n"
                    "# test-runner: active (1 prompt pending)\n"
                    "```"
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/daemon/manager.py` — multi-session support\n"
                    "- Modify: `src/atlasbridge/core/session/manager.py` — concurrent registry\n"
                    "- New: `src/atlasbridge/core/coordination/`\n"
                    "  - `registry.py` — active agent tracking\n"
                    "  - `protocol.py` — conflict prevention\n"
                    "  - `orchestrator.py` — workflow definition and execution\n"
                    "- File locking for shared resource coordination\n"
                    "- Per-session policy evaluation (agents can have different profiles)"
                ),
                safety=(
                    "- Concurrent agents must not interfere with each other's PTY sessions\n"
                    "- Shared context is read-only to prevent corruption\n"
                    "- Each agent evaluated independently by policy\n"
                    "- Kill switch stops ALL agents, not just one\n"
                    "- Audit log tracks which agent made each decision"
                ),
                acceptance=(
                    "- [ ] Multiple `atlasbridge run` sessions can operate concurrently\n"
                    "- [ ] `agents list` shows all active sessions\n"
                    "- [ ] File conflict detection between concurrent agents\n"
                    "- [ ] Shared read-only context between sessions\n"
                    "- [ ] Per-agent policy evaluation with profile support\n"
                    "- [ ] Kill switch stops all agents simultaneously"
                ),
                tests=(
                    "- Unit: session registry, conflict detection\n"
                    "- Integration: two concurrent sessions with mock PTY\n"
                    "- Safety: kill switch stops all agents, conflict detection works"
                ),
                dependencies=(
                    "- Prerequisite: A1 (agent profiles for per-agent config)\n"
                    "- Related: #153\n"
                    "- Blocks: None"
                ),
                milestone="Phase G — v1.2.0",
            ),
            labels=["enhancement", "phase:G-saas"],
            phase="G",
            priority="P2",
            category="Core",
            effort="XL",
            edition="Pro",
            risk_level="High",
            target_date="v1.2.0",
            batch=5,
        )
    )

    return issues


# ---------------------------------------------------------------------------
# Phase H issues (13: 3 epic children + 1 epic + 9 standalone)
# ---------------------------------------------------------------------------


def phase_h_issues() -> list[Issue]:
    issues: list[Issue] = []

    # --- B1 epic children (batch 1) ---
    issues.append(
        Issue(
            id="B1a",
            title="feat(rbac): Role model + permission schema",
            body=build_body(
                phase="H",
                priority="P0",
                category="Governance",
                effort="L",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — role hierarchy, permission model, storage schema",
                recommended_phase="H — enterprise feature, not needed for community/pro editions",
                problem=(
                    "AtlasBridge has no concept of user roles or permissions. Every user with config "
                    "access has full control. In team environments, organizations need to restrict who "
                    "can modify policies, who can approve plans, and who can access audit logs."
                ),
                solution=(
                    "Define a role-based access control model:\n\n"
                    "```python\n"
                    "class Role(BaseModel):\n"
                    "    name: str  # e.g. 'admin', 'operator', 'viewer'\n"
                    "    permissions: list[Permission]\n"
                    "    inherits: list[str] = []  # role inheritance\n\n"
                    "class Permission(BaseModel):\n"
                    "    resource: str  # e.g. 'policy', 'session', 'audit'\n"
                    "    actions: list[str]  # e.g. ['read', 'write', 'approve']\n"
                    "```\n\n"
                    "Stored in SQLite with role assignment table."
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/rbac/`\n"
                    "  - `models.py` — Role, Permission, RoleAssignment\n"
                    "  - `store.py` — SQLite storage for roles and assignments\n"
                    "- Database migration: roles + role_assignments tables\n"
                    "- Default roles: admin, operator, viewer\n"
                    "- Backward compatible — single-user mode has implicit admin"
                ),
                safety=(
                    "- Role model is foundational for all enterprise access control\n"
                    "- Default single-user behavior must not change\n"
                    "- Admin role cannot be deleted or stripped of all permissions"
                ),
                acceptance=(
                    "- [ ] Role and Permission Pydantic models defined\n"
                    "- [ ] SQLite schema for roles and assignments\n"
                    "- [ ] Default roles created on first enterprise setup\n"
                    "- [ ] Role inheritance works correctly\n"
                    "- [ ] Single-user mode unaffected (implicit admin)\n"
                    "- [ ] Unit tests for role model and permission checks"
                ),
                tests=(
                    "- Unit: role model, permission checking, inheritance\n"
                    "- Integration: role storage round-trip in SQLite"
                ),
                dependencies=(
                    "- Prerequisite: None\n- Blocks: B1b (GBAC rules), B1c (enforcement middleware)"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "governance", "phase:H-enterprise"],
            phase="H",
            priority="P0",
            category="Governance",
            effort="L",
            edition="Enterprise",
            risk_level="Medium",
            target_date="v2.0.0",
            batch=1,
        )
    )

    issues.append(
        Issue(
            id="B1b",
            title="feat(rbac): GBAC policy rules",
            body=build_body(
                phase="H",
                priority="P0",
                category="Governance",
                effort="L",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — extends policy DSL with group-based access criteria",
                recommended_phase="H — enterprise feature requiring role model (B1a)",
                problem=(
                    "Policy rules cannot currently reference user identity or group membership. "
                    "In multi-user environments, different teams need different policy rules. "
                    "GBAC (Group-Based Access Control) enables policy scoping by team or group "
                    "without duplicating entire policy files."
                ),
                solution=(
                    "Add group-based match criteria to the policy DSL:\n\n"
                    "```yaml\n"
                    "rules:\n"
                    "  - name: dev-team-auto-approve\n"
                    "    match:\n"
                    "      user_group: developers\n"
                    "      prompt_type: yes_no\n"
                    "      confidence: high\n"
                    "    action: auto_respond\n"
                    "    params:\n"
                    "      response: 'y'\n"
                    "  - name: ops-team-escalate\n"
                    "    match:\n"
                    "      user_group: operations\n"
                    "    action: require_human\n"
                    "```"
                ),
                architecture=(
                    "- Modify: `src/atlasbridge/core/policy/model.py` — `user_group`, `user_role` criteria\n"
                    "- Modify: `src/atlasbridge/core/policy/evaluator.py` — group context in evaluation\n"
                    "- Uses role model from B1a for group resolution\n"
                    "- Backward compatible — missing group context = match always"
                ),
                safety=(
                    "- Group mismatch must not silently skip rules\n"
                    "- Missing group context defaults to most restrictive behavior\n"
                    "- Audit log records user identity and group for every decision"
                ),
                acceptance=(
                    "- [ ] `user_group` and `user_role` match criteria in policy DSL\n"
                    "- [ ] Evaluator resolves group membership from role model\n"
                    "- [ ] Rules with group criteria skip non-matching users\n"
                    "- [ ] Missing group context defaults to escalate\n"
                    "- [ ] Policy test command supports `--user-group` flag\n"
                    "- [ ] Audit log records user/group context"
                ),
                tests=(
                    "- Unit: group matching, role resolution\n"
                    "- Safety: missing group context escalates\n"
                    "- Integration: policy evaluation with group context"
                ),
                dependencies=(
                    "- Prerequisite: B1a (role model)\n- Blocks: B1c (enforcement middleware)"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "governance", "phase:H-enterprise"],
            phase="H",
            priority="P0",
            category="Governance",
            effort="L",
            edition="Enterprise",
            risk_level="Medium",
            target_date="v2.0.0",
            batch=1,
        )
    )

    issues.append(
        Issue(
            id="B1c",
            title="feat(rbac): RBAC enforcement middleware + audit integration",
            body=build_body(
                phase="H",
                priority="P0",
                category="Security",
                effort="L",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — middleware layer, audit integration, permission enforcement",
                recommended_phase="H — enterprise feature requiring role model + GBAC",
                problem=(
                    "With roles defined (B1a) and group-based rules available (B1b), there is still "
                    "no enforcement layer that prevents unauthorized access to CLI commands, dashboard "
                    "endpoints, or configuration changes. The permission model exists but is not "
                    "enforced at system boundaries."
                ),
                solution=(
                    "Implement enforcement middleware for all access points:\n\n"
                    "1. **CLI middleware** — check permissions before executing commands\n"
                    "2. **Dashboard middleware** — FastAPI dependency for route-level auth\n"
                    "3. **Channel middleware** — verify sender identity against roles\n"
                    "4. **Audit integration** — every permission check logged\n\n"
                    "```python\n"
                    "# CLI enforcement\n"
                    "@require_permission('policy', 'write')\n"
                    "def policy_validate(ctx, ...): ...\n\n"
                    "# Dashboard enforcement\n"
                    "@app.get('/api/audit', dependencies=[Depends(require_role('viewer'))])\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/core/rbac/middleware.py` — enforcement decorators\n"
                    "- Modify: CLI commands — add permission decorators\n"
                    "- Modify: dashboard routes — add auth dependencies\n"
                    "- Modify: channel message handling — sender identity check\n"
                    "- Modify: audit writer — permission check events"
                ),
                safety=(
                    "- Permission check failure must block the operation entirely\n"
                    "- No silent degradation — denied = denied\n"
                    "- All permission checks logged to audit trail\n"
                    "- Admin role bypass for emergency access (logged separately)"
                ),
                acceptance=(
                    "- [ ] CLI commands gated by permission decorators\n"
                    "- [ ] Dashboard routes gated by role-based auth\n"
                    "- [ ] Channel messages verified against sender roles\n"
                    "- [ ] Permission denial logged to audit trail\n"
                    "- [ ] Admin emergency bypass with audit logging\n"
                    "- [ ] Single-user mode unaffected (all permissions granted)"
                ),
                tests=(
                    "- Unit: middleware permission checking\n"
                    "- Safety: denied permission blocks operation\n"
                    "- Integration: full request with role-based auth"
                ),
                dependencies=(
                    "- Prerequisite: B1a (role model), B1b (GBAC rules)\n"
                    "- Blocks: B1 (RBAC epic completion)"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "security", "phase:H-enterprise"],
            phase="H",
            priority="P0",
            category="Security",
            effort="L",
            edition="Enterprise",
            risk_level="High",
            target_date="v2.0.0",
            batch=1,
        )
    )

    # --- B1 epic (batch 2) ---
    issues.append(
        Issue(
            id="B1",
            title="epic(rbac): Full RBAC + GBAC",
            body=build_body(
                phase="H",
                priority="P0",
                category="Governance",
                effort="XL",
                edition="Enterprise",
                issue_type="Epic",
                market_segment="Enterprise governance",
                complexity="5/5 — role hierarchy, group-based policy, enforcement across all surfaces",
                recommended_phase="H — enterprise feature, foundational for multi-user deployment",
                problem=(
                    "AtlasBridge is single-user with no access control. Enterprise deployments need "
                    "role-based access control (RBAC) to restrict who can modify policies, approve "
                    "plans, access audit logs, and manage configuration. Group-based access control "
                    "(GBAC) extends this to team-level policy scoping."
                ),
                solution=(
                    "Implement full RBAC + GBAC in three phases:\n"
                    "1. **Role model** — roles, permissions, inheritance, storage\n"
                    "2. **GBAC rules** — group-based match criteria in policy DSL\n"
                    "3. **Enforcement** — middleware for CLI, dashboard, channels\n\n"
                    "## Child Issues\n"
                    "- {B1a} — Role model + permission schema\n"
                    "- {B1b} — GBAC policy rules\n"
                    "- {B1c} — RBAC enforcement middleware + audit integration"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/core/rbac/`\n"
                    "- Database migration: roles + role_assignments tables\n"
                    "- Enforcement middleware across CLI, dashboard, channels\n"
                    "- Backward compatible — single-user = implicit admin"
                ),
                safety=(
                    "- RBAC is the enterprise security foundation\n"
                    "- Permission denial must be absolute — no bypass except admin emergency\n"
                    "- All access control decisions logged to audit trail"
                ),
                acceptance=(
                    "- [ ] All three child issues completed\n"
                    "- [ ] End-to-end: create role -> assign user -> verify access control\n"
                    "- [ ] Single-user mode backward compatible\n"
                    "- [ ] Enterprise deployment documentation"
                ),
                tests="- See child issues for detailed test requirements",
                dependencies=("- Prerequisite: None\n- Blocks: B2 (SSO), B7 (multi-workspace)"),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "epic", "governance", "phase:H-enterprise"],
            phase="H",
            priority="P0",
            category="Governance",
            effort="XL",
            edition="Enterprise",
            risk_level="High",
            target_date="v2.0.0",
            batch=2,
            epic_children=["B1a", "B1b", "B1c"],
        )
    )

    # --- Phase H standalone (batch 6) ---
    issues.append(
        Issue(
            id="B9",
            title="feat(governance): Enterprise kill switch",
            body=build_body(
                phase="H",
                priority="P0",
                category="Governance",
                effort="M",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — central kill signal, propagation to all sessions, audit trail",
                recommended_phase="H — enterprise safety feature for organization-wide control",
                problem=(
                    "The existing kill switch stops a single AtlasBridge instance. In enterprise "
                    "deployments with multiple developers and agents, there is no way for a security "
                    "team to halt all AtlasBridge instances across the organization simultaneously. "
                    "A compromised agent or policy misconfiguration requires manual intervention on "
                    "each workstation."
                ),
                solution=(
                    "Implement an enterprise kill switch:\n\n"
                    "1. **Central signal** — kill command distributed via cloud API or local network\n"
                    "2. **Instant halt** — all sessions pause immediately on kill signal\n"
                    "3. **Selective resume** — individual sessions can be reviewed and resumed\n"
                    "4. **Audit trail** — kill event logged with reason and initiator\n\n"
                    "```bash\n"
                    "# Admin kills all instances\n"
                    "atlasbridge enterprise kill --reason 'policy review required' --scope all\n"
                    "# Developer sees:\n"
                    "# ENTERPRISE KILL: All sessions paused by admin. Reason: policy review required\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/enterprise/kill_switch.py`\n"
                    "- Signal distribution: cloud API endpoint or local file-based signal\n"
                    "- Modify: daemon manager — check kill signal on every decision\n"
                    "- Modify: autopilot engine — respect enterprise kill state\n"
                    "- Resume requires explicit admin action"
                ),
                safety=(
                    "- Kill switch must be non-bypassable — highest priority signal\n"
                    "- Kill signal must propagate within seconds\n"
                    "- Audit log records kill event, reason, initiator, and affected sessions\n"
                    "- Resume requires authentication"
                ),
                acceptance=(
                    "- [ ] Enterprise kill command halts all local sessions\n"
                    "- [ ] Kill signal propagates to all active instances\n"
                    "- [ ] Sessions pause immediately (no pending operations complete)\n"
                    "- [ ] Selective resume with admin authentication\n"
                    "- [ ] Full audit trail for kill/resume events\n"
                    "- [ ] Existing single-instance kill switch unaffected"
                ),
                tests=(
                    "- Unit: kill signal handling, session pause logic\n"
                    "- Safety: kill signal non-bypassable\n"
                    "- Integration: multi-session kill and selective resume"
                ),
                dependencies=("- Prerequisite: B1 (RBAC for admin authentication)\n- Blocks: None"),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "governance", "phase:H-enterprise"],
            phase="H",
            priority="P0",
            category="Governance",
            effort="M",
            edition="Enterprise",
            risk_level="High",
            target_date="v2.0.0",
            batch=6,
        )
    )

    issues.append(
        Issue(
            id="B2",
            title="feat(auth): SSO integration (Azure AD, Okta, Google)",
            body=build_body(
                phase="H",
                priority="P1",
                category="Security",
                effort="L",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="4/5 — OIDC/SAML flows, token management, identity mapping",
                recommended_phase="H — enterprise authentication, requires RBAC foundation",
                problem=(
                    "Enterprise organizations use centralized identity providers (Azure AD, Okta, "
                    "Google Workspace) for access management. AtlasBridge currently has no "
                    "authentication beyond channel identity (Telegram user ID, Slack user ID). "
                    "This means user identity cannot be verified against corporate directories.\n\n"
                    "Supersedes #86 (SSO stub). References #107 (design placeholder)."
                ),
                solution=(
                    "Implement SSO integration via OIDC:\n\n"
                    "1. **OIDC client** — standard OpenID Connect flow\n"
                    "2. **Provider config** — Azure AD, Okta, Google pre-configured\n"
                    "3. **Identity mapping** — SSO identity -> AtlasBridge role assignment\n"
                    "4. **Token management** — secure token storage and refresh\n\n"
                    "```yaml\n"
                    "auth:\n"
                    "  provider: azure_ad\n"
                    "  tenant_id: 'abc-123'\n"
                    "  client_id: 'def-456'\n"
                    "  group_mapping:\n"
                    "    'Engineering': developers\n"
                    "    'DevOps': operations\n"
                    "```"
                ),
                architecture=(
                    "- New module: `src/atlasbridge/enterprise/auth/`\n"
                    "  - `oidc.py` — OIDC client implementation\n"
                    "  - `providers.py` — Azure AD, Okta, Google config\n"
                    "  - `mapping.py` — identity -> role mapping\n"
                    "  - `tokens.py` — secure token storage\n"
                    "- Modify: RBAC middleware — accept SSO identity\n"
                    "- Config: `auth:` section in enterprise config"
                ),
                safety=(
                    "- Token storage must use system keyring (never plaintext)\n"
                    "- OIDC flow must validate tokens cryptographically\n"
                    "- Identity mapping must be explicit (no auto-provisioning)\n"
                    "- Failed authentication = no access (fail-closed)"
                ),
                acceptance=(
                    "- [ ] OIDC flow works with Azure AD\n"
                    "- [ ] OIDC flow works with Okta\n"
                    "- [ ] OIDC flow works with Google Workspace\n"
                    "- [ ] SSO identity mapped to AtlasBridge roles\n"
                    "- [ ] Tokens stored securely in system keyring\n"
                    "- [ ] Token refresh handled automatically\n"
                    "- [ ] Failed auth blocks all access"
                ),
                tests=(
                    "- Unit: OIDC token validation, identity mapping\n"
                    "- Integration: mock OIDC provider flow\n"
                    "- Safety: expired/invalid tokens rejected"
                ),
                dependencies=(
                    "- Prerequisite: B1 (RBAC for role mapping target)\n"
                    "- Supersedes: #86\n"
                    "- References: #107\n"
                    "- Blocks: None"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "security", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="Security",
            effort="L",
            edition="Enterprise",
            risk_level="High",
            target_date="v2.0.0",
            batch=6,
        )
    )

    issues.append(
        Issue(
            id="B6",
            title="feat(governance): Enterprise risk engine",
            body=build_body(
                phase="H",
                priority="P1",
                category="Governance",
                effort="L",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="4/5 — multi-signal risk scoring, threshold management, alerting",
                recommended_phase="H — enterprise governance, requires metrics + contracts foundation",
                problem=(
                    "Enterprise organizations need a holistic risk assessment that combines multiple "
                    "signals: autonomy confidence metrics, contract violations, drift scores, escalation "
                    "rates, and audit anomalies. Currently these signals exist independently with no "
                    "unified risk score or alerting framework."
                ),
                solution=(
                    "Build an enterprise risk engine that aggregates signals:\n\n"
                    "1. **Risk score** — 0-100 composite from multiple signals\n"
                    "2. **Signal weights** — configurable importance per signal\n"
                    "3. **Threshold alerting** — notify when risk exceeds configured level\n"
                    "4. **Trend analysis** — risk trajectory over time\n"
                    "5. **Dashboard integration** — real-time risk dashboard widget\n\n"
                    "```yaml\n"
                    "risk_engine:\n"
                    "  signals:\n"
                    "    escalation_rate: { weight: 0.3, threshold: 0.4 }\n"
                    "    contract_violations: { weight: 0.3, threshold: 2 }\n"
                    "    drift_score: { weight: 0.2, threshold: 50 }\n"
                    "    low_confidence_rate: { weight: 0.2, threshold: 0.3 }\n"
                    "  alert_threshold: 70\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/enterprise/risk/`\n"
                    "  - `engine.py` — signal aggregation and scoring\n"
                    "  - `signals.py` — signal providers\n"
                    "  - `alerts.py` — threshold-based alerting\n"
                    "- Modify: dashboard — risk score widget\n"
                    "- Config: `risk_engine:` section in enterprise config\n"
                    "- Computed on-demand from existing data sources"
                ),
                safety=(
                    "- Risk engine is advisory — does not modify runtime behavior by default\n"
                    "- Can optionally trigger enterprise kill switch at critical risk\n"
                    "- All risk assessments logged to audit trail"
                ),
                acceptance=(
                    "- [ ] Composite risk score computed from multiple signals\n"
                    "- [ ] Signal weights configurable per deployment\n"
                    "- [ ] Alerting when risk exceeds threshold\n"
                    "- [ ] Risk trend visible in dashboard\n"
                    "- [ ] CLI command: `atlasbridge risk status`\n"
                    "- [ ] Optional integration with enterprise kill switch"
                ),
                tests=(
                    "- Unit: risk scoring, signal aggregation, threshold detection\n"
                    "- Integration: risk engine with sample data from all signal sources"
                ),
                dependencies=(
                    "- Prerequisite: C2 (metrics), C3 (contracts), B11 (drift)\n- Blocks: None"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "governance", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="Governance",
            effort="L",
            edition="Enterprise",
            risk_level="Medium",
            target_date="v2.0.0",
            batch=6,
        )
    )

    issues.append(
        Issue(
            id="B7",
            title="feat(runtime): Multi-workspace isolation",
            body=build_body(
                phase="H",
                priority="P1",
                category="Core",
                effort="XL",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="5/5 — workspace boundaries, config isolation, cross-workspace prevention",
                recommended_phase="H — enterprise feature requiring RBAC and multi-agent foundations",
                problem=(
                    "AtlasBridge operates in a single workspace context. Enterprise organizations "
                    "with multiple projects need isolation between workspaces — different policies, "
                    "different agent profiles, different audit trails. Currently there is no boundary "
                    "between projects running on the same machine or across an organization."
                ),
                solution=(
                    "Implement workspace isolation:\n\n"
                    "1. **Workspace model** — named, isolated config + data directories\n"
                    "2. **Workspace switching** — `atlasbridge workspace use <name>`\n"
                    "3. **Isolation enforcement** — sessions cannot access cross-workspace data\n"
                    "4. **Policy isolation** — each workspace has independent policy file\n"
                    "5. **Audit isolation** — per-workspace audit trails\n\n"
                    "```bash\n"
                    "atlasbridge workspace create prod-backend\n"
                    "atlasbridge workspace use prod-backend\n"
                    "atlasbridge workspace list\n"
                    "# * prod-backend  (active, 3 sessions, policy v2)\n"
                    "#   staging       (idle, 0 sessions, policy v1)\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/enterprise/workspace/`\n"
                    "  - `models.py` — Workspace model\n"
                    "  - `manager.py` — CRUD, switching, isolation\n"
                    "  - `isolation.py` — cross-workspace prevention\n"
                    "- Modify: config paths — workspace-scoped directories\n"
                    "- Modify: database — per-workspace SQLite files\n"
                    "- Modify: daemon — workspace context on startup"
                ),
                safety=(
                    "- Cross-workspace data access must be impossible\n"
                    "- Workspace switching requires appropriate permissions\n"
                    "- Audit trail per workspace prevents information leakage\n"
                    "- Default workspace for backward compatibility"
                ),
                acceptance=(
                    "- [ ] Workspaces created with isolated config + data directories\n"
                    "- [ ] `workspace use` switches active workspace\n"
                    "- [ ] Sessions bound to workspace at creation time\n"
                    "- [ ] Cross-workspace data access prevented\n"
                    "- [ ] Per-workspace policy and audit files\n"
                    "- [ ] Default workspace for single-workspace backward compat"
                ),
                tests=(
                    "- Unit: workspace model, isolation checks\n"
                    "- Safety: cross-workspace access prevention\n"
                    "- Integration: workspace lifecycle (create -> use -> verify isolation)"
                ),
                dependencies=(
                    "- Prerequisite: B1 (RBAC for workspace permissions), A5 (multi-agent)\n"
                    "- Blocks: None"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="Core",
            effort="XL",
            edition="Enterprise",
            risk_level="High",
            target_date="v2.0.0",
            batch=6,
        )
    )

    issues.append(
        Issue(
            id="B5",
            title="feat(governance): Compliance mode (SOC2/ISO)",
            body=build_body(
                phase="H",
                priority="P2",
                category="Governance",
                effort="L",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="4/5 — compliance frameworks, evidence collection, report generation",
                recommended_phase="H — enterprise compliance, requires audit export + RBAC",
                problem=(
                    "Organizations subject to SOC2, ISO 27001, or similar compliance frameworks "
                    "need to demonstrate that AI agent operations are controlled, auditable, and "
                    "within defined parameters. AtlasBridge has the raw data (audit logs, decisions) "
                    "but no compliance-oriented reporting or evidence collection."
                ),
                solution=(
                    "Implement compliance mode with framework-specific features:\n\n"
                    "1. **Evidence collection** — automated gathering of compliance-relevant data\n"
                    "2. **Control mapping** — map AtlasBridge features to compliance controls\n"
                    "3. **Report generation** — periodic compliance reports\n"
                    "4. **Continuous monitoring** — alert on compliance-relevant events\n\n"
                    "```bash\n"
                    "atlasbridge compliance enable --framework soc2\n"
                    "atlasbridge compliance report --period 2024-Q1\n"
                    "# SOC2 Compliance Report — 2024 Q1\n"
                    "# CC6.1 (Logical Access): PASS — RBAC enforced, 0 unauthorized access\n"
                    "# CC7.2 (System Monitoring): PASS — audit chain verified, no gaps\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/enterprise/compliance/`\n"
                    "  - `frameworks.py` — SOC2, ISO control definitions\n"
                    "  - `evidence.py` — automated evidence collection\n"
                    "  - `reports.py` — report generation\n"
                    "  - `monitoring.py` — continuous compliance checks\n"
                    "- Uses: audit export (B4), RBAC (B1), risk engine (B6)\n"
                    "- Config: `compliance:` section in enterprise config"
                ),
                safety=(
                    "- Compliance reports must be accurate — false positives unacceptable\n"
                    "- Evidence must be tamper-evident (hash-signed)\n"
                    "- Report generation is read-only — no side effects"
                ),
                acceptance=(
                    "- [ ] SOC2 control mapping defined\n"
                    "- [ ] ISO 27001 control mapping defined\n"
                    "- [ ] Automated evidence collection from audit + decision data\n"
                    "- [ ] Quarterly compliance report generation\n"
                    "- [ ] Continuous monitoring for compliance-relevant events\n"
                    "- [ ] Dashboard compliance status widget"
                ),
                tests=(
                    "- Unit: control mapping, evidence collection, report generation\n"
                    "- Integration: compliance report with sample data"
                ),
                dependencies=(
                    "- Prerequisite: B4 (audit export), B1 (RBAC), B6 (risk engine)\n- Blocks: None"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "governance", "phase:H-enterprise"],
            phase="H",
            priority="P2",
            category="Governance",
            effort="L",
            edition="Enterprise",
            risk_level="Medium",
            target_date="v2.0.0",
            batch=6,
        )
    )

    issues.append(
        Issue(
            id="B8",
            title="feat(dashboard): Enterprise dashboard metrics",
            body=build_body(
                phase="H",
                priority="P2",
                category="UX",
                effort="M",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="2/5 — dashboard views over existing enterprise data",
                recommended_phase="H — enterprise UX, requires enterprise data sources",
                problem=(
                    "The local dashboard shows per-instance data. Enterprise deployments need "
                    "aggregated views across all instances: organization-wide risk scores, "
                    "team-level autonomy metrics, RBAC activity, and compliance status. These "
                    "views require data from enterprise-specific modules."
                ),
                solution=(
                    "Extend the dashboard with enterprise views:\n\n"
                    "1. **Organization overview** — aggregate metrics across instances\n"
                    "2. **Team dashboard** — per-team autonomy and risk metrics\n"
                    "3. **RBAC activity** — permission grants, denials, role changes\n"
                    "4. **Compliance dashboard** — real-time compliance control status\n"
                    "5. **Workspace comparison** — side-by-side workspace metrics\n\n"
                    "Enterprise routes under `/dashboard/enterprise/`."
                ),
                architecture=(
                    "- New templates: `src/atlasbridge/dashboard/templates/enterprise/`\n"
                    "- Modify: `src/atlasbridge/dashboard/app.py` — enterprise routes\n"
                    "- Data sources: risk engine, RBAC, compliance, workspace metrics\n"
                    "- Gated by enterprise edition check"
                ),
                safety=(
                    "- Enterprise views require appropriate RBAC permissions\n"
                    "- Cross-workspace data only visible to organization admins\n"
                    "- Dashboard access logged to audit trail"
                ),
                acceptance=(
                    "- [ ] Organization overview dashboard with aggregate metrics\n"
                    "- [ ] Team-level metrics dashboard\n"
                    "- [ ] RBAC activity view\n"
                    "- [ ] Compliance status dashboard\n"
                    "- [ ] Workspace comparison view\n"
                    "- [ ] Enterprise routes gated by edition + RBAC"
                ),
                tests=(
                    "- Unit: metric aggregation for enterprise views\n"
                    "- Integration: dashboard routes with enterprise test data"
                ),
                dependencies=(
                    "- Prerequisite: B1 (RBAC), B6 (risk engine), A4 (risk heatmap)\n- Blocks: None"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P2",
            category="UX",
            effort="M",
            edition="Enterprise",
            risk_level="Low",
            target_date="v2.0.0",
            batch=6,
        )
    )

    issues.append(
        Issue(
            id="B14",
            title="feat(governance): Change impact analysis",
            body=build_body(
                phase="H",
                priority="P2",
                category="Governance",
                effort="L",
                edition="Enterprise",
                issue_type="Feature",
                market_segment="Enterprise governance",
                complexity="3/5 — policy diff analysis, simulation, impact scoring",
                recommended_phase="H — enterprise governance, requires policy versioning + replay",
                problem=(
                    "When a policy change is proposed, there is no way to assess its impact before "
                    "deploying it. Will the change increase auto-execution? Will it break existing "
                    "workflows? How many sessions would be affected? Enterprise organizations need "
                    "impact analysis before rolling out policy changes."
                ),
                solution=(
                    "Implement change impact analysis for policy modifications:\n\n"
                    "1. **Impact simulation** — replay recent sessions against proposed policy\n"
                    "2. **Impact score** — % of decisions that would change\n"
                    "3. **Affected sessions** — list sessions impacted by the change\n"
                    "4. **Risk assessment** — would the change increase or decrease risk?\n\n"
                    "```bash\n"
                    "atlasbridge policy impact --proposed new-policy.yaml\n"
                    "# Impact analysis (last 7 days, 342 sessions):\n"
                    "# Decisions changed: 12% (41/342)\n"
                    "# Risk delta: +3 (low -> low, no threshold crossed)\n"
                    "# Newly auto-approved: 28 prompts\n"
                    "# Newly escalated: 13 prompts\n"
                    "```"
                ),
                architecture=(
                    "- New: `src/atlasbridge/enterprise/impact/`\n"
                    "  - `analyzer.py` — impact simulation engine\n"
                    "  - `scoring.py` — impact score computation\n"
                    "  - `report.py` — impact report generation\n"
                    "- Uses: replay engine (C1), policy versioning (B3)\n"
                    "- New CLI: `atlasbridge policy impact --proposed <file>`"
                ),
                safety=(
                    "- Impact analysis is read-only — no side effects\n"
                    "- Simulation uses replay engine (no PTY interaction)\n"
                    "- Impact report may contain prompt content — redaction option"
                ),
                acceptance=(
                    "- [ ] `policy impact` replays recent sessions against proposed policy\n"
                    "- [ ] Impact score shows % of decisions changed\n"
                    "- [ ] Affected sessions listed\n"
                    "- [ ] Risk delta computed\n"
                    "- [ ] Report exportable as JSON/CSV\n"
                    "- [ ] Redaction option for sensitive content"
                ),
                tests=(
                    "- Unit: impact scoring, risk delta computation\n"
                    "- Integration: impact analysis with sample session data"
                ),
                dependencies=(
                    "- Prerequisite: C1 (replay engine), B3 (policy versioning)\n- Blocks: None"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "governance", "phase:H-enterprise"],
            phase="H",
            priority="P2",
            category="Governance",
            effort="L",
            edition="Enterprise",
            risk_level="Low",
            target_date="v2.0.0",
            batch=6,
        )
    )

    issues.append(
        Issue(
            id="A9",
            title="feat(config): Project templates",
            body=build_body(
                phase="H",
                priority="P3",
                category="UX",
                effort="S",
                edition="Community",
                issue_type="Feature",
                market_segment="Developer tooling",
                complexity="1/5 — template files + CLI scaffolding",
                recommended_phase="H — UX convenience, low priority",
                problem=(
                    "New AtlasBridge users must manually create policy files, configure adapters, "
                    "and set up profiles from scratch. There are no project templates that provide "
                    "sensible defaults for common use cases (web development, data science, DevOps)."
                ),
                solution=(
                    "Add project templates with pre-configured policies and profiles:\n\n"
                    "```bash\n"
                    "atlasbridge init --template web-dev\n"
                    "# Created:\n"
                    "#   policy.yaml (web dev defaults — auto-approve linting, escalate deploys)\n"
                    "#   profiles/claude-code.yaml (safe refactoring profile)\n"
                    "#   .atlasbridge/config.yaml (sensible defaults)\n"
                    "```\n\n"
                    "Built-in templates: `web-dev`, `data-science`, `devops`, `minimal`, `strict`."
                ),
                architecture=(
                    "- New: `src/atlasbridge/templates/` — template files\n"
                    "- New CLI: `atlasbridge init --template <name>`\n"
                    "- Templates are static YAML files bundled with the package\n"
                    "- Template customization via prompts during init"
                ),
                safety=(
                    "- Templates must default to safe settings (assist mode, conservative policies)\n"
                    "- `strict` template enables maximum restrictions\n"
                    "- Templates must not overwrite existing config without confirmation"
                ),
                acceptance=(
                    "- [ ] `atlasbridge init --template <name>` scaffolds project\n"
                    "- [ ] 5 built-in templates: web-dev, data-science, devops, minimal, strict\n"
                    "- [ ] Templates include policy, profile, and config files\n"
                    "- [ ] Existing config not overwritten without confirmation\n"
                    "- [ ] `atlasbridge init --list` shows available templates"
                ),
                tests=(
                    "- Unit: template rendering, config generation\n"
                    "- Integration: init flow with each template"
                ),
                dependencies=("- Prerequisite: A1 (agent profiles)\n- Blocks: None"),
                milestone="Phase H — v2.0.0",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P3",
            category="UX",
            effort="S",
            edition="Community",
            risk_level="Low",
            target_date="v2.0.0",
            batch=6,
        )
    )

    issues.append(
        Issue(
            id="B15",
            title="docs(enterprise): Enterprise deployment model",
            body=build_body(
                phase="H",
                priority="P3",
                category="Docs",
                effort="S",
                edition="Enterprise",
                issue_type="Enhancement",
                market_segment="Enterprise governance",
                complexity="1/5 — documentation only",
                recommended_phase="H — accompanies enterprise features",
                problem=(
                    "As enterprise features are built, there is no comprehensive deployment guide "
                    "for organizations. Individual feature docs exist, but there is no end-to-end "
                    "guide covering architecture, RBAC setup, SSO configuration, workspace isolation, "
                    "compliance reporting, and operational best practices."
                ),
                solution=(
                    "Write a comprehensive enterprise deployment guide:\n\n"
                    "1. **Architecture overview** — enterprise topology and data flow\n"
                    "2. **Deployment guide** — step-by-step setup for enterprise features\n"
                    "3. **RBAC cookbook** — role design patterns for common org structures\n"
                    "4. **SSO integration guide** — per-provider setup instructions\n"
                    "5. **Compliance setup** — framework-specific configuration\n"
                    "6. **Operations runbook** — monitoring, alerting, incident response\n\n"
                    "Published as `docs/enterprise/` directory."
                ),
                architecture=(
                    "- New: `docs/enterprise/` directory\n"
                    "  - `architecture.md` — enterprise topology\n"
                    "  - `deployment.md` — setup guide\n"
                    "  - `rbac-cookbook.md` — role design patterns\n"
                    "  - `sso-guide.md` — per-provider SSO setup\n"
                    "  - `compliance-setup.md` — framework configuration\n"
                    "  - `operations.md` — monitoring and incident response"
                ),
                safety=(
                    "- Documentation must not include real credentials or tokens\n"
                    "- Security best practices emphasized throughout\n"
                    "- Example configs use placeholder values"
                ),
                acceptance=(
                    "- [ ] Enterprise architecture overview document\n"
                    "- [ ] Step-by-step deployment guide\n"
                    "- [ ] RBAC design cookbook with examples\n"
                    "- [ ] SSO integration guide for Azure AD, Okta, Google\n"
                    "- [ ] Compliance configuration guide\n"
                    "- [ ] Operations runbook with monitoring guidance"
                ),
                tests="- Documentation review (no code tests)",
                dependencies=(
                    "- Prerequisite: B1, B2, B5, B7 (enterprise features)\n- Blocks: None"
                ),
                milestone="Phase H — v2.0.0",
            ),
            labels=["documentation", "phase:H-enterprise"],
            phase="H",
            priority="P3",
            category="Docs",
            effort="S",
            edition="Enterprise",
            risk_level="Low",
            target_date="v2.0.0",
            batch=6,
        )
    )

    return issues


# ---------------------------------------------------------------------------
# Execution engine
# ---------------------------------------------------------------------------


def all_issues() -> list[Issue]:
    """Return all 37 issues from all phases."""
    return phase_e_issues() + phase_f_issues() + phase_g_issues() + phase_h_issues()


def validate_all(issues: list[Issue]) -> None:
    """Check prohibited terms in all issue bodies and titles."""
    for issue in issues:
        check_prohibited(issue.title, f"title of {issue.id}")
        check_prohibited(issue.body, f"body of {issue.id}")
    print(f"Validated {len(issues)} issues — no prohibited terms found.")


def create_issue(issue: Issue, *, dry_run: bool = False) -> int | None:
    """Create a GitHub issue. Returns issue number or None for dry run."""
    if dry_run:
        print(f"[DRY RUN] Would create: {issue.title}")
        print(f"  Labels: {', '.join(issue.labels)}")
        print(f"  Phase: {issue.phase} | Priority: {issue.priority} | Effort: {issue.effort}")
        return None

    label_args = []
    for label in issue.labels:
        label_args.extend(["--label", label])

    result = subprocess.run(
        ["gh", "issue", "create", "--title", issue.title, "--body", issue.body, *label_args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"FAILED to create {issue.id}: {result.stderr}", file=sys.stderr)
        return None

    # Parse issue number from URL
    url = result.stdout.strip()
    number = int(url.rstrip("/").split("/")[-1])
    issue.gh_number = number
    print(f"Created #{number}: {issue.title}")
    return number


def add_to_project_board(issue: Issue, *, dry_run: bool = False) -> None:
    """Add issue to project board and set all fields."""
    if issue.gh_number is None:
        return

    try:
        node_id = get_issue_node_id(issue.gh_number)
        item_id = add_item_to_project(node_id, dry_run=dry_run)
        if item_id is None:
            return

        print(f"  Added #{issue.gh_number} to project board")

        set_single_select_field(item_id, STATUS, "Backlog", dry_run=dry_run)
        set_single_select_field(item_id, PHASE, issue.phase, dry_run=dry_run)
        set_single_select_field(item_id, PRIORITY, issue.priority, dry_run=dry_run)
        set_single_select_field(item_id, CATEGORY, issue.category, dry_run=dry_run)
        set_single_select_field(item_id, EFFORT, issue.effort, dry_run=dry_run)
        set_single_select_field(item_id, EDITION, issue.edition, dry_run=dry_run)

        # Risk level
        risk = _effort_to_risk(issue)
        set_single_select_field(item_id, RISK_LEVEL, risk, dry_run=dry_run)

        # Target date as text
        # Target date is a Date field — use date mutation with ISO date
        target_dates = {
            "v1.0.0": "2026-06-01",
            "v1.1.0": "2026-09-01",
            "v1.2.0": "2027-01-01",
            "v2.0.0": "2027-06-01",
        }
        date_val = target_dates.get(issue.target_date)
        if date_val:
            _set_date_field(item_id, TARGET_DATE_FIELD_ID, date_val, dry_run=dry_run)

    except Exception as e:
        print(f"  WARNING: project board setup failed for #{issue.gh_number}: {e}", file=sys.stderr)


def _set_date_field(
    item_id: str,
    field_id: str,
    date_value: str,
    *,
    dry_run: bool = False,
) -> None:
    """Set a date field on a project item. date_value must be ISO format (YYYY-MM-DD).

    Uses raw JSON input to pass Date scalar correctly.
    """
    from project_fields import _RATE_LIMIT_DELAY, PROJECT_ID, redact_for_logging

    if dry_run:
        print(f"[DRY RUN] Would set date {field_id[-4:]}... = {date_value}")
        return

    # Inline the values to avoid String/Date type mismatch with -f variables
    mutation = (
        "mutation { updateProjectV2ItemFieldValue(input: {"
        f' projectId: "{PROJECT_ID}"'
        f' itemId: "{item_id}"'
        f' fieldId: "{field_id}"'
        f' value: {{ date: "{date_value}" }}'
        " }) { projectV2Item { id } } }"
    )
    payload = json.dumps({"query": mutation})

    time.sleep(_RATE_LIMIT_DELAY)
    result = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = redact_for_logging(result.stderr)
        print(f"  WARNING: date field set failed: {stderr}", file=sys.stderr)
        return

    print(f"  Set date field {field_id[-4:]}... = {date_value}")


def _effort_to_risk(issue: Issue) -> str:
    """Map issue risk_level to RISK_LEVEL option."""
    return issue.risk_level


def resolve_epic_body(epic: Issue, all_issues: list[Issue]) -> None:
    """Replace {A1a}, {A1b} etc. with actual issue numbers in epic body."""
    by_id = {i.id: i for i in all_issues}
    body = epic.body
    for child_id in epic.epic_children:
        child = by_id.get(child_id)
        if child and child.gh_number:
            body = body.replace(f"{{{child_id}}}", f"#{child.gh_number}")
        else:
            body = body.replace(f"{{{child_id}}}", f"{child_id} (pending)")
    epic.body = body


def run(*, dry_run: bool = False, batch_filter: int | None = None) -> None:
    """Main execution: create issues in dependency order."""
    issues = all_issues()
    validate_all(issues)

    # Group by batch
    batches: dict[int, list[Issue]] = {}
    for issue in issues:
        batches.setdefault(issue.batch, []).append(issue)

    batch_order = [1, 2, 3, 4, 5, 6]

    for batch_num in batch_order:
        if batch_filter is not None and batch_num != batch_filter:
            continue

        batch_issues = batches.get(batch_num, [])
        if not batch_issues:
            continue

        batch_names = {
            1: "Epic children",
            2: "Epics",
            3: "Phase E standalone",
            4: "Phase F standalone",
            5: "Phase G standalone",
            6: "Phase H standalone",
        }
        print(f"\n{'=' * 60}")
        print(
            f"Batch {batch_num}: {batch_names.get(batch_num, 'Unknown')} ({len(batch_issues)} issues)"
        )
        print(f"{'=' * 60}\n")

        # For epics (batch 2), resolve child references first
        if batch_num == 2:
            for epic in batch_issues:
                resolve_epic_body(epic, issues)

        for issue in batch_issues:
            create_issue(issue, dry_run=dry_run)
            if not dry_run:
                time.sleep(1)  # Rate limit

        # Add to project board after batch creation
        if not dry_run:
            print(f"\nAdding batch {batch_num} to project board...")
            for issue in batch_issues:
                add_to_project_board(issue, dry_run=dry_run)

    # Summary
    created = [i for i in issues if i.gh_number is not None]
    print(f"\n{'=' * 60}")
    print(f"Summary: {len(created)}/{len(issues)} issues created")
    if batch_filter is not None:
        print(f"(filtered to batch {batch_filter})")
    print(f"{'=' * 60}")

    if created:
        print("\nCreated issues:")
        for i in created:
            print(f"  #{i.gh_number}: {i.title}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create AtlasBridge feature issues")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--batch", type=int, help="Run only specific batch (1-6)")
    parser.add_argument("--validate-only", action="store_true", help="Only check prohibited terms")
    args = parser.parse_args()

    if args.validate_only:
        issues = all_issues()
        validate_all(issues)
        print(f"Total issues defined: {len(issues)}")
        by_batch = {}
        for i in issues:
            by_batch.setdefault(i.batch, []).append(i)
        for b in sorted(by_batch):
            print(f"  Batch {b}: {len(by_batch[b])} issues")
        return

    run(dry_run=args.dry_run, batch_filter=args.batch)


if __name__ == "__main__":
    main()
