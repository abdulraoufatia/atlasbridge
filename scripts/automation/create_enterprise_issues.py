#!/usr/bin/env python3
"""Create 20 enterprise governance GitHub issues for AtlasBridge.

Two batches:
  Batch 1: Governance Engine Features (E1-E10)
  Batch 2: Enterprise Dashboard UX (D1-D10)

Usage:
    python scripts/automation/create_enterprise_issues.py --validate-only
    python scripts/automation/create_enterprise_issues.py --dry-run
    python scripts/automation/create_enterprise_issues.py --batch 1
    python scripts/automation/create_enterprise_issues.py --batch 2
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass

# Reuse project board helpers
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from project_fields import (
    _RATE_LIMIT_DELAY,
    CATEGORY,
    EDITION,
    EFFORT,
    PHASE,
    PRIORITY,
    PROJECT_ID,
    RISK_LEVEL,
    STATUS,
    TARGET_DATE_FIELD_ID,
    add_item_to_project,
    get_issue_node_id,
    redact_for_logging,
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
    id: str  # internal reference like E1, D2, etc.
    title: str
    body: str
    labels: list[str]
    phase: str  # E, G, H
    priority: str  # P0, P1, P2
    category: str  # Core, Governance, UX, Security
    effort: str  # S, M, L, XL
    edition: str  # Community, Pro, Enterprise
    risk_level: str  # Low, Medium, High, Critical
    target_date: str  # v1.0.0, v1.1.0, v2.0.0
    batch: int  # 1=governance engine, 2=dashboard UX
    gh_number: int | None = None  # filled after creation


# ---------------------------------------------------------------------------
# Enterprise body template (12 sections)
# ---------------------------------------------------------------------------


def build_enterprise_body(
    *,
    phase: str,
    priority: str,
    category: str,
    effort: str,
    edition: str,
    summary: str,
    business_impact: str,
    priority_tier: str,
    complexity: str,
    requirements: str,
    acceptance: str,
    ui_ux: str,
    non_goals: str,
    dependencies: str,
    metrics: str,
    enterprise_value: str,
    related_issues: str,
) -> str:
    return f"""**Phase:** {phase} | **Priority:** {priority} | **Category:** {category} | **Effort:** {effort}
**Edition:** {edition}

## Summary
{summary}

## Business Impact
{business_impact}

## Priority Tier
{priority_tier}

## Engineering Complexity
{complexity}

## Detailed Functional Requirements
{requirements}

## Acceptance Criteria
{acceptance}

## UI/UX Requirements
{ui_ux}

## Non-Goals
{non_goals}

## Dependencies
{dependencies}

## Metrics of Success
{metrics}

## Enterprise Tier Value
{enterprise_value}

