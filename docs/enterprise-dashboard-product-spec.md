# DESIGN ONLY — NO IMPLEMENTATION IN THIS RELEASE

# Enterprise Dashboard — Product Specification

**Maturity:** Design Document — No Implementation
**Phase:** C (Enterprise Dashboard)
**Depends on:** Phase A (shipped), Phase B (scaffold only)
**Trust model:** Cloud OBSERVES, local EXECUTES.

---

## What the Dashboard Is

The AtlasBridge Enterprise Dashboard is a web-based governance and observability
console for organizations running multiple AtlasBridge runtime agents. It
provides centralized visibility into sessions, decisions, audit trails, risk
metrics, and policy management — without any execution authority.

The dashboard reads metadata that local runtimes push asynchronously. It cannot
send commands, inject replies, access PTYs, or modify local behavior. Policy
distribution is the only write path, and it requires Ed25519 signature
verification by the receiving runtime before acceptance.

**In one sentence:** A read-only governance pane over a fleet of autonomous
runtime agents.

---

## What It Does NOT Do

These are non-negotiable exclusions:

| Excluded Capability | Reason |
|---------------------|--------|
| Remote shell execution | Cloud has no PTY access. Execution is local only. |
| Prompt reply via dashboard | Replies go through Telegram/Slack. Dashboard has no injection path. |
| CI/CD bypass or override | Policy evaluation is local. Cloud cannot override a decision. |
| Direct database writes to runtime | Data flows one-way: local → cloud. Cloud cannot push data into local SQLite. |
| PTY output viewing | PTY output never leaves the local runtime. Dashboard shows prompt excerpts only (max 200 chars). |
| Force-overwrite local policy | Runtime validates Ed25519 signatures. Invalid policies are rejected. Local file edits always win. |

---

## User Personas

### Fleet Admin

**Role:** `admin` or `owner`
**Goal:** Ensure all runtime agents are healthy, running approved policies, and
producing a clean audit trail.
**Key screens:** Fleet Overview, Agent Status, Settings.
**Typical workflow:** Morning check of fleet health → review overnight
escalations → verify policy versions are consistent → check risk dashboard for
anomalies.

### Security Reviewer

**Role:** `viewer` or `admin`
**Goal:** Audit decision trails for compliance, verify hash chain integrity,
investigate incidents.
**Key screens:** Audit Trail, Session Detail, Risk Dashboard.
**Typical workflow:** Filter audit events by date range and risk level → verify
hash chain continuity → export events for compliance reporting → investigate
flagged escalations.

### Policy Author

**Role:** `admin`
**Goal:** Write, test, sign, and distribute policy rules across the fleet.
**Key screens:** Policy Editor, Session Detail (for decision analysis).
**Typical workflow:** Draft policy YAML → validate and test against sample
prompts → compare diff with current active policy → sign and distribute →
monitor per-rule hit counts.

### Executive

**Role:** `viewer`
**Goal:** High-level risk posture and operational metrics without deep
technical detail.
**Key screens:** Fleet Overview, Risk Dashboard.
**Typical workflow:** Check summary cards (agents, sessions, escalation rate)
→ review risk trend chart → confirm no critical alerts.

---

## Feature Matrix by Edition

| Feature | Community | Pro | Enterprise |
|---------|-----------|-----|------------|
| Local runtime (CLI) | Yes | Yes | Yes |
| Local policy evaluation | Yes | Yes | Yes |
| Telegram/Slack relay | Yes | Yes | Yes |
| Local audit trail | Yes | Yes | Yes |
| Dashboard: Fleet Overview | — | Yes | Yes |
| Dashboard: Session list + detail | — | Yes | Yes |
| Dashboard: Audit trail (read) | — | Yes | Yes |
| Dashboard: Policy viewer | — | Yes | Yes |
| Dashboard: Policy editor + distribute | — | — | Yes |
| Dashboard: Risk dashboard + alerts | — | — | Yes |
| Dashboard: User/team management | — | — | Yes |
| Dashboard: SAML/OIDC SSO | — | — | Yes |
| Dashboard: Data residency selection | — | — | Yes |
| Dashboard: Audit export (CSV/JSON) | — | — | Yes |
| API access (agent sync) | — | Yes | Yes |
| API access (management) | — | — | Yes |
| Agent limit | 1 (local) | 10 | Unlimited |
| User limit | 1 (local) | 10 | Unlimited |

Community edition is local-only. No cloud components.

---

## MVP Scope vs. Future Scope

### MVP (Phase C v1)

- Fleet Overview screen with summary cards and agent status
- Session list and session detail (prompt timeline)
- Audit trail with search, filter, and hash chain integrity indicator
- Policy viewer (read-only for all roles; edit for admin+)
- Risk dashboard with summary metrics and time-window trends
- Settings screen (org profile, user management, agent registry)
- Login via OIDC (one provider)
- Agent sync endpoints (sessions, prompts, decisions, audit, heartbeat)
- RBAC enforcement (4 roles: viewer, operator, admin, owner)
- PostgreSQL with RLS for tenant isolation

### Future Scope (not in MVP)

- SAML 2.0 SSO
- Multi-region data residency
- Policy approval workflow (two-admin sign-off)
- Audit cold storage (S3 archival)
- PagerDuty / email alert integrations
- Agent grouping (production / development / staging)
- Billing integration (Stripe)
- Multi-org support per user
- Custom dashboard widgets
- Webhook notifications for external systems

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Agent sync latency (p95) | < 5 seconds | Time from local event to cloud storage |
| Dashboard page load (p95) | < 2 seconds | Time to interactive for any screen |
| Audit chain integrity | 100% (zero breaks) | Hash chain validation on ingestion |
| Policy distribution latency | < 10 seconds | Time from sign to agent acceptance |
| Escalation visibility | 100% of escalations visible in dashboard within 30s | WebSocket event delivery |
| Adoption: agents connected | > 80% of org agents within 30 days of onboarding | Agent registry vs. heartbeat count |
| Incident response time | < 5 minutes from alert to human acknowledgment | Risk alert → dashboard interaction timestamp |

---

> **Reminder:** This is a design document. No implementation exists.
> The local runtime is fully functional without any cloud component.
> Cloud features are additive and degradable.