## Related Issues
{related_issues}"""


# ---------------------------------------------------------------------------
# Target date mapping
# ---------------------------------------------------------------------------

TARGET_DATES = {
    "v1.0.0": "2026-06-01",
    "v1.1.0": "2026-09-01",
    "v2.0.0": "2027-06-01",
}


# ---------------------------------------------------------------------------
# Batch 1: Governance Engine Features (E1-E10)
# ---------------------------------------------------------------------------


def governance_engine_issues() -> list[Issue]:
    issues: list[Issue] = []

    # E1 — Incident Mode
    issues.append(
        Issue(
            id="E1",
            title="feat(governance): Incident mode — emergency governance state",
            body=build_enterprise_body(
                phase="E",
                priority="P0",
                category="Governance",
                effort="L",
                edition="Community",
                summary=(
                    "When a governed agent behaves unexpectedly — producing dangerous commands, "
                    "triggering repeated escalations, or violating safety invariants — operators need "
                    "an immediate, coordinated response. Today AtlasBridge can pause individual sessions "
                    "via the kill switch, but there is no system-wide emergency state that locks down "
                    "all active sessions, notifies all channels, and creates an incident record.\n\n"
                    "Incident mode is a first-class governance primitive: a single action that transitions "
                    "the entire runtime into a safe state. All sessions are paused, all pending prompts are "
                    "held, and the operator receives a structured incident summary. Recovery requires "
                    "explicit operator confirmation.\n\n"
                    "This is the foundational safety primitive that makes AtlasBridge suitable for "
                    "production autonomous workloads. Without it, operators must manually coordinate "
                    "across sessions during an emergency."
                ),
                business_impact=(
                    "- **Core impact:** Enables production-grade safety for autonomous agent workloads\n"
                    "- **Enterprise impact:** High — incident response is table stakes for regulated environments\n"
                    "- **Strategic alignment:** Strengthens AtlasBridge's position as the only deterministic "
                    "governance runtime with layered safety controls"
                ),
                priority_tier=(
                    "**Pre-GA (Phase E)** — Incident mode is a foundational safety primitive. Without it, "
                    "AtlasBridge cannot credibly claim production readiness for autonomous workloads. "
                    "Must ship before v1.0.0."
                ),
                complexity=(
                    "**High** — Requires coordination across daemon manager, autopilot engine, channel layer, "
                    "and audit system. State machine transitions must be atomic and recoverable. Channel "
                    "fan-out must handle partial failures gracefully."
                ),
                requirements=(
                    "- `IncidentState` enum: `NORMAL`, `INCIDENT_ACTIVE`, `RECOVERING`\n"
                    "- `trigger_incident(reason, source)` — atomically transitions to INCIDENT_ACTIVE\n"
                    "- All active sessions paused within 500ms of trigger\n"
                    "- All pending prompts held (not expired) during incident\n"
                    "- Incident notification sent to all configured channels\n"
                    "- Structured incident record written to audit log\n"
                    "- `resolve_incident(operator_id)` — requires explicit confirmation\n"
                    "- Recovery resumes held prompts in original order\n"
                    "- CLI: `atlasbridge incident trigger <reason>`, `atlasbridge incident resolve`\n"
                    "- CLI: `atlasbridge incident status` — shows current state + timeline"
                ),
                acceptance=(
                    "- [ ] `trigger_incident()` pauses all active sessions atomically\n"
                    "- [ ] Pending prompts are held, not expired, during incident\n"
                    "- [ ] All configured channels receive incident notification\n"
                    "- [ ] Audit log contains structured incident record with timestamp and reason\n"
                    "- [ ] `resolve_incident()` requires operator identity\n"
                    "- [ ] Recovery resumes held prompts in correct order\n"
                    "- [ ] Double-trigger is idempotent (no state corruption)\n"
                    "- [ ] CLI commands work end-to-end\n"
                    "- [ ] Unit tests cover all state transitions\n"
                    "- [ ] Safety tests verify no prompt injection during incident"
                ),
                ui_ux=(
                    "- CLI output uses structured format, no decorative elements\n"
                    "- Incident status displays timeline with timestamps\n"
                    "- Channel notifications use serious, factual tone\n"
                    "- Recovery confirmation requires explicit acknowledgment"
                ),
                non_goals=(
                    "- Automated incident detection (future — requires anomaly baseline)\n"
                    "- Multi-operator incident coordination (v2.0.0)\n"
                    "- Incident playbooks or runbooks\n"
                    "- Integration with external incident management systems"
                ),
                dependencies=(
                    "- `core/daemon/manager.py` — session pause orchestration\n"
                    "- `core/autopilot/engine.py` — state machine integration\n"
                    "- `channels/multi.py` — fan-out notification\n"
                    "- `core/audit/writer.py` — incident record schema\n"
                    "- `core/store/database.py` — held prompt storage"
                ),
                metrics=(
                    "- Time to full pause: < 500ms from trigger to all sessions paused\n"
                    "- Zero prompt loss during incident lifecycle\n"
                    "- Recovery success rate: 100% of held prompts resumed\n"
                    "- Test coverage: incident state machine fully covered"
                ),
                enterprise_value=(
                    "Incident mode is the single most important governance primitive for enterprise "
                    "adoption. Organizations evaluating autonomous agent runtimes require emergency "
                    "response capabilities as a baseline. AtlasBridge with incident mode becomes the "
                    "only open-source runtime offering deterministic emergency governance."
                ),
                related_issues="None — new foundational primitive.",
            ),
            labels=["enhancement", "governance", "phase:E-ga"],
            phase="E",
            priority="P0",
            category="Governance",
            effort="L",
            edition="Community",
            risk_level="Critical",
            target_date="v1.0.0",
            batch=1,
        )
    )

    # E2 — Governance Score
    issues.append(
        Issue(
            id="E2",
            title="feat(governance): Governance score — composite health metric (0-100)",
            body=build_enterprise_body(
                phase="E",
                priority="P1",
                category="Governance",
                effort="M",
                edition="Community",
                summary=(
                    "Operators currently have no single metric that summarizes how well their governance "
                    "policies are performing. They must manually correlate escalation rates, policy match "
                    "rates, confidence distributions, and override frequencies to form a mental model of "
                    "governance health.\n\n"
                    "The governance score is a composite metric (0-100) computed from weighted signals: "
                    "policy coverage, escalation rate, confidence distribution, override frequency, and "
                    "incident history. It provides a headline number for governance health that operators "
                    "can track over time.\n\n"
                    "This metric becomes the foundation for governance dashboards, alerting thresholds, "
                    "and trend analysis. It answers the question: 'Is my governance getting better or worse?'"
                ),
                business_impact=(
                    "- **Core impact:** First quantitative governance metric — enables data-driven policy tuning\n"
                    "- **Enterprise impact:** Medium — headline metric for governance reporting\n"
                    "- **Strategic alignment:** Differentiates AtlasBridge from prompt-and-pray agent frameworks"
                ),
                priority_tier=(
                    "**Pre-GA (Phase E)** — The governance score is the headline metric that demonstrates "
                    "AtlasBridge's value proposition. Without a quantitative health signal, governance "
                    "improvements are invisible to operators."
                ),
                complexity=(
                    "**Medium** — Requires aggregating data from multiple subsystems (audit log, decision "
                    "trace, policy evaluator) but the computation itself is straightforward weighted averaging. "
                    "The challenge is defining stable, meaningful weights."
                ),
                requirements=(
                    "- `GovernanceScore` model with component scores and composite\n"
                    "- Components: policy_coverage (0-100), escalation_rate (inverted), "
                    "confidence_distribution, override_frequency (inverted), incident_penalty\n"
                    "- Default weights: coverage=30, escalation=25, confidence=20, override=15, incident=10\n"
                    "- `compute_score(window_hours=24)` — aggregates from audit log and decision trace\n"
                    "- Score persisted to SQLite for trend tracking\n"
                    "- CLI: `atlasbridge governance score` — shows current score + breakdown\n"
                    "- CLI: `atlasbridge governance score --trend 7d` — shows 7-day trend"
                ),
                acceptance=(
                    "- [ ] `GovernanceScore` model defined with component breakdown\n"
                    "- [ ] Score computation uses configurable weights\n"
                    "- [ ] Score range is 0-100, monotonic (higher = healthier)\n"
                    "- [ ] Score persisted to SQLite with timestamp\n"
                    "- [ ] CLI displays score + component breakdown\n"
                    "- [ ] Trend view shows score over configurable window\n"
                    "- [ ] Unit tests cover edge cases (no data, all escalations, perfect score)\n"
                    "- [ ] Score is deterministic for same input data"
                ),
                ui_ux=(
                    "- Score displayed as integer (no decimals) with qualitative label\n"
                    "- Labels: 0-39 Critical, 40-59 Poor, 60-79 Good, 80-100 Excellent\n"
                    "- Breakdown shows each component with its contribution\n"
                    "- Trend uses simple ASCII chart in CLI"
                ),
                non_goals=(
                    "- ML-based scoring or prediction\n"
                    "- Per-agent or per-session scoring (aggregate only in v1)\n"
                    "- Alerting on score changes (see E7 Drift Alerts)\n"
                    "- Custom weight configuration via UI (CLI/config only)"
                ),
                dependencies=(
                    "- `core/audit/writer.py` — audit log read access\n"
                    "- `core/autopilot/trace.py` — decision trace read access\n"
                    "- `core/store/database.py` — score persistence\n"
                    "- `core/policy/evaluator.py` — coverage computation"
                ),
                metrics=(
                    "- Score computation time: < 2s for 24h window\n"
                    "- Score stability: < 5 point variance for identical workloads\n"
                    "- Test coverage: all component computations covered"
                ),
                enterprise_value=(
                    "The governance score provides a quantitative foundation for governance reporting. "
                    "Organizations can track governance health over time, set minimum score thresholds, "
                    "and demonstrate governance posture to stakeholders. This is the metric that makes "
                    "governance visible and measurable."
                ),
                related_issues="None — new metric system.",
            ),
            labels=["enhancement", "governance", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Governance",
            effort="M",
            edition="Community",
            risk_level="Medium",
            target_date="v1.0.0",
            batch=1,
        )
    )

    # E3 — Session Risk Timeline
    issues.append(
        Issue(
            id="E3",
            title="feat(governance): Session risk timeline — chronological risk visualization",
            body=build_enterprise_body(
                phase="G",
                priority="P1",
                category="Governance",
                effort="M",
                edition="Pro",
                summary=(
                    "When reviewing a completed or active session, operators see a flat list of decisions "
                    "and escalations. There is no chronological view that shows how risk evolved over the "
                    "session's lifetime — when escalations clustered, when confidence dropped, or when "
                    "policy overrides occurred.\n\n"
                    "The session risk timeline is a chronological visualization of risk events within a "
                    "session. Each event (prompt, decision, escalation, override) is plotted on a timeline "
                    "with a risk score. Operators can see risk spikes, correlate them with specific prompts, "
                    "and understand the session's risk narrative.\n\n"
                    "This transforms session review from reading logs to understanding risk patterns."
                ),
                business_impact=(
                    "- **Core impact:** Transforms session review from log reading to risk pattern analysis\n"
                    "- **Enterprise impact:** Medium — essential for post-incident review and compliance\n"
                    "- **Strategic alignment:** Unique capability — no other agent runtime offers session risk visualization"
                ),
                priority_tier=(
                    "**Post-GA (Phase G)** — Valuable for deep session analysis but not required for "
                    "core governance. Pre-GA focus is on computing risk; visualization is the next step."
                ),
                complexity=(
                    "**Medium** — Requires aggregating events from multiple sources (audit log, decision trace, "
                    "session store) and computing per-event risk scores. The timeline rendering itself is "
                    "straightforward."
                ),
                requirements=(
                    "- `SessionTimeline` model: ordered list of `TimelineEvent` entries\n"
                    "- Each event has: timestamp, event_type, risk_score (0-100), description, prompt_id\n"
                    "- Risk score computed from confidence, policy match quality, and escalation status\n"
                    "- `build_timeline(session_id)` aggregates from audit + decision trace + session store\n"
                    "- CLI: `atlasbridge session timeline <session_id>` — renders ASCII timeline\n"
                    "- Dashboard API: `/api/sessions/{id}/timeline` — returns JSON for visualization\n"
                    "- Highlight risk spikes (> 2 standard deviations from session mean)"
                ),
                acceptance=(
                    "- [ ] `SessionTimeline` and `TimelineEvent` models defined\n"
                    "- [ ] Per-event risk score computed consistently\n"
                    "- [ ] Timeline includes all event types (prompt, decision, escalation, override)\n"
                    "- [ ] CLI renders readable ASCII timeline\n"
                    "- [ ] Dashboard API returns well-structured JSON\n"
                    "- [ ] Risk spikes highlighted with annotations\n"
                    "- [ ] Unit tests cover timeline construction and risk computation\n"
                    "- [ ] Empty session produces empty timeline (no errors)"
                ),
                ui_ux=(
                    "- CLI timeline uses minimal ASCII art with timestamps and risk indicators\n"
                    "- Risk levels indicated by markers: [LOW] [MED] [HIGH] [CRIT]\n"
                    "- Dashboard renders as interactive timeline (implementation in D3)\n"
                    "- Human override points clearly marked on timeline"
                ),
                non_goals=(
                    "- Real-time streaming timeline (batch computation only)\n"
                    "- Cross-session timeline comparison (see D4 Risk Intelligence)\n"
                    "- Predictive risk scoring\n"
                    "- Custom risk weight configuration"
                ),
                dependencies=(
                    "- `core/audit/writer.py` — event source\n"
                    "- `core/autopilot/trace.py` — decision source\n"
                    "- `core/session/manager.py` — session metadata\n"
                    "- `dashboard/app.py` — API endpoint registration"
                ),
                metrics=(
                    "- Timeline build time: < 1s for sessions with up to 500 events\n"
                    "- Risk score consistency: deterministic for same input\n"
                    "- Test coverage: timeline construction and all event types"
                ),
                enterprise_value=(
                    "Session risk timelines enable structured post-incident review. Organizations can "
                    "trace exactly when and why risk escalated, correlate with operator actions, and "
                    "identify governance gaps. This capability is essential for compliance reporting "
                    "and governance improvement."
                ),
                related_issues="None — new visualization primitive.",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Governance",
            effort="M",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.1.0",
            batch=1,
        )
    )

    # E4 — Agent Sandboxing Modes
    issues.append(
        Issue(
            id="E4",
            title="feat(runtime): Agent sandboxing modes — tiered execution constraints",
            body=build_enterprise_body(
                phase="E",
                priority="P0",
                category="Core",
                effort="XL",
                edition="Community",
                summary=(
                    "AtlasBridge currently governs what agents can do via policy rules that evaluate "
                    "prompts. But there is no enforcement at the execution layer — a governed agent that "
                    "receives an auto-response can still execute arbitrary commands if the underlying CLI "
                    "tool allows it. Policy governs decisions; sandboxing constrains execution.\n\n"
                    "Agent sandboxing introduces tiered execution constraints that limit what a governed "
                    "agent can do at the OS level. Three tiers: unrestricted (current behavior), "
                    "restricted (filesystem and network boundaries), and isolated (containerized execution). "
                    "The tier is set per agent profile and enforced by the PTY supervisor.\n\n"
                    "This is defense-in-depth: even if a policy rule is misconfigured, the sandbox limits "
                    "the blast radius. Combined with incident mode (E1), this makes AtlasBridge the only "
                    "agent runtime with both governance and execution safety layers."
                ),
                business_impact=(
                    "- **Core impact:** Defense-in-depth execution safety — limits blast radius of misconfigurations\n"
                    "- **Enterprise impact:** High — execution constraints are required for regulated environments\n"
                    "- **Strategic alignment:** Only agent runtime with both policy governance AND execution sandboxing"
                ),
                priority_tier=(
                    "**Pre-GA (Phase E)** — Execution constraints are essential for production safety. "
                    "Without sandboxing, policy misconfiguration has unbounded blast radius. At minimum, "
                    "filesystem boundary enforcement must ship before v1.0.0."
                ),
                complexity=(
                    "**Very High** — Requires OS-level enforcement (filesystem permissions, network "
                    "filtering), cross-platform implementation (macOS/Linux), integration with PTY "
                    "supervisor, and graceful degradation when OS features are unavailable."
                ),
                requirements=(
                    "- `SandboxTier` enum: `UNRESTRICTED`, `RESTRICTED`, `ISOLATED`\n"
                    "- `SandboxConfig` model: tier, allowed_paths, blocked_paths, network_policy\n"
                    "- UNRESTRICTED: current behavior, no enforcement\n"
                    "- RESTRICTED: filesystem boundaries (allowed_paths whitelist), optional network filtering\n"
                    "- ISOLATED: containerized execution via user namespaces or lightweight container\n"
                    "- Sandbox tier set via agent profile or CLI flag: `atlasbridge run claude --sandbox restricted`\n"
                    "- PTY supervisor enforces sandbox at spawn time\n"
                    "- Sandbox violations logged to audit trail\n"
                    "- Graceful degradation: if OS feature unavailable, warn and fall back to next lower tier\n"
                    "- macOS: filesystem boundaries via sandbox-exec or path validation\n"
                    "- Linux: filesystem boundaries via mount namespaces or seccomp"
                ),
                acceptance=(
                    "- [ ] `SandboxTier` and `SandboxConfig` models defined\n"
                    "- [ ] UNRESTRICTED tier passes all existing tests (backward compatible)\n"
                    "- [ ] RESTRICTED tier enforces filesystem boundaries\n"
                    "- [ ] Sandbox violations produce audit log entries\n"
                    "- [ ] `--sandbox` flag accepted on `run` command\n"
                    "- [ ] Profile-based sandbox tier works end-to-end\n"
                    "- [ ] Graceful degradation on unsupported platforms\n"
                    "- [ ] macOS filesystem boundaries functional\n"
                    "- [ ] Linux filesystem boundaries functional\n"
                    "- [ ] Unit tests cover all tiers and violation scenarios\n"
                    "- [ ] Safety tests verify sandbox cannot be bypassed via policy"
                ),
                ui_ux=(
                    "- Sandbox tier displayed in session status output\n"
                    "- Violation warnings sent to operator via channel\n"
                    "- Configuration uses familiar path-based syntax\n"
                    "- Human override accessible for tier changes during session"
                ),
                non_goals=(
                    "- Full container orchestration (Docker/Podman integration)\n"
                    "- Network-level isolation (iptables/nftables rules)\n"
                    "- Windows sandboxing (future platform work)\n"
                    "- Per-command sandboxing (tier is per-session)"
                ),
                dependencies=(
                    "- `os/tty/base.py` — sandbox enforcement at PTY spawn\n"
                    "- `os/tty/macos.py` — macOS-specific sandbox implementation\n"
                    "- `os/tty/linux.py` — Linux-specific sandbox implementation\n"
                    "- `adapters/base.py` — sandbox config propagation\n"
                    "- `core/audit/writer.py` — violation logging"
                ),
                metrics=(
                    "- Sandbox enforcement overhead: < 50ms at session start\n"
                    "- Zero false positive violations for well-configured sandboxes\n"
                    "- All existing tests pass with UNRESTRICTED tier\n"
                    "- Test coverage: all tiers, all platforms, violation scenarios"
                ),
                enterprise_value=(
                    "Execution sandboxing is the strongest technical differentiator for enterprise "
                    "adoption. Organizations require defense-in-depth: policy governance alone is "
                    "insufficient when agents can execute arbitrary commands. AtlasBridge with sandboxing "
                    "becomes the only agent runtime offering both governance and execution constraints."
                ),
                related_issues="None — new execution safety layer.",
            ),
            labels=["enhancement", "security", "phase:E-ga"],
            phase="E",
            priority="P0",
            category="Core",
            effort="XL",
            edition="Community",
            risk_level="High",
            target_date="v1.0.0",
            batch=1,
        )
    )

    # E5 — Explain Risk
    issues.append(
        Issue(
            id="E5",
            title="feat(governance): Explain risk — one-click deterministic risk explanation",
            body=build_enterprise_body(
                phase="E",
                priority="P1",
                category="Governance",
                effort="S",
                edition="Community",
                summary=(
                    "When AtlasBridge makes a governance decision — auto-respond, escalate, or require "
                    "human — operators see the outcome but not the reasoning. The existing `autopilot explain` "
                    "command shows the decision trace, but it requires knowing which decision to look at "
                    "and interpreting raw trace data.\n\n"
                    "Explain risk provides a one-click explanation for any governance decision. Given a "
                    "prompt or decision ID, it produces a human-readable explanation: which rules matched, "
                    "why the confidence level was assigned, what the alternative outcomes would have been, "
                    "and what the risk factors are.\n\n"
                    "This is governance transparency — making the 'why' behind every decision accessible "
                    "without requiring deep policy knowledge."
                ),
                business_impact=(
                    "- **Core impact:** Governance transparency — operators understand why decisions were made\n"
                    "- **Enterprise impact:** Medium — explainability is expected for auditable systems\n"
                    "- **Strategic alignment:** Completes the governance story — detect, decide, explain"
                ),
                priority_tier=(
                    "**Pre-GA (Phase E)** — Explainability is table stakes for a governance runtime. "
                    "Without it, operators must reverse-engineer policy behavior from trace data. "
                    "Cheapest high-value feature (Low complexity, S effort)."
                ),
                complexity=(
                    "**Low** — Builds on existing `explain_decision()` infrastructure in the policy module. "
                    "Primary work is formatting the explanation for different output targets (CLI, channel, "
                    "dashboard API)."
                ),
                requirements=(
                    "- `explain_risk(prompt_id_or_decision_id)` → structured `RiskExplanation`\n"
                    "- `RiskExplanation` includes: matched_rules, confidence_reasoning, "
                    "alternative_outcomes, risk_factors, recommendation\n"
                    "- CLI: `atlasbridge explain <id>` — human-readable explanation\n"
                    "- Channel integration: reply with 'explain' to any decision notification\n"
                    "- Dashboard API: `/api/decisions/{id}/explain` — structured JSON\n"
                    "- Explanation is deterministic — same input always produces same output\n"
                    "- Works for both live and historical decisions"
                ),
                acceptance=(
                    "- [ ] `RiskExplanation` model defined with all required fields\n"
                    "- [ ] `explain_risk()` produces correct explanation for auto-respond decisions\n"
                    "- [ ] `explain_risk()` produces correct explanation for escalated decisions\n"
                    "- [ ] CLI output is human-readable and structured\n"
                    "- [ ] Channel reply integration works for Telegram and Slack\n"
                    "- [ ] Dashboard API returns well-structured JSON\n"
                    "- [ ] Explanation is deterministic (same input = same output)\n"
                    "- [ ] Historical decisions can be explained\n"
                    "- [ ] Unit tests cover all decision types"
                ),
                ui_ux=(
                    "- Explanation uses clear, factual language\n"
                    "- Rule matches shown with rule name and match reason\n"
                    "- Alternative outcomes listed with their conditions\n"
                    "- Risk factors use severity labels, not numeric scores\n"
                    "- Channel explanations are concise (under 500 chars)"
                ),
                non_goals=(
                    "- Natural language generation or AI-powered explanations\n"
                    "- Explanation caching or pre-computation\n"
                    "- Comparative explanations ('why this instead of that')\n"
                    "- Explanation customization or templates"
                ),
                dependencies=(
                    "- `core/policy/explain.py` — existing explain infrastructure\n"
                    "- `core/autopilot/trace.py` — decision trace access\n"
                    "- `core/store/database.py` — historical decision lookup\n"
                    "- `channels/base.py` — reply handler integration"
                ),
                metrics=(
                    "- Explanation generation time: < 200ms per decision\n"
                    "- Explanation completeness: covers all decision factors\n"
                    "- Test coverage: all decision types and edge cases"
                ),
                enterprise_value=(
                    "Explainability is a governance requirement for organizations deploying autonomous "
                    "agents. The ability to deterministically explain any governance decision — why it "
                    "was made, what alternatives existed, and what risk factors were present — transforms "
                    "AtlasBridge from a black-box runtime to a transparent governance platform."
                ),
                related_issues="None — extends existing explain infrastructure.",
            ),
            labels=["enhancement", "governance", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Governance",
            effort="S",
            edition="Community",
            risk_level="Low",
            target_date="v1.0.0",
            batch=1,
        )
    )

    # E6 — Blast Radius Estimator
    issues.append(
        Issue(
            id="E6",
            title="feat(governance): Blast radius estimator — pre-execution impact analysis",
            body=build_enterprise_body(
                phase="G",
                priority="P1",
                category="Governance",
                effort="L",
                edition="Pro",
                summary=(
                    "When AtlasBridge auto-responds to a prompt, the operator has no visibility into "
                    "the potential impact of that response. A 'yes' to 'Apply changes to 3 files?' has "
                    "very different implications than 'yes' to 'Deploy to production?'. Policy rules can "
                    "match on prompt text, but they cannot assess the downstream impact of the response.\n\n"
                    "The blast radius estimator analyzes the context surrounding a prompt — recent agent "
                    "output, session history, detected plan — and produces a pre-execution impact "
                    "assessment. This assessment includes: scope (files, commands, systems affected), "
                    "reversibility (can the action be undone?), and severity (what happens if it goes wrong?).\n\n"
                    "This enables risk-proportional governance: low-blast-radius actions auto-execute, "
                    "high-blast-radius actions escalate, regardless of prompt type."
                ),
                business_impact=(
                    "- **Core impact:** Risk-proportional governance — actions assessed by impact, not just type\n"
                    "- **Enterprise impact:** High — pre-execution impact analysis is a governance differentiator\n"
                    "- **Strategic alignment:** Moves governance from reactive (prompt matching) to proactive "
                    "(impact prediction)"
                ),
                priority_tier=(
                    "**Post-GA (Phase G)** — Requires stable output router and plan detection (v0.10.0 "
                    "infrastructure). High value but depends on context extraction maturity."
                ),
                complexity=(
                    "**High** — Requires parsing agent output for context clues, maintaining a model of "
                    "session state, and mapping detected actions to impact categories. Accuracy depends "
                    "heavily on output router quality."
                ),
                requirements=(
                    "- `BlastRadius` model: scope, reversibility, severity, confidence, rationale\n"
                    "- `estimate_blast_radius(prompt, session_context)` → `BlastRadius`\n"
                    "- Scope categories: file_change, command_execution, network_request, deployment, "
                    "configuration_change, data_modification\n"
                    "- Reversibility: fully_reversible, partially_reversible, irreversible\n"
                    "- Severity: minimal, moderate, significant, critical\n"
                    "- Context sources: recent output buffer, detected plan, session history\n"
                    "- Policy integration: `blast_radius` match criterion in DSL\n"
                    "- CLI: `atlasbridge governance blast-radius <session_id>` — show latest estimate"
                ),
                acceptance=(
                    "- [ ] `BlastRadius` model defined with all categories\n"
                    "- [ ] Estimator produces consistent results for known patterns\n"
                    "- [ ] File change scope correctly identified from agent output\n"
                    "- [ ] Deployment scope detected for deploy/push/release patterns\n"
                    "- [ ] `blast_radius` match criterion works in policy rules\n"
                    "- [ ] CLI shows blast radius for current or specified session\n"
                    "- [ ] Estimation completes within timeout (< 500ms)\n"
                    "- [ ] Unknown patterns produce conservative (high) estimates\n"
                    "- [ ] Unit tests cover all scope categories and severity levels"
                ),
                ui_ux=(
                    "- Blast radius shown with scope and severity labels\n"
                    "- Reversibility clearly indicated\n"
                    "- Rationale explains why the estimate was assigned\n"
                    "- Channel notifications include blast radius for escalated prompts"
                ),
                non_goals=(
                    "- ML-based impact prediction\n"
                    "- Real-time blast radius updates during execution\n"
                    "- Cross-session impact analysis\n"
                    "- Integration with external change management systems"
                ),
                dependencies=(
                    "- `core/interaction/output_router.py` — context extraction\n"
                    "- `core/interaction/plan_detector.py` — plan detection\n"
                    "- `core/interaction/streaming.py` — output buffer access\n"
                    "- `core/policy/model.py` — blast_radius match criterion\n"
                    "- `core/policy/evaluator.py` — blast_radius evaluation"
                ),
                metrics=(
                    "- Estimation time: < 500ms per prompt\n"
                    "- Accuracy: > 80% correct scope identification for known patterns\n"
                    "- Conservative default: unknown patterns → high severity\n"
                    "- Test coverage: all scope categories and severity levels"
                ),
                enterprise_value=(
                    "Pre-execution impact analysis is a governance capability that no other agent runtime "
                    "offers. Organizations can enforce risk-proportional governance: routine actions "
                    "auto-execute while high-impact actions require human review. This reduces operator "
                    "fatigue while maintaining safety for consequential actions."
                ),
                related_issues="None — new impact analysis primitive.",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Governance",
            effort="L",
            edition="Pro",
            risk_level="High",
            target_date="v1.1.0",
            batch=1,
        )
    )

    # E7 — Governance Drift Alerts
    issues.append(
        Issue(
            id="E7",
            title="feat(governance): Governance drift alerts — automated deviation detection",
            body=build_enterprise_body(
                phase="G",
                priority="P1",
                category="Governance",
                effort="M",
                edition="Pro",
                summary=(
                    "Governance policies are tuned for specific workload patterns. Over time, agent "
                    "behavior drifts — new prompt types appear, escalation rates shift, confidence "
                    "distributions change. Without monitoring, operators don't notice drift until "
                    "something goes wrong.\n\n"
                    "Governance drift alerts continuously compare current governance metrics against "
                    "a baseline (configurable window). When metrics deviate beyond configurable thresholds "
                    "— escalation rate spikes, confidence drops, new unmatched prompt patterns emerge — "
                    "the system generates an alert via the configured channel.\n\n"
                    "This transforms governance from set-and-forget to actively monitored. Operators "
                    "learn about drift before it causes incidents."
                ),
                business_impact=(
                    "- **Core impact:** Proactive governance monitoring — catch drift before incidents\n"
                    "- **Enterprise impact:** Medium — automated deviation detection reduces operational burden\n"
                    "- **Strategic alignment:** Completes the governance lifecycle: define → enforce → monitor → alert"
                ),
                priority_tier=(
                    "**Post-GA (Phase G)** — Requires stable governance score (E2) and decision trace "
                    "infrastructure. High value for ongoing operations but not a GA blocker."
                ),
                complexity=(
                    "**Medium** — Requires baseline computation, threshold configuration, comparison logic, "
                    "and alert routing. Individual components are straightforward; the challenge is tuning "
                    "default thresholds to minimize false positives."
                ),
                requirements=(
                    "- `DriftBaseline` model: computed from configurable window (default 7 days)\n"
                    "- `DriftAlert` model: metric_name, baseline_value, current_value, deviation_pct, severity\n"
                    "- Monitored metrics: escalation_rate, policy_match_rate, avg_confidence, "
                    "governance_score, unmatched_prompt_rate\n"
                    "- Configurable thresholds per metric (default: 20% deviation)\n"
                    "- Alert routing via configured channels (Telegram, Slack)\n"
                    "- Alert deduplication: same metric drift → one alert per configurable cooldown\n"
                    "- CLI: `atlasbridge governance drift` — show current drift status\n"
                    "- CLI: `atlasbridge governance drift --baseline 14d` — recompute baseline"
                ),
                acceptance=(
                    "- [ ] `DriftBaseline` computation from configurable window\n"
                    "- [ ] `DriftAlert` generated when metric exceeds threshold\n"
                    "- [ ] Alert sent via configured channel\n"
                    "- [ ] Alert deduplication prevents spam\n"
                    "- [ ] CLI shows current drift status\n"
                    "- [ ] Baseline recomputation works with custom window\n"
                    "- [ ] Default thresholds produce reasonable alerts (not too noisy)\n"
                    "- [ ] Unit tests cover baseline computation and drift detection\n"
                    "- [ ] No alerts generated when metrics are within normal range"
                ),
                ui_ux=(
                    "- Drift alerts use factual, non-alarmist tone\n"
                    "- Each alert includes: what drifted, by how much, and suggested action\n"
                    "- CLI drift status shows all metrics with baseline comparison\n"
                    "- Channel alerts are concise and actionable"
                ),
                non_goals=(
                    "- Automated policy adjustment based on drift\n"
                    "- ML-based anomaly detection\n"
                    "- Cross-workspace drift comparison\n"
                    "- Historical drift trend visualization (see D4)"
                ),
                dependencies=(
                    "- `core/autopilot/trace.py` — metric computation source\n"
                    "- `core/audit/writer.py` — event source for metrics\n"
                    "- `channels/multi.py` — alert routing\n"
                    "- E2 (Governance Score) — baseline score tracking"
                ),
                metrics=(
                    "- Drift check latency: < 5s for 7-day baseline\n"
                    "- False positive rate: < 10% with default thresholds\n"
                    "- Alert delivery: < 30s from detection to channel notification\n"
                    "- Test coverage: all monitored metrics and threshold scenarios"
                ),
                enterprise_value=(
                    "Automated drift detection transforms governance from a static configuration to "
                    "an actively monitored system. Organizations operating multiple agents or workloads "
                    "cannot manually track governance health. Drift alerts ensure governance stays "
                    "effective as workload patterns evolve."
                ),
                related_issues=(
                    "- Related: #232 (Governance drift detection) — E7 adds the alerting pipeline on top "
                    "of #232's baseline scoring and deviation computation."
                ),
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Governance",
            effort="M",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.1.0",
            batch=1,
        )
    )

    # E8 — Escalation Pattern Detection
    issues.append(
        Issue(
            id="E8",
            title="feat(governance): Escalation pattern detection — recurring escalation analysis",
            body=build_enterprise_body(
                phase="G",
                priority="P2",
                category="Governance",
                effort="M",
                edition="Pro",
                summary=(
                    "When agents trigger frequent escalations, operators handle them individually without "
                    "visibility into patterns. The same type of prompt might escalate dozens of times "
                    "because the policy lacks a matching rule — but the operator doesn't see this pattern, "
                    "only individual escalation notifications.\n\n"
                    "Escalation pattern detection analyzes the decision trace to identify recurring "
                    "escalation patterns: prompts that repeatedly escalate with similar text, confidence "
                    "levels, or session contexts. When a pattern is detected, the system suggests a "
                    "policy rule that would handle the pattern automatically.\n\n"
                    "This closes the governance feedback loop: escalations generate policy improvement "
                    "suggestions, reducing operator toil over time."
                ),
                business_impact=(
                    "- **Core impact:** Closes governance feedback loop — escalations drive policy improvements\n"
                    "- **Enterprise impact:** Medium — reduces operator toil for repeated escalation patterns\n"
                    "- **Strategic alignment:** Makes governance self-improving — unique capability"
                ),
                priority_tier=(
                    "**Post-GA (Phase G, P2)** — Valuable for operational efficiency but not blocking "
                    "any core functionality. Requires stable decision trace infrastructure."
                ),
                complexity=(
                    "**Medium** — Pattern detection via text similarity and clustering on decision trace data. "
                    "The challenge is defining useful similarity metrics and generating actionable policy "
                    "suggestions without false positives."
                ),
                requirements=(
                    "- `EscalationPattern` model: pattern_id, prompt_similarity_group, frequency, "
                    "first_seen, last_seen, suggested_rule\n"
                    "- Pattern detection via text similarity clustering on escalated prompts\n"
                    "- Configurable similarity threshold (default: 80% text overlap)\n"
                    "- Minimum frequency for pattern recognition (default: 3 occurrences in 7 days)\n"
                    "- `suggest_rule(pattern)` → YAML policy rule suggestion\n"
                    "- CLI: `atlasbridge governance patterns` — list detected patterns\n"
                    "- CLI: `atlasbridge governance patterns --suggest` — show rule suggestions\n"
                    "- Periodic detection: runs on configurable schedule (default: daily)"
                ),
                acceptance=(
                    "- [ ] `EscalationPattern` model defined\n"
                    "- [ ] Pattern detection identifies recurring escalations\n"
                    "- [ ] Suggested rules are valid YAML policy syntax\n"
                    "- [ ] CLI lists detected patterns with frequency and timespan\n"
                    "- [ ] CLI shows rule suggestions in copy-paste-ready format\n"
                    "- [ ] Configurable similarity and frequency thresholds\n"
                    "- [ ] No false positive patterns for diverse escalation types\n"
                    "- [ ] Unit tests cover pattern detection and rule generation"
                ),
                ui_ux=(
                    "- Patterns displayed with frequency, timespan, and sample prompts\n"
                    "- Rule suggestions formatted as valid YAML, ready to paste into policy\n"
                    "- Channel notification for new high-frequency patterns\n"
                    "- Clear indication of confidence in pattern detection"
                ),
                non_goals=(
                    "- Automated policy modification (suggestions only)\n"
                    "- Real-time pattern detection (batch analysis)\n"
                    "- ML-based semantic similarity\n"
                    "- Cross-session pattern correlation"
                ),
                dependencies=(
                    "- `core/autopilot/trace.py` — escalation event source\n"
                    "- `core/policy/model.py` — rule model for suggestions\n"
                    "- `core/policy/parser.py` — YAML generation for suggestions"
                ),
                metrics=(
                    "- Pattern detection time: < 10s for 7-day window\n"
                    "- Pattern accuracy: > 90% of detected patterns represent genuine recurring escalations\n"
                    "- Rule suggestion validity: 100% of suggestions parse as valid policy rules\n"
                    "- Test coverage: pattern detection, rule generation, edge cases"
                ),
                enterprise_value=(
                    "Escalation pattern detection enables self-improving governance. Organizations "
                    "operating at scale generate large volumes of escalations. Automated pattern "
                    "detection and rule suggestions reduce the operational burden of policy tuning "
                    "and ensure governance improves continuously."
                ),
                related_issues="None — new analysis capability.",
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P2",
            category="Governance",
            effort="M",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.1.0",
            batch=1,
        )
    )

    # E9 — Policy Coverage Analyzer
    issues.append(
        Issue(
            id="E9",
            title="feat(policy): Policy coverage analyzer — rule gap identification",
            body=build_enterprise_body(
                phase="E",
                priority="P1",
                category="Governance",
                effort="M",
                edition="Community",
                summary=(
                    "Policy authors have no way to assess the completeness of their policy rules. "
                    "A policy might handle yes/no prompts and file confirmations but miss authentication "
                    "prompts, multi-step wizards, or error recovery scenarios. The only way to discover "
                    "gaps is when a prompt escalates unexpectedly in production.\n\n"
                    "The policy coverage analyzer examines a policy file and reports: which prompt types "
                    "are covered, which confidence levels are handled, which action types are used, and "
                    "what gaps exist. It compares rule coverage against known prompt categories and "
                    "historical prompt data (if available) to identify blind spots.\n\n"
                    "This is policy quality assurance — ensuring governance rules are comprehensive "
                    "before deploying them to production."
                ),
                business_impact=(
                    "- **Core impact:** Policy quality assurance — identify rule gaps before production\n"
                    "- **Enterprise impact:** Medium — ensures governance completeness for critical workloads\n"
                    "- **Strategic alignment:** Completes the governance authoring story: write → validate → analyze"
                ),
                priority_tier=(
                    "**Pre-GA (Phase E)** — Policy coverage analysis is essential for governance quality. "
                    "Without it, operators discover gaps reactively in production. Must ship alongside "
                    "the policy authoring tools."
                ),
                complexity=(
                    "**Medium** — Requires mapping policy rules to prompt type taxonomy, computing coverage "
                    "percentages, and generating gap reports. Historical data integration adds complexity "
                    "but is optional for v1."
                ),
                requirements=(
                    "- `PolicyCoverage` model: total_rules, covered_prompt_types, covered_confidence_levels, "
                    "covered_actions, gaps, coverage_score (0-100)\n"
                    "- `analyze_coverage(policy)` → `PolicyCoverage`\n"
                    "- Known prompt type taxonomy: yes_no, multi_choice, free_text, confirmation, "
                    "authentication, file_path, error_recovery\n"
                    "- Gap detection: prompt types with no matching rule, confidence levels with no "
                    "explicit handling, missing default/fallback rule\n"
                    "- Optional: compare against historical prompt data for data-driven gaps\n"
                    "- CLI: `atlasbridge policy coverage <policy_file>` — coverage report\n"
                    "- CLI: `atlasbridge policy coverage --data` — include historical data analysis"
                ),
                acceptance=(
                    "- [ ] `PolicyCoverage` model defined with all fields\n"
                    "- [ ] Coverage score computed correctly (0-100)\n"
                    "- [ ] All known prompt types checked for coverage\n"
                    "- [ ] Gap report identifies uncovered prompt types\n"
                    "- [ ] Missing default rule flagged as critical gap\n"
                    "- [ ] CLI displays readable coverage report\n"
                    "- [ ] Historical data integration works when data available\n"
                    "- [ ] Graceful behavior when no historical data exists\n"
                    "- [ ] Unit tests cover full coverage, partial coverage, and empty policy"
                ),
                ui_ux=(
                    "- Coverage report uses table format with type/status columns\n"
                    "- Coverage score prominently displayed with qualitative label\n"
                    "- Gaps listed with severity (critical for missing default, medium for missing types)\n"
                    "- Suggestions provided for each gap"
                ),
                non_goals=(
                    "- Automated rule generation for gaps\n"
                    "- Real-time coverage monitoring during policy edits\n"
                    "- Cross-policy comparison\n"
                    "- Policy optimization suggestions beyond gap identification"
                ),
                dependencies=(
                    "- `core/policy/parser.py` — policy loading\n"
                    "- `core/policy/model.py` — rule model access\n"
                    "- `core/prompt/models.py` — prompt type taxonomy\n"
                    "- `core/autopilot/trace.py` — historical prompt data (optional)"
                ),
                metrics=(
                    "- Analysis time: < 1s per policy file\n"
                    "- Gap detection accuracy: 100% for known prompt types\n"
                    "- Coverage score deterministic for same policy\n"
                    "- Test coverage: full, partial, empty, and complex policies"
                ),
                enterprise_value=(
                    "Policy coverage analysis ensures governance rules are comprehensive before "
                    "deployment. Organizations deploying AtlasBridge for critical workloads need "
                    "confidence that their policies handle all expected scenarios. Coverage analysis "
                    "provides that confidence with a quantitative score and actionable gap report."
                ),
                related_issues="None — new policy analysis tool.",
            ),
            labels=["enhancement", "governance", "phase:E-ga"],
            phase="E",
            priority="P1",
            category="Governance",
            effort="M",
            edition="Community",
            risk_level="Medium",
            target_date="v1.0.0",
            batch=1,
        )
    )

    # E10 — Decision Replay Sandbox
    issues.append(
        Issue(
            id="E10",
            title="feat(governance): Decision replay sandbox — re-evaluate with different context",
            body=build_enterprise_body(
                phase="G",
                priority="P1",
                category="Governance",
                effort="L",
                edition="Pro",
                summary=(
                    "After a governance incident or unexpected decision, operators want to understand: "
                    "'What would have happened if the policy were different?' or 'What if the confidence "
                    "threshold were lower?' Currently, the only way to test alternative policies is to "
                    "wait for similar prompts to appear in production.\n\n"
                    "The decision replay sandbox takes a historical decision (from the audit log or "
                    "decision trace) and re-evaluates it against a different policy, different confidence "
                    "thresholds, or different context. This enables counterfactual analysis: testing "
                    "policy changes against real-world data without affecting production.\n\n"
                    "This is single-decision replay — re-evaluating one decision with alternative "
                    "parameters. Full session replay (replaying an entire session timeline) is a separate, "
                    "larger feature."
                ),
                business_impact=(
                    "- **Core impact:** Counterfactual governance analysis — test policy changes safely\n"
                    "- **Enterprise impact:** Medium — enables safe policy iteration without production risk\n"
                    "- **Strategic alignment:** Unique governance capability — test-before-deploy for policies"
                ),
                priority_tier=(
                    "**Post-GA (Phase G)** — Requires stable decision trace and policy evaluation "
                    "infrastructure. High value for policy iteration but not a GA blocker."
                ),
                complexity=(
                    "**Medium** — Requires extracting decision context from trace, reconstructing "
                    "evaluation environment, and running the evaluator with alternative parameters. "
                    "The challenge is faithfully reproducing the original evaluation context."
                ),
                requirements=(
                    "- `ReplayRequest` model: decision_id, alternative_policy (optional), "
                    "alternative_confidence (optional), alternative_context (optional)\n"
                    "- `ReplayResult` model: original_outcome, replay_outcome, diff, explanation\n"
                    "- `replay_decision(request)` → `ReplayResult`\n"
                    "- Context reconstruction from decision trace + audit log\n"
                    "- Policy evaluation in isolated sandbox (no side effects)\n"
                    "- CLI: `atlasbridge governance replay <decision_id>` — replay with current policy\n"
                    "- CLI: `atlasbridge governance replay <id> --policy <alt.yaml>` — replay with alternative\n"
                    "- CLI: `atlasbridge governance replay <id> --confidence high` — replay with different threshold"
                ),
                acceptance=(
                    "- [ ] `ReplayRequest` and `ReplayResult` models defined\n"
                    "- [ ] Context reconstruction from trace produces faithful reproduction\n"
                    "- [ ] Replay with same policy produces same outcome\n"
                    "- [ ] Replay with alternative policy shows correct alternative outcome\n"
                    "- [ ] Diff clearly shows what changed between original and replay\n"
                    "- [ ] No side effects from replay (no audit entries, no state changes)\n"
                    "- [ ] CLI works end-to-end for all replay modes\n"
                    "- [ ] Unit tests cover context reconstruction and evaluation scenarios"
                ),
                ui_ux=(
                    "- Replay output shows side-by-side comparison (original vs alternative)\n"
                    "- Diff uses clear labels: SAME, CHANGED, NEW\n"
                    "- Explanation describes why the outcome changed\n"
                    "- CLI output is structured and readable"
                ),
                non_goals=(
                    "- Full session replay (replaying entire session timeline — see #222)\n"
                    "- Batch replay of multiple decisions\n"
                    "- Automated policy optimization based on replay results\n"
                    "- Real-time replay during live sessions"
                ),
                dependencies=(
                    "- `core/autopilot/trace.py` — decision trace access\n"
                    "- `core/policy/evaluator.py` — isolated evaluation\n"
                    "- `core/policy/parser.py` — alternative policy loading\n"
                    "- `core/store/database.py` — historical decision lookup"
                ),
                metrics=(
                    "- Replay time: < 500ms per decision\n"
                    "- Faithfulness: replay with original params produces identical outcome\n"
                    "- No side effects: zero audit entries or state mutations from replay\n"
                    "- Test coverage: all replay modes and context reconstruction"
                ),
                enterprise_value=(
                    "Decision replay enables safe policy iteration. Organizations can test policy "
                    "changes against real-world decisions without deploying to production. This "
                    "reduces the risk of policy changes and enables data-driven governance tuning."
                ),
                related_issues=(
                    "- Related: #222 (Session replay engine) — E10 is single-decision replay; "
                    "#222 is full session replay. E10 can be built independently."
                ),
            ),
            labels=["enhancement", "governance", "phase:G-saas"],
            phase="G",
            priority="P1",
            category="Governance",
            effort="L",
            edition="Pro",
            risk_level="Medium",
            target_date="v1.1.0",
            batch=1,
        )
    )

    return issues


# ---------------------------------------------------------------------------
# Batch 2: Enterprise Dashboard UX (D1-D10)
# ---------------------------------------------------------------------------


def dashboard_ux_issues() -> list[Issue]:
    issues: list[Issue] = []

    # D1 — Governance Control Tower IA
    issues.append(
        Issue(
            id="D1",
            title="feat(dashboard): Governance control tower — information architecture",
            body=build_enterprise_body(
                phase="H",
                priority="P1",
                category="UX",
                effort="M",
                edition="Enterprise",
                summary=(
                    "The current dashboard provides basic session listing, decision viewing, and audit "
                    "log access. As enterprise governance features are added — risk intelligence, policy "
                    "analytics, incident management — the dashboard needs a coherent information "
                    "architecture that organizes these capabilities into a governance control tower.\n\n"
                    "This issue defines the navigation structure, page hierarchy, and information flow "
                    "for the enterprise dashboard. It establishes the IA foundation that all subsequent "
                    "dashboard features (D2-D10) build on. Without this, new pages would be added ad hoc "
                    "without a coherent navigation model.\n\n"
                    "The control tower metaphor reflects the operator's role: observing, understanding, "
                    "and directing governance across all sessions and agents."
                ),
                business_impact=(
                    "- **Core impact:** Coherent navigation for enterprise governance features\n"
                    "- **Enterprise impact:** Medium — gates all subsequent dashboard work\n"
                    "- **Strategic alignment:** Establishes AtlasBridge as a governance platform, not just a CLI tool"
                ),
                priority_tier=(
                    "**Post-GA (Phase H)** — Enterprise dashboard work. Gates D2-D10 but not required "
                    "for core CLI governance."
                ),
                complexity=(
                    "**Medium** — Information architecture design plus navigation implementation. "
                    "Requires understanding all planned dashboard pages and their relationships."
                ),
                requirements=(
                    "- Top-level navigation: Overview, Sessions, Risk, Policy, Audit, Settings\n"
                    "- Each section has sub-pages defined in spec\n"
                    "- Responsive navigation (sidebar on desktop, hamburger on mobile)\n"
                    "- Breadcrumb trail for deep pages\n"
                    "- Global status indicators in nav header (autonomy mode, incident status)\n"
                    "- Page routing with deep-link support\n"
                    "- Navigation state persisted across page loads"
                ),
                acceptance=(
                    "- [ ] Navigation structure implemented with all top-level sections\n"
                    "- [ ] Responsive behavior works on desktop and mobile viewports\n"
                    "- [ ] Breadcrumb navigation functional for nested pages\n"
                    "- [ ] Global status indicators display correctly\n"
                    "- [ ] Deep linking works for all pages\n"
                    "- [ ] Navigation state persists across page loads\n"
                    "- [ ] Placeholder pages exist for all planned sections\n"
                    "- [ ] Unit tests cover navigation routing"
                ),
                ui_ux=(
                    "- Serious, professional visual design — no playful elements\n"
                    "- Minimal color palette: status colors only for governance state\n"
                    "- Navigation labels are clear and governance-focused\n"
                    "- Human override always accessible from any page\n"
                    "- Risk information visible without navigation"
                ),
                non_goals=(
                    "- Implementing page content (see D2-D10)\n"
                    "- Multi-user authentication or authorization\n"
                    "- Custom navigation configuration\n"
                    "- Dashboard theming beyond light/dark"
                ),
                dependencies=(
                    "- `dashboard/app.py` — FastAPI route registration\n"
                    "- `dashboard/templates/` — Jinja2 template structure\n"
                    "- `dashboard/static/` — CSS and JS assets"
                ),
                metrics=(
                    "- Page navigation time: < 200ms between any two pages\n"
                    "- Navigation renders correctly on viewport widths 375px to 2560px\n"
                    "- All navigation links functional (no dead links)\n"
                    "- Test coverage: navigation routing and responsive behavior"
                ),
                enterprise_value=(
                    "A coherent governance control tower establishes AtlasBridge as a platform, "
                    "not just a CLI tool. Enterprise operators expect dashboard-grade visibility "
                    "into governance operations. The control tower IA ensures all governance "
                    "features are discoverable and organized."
                ),
                related_issues="None — new dashboard architecture.",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="UX",
            effort="M",
            edition="Enterprise",
            risk_level="Medium",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D2 — Overview Page
    issues.append(
        Issue(
            id="D2",
            title="feat(dashboard): Overview page — executive governance KPIs",
            body=build_enterprise_body(
                phase="H",
                priority="P1",
                category="UX",
                effort="M",
                edition="Enterprise",
                summary=(
                    "The dashboard currently opens to a session list. For enterprise operators, the "
                    "first screen should provide a governance overview: key metrics, active sessions, "
                    "recent decisions, and system health at a glance.\n\n"
                    "The overview page is the dashboard landing screen. It displays governance KPIs: "
                    "governance score (E2), active session count, recent escalation rate, policy coverage "
                    "score, and incident status. Each metric links to its detailed page.\n\n"
                    "This page answers the operator's first question: 'Is everything okay?' in under "
                    "5 seconds."
                ),
                business_impact=(
                    "- **Core impact:** Instant governance health visibility for operators\n"
                    "- **Enterprise impact:** Low — foundational but depends on other metrics\n"
                    "- **Strategic alignment:** First impression of AtlasBridge as a governance platform"
                ),
                priority_tier=(
                    "**Post-GA (Phase H)** — Depends on governance score (E2) and other metric "
                    "infrastructure. Enterprise dashboard buildout."
                ),
                complexity=(
                    "**Medium** — Requires aggregating data from multiple sources into a single view. "
                    "Design challenge is information density without clutter."
                ),
                requirements=(
                    "- Governance score widget (from E2) with trend indicator\n"
                    "- Active sessions count with status breakdown\n"
                    "- Recent escalation rate (last 24h) with trend\n"
                    "- Policy coverage score (from E9) if available\n"
                    "- Incident status banner (from E1) if incident active\n"
                    "- Recent decisions list (last 10) with quick actions\n"
                    "- Auto-refresh on configurable interval (default: 30s)\n"
                    "- Each widget links to its detailed page"
                ),
                acceptance=(
                    "- [ ] Overview page is the default dashboard landing page\n"
                    "- [ ] Governance score displayed with trend indicator\n"
                    "- [ ] Active session count and status breakdown shown\n"
                    "- [ ] Escalation rate displayed with 24h trend\n"
                    "- [ ] Incident status banner shown when incident active\n"
                    "- [ ] Recent decisions list populated and clickable\n"
                    "- [ ] Auto-refresh works without full page reload\n"
                    "- [ ] Graceful degradation when metric sources unavailable\n"
                    "- [ ] Unit tests cover data aggregation and display logic"
                ),
                ui_ux=(
                    "- Clean grid layout with clearly labeled KPI cards\n"
                    "- Status colors: green (healthy), amber (attention), red (critical)\n"
                    "- Trend indicators: up/down arrows with percentage\n"
                    "- No decorative elements — every pixel serves a governance purpose\n"
                    "- Loads in under 2 seconds with all widgets"
                ),
                non_goals=(
                    "- Customizable widget layout\n"
                    "- Historical KPI comparison (trend only)\n"
                    "- Per-agent or per-session metrics on overview\n"
                    "- Export or sharing of overview data"
                ),
                dependencies=(
                    "- E2 (Governance Score) — headline metric\n"
                    "- E9 (Policy Coverage) — coverage score widget\n"
                    "- E1 (Incident Mode) — incident status banner\n"
                    "- `dashboard/repo.py` — data access layer"
                ),
                metrics=(
                    "- Page load time: < 2s with all widgets populated\n"
                    "- Auto-refresh without layout shift\n"
                    "- All widgets display correct data from sources\n"
                    "- Test coverage: data aggregation and graceful degradation"
                ),
                enterprise_value=(
                    "The overview page is the first screen enterprise operators see. It establishes "
                    "governance visibility as a first-class capability and answers the most important "
                    "question — 'Is everything okay?' — in under 5 seconds."
                ),
                related_issues="None — new dashboard page.",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="UX",
            effort="M",
            edition="Enterprise",
            risk_level="Low",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D3 — Session Deep Trace
    issues.append(
        Issue(
            id="D3",
            title="feat(dashboard): Session deep trace — full decision trace per session",
            body=build_enterprise_body(
                phase="H",
                priority="P1",
                category="UX",
                effort="L",
                edition="Enterprise",
                summary=(
                    "The current session view shows basic session metadata and a list of prompts. "
                    "Enterprise operators need a deep trace view: every decision, every policy evaluation, "
                    "every escalation, and every injection — rendered chronologically with full context.\n\n"
                    "The session deep trace page provides a complete governance timeline for a single "
                    "session. Each event is expandable: clicking a decision shows the matched rule, "
                    "confidence reasoning, and alternative outcomes. Clicking an escalation shows the "
                    "channel notification and operator response.\n\n"
                    "This is the detailed investigation view — used during post-incident review, "
                    "compliance auditing, and governance troubleshooting."
                ),
                business_impact=(
                    "- **Core impact:** Complete governance visibility per session for investigation\n"
                    "- **Enterprise impact:** Medium — essential for compliance and post-incident review\n"
                    "- **Strategic alignment:** Makes every governance action traceable and explainable"
                ),
                priority_tier=(
                    "**Post-GA (Phase H)** — Enterprise dashboard feature. Depends on decision trace "
                    "infrastructure and explain risk (E5) capabilities."
                ),
                complexity=(
                    "**High** — Requires aggregating events from multiple sources (audit, trace, session, "
                    "channel), rendering them chronologically, and providing expandable detail views. "
                    "Performance matters for long sessions."
                ),
                requirements=(
                    "- Chronological event timeline for a single session\n"
                    "- Event types: prompt_detected, policy_evaluated, decision_made, escalated, "
                    "operator_responded, reply_injected, prompt_resolved\n"
                    "- Expandable event details (rule match, confidence, alternatives)\n"
                    "- Session risk timeline integration (from E3) if available\n"
                    "- Event filtering by type, severity, time range\n"
                    "- Export session trace as JSON\n"
                    "- Pagination for sessions with 100+ events"
                ),
                acceptance=(
                    "- [ ] All event types rendered in chronological order\n"
                    "- [ ] Expandable details show full context per event\n"
                    "- [ ] Event filtering works for all filter criteria\n"
                    "- [ ] Export produces valid, complete JSON\n"
                    "- [ ] Pagination works for long sessions\n"
                    "- [ ] Page loads in < 3s for sessions with 200 events\n"
                    "- [ ] Risk timeline overlay functional when E3 data available\n"
                    "- [ ] Unit tests cover event aggregation and rendering"
                ),
                ui_ux=(
                    "- Timeline uses vertical layout with time markers\n"
                    "- Event types distinguished by icon/color\n"
                    "- Expanded details use consistent card layout\n"
                    "- Risk events highlighted with severity indicators\n"
                    "- Human override points prominently marked"
                ),
                non_goals=(
                    "- Real-time session streaming (batch rendering)\n"
                    "- Cross-session trace comparison\n"
                    "- Inline policy editing from trace view\n"
                    "- Video or screen recording of session"
                ),
                dependencies=(
                    "- `core/autopilot/trace.py` — decision trace\n"
                    "- `core/audit/writer.py` — audit events\n"
                    "- `core/session/manager.py` — session metadata\n"
                    "- `dashboard/repo.py` — data access\n"
                    "- E5 (Explain Risk) — explanation integration"
                ),
                metrics=(
                    "- Page load time: < 3s for 200-event sessions\n"
                    "- Event completeness: all governance events present\n"
                    "- Export accuracy: JSON matches displayed data\n"
                    "- Test coverage: event aggregation, filtering, pagination"
                ),
                enterprise_value=(
                    "Session deep trace provides the investigation capability required for compliance "
                    "and post-incident review. Organizations can trace every governance action in a "
                    "session, understand the reasoning, and verify that governance was applied correctly."
                ),
                related_issues="None — new dashboard page.",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="UX",
            effort="L",
            edition="Enterprise",
            risk_level="Medium",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D4 — Risk Intelligence Page
    issues.append(
        Issue(
            id="D4",
            title="feat(dashboard): Risk intelligence page — centralized risk analysis",
            body=build_enterprise_body(
                phase="H",
                priority="P1",
                category="UX",
                effort="L",
                edition="Enterprise",
                summary=(
                    "Risk data is currently scattered across session views, audit logs, and CLI outputs. "
                    "Enterprise operators need a centralized risk intelligence page that aggregates risk "
                    "signals across all sessions and time periods.\n\n"
                    "The risk intelligence page provides: risk trend over time, top risk contributors "
                    "(sessions, agents, prompt types), escalation heatmap (time-of-day patterns), and "
                    "governance drift indicators (from E7). It transforms raw risk data into actionable "
                    "intelligence.\n\n"
                    "This page answers: 'Where is risk concentrated, and is it getting better or worse?'"
                ),
                business_impact=(
                    "- **Core impact:** Centralized risk visibility across all governance operations\n"
                    "- **Enterprise impact:** Medium — enables data-driven risk management\n"
                    "- **Strategic alignment:** Risk intelligence is the enterprise governance differentiator"
                ),
                priority_tier=(
                    "**Post-GA (Phase H)** — Requires governance score (E2), drift detection (E7), "
                    "and session risk data. Enterprise dashboard buildout."
                ),
                complexity=(
                    "**High** — Requires aggregating risk data from multiple sources, computing trends, "
                    "and rendering interactive visualizations. Data volume grows with usage."
                ),
                requirements=(
                    "- Risk trend chart: governance score over configurable window\n"
                    "- Top risk contributors: sessions/agents/prompt types ranked by risk\n"
                    "- Escalation heatmap: time-of-day × day-of-week escalation frequency\n"
                    "- Drift indicators: current drift status from E7\n"
                    "- Risk distribution: histogram of decision risk levels\n"
                    "- Configurable time window (24h, 7d, 30d)\n"
                    "- Drill-down from any metric to contributing sessions"
                ),
                acceptance=(
                    "- [ ] Risk trend chart renders correctly\n"
                    "- [ ] Top risk contributors accurately ranked\n"
                    "- [ ] Escalation heatmap shows correct time patterns\n"
                    "- [ ] Drift indicators display current status\n"
                    "- [ ] Time window selection works for all periods\n"
                    "- [ ] Drill-down navigation links to relevant sessions\n"
                    "- [ ] Page loads in < 3s for 30-day window\n"
                    "- [ ] Graceful degradation when data sources unavailable"
                ),
                ui_ux=(
                    "- Charts use minimal, governance-appropriate styling\n"
                    "- Risk levels use consistent color coding across all visualizations\n"
                    "- Interactive elements have clear hover/click affordances\n"
                    "- Summary statistics visible without scrolling"
                ),
                non_goals=(
                    "- Predictive risk modeling\n"
                    "- Custom visualization or chart types\n"
                    "- Automated risk mitigation\n"
                    "- Export of risk reports (v2.1)"
                ),
                dependencies=(
                    "- E2 (Governance Score) — trend data\n"
                    "- E7 (Drift Alerts) — drift indicators\n"
                    "- `dashboard/repo.py` — data aggregation\n"
                    "- `core/audit/writer.py` — event source"
                ),
                metrics=(
                    "- Page load time: < 3s for 30-day window\n"
                    "- Data accuracy: metrics match CLI output for same period\n"
                    "- All visualizations render correctly\n"
                    "- Test coverage: data aggregation, trend computation"
                ),
                enterprise_value=(
                    "Centralized risk intelligence enables data-driven governance management. "
                    "Organizations can identify risk concentrations, track governance improvement "
                    "over time, and make informed decisions about policy tuning."
                ),
                related_issues="None — new dashboard page.",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="UX",
            effort="L",
            edition="Enterprise",
            risk_level="Medium",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D5 — Policy Intelligence Page
    issues.append(
        Issue(
            id="D5",
            title="feat(dashboard): Policy intelligence page — effectiveness and coverage metrics",
            body=build_enterprise_body(
                phase="H",
                priority="P1",
                category="UX",
                effort="L",
                edition="Enterprise",
                summary=(
                    "Policy rules are currently managed via YAML files and validated through the CLI. "
                    "There is no dashboard view that shows how policies are performing: which rules fire "
                    "most often, which rules never match, what the coverage gaps are, and how rule "
                    "effectiveness changes over time.\n\n"
                    "The policy intelligence page provides a data-driven view of policy effectiveness. "
                    "It shows: rule hit rates, coverage score (from E9), escalation patterns (from E8), "
                    "and rule effectiveness trends. Operators can identify underperforming rules and "
                    "coverage gaps from the dashboard.\n\n"
                    "This page answers: 'Are my policies working, and where should I improve them?'"
                ),
                business_impact=(
                    "- **Core impact:** Policy effectiveness visibility for data-driven tuning\n"
                    "- **Enterprise impact:** Medium — enables systematic policy improvement\n"
                    "- **Strategic alignment:** Makes governance policy a managed, measurable asset"
                ),
                priority_tier=(
                    "**Post-GA (Phase H)** — Requires policy coverage (E9) and escalation patterns (E8). "
                    "Enterprise dashboard buildout."
                ),
                complexity=(
                    "**High** — Requires correlating policy rules with decision outcomes, computing "
                    "effectiveness metrics, and rendering interactive policy analytics."
                ),
                requirements=(
                    "- Rule hit rate table: each rule with match count, last match, trend\n"
                    "- Coverage score visualization (from E9)\n"
                    "- Dead rules detection: rules that haven't matched in configurable period\n"
                    "- Escalation pattern suggestions (from E8) if available\n"
                    "- Rule effectiveness: matches vs escalations ratio per rule\n"
                    "- Configurable time window (24h, 7d, 30d)\n"
                    "- Link to policy file for each rule"
                ),
                acceptance=(
                    "- [ ] Rule hit rate table populated with correct data\n"
                    "- [ ] Coverage score visualization renders correctly\n"
                    "- [ ] Dead rules identified and flagged\n"
                    "- [ ] Escalation patterns shown when data available\n"
                    "- [ ] Rule effectiveness computed correctly\n"
                    "- [ ] Time window selection works\n"
                    "- [ ] Page loads in < 3s\n"
                    "- [ ] Graceful degradation when optional data sources unavailable"
                ),
                ui_ux=(
                    "- Rules table sortable by hit rate, effectiveness, last match\n"
                    "- Coverage score prominently displayed\n"
                    "- Dead rules highlighted with warning indicator\n"
                    "- Actionable suggestions displayed alongside gaps"
                ),
                non_goals=(
                    "- Inline policy editing from dashboard\n"
                    "- Policy version comparison\n"
                    "- Automated policy optimization\n"
                    "- Policy templates or marketplace"
                ),
                dependencies=(
                    "- E9 (Policy Coverage) — coverage score\n"
                    "- E8 (Escalation Patterns) — pattern suggestions\n"
                    "- `core/policy/evaluator.py` — rule match tracking\n"
                    "- `dashboard/repo.py` — data access"
                ),
                metrics=(
                    "- Page load time: < 3s for 30-day window\n"
                    "- Rule hit rates match CLI computation for same period\n"
                    "- Dead rules correctly identified\n"
                    "- Test coverage: data aggregation and metric computation"
                ),
                enterprise_value=(
                    "Policy intelligence transforms governance from static configuration to a "
                    "managed, measurable asset. Organizations can systematically improve their "
                    "policies based on data, identify underperforming rules, and close coverage gaps."
                ),
                related_issues="None — new dashboard page.",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="UX",
            effort="L",
            edition="Enterprise",
            risk_level="Medium",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D6 — Immutable Audit Console
    issues.append(
        Issue(
            id="D6",
            title="feat(dashboard): Immutable audit console — interactive hash-verified log viewer",
            body=build_enterprise_body(
                phase="H",
                priority="P0",
                category="UX",
                effort="L",
                edition="Enterprise",
                summary=(
                    "AtlasBridge maintains a hash-chained audit log — every governance event is recorded "
                    "with a cryptographic hash linking it to the previous event. Currently, this log is "
                    "only accessible via the CLI or raw file inspection. There is no dashboard view that "
                    "lets operators browse, search, and verify the audit trail.\n\n"
                    "The immutable audit console provides an interactive audit log viewer with hash "
                    "verification. Operators can browse events chronologically, search by criteria, "
                    "verify hash chain integrity, and export audit records for compliance reporting.\n\n"
                    "Hash verification is the key differentiator: operators can prove that the audit "
                    "trail has not been tampered with. This is the compliance feature that enterprise "
                    "organizations require."
                ),
                business_impact=(
                    "- **Core impact:** Interactive audit trail with tamper detection\n"
                    "- **Enterprise impact:** High — hash-verified audit is a compliance requirement\n"
                    "- **Strategic alignment:** Only agent runtime with verifiable governance audit trail"
                ),
                priority_tier=(
                    "**Post-GA (Phase H)** — Enterprise compliance feature. Hash chain exists; "
                    "this adds interactive viewing and verification."
                ),
                complexity=(
                    "**High** — Requires hash chain verification UI, efficient log browsing for large "
                    "audit trails, search indexing, and export formatting. Performance matters for "
                    "audit trails with thousands of entries."
                ),
                requirements=(
                    "- Chronological audit log browser with pagination\n"
                    "- Event detail view with full payload\n"
                    "- Hash chain verification: one-click integrity check\n"
                    "- Visual indicator for chain integrity status\n"
                    "- Search by event type, session, time range, content\n"
                    "- Export as JSON, CSV for compliance reporting\n"
                    "- Chain break detection with exact break point identification\n"
                    "- Real-time new event indicator"
                ),
                acceptance=(
                    "- [ ] Audit log browser displays events chronologically\n"
                    "- [ ] Pagination works for logs with 10,000+ entries\n"
                    "- [ ] Event detail view shows complete payload\n"
                    "- [ ] Hash chain verification completes in < 10s for 10,000 entries\n"
                    "- [ ] Chain integrity indicator updates after verification\n"
                    "- [ ] Chain break detection identifies exact break point\n"
                    "- [ ] Search returns correct results for all criteria\n"
                    "- [ ] Export produces valid JSON and CSV\n"
                    "- [ ] Real-time indicator shows new events without page reload"
                ),
                ui_ux=(
                    "- Integrity indicator: green shield (verified), red shield (broken), "
                    "gray shield (unverified)\n"
                    "- Events use monospace font for technical data\n"
                    "- Hash values shown in truncated form with expand option\n"
                    "- Chain break highlighted with visual separator and explanation"
                ),
                non_goals=(
                    "- Audit log writing or modification from dashboard\n"
                    "- External audit system integration (Splunk, ELK)\n"
                    "- Multi-workspace audit aggregation\n"
                    "- Compliance report generation (export data only)"
                ),
                dependencies=(
                    "- `core/audit/writer.py` — audit log format and hash chain\n"
                    "- `dashboard/repo.py` — audit log read access\n"
                    "- `dashboard/app.py` — API endpoints for audit data"
                ),
                metrics=(
                    "- Hash chain verification: < 10s for 10,000 entries\n"
                    "- Log browsing: < 1s page load for any page\n"
                    "- Search: < 2s for full-text search across audit trail\n"
                    "- Export: < 5s for 10,000-entry JSON export"
                ),
                enterprise_value=(
                    "Hash-verified audit trail is the strongest compliance feature AtlasBridge offers. "
                    "Organizations can prove that governance was applied correctly and that the audit "
                    "trail has not been tampered with. This is a hard requirement for regulated "
                    "industries and a strong differentiator against other agent runtimes."
                ),
                related_issues="None — new dashboard page.",
            ),
            labels=["enhancement", "ux", "security", "phase:H-enterprise"],
            phase="H",
            priority="P0",
            category="UX",
            effort="L",
            edition="Enterprise",
            risk_level="High",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D7 — Multi-Workspace Governance
    issues.append(
        Issue(
            id="D7",
            title="feat(dashboard): Multi-workspace governance — cross-workspace comparison",
            body=build_enterprise_body(
                phase="H",
                priority="P2",
                category="UX",
                effort="XL",
                edition="Enterprise",
                summary=(
                    "Enterprise organizations run multiple AtlasBridge workspaces — different teams, "
                    "projects, or environments. Currently, each workspace is an isolated island with "
                    "no cross-workspace visibility. Operators managing multiple workspaces must switch "
                    "between dashboards to understand overall governance posture.\n\n"
                    "Multi-workspace governance provides a unified view across multiple AtlasBridge "
                    "workspaces. Operators can compare governance scores, risk trends, and policy "
                    "effectiveness across workspaces. This enables organizational governance: ensuring "
                    "consistent governance standards across teams.\n\n"
                    "This is the highest-complexity dashboard feature and requires workspace discovery, "
                    "data aggregation, and cross-workspace authorization."
                ),
                business_impact=(
                    "- **Core impact:** Organizational governance visibility across workspaces\n"
                    "- **Enterprise impact:** High — multi-workspace governance is an enterprise requirement\n"
                    "- **Strategic alignment:** Positions AtlasBridge for organization-wide deployment"
                ),
                priority_tier=(
                    "**Post-GA (Phase H, P2)** — Requires workspace isolation (#237) as foundation. "
                    "Highest-complexity feature in the dashboard roadmap."
                ),
                complexity=(
                    "**Very High** — Requires workspace discovery protocol, cross-workspace data "
                    "aggregation, authorization model, and comparison visualizations. Each workspace "
                    "may run different versions."
                ),
                requirements=(
                    "- Workspace registry: add/remove workspace endpoints\n"
                    "- Cross-workspace governance score comparison\n"
                    "- Cross-workspace risk trend overlay\n"
                    "- Policy consistency check: compare rules across workspaces\n"
                    "- Per-workspace health indicator on overview\n"
                    "- Workspace switching without re-authentication\n"
                    "- Data freshness indicator per workspace\n"
                    "- Graceful handling of unavailable workspaces"
                ),
                acceptance=(
                    "- [ ] Workspace registry functional (add/remove endpoints)\n"
                    "- [ ] Governance score comparison across workspaces\n"
                    "- [ ] Risk trend overlay renders correctly\n"
                    "- [ ] Policy consistency check identifies differences\n"
                    "- [ ] Overview shows per-workspace health\n"
                    "- [ ] Workspace switching is seamless\n"
                    "- [ ] Unavailable workspaces handled gracefully\n"
                    "- [ ] Data freshness indicators accurate\n"
                    "- [ ] Unit tests cover aggregation and comparison logic"
                ),
                ui_ux=(
                    "- Workspace selector in global navigation\n"
                    "- Comparison views use side-by-side or overlay layouts\n"
                    "- Unavailable workspaces shown as degraded, not hidden\n"
                    "- Clear labeling of which workspace data comes from"
                ),
                non_goals=(
                    "- Cross-workspace policy synchronization\n"
                    "- Centralized policy management\n"
                    "- Cross-workspace session management\n"
                    "- Organizational user management"
                ),
                dependencies=(
                    "- #237 (Multi-workspace isolation) — runtime workspace isolation\n"
                    "- D1 (Control Tower IA) — navigation structure\n"
                    "- D2 (Overview Page) — per-workspace widgets\n"
                    "- `dashboard/app.py` — cross-workspace API"
                ),
                metrics=(
                    "- Cross-workspace data aggregation: < 5s for 10 workspaces\n"
                    "- Workspace switching: < 1s\n"
                    "- Comparison views render correctly for up to 10 workspaces\n"
                    "- Test coverage: aggregation, comparison, degraded workspace handling"
                ),
                enterprise_value=(
                    "Multi-workspace governance enables organization-wide deployment. Enterprise "
                    "organizations need centralized visibility across all teams and projects using "
                    "AtlasBridge. Cross-workspace comparison ensures consistent governance standards "
                    "and identifies teams that need governance improvement."
                ),
                related_issues=(
                    "- Related: #237 (Multi-workspace isolation) — D7 is the dashboard view; "
                    "#237 is the runtime isolation layer. D7 depends on #237's workspace boundaries."
                ),
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P2",
            category="UX",
            effort="XL",
            edition="Enterprise",
            risk_level="High",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D8 — Global Autonomy Status
    issues.append(
        Issue(
            id="D8",
            title="feat(dashboard): Global autonomy status — system-wide autonomy state display",
            body=build_enterprise_body(
                phase="H",
                priority="P1",
                category="UX",
                effort="S",
                edition="Enterprise",
                summary=(
                    "The current dashboard shows session-level status but has no system-wide autonomy "
                    "indicator. Operators cannot see at a glance whether the system is in Off, Assist, "
                    "or Full autonomy mode, or whether incident mode is active.\n\n"
                    "The global autonomy status widget is a persistent, always-visible indicator that "
                    "shows: current autonomy mode, incident status, active session count, and time since "
                    "last operator interaction. It appears in the navigation header on every page.\n\n"
                    "This is the simplest dashboard feature but one of the most important — it provides "
                    "constant awareness of governance posture."
                ),
                business_impact=(
                    "- **Core impact:** Persistent governance awareness on every dashboard page\n"
                    "- **Enterprise impact:** Low — simple but foundational\n"
                    "- **Strategic alignment:** Governance visibility as a constant, not an afterthought"
                ),
                priority_tier=(
                    "**Post-GA (Phase H)** — Simple widget, but depends on dashboard navigation (D1) "
                    "for placement. Cheapest enterprise feature."
                ),
                complexity=(
                    "**Low** — Single widget reading from existing APIs. Primary work is visual design "
                    "and ensuring the indicator is always accurate."
                ),
                requirements=(
                    "- Persistent widget in navigation header\n"
                    "- Shows: autonomy mode (Off/Assist/Full) with color indicator\n"
                    "- Shows: incident status (Normal/Active) with color indicator\n"
                    "- Shows: active session count\n"
                    "- Shows: time since last operator interaction\n"
                    "- Updates in real-time (WebSocket or polling)\n"
                    "- Clickable: links to detailed status page"
                ),
                acceptance=(
                    "- [ ] Widget visible on every dashboard page\n"
                    "- [ ] Autonomy mode correctly displayed with color\n"
                    "- [ ] Incident status correctly displayed\n"
                    "- [ ] Active session count accurate\n"
                    "- [ ] Time since last interaction updates live\n"
                    "- [ ] Widget updates without page reload\n"
                    "- [ ] Click navigates to status details\n"
                    "- [ ] Unit tests cover state rendering"
                ),
                ui_ux=(
                    "- Compact design that fits in navigation header\n"
                    "- Color coding: green (Full), amber (Assist), gray (Off), red (Incident)\n"
                    "- Mode label always readable (no icon-only state)\n"
                    "- Transitions between states animate smoothly"
                ),
                non_goals=(
                    "- Mode switching from the widget (use dedicated page)\n"
                    "- Historical mode timeline\n"
                    "- Per-session autonomy status\n"
                    "- Customizable widget appearance"
                ),
                dependencies=(
                    "- D1 (Control Tower IA) — navigation header placement\n"
                    "- `core/autopilot/engine.py` — autonomy mode API\n"
                    "- E1 (Incident Mode) — incident status API"
                ),
                metrics=(
                    "- Widget update latency: < 2s from state change to display update\n"
                    "- Widget render time: < 50ms\n"
                    "- State accuracy: always matches actual system state\n"
                    "- Test coverage: all mode and status combinations"
                ),
                enterprise_value=(
                    "Persistent governance awareness ensures operators always know the system's "
                    "governance posture. This simple feature prevents the common failure mode of "
                    "operators not realizing the system is in a degraded or emergency state."
                ),
                related_issues="None — new dashboard widget.",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="UX",
            effort="S",
            edition="Enterprise",
            risk_level="Low",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D9 — Emergency Kill Switch Dashboard
    issues.append(
        Issue(
            id="D9",
            title="feat(dashboard): Emergency kill switch — visual kill switch with confirmation flow",
            body=build_enterprise_body(
                phase="H",
                priority="P0",
                category="UX",
                effort="M",
                edition="Enterprise",
                summary=(
                    "AtlasBridge has a backend kill switch that can pause all agents and trigger "
                    "incident mode. Currently, this is only accessible via CLI or channel commands. "
                    "Enterprise operators need a visual kill switch on the dashboard — a prominent, "
                    "always-accessible emergency action with a confirmation flow.\n\n"
                    "The emergency kill switch is a dashboard UX for the backend kill switch "
                    "infrastructure. It provides: a prominent kill switch button visible from any page, "
                    "a confirmation dialog with impact summary, one-click incident mode activation, "
                    "and a recovery flow with status tracking.\n\n"
                    "This is the highest-priority dashboard UX feature because it directly enables "
                    "emergency response from the dashboard."
                ),
                business_impact=(
                    "- **Core impact:** Dashboard-accessible emergency response\n"
                    "- **Enterprise impact:** High — visual kill switch is an enterprise safety requirement\n"
                    "- **Strategic alignment:** Completes the emergency response surface: CLI + channel + dashboard"
                ),
                priority_tier=(
                    "**Post-GA (Phase H, P0)** — Highest-priority dashboard feature. Depends on "
                    "E1 (Incident Mode) for backend functionality."
                ),
                complexity=(
                    "**Medium** — Frontend UX for existing backend capability. The challenge is designing "
                    "a confirmation flow that is fast enough for emergencies but safe enough to prevent "
                    "accidental activation."
                ),
                requirements=(
                    "- Kill switch button: visible from every dashboard page, prominent but not accidentally clickable\n"
                    "- Confirmation dialog: shows impact summary (active sessions, pending prompts)\n"
                    "- Confirmation requires explicit action (type 'CONFIRM' or hold button for 3s)\n"
                    "- Triggers incident mode (E1) on backend\n"
                    "- Post-activation: shows incident status with timeline\n"
                    "- Recovery flow: guided recovery with status tracking\n"
                    "- Audit trail: kill switch activation logged with operator identity"
                ),
                acceptance=(
                    "- [ ] Kill switch button visible on every page\n"
                    "- [ ] Confirmation dialog shows accurate impact summary\n"
                    "- [ ] Accidental activation prevented by confirmation requirement\n"
                    "- [ ] Activation triggers incident mode within 2s\n"
                    "- [ ] Post-activation status displayed correctly\n"
                    "- [ ] Recovery flow guides operator through resolution\n"
                    "- [ ] Audit log records activation with operator identity\n"
                    "- [ ] Button disabled when incident already active\n"
                    "- [ ] Unit tests cover activation flow and edge cases"
                ),
                ui_ux=(
                    "- Kill switch: red, prominent, labeled clearly — not an unlabeled icon\n"
                    "- Confirmation: serious design, impact summary visible, explicit action required\n"
                    "- Post-activation: full-screen incident status overlay\n"
                    "- Recovery: step-by-step guided flow with progress indicators"
                ),
                non_goals=(
                    "- Automated kill switch triggers from dashboard\n"
                    "- Partial kill switch (specific sessions only — use session controls)\n"
                    "- Kill switch scheduling or delay\n"
                    "- Multi-operator confirmation for kill switch"
                ),
                dependencies=(
                    "- E1 (Incident Mode) — backend incident management\n"
                    "- D1 (Control Tower IA) — button placement in navigation\n"
                    "- `dashboard/app.py` — API endpoint for kill switch\n"
                    "- `core/daemon/manager.py` — session pause orchestration"
                ),
                metrics=(
                    "- Activation time: < 2s from confirmation to all sessions paused\n"
                    "- Confirmation dialog load time: < 500ms\n"
                    "- Zero accidental activations (confirmation flow effective)\n"
                    "- Test coverage: activation flow, recovery flow, edge cases"
                ),
                enterprise_value=(
                    "A visual kill switch completes the emergency response surface. Enterprise "
                    "operators expect dashboard-accessible emergency controls. The confirmation flow "
                    "balances speed (emergencies) with safety (preventing accidents)."
                ),
                related_issues=(
                    "- Related: #234 (Enterprise kill switch) — D9 is the dashboard UX; "
                    "#234 is the backend kill switch signal and propagation infrastructure."
                ),
            ),
            labels=["enhancement", "ux", "security", "phase:H-enterprise"],
            phase="H",
            priority="P0",
            category="UX",
            effort="M",
            edition="Enterprise",
            risk_level="Critical",
            target_date="v2.0.0",
            batch=2,
        )
    )

    # D10 — Structured Session Chat Pane
    issues.append(
        Issue(
            id="D10",
            title="feat(dashboard): Structured session chat pane — governance-annotated conversation view",
            body=build_enterprise_body(
                phase="H",
                priority="P1",
                category="UX",
                effort="M",
                edition="Enterprise",
                summary=(
                    "When operators view a session in the dashboard, they see governance data: decisions, "
                    "escalations, and audit events. But they don't see the actual conversation between "
                    "the agent and AtlasBridge — the prompts, responses, and operator messages that "
                    "constitute the session's narrative.\n\n"
                    "The structured session chat pane provides a conversation view of a session, similar "
                    "to a chat interface, but annotated with governance metadata. Each message shows: "
                    "who sent it (agent prompt, auto-response, operator reply), the governance decision "
                    "that was applied, and the risk context. This gives operators a complete picture: "
                    "what happened (conversation) and why (governance).\n\n"
                    "This bridges the gap between governance data and human understanding."
                ),
                business_impact=(
                    "- **Core impact:** Human-readable session narrative with governance annotations\n"
                    "- **Enterprise impact:** Low — complements deep trace (D3) for different audience\n"
                    "- **Strategic alignment:** Makes governance decisions understandable in conversational context"
                ),
                priority_tier=(
                    "**Post-GA (Phase H)** — Enterprise dashboard feature. Depends on conversation "
                    "session binding infrastructure (v0.9.8)."
                ),
                complexity=(
                    "**Medium** — Requires merging conversation data with governance annotations. "
                    "The challenge is presenting governance metadata without overwhelming the "
                    "conversation view."
                ),
                requirements=(
                    "- Chat-style message list: agent prompts, auto-responses, operator replies\n"
                    "- Governance annotations per message: decision type, confidence, rule matched\n"
                    "- Expandable governance detail on each message\n"
                    "- Visual distinction: agent messages, system messages, operator messages\n"
                    "- Message search within session\n"
                    "- Link to deep trace (D3) for full governance analysis\n"
                    "- Real-time updates for active sessions"
                ),
                acceptance=(
                    "- [ ] All conversation messages displayed in chronological order\n"
                    "- [ ] Governance annotations present on each governed message\n"
                    "- [ ] Expandable details show full governance context\n"
                    "- [ ] Visual distinction between message types\n"
                    "- [ ] Search works within session messages\n"
                    "- [ ] Link to deep trace functional\n"
                    "- [ ] Real-time updates for active sessions\n"
                    "- [ ] Unit tests cover message rendering and annotation"
                ),
                ui_ux=(
                    "- Chat layout: familiar messaging interface\n"
                    "- Governance annotations: subtle badges, not inline text\n"
                    "- Risk indicators: color-coded dot per message\n"
                    "- Expandable details use slide-out panel, not inline expansion\n"
                    "- Readable at mobile viewport widths"
                ),
                non_goals=(
                    "- Replying to messages from dashboard (use channel)\n"
                    "- Message editing or deletion\n"
                    "- Cross-session conversation view\n"
                    "- AI-generated conversation summaries"
                ),
                dependencies=(
                    "- `core/conversation/session_binding.py` — conversation data\n"
                    "- `core/interaction/engine.py` — governance decision context\n"
                    "- D3 (Session Deep Trace) — link target\n"
                    "- `dashboard/repo.py` — data access"
                ),
                metrics=(
                    "- Page load time: < 2s for sessions with 100 messages\n"
                    "- Message rendering: correct chronological order\n"
                    "- Annotation accuracy: governance data matches decision trace\n"
                    "- Test coverage: message rendering, annotation, search"
                ),
                enterprise_value=(
                    "The structured chat pane makes governance decisions understandable in their "
                    "conversational context. Enterprise operators reviewing sessions get both the "
                    "narrative (what happened) and the governance story (why decisions were made) "
                    "in a single, integrated view."
                ),
                related_issues="None — new dashboard view.",
            ),
            labels=["enhancement", "ux", "phase:H-enterprise"],
            phase="H",
            priority="P1",
            category="UX",
            effort="M",
            edition="Enterprise",
            risk_level="Low",
            target_date="v2.0.0",
            batch=2,
        )
    )

    return issues


# ---------------------------------------------------------------------------
# All issues
# ---------------------------------------------------------------------------


def all_issues() -> list[Issue]:
    return governance_engine_issues() + dashboard_ux_issues()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_all(issues: list[Issue]) -> None:
    """Check prohibited terms in all issue bodies and titles."""
    for issue in issues:
        check_prohibited(issue.title, f"title of {issue.id}")
        check_prohibited(issue.body, f"body of {issue.id}")
    print(f"Validated {len(issues)} issues — no prohibited terms found.")


# ---------------------------------------------------------------------------
# Issue creation
# ---------------------------------------------------------------------------


def create_issue(issue: Issue, *, dry_run: bool = False) -> int | None:
    """Create a GitHub issue. Returns issue number or None for dry run."""
    if dry_run:
        print(f"[DRY RUN] Would create: {issue.title}")
        print(f"  Labels: {', '.join(issue.labels)}")
        print(f"  Phase: {issue.phase} | Priority: {issue.priority} | Effort: {issue.effort}")
        print(
            f"  Edition: {issue.edition} | Risk: {issue.risk_level} | Target: {issue.target_date}"
        )
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

    url = result.stdout.strip()
    number = int(url.rstrip("/").split("/")[-1])
    issue.gh_number = number
    print(f"Created #{number}: {issue.title}")
    return number


# ---------------------------------------------------------------------------
# Project board integration
# ---------------------------------------------------------------------------


def _set_date_field(
    item_id: str,
    field_id: str,
    date_value: str,
    *,
    dry_run: bool = False,
) -> None:
    """Set a date field on a project item. date_value must be ISO format (YYYY-MM-DD)."""
    if dry_run:
        print(f"[DRY RUN] Would set date {field_id[-4:]}... = {date_value}")
        return

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
        set_single_select_field(item_id, RISK_LEVEL, issue.risk_level, dry_run=dry_run)

        date_val = TARGET_DATES.get(issue.target_date)
        if date_val:
            _set_date_field(item_id, TARGET_DATE_FIELD_ID, date_val, dry_run=dry_run)

    except Exception as e:
        print(f"  WARNING: project board setup failed for #{issue.gh_number}: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


def run(*, dry_run: bool = False, batch_filter: int | None = None) -> None:
    """Main execution: create issues by batch."""
    issues = all_issues()
    validate_all(issues)

    batches: dict[int, list[Issue]] = {}
    for issue in issues:
        batches.setdefault(issue.batch, []).append(issue)

    batch_names = {
        1: "Governance Engine Features",
        2: "Enterprise Dashboard UX",
    }

    for batch_num in [1, 2]:
        if batch_filter is not None and batch_num != batch_filter:
            continue

        batch_issues = batches.get(batch_num, [])
        if not batch_issues:
            continue

        print(f"\n{'=' * 60}")
        print(
            f"Batch {batch_num}: {batch_names.get(batch_num, 'Unknown')} ({len(batch_issues)} issues)"
        )
        print(f"{'=' * 60}\n")

        for issue in batch_issues:
            create_issue(issue, dry_run=dry_run)
            if not dry_run:
                time.sleep(1)

        if not dry_run:
            print(f"\nAdding batch {batch_num} to project board...")
            for issue in batch_issues:
                add_to_project_board(issue, dry_run=dry_run)

    # Summary
    created = [i for i in issues if i.gh_number is not None]
    skipped = len(issues) - len(created)
    print(f"\n{'=' * 60}")
    print(f"Summary: {len(created)}/{len(issues)} issues created")
    if batch_filter is not None:
        print(f"(filtered to batch {batch_filter})")
        if skipped > 0:
            print(f"{skipped} issues in other batches skipped")
    print(f"{'=' * 60}")

    if created:
        print("\nCreated issues:")
        for i in created:
            print(f"  #{i.gh_number}: {i.title}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create 20 AtlasBridge enterprise governance issues"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument(
        "--batch",
        type=int,
        choices=[1, 2],
        help="Run only specific batch (1=governance, 2=dashboard)",
    )
    parser.add_argument("--validate-only", action="store_true", help="Only check prohibited terms")
    args = parser.parse_args()

    if args.validate_only:
        issues = all_issues()
        validate_all(issues)
        print(f"\nTotal issues defined: {len(issues)}")
        by_batch: dict[int, list[Issue]] = {}
        for i in issues:
            by_batch.setdefault(i.batch, []).append(i)
        for b in sorted(by_batch):
            batch_names = {1: "Governance Engine Features", 2: "Enterprise Dashboard UX"}
            print(f"  Batch {b} ({batch_names.get(b, 'Unknown')}): {len(by_batch[b])} issues")

        # Verify cross-references
        print("\nCross-references:")
        for i in issues:
            for ref in ["#232", "#222", "#237", "#234"]:
                if ref in i.body:
                    print(f"  {i.id} ({i.title[:50]}...) references {ref}")
        return

    run(dry_run=args.dry_run, batch_filter=args.batch)


if __name__ == "__main__":
    main()
