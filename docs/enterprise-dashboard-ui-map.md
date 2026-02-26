# DESIGN ONLY — NO IMPLEMENTATION IN THIS RELEASE

# Enterprise Dashboard — UI Screen Map

**Maturity:** Design Document — No Implementation
**Phase:** C (Enterprise Dashboard)
**Trust model:** Cloud OBSERVES, local EXECUTES.
**Canonical source:** enterprise-saas-architecture.md § Dashboard UI Screens

---

## Screen Inventory

| # | Screen | URL Pattern | Purpose | Min Role |
|---|--------|-------------|---------|----------|
| 1 | Login | `/login` | Authenticate user, establish org context | — |
| 2 | Fleet Overview | `/` | At-a-glance fleet health and activity | viewer |
| 3 | Sessions List | `/sessions` | Browse and filter all sessions | viewer |
| 4 | Session Detail | `/sessions/:id` | Prompt-by-prompt timeline for one session | viewer |
| 5 | Policy Editor | `/policies` | View, edit, test, sign, and distribute policies | viewer (read), admin (write) |
| 6 | Audit Trail | `/audit` | Searchable audit log with integrity verification | viewer |
| 7 | Risk Dashboard | `/risk` | Aggregated risk metrics, trends, and alerts | viewer |
| 8 | Settings | `/settings/*` | Org config, users, agents, API keys, retention | admin/owner |

---

## Navigation Flow

```
                         ┌──────────┐
                         │  Login   │
                         └────┬─────┘
                              │ (auth success)
                              v
┌─────────────────────────────────────────────────────────┐
│                    Top Navigation Bar                     │
│  [Fleet]  [Sessions]  [Policies]  [Audit]  [Risk]  [⚙]  │
└─────┬────────┬──────────┬─────────┬────────┬────────┬───┘
      │        │          │         │        │        │
      v        v          v         v        v        v
   Fleet    Sessions   Policies   Audit    Risk    Settings
  Overview    List      Editor    Trail   Dashboard  Tabs
      │        │
      │        └──> Session Detail (click row)
      │
      └──> Session Detail (click activity feed item)
           Agent Detail (click agent row) → Sessions filtered by agent
```

All top-level screens are accessible from the persistent navigation bar.
Session Detail is reached by clicking a row in Sessions List or an item in the
Fleet Overview activity feed. Settings tabs are reached via the gear icon.

---

## Screen 1 — Login

**Purpose:** Authenticate and establish org context.

```
┌─────────────────────────────────────────┐
│                                         │
│           ┌─────────────────┐           │
│           │  [AtlasBridge]  │           │
│           │                 │           │
│           │  Sign in with   │           │
│           │  [  SSO  ]      │           │
│           │                 │           │
│           │  ─── or ───     │           │
│           │                 │           │
│           │  Email ______   │           │
│           │  Pass  ______   │           │
│           │  [  Sign in  ]  │           │
│           │                 │           │
│           │  Org: [▾ pick]  │           │
│           └─────────────────┘           │
│                                         │
└─────────────────────────────────────────┘
```

**States:**
- **Default:** Form visible, SSO button prominent.
- **Loading:** Spinner on button after click. Form disabled.
- **Error:** Inline error below form ("Invalid credentials" / "SSO failed").
- **MFA:** TOTP input replaces login form if MFA enabled.
- **Multi-org:** Org selector appears if user belongs to multiple orgs.

**Data dependencies:** None (pre-auth).

---

## Screen 2 — Fleet Overview

**Purpose:** At-a-glance health of all managed agents.

```
┌─────────────────────────────────────────────────────────┐
│  Fleet Overview                           [Last 24h ▾]  │
├────────────┬───────────┬───────────┬────────────────────┤
│  Agents    │ Sessions  │ Prompts   │ Escalations        │
│    12      │    47     │  1,204    │    38  (3.2%)      │
│  active    │  today    │  today    │  target <5%        │
├────────────┴───────────┴───────────┴────────────────────┤
│  Prompt Volume (24h)         │  Decision Breakdown      │
│  ┌────────────────────────┐  │  ┌────────────────────┐  │
│  │ ▂▃▅▇█▇▅▃▂▁ ▂▃▅▇█▇▅▃  │  │  │ Auto-approve  72%  │  │
│  │ 12a  6a  12p  6p  12a │  │  │ Escalated     25%  │  │
│  └────────────────────────┘  │  │ Denied         3%  │  │
│                              │  └────────────────────┘  │
├──────────────────────────────┴──────────────────────────┤
│  Recent Activity (live via WebSocket)                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 14:22  agent-mac-01  prompt resolved  auto       │   │
│  │ 14:21  agent-linux-3 escalated        human      │   │
│  │ 14:20  agent-mac-01  session started  claude     │   │
│  └──────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│  Agent Status                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │ ● agent-mac-01    claude  v0.8.6  2 sess  14:22 │   │
│  │ ● agent-linux-3   openai  v0.8.6  1 sess  14:21 │   │
│  │ ○ agent-ci-runner gemini  v0.8.6  offline 12:00 │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**States:**
- **Loading:** Skeleton cards (gray pulsing rectangles) in place of summary cards and charts.
- **Empty:** "No agents registered yet. Connect your first agent to get started." with setup link.
- **Error:** "Failed to load fleet data. Retrying..." with manual retry button.
- **Populated:** Full layout as shown above.

**Data dependencies:**
- `GET /agents` → agent table
- `GET /sessions?range=24h` → session count, prompt count
- `GET /audit?range=24h&limit=20` → activity feed
- `WS /live` → real-time activity updates

**Components:**
- `SummaryCardRow` — 4 metric cards with sparkline support
- `PromptVolumeChart` — time-series area chart (24h default)
- `DecisionBreakdownPie` — donut chart of auto/escalated/denied
- `ActivityFeed` — scrolling event list, WebSocket-driven
- `AgentStatusTable` — sortable table with status indicators

---

## Screen 3 — Sessions List

**Purpose:** Browse and filter sessions across the fleet.

```
┌─────────────────────────────────────────────────────────┐
│  Sessions                                [Export CSV]    │
├─────────────────────────────────────────────────────────┤
│  Filters: [Date range ▾] [Agent ▾] [Adapter ▾] [Status]│
├──────┬──────────┬─────────┬────────┬────────┬───────────┤
│  ID  │ Agent    │ Adapter │ Start  │ Status │ Prompts   │
├──────┼──────────┼─────────┼────────┼────────┼───────────┤
│ ab12 │ mac-01   │ claude  │ 14:00  │ ● run  │ 8 (1 esc) │
│ cd34 │ linux-3  │ openai  │ 13:45  │ ● done │ 3         │
│ ef56 │ mac-02   │ claude  │ 12:30  │ ○ crash│ 5 (2 esc) │
│ ...  │          │         │        │        │           │
├──────┴──────────┴─────────┴────────┴────────┴───────────┤
│  Page 1 of 12                    [< Prev] [Next >]      │
└─────────────────────────────────────────────────────────┘
```

**States:**
- **Loading:** Table skeleton with pulsing rows.
- **Empty:** "No sessions found matching your filters." Clear filters link.
- **Error:** Inline error banner with retry.
- **Populated:** Paginated table. Click row → Session Detail.

**Data dependencies:** `GET /sessions?page=&per_page=50&sort=-started_at&filter[]=...`

---

## Screen 4 — Session Detail

**Purpose:** Prompt-by-prompt timeline of a single session.

```
┌─────────────────────────────────────────────────────────┐
│  Session ab12345                          [Export JSON]  │
│  Agent: mac-01 (claude) │ Started: 14:00 │ 22 min      │
│  Status: completed │ Exit: 0 │ Prompts: 8 │ Escalated: 1│
├─────────────────────────────────────────────────────────┤
│  Prompt Timeline                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 14:02  yes_no    HIGH  auto_approve              │   │
│  │        "Continue? [y/n]"                          │   │
│  │        Rule: allow-tests → "y"  Risk: LOW  12ms  │   │
│  │                                                    │   │
│  │ 14:05  free_text MED   escalated                  │   │
│  │        "Enter the API key:"                       │   │
│  │        → Telegram  Resolved 45s  telegram:123456  │   │
│  │                                                    │   │
│  │ 14:08  yes_no    HIGH  auto_approve              │   │
│  │        "Run tests? [y/n]"                         │   │
│  │        Rule: allow-tests → "y"  Risk: LOW  8ms   │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ⚠ No PTY output. PTY output never leaves the runtime.  │
└─────────────────────────────────────────────────────────┘
```

**States:**
- **Loading:** Header skeleton + empty timeline with spinner.
- **Error:** "Session not found" (404) or "Failed to load" (retry).
- **Populated:** Full prompt timeline with expandable entries.

**Data dependencies:**
- `GET /sessions/:id` → header metadata
- `GET /sessions/:id/events?per_page=100` → timeline events

**Components:**
- `SessionHeader` — metadata row (agent, adapter, duration, status, counts)
- `PromptTimeline` — vertical timeline of prompt events
- `PromptEntry` — expandable card per prompt (type, confidence, rule, decision, risk, latency)
- `EscalationBadge` — highlights escalated prompts with channel and responder
- `PTYDisclaimer` — persistent notice that PTY output is never shown

---

## Screen 5 — Policy Editor

**Purpose:** View, edit, test, sign, and distribute policies.

```
┌─────────────────────────────────────────────────────────┐
│  Policies                                                │
├──────────────┬──────────────────────────┬───────────────┤
│  Versions    │  Editor                  │  Metadata     │
│              │                          │               │
│  v13 ● active│  1│ version: "1"         │  Name: prod   │
│  v12         │  2│ rules:               │  Rules: 10    │
│  v11         │  3│  - name: allow-tests │  DSL: v1      │
│  v10         │  4│    match:            │  Hash: sha2.. │
│  v9          │  5│      prompt_type:    │  Signed: ✓    │
│              │  6│        - yes_no      │               │
│              │ ...                      │               │
│              ├──────────────────────────┤               │
│              │  Test Rule               │               │
│              │  Prompt: [________]      │               │
│              │  Type: [yes_no ▾]        │               │
│              │  Conf: [high ▾]          │               │
│              │  [Test] → allow-tests    │               │
├──────────────┴──────────────────────────┴───────────────┤
│  [Validate] [Save Draft] [Diff v12↔v13] [Sign+Distrib] │
└─────────────────────────────────────────────────────────┘
```

**States:**
- **Loading:** Skeleton panels.
- **Empty:** "No policies created yet. Create your first policy." with template button.
- **Validation error:** Inline error markers in editor gutter + error panel below.
- **Populated:** Three-panel layout as shown.

**Data dependencies:**
- `GET /policies` → version list
- `GET /policies/:version` → YAML content and metadata
- `POST /policies/test` → rule match simulation
- `POST /policies` → save new version
- `POST /policies/:version/distribute` → sign and push

**Access control:** Viewers and operators see read-only editor. Admin+ can edit, save, sign, distribute.

---

## Screen 6 — Audit Trail

**Purpose:** Searchable audit log with integrity verification.

```
┌─────────────────────────────────────────────────────────┐
│  Audit Trail                              [Export ▾]    │
├─────────────────────────────────────────────────────────┤
│  Search: [___________________]  [Date ▾] [Type ▾]      │
│  Agent: [All ▾]  Session: [All ▾]                      │
├──────────┬──────────┬────────────┬──────┬───────────────┤
│ Time     │ Agent    │ Event      │ Sess │ Chain         │
├──────────┼──────────┼────────────┼──────┼───────────────┤
│ 14:22:01 │ mac-01   │ reply_inj  │ ab12 │ ✓ verified   │
│ 14:22:00 │ mac-01   │ policy_ev  │ ab12 │ ✓ verified   │
│ 14:21:45 │ linux-3  │ escalated  │ cd34 │ ✓ verified   │
│ 14:21:30 │ linux-3  │ prompt_det │ cd34 │ ⚠ gap        │
│ ...      │          │            │      │               │
├──────────┴──────────┴────────────┴──────┴───────────────┤
│  Chain integrity: 99.8% verified │ 2 gaps (offline)     │
│  Page 1 of 84                    [< Prev] [Next >]      │
└─────────────────────────────────────────────────────────┘
```

**States:**
- **Loading:** Skeleton table.
- **Empty:** "No audit events found for the selected filters."
- **Error:** Inline banner with retry.
- **Populated:** Paginated event table with hash chain status per event.

**Hash chain indicators:**
- ✓ Green: hash verified, chain continuous
- ⚠ Yellow: sync gap detected (offline period) — expected and safe
- ✗ Red: broken chain — integrity violation, requires investigation

**Data dependencies:**
- `GET /audit?search=&event_type=&range=&page=` → event list
- `GET /audit/integrity` → chain integrity summary
- `GET /audit/export` → CSV/JSON download

---

## Screen 7 — Risk Dashboard

**Purpose:** Aggregated risk metrics and alert management.

```
┌─────────────────────────────────────────────────────────┐
│  Risk Overview                            [Last 7d ▾]   │
├───────────┬───────────┬───────────┬─────────────────────┤
│  CRITICAL │   HIGH    │  MEDIUM   │  Risk Trend (7d)    │
│     0     │     3     │    42     │  ▂▃▃▂▂▃▅ declining  │
├───────────┴───────────┴───────────┴─────────────────────┤
│  Risk Breakdown by Factor                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Escalation rate:       3.2%  (target <5%)   OK   │   │
│  │ Low-confidence rate:   12%   (target <15%)  OK   │   │
│  │ Policy miss rate:      2.1%  (target <3%)   OK   │   │
│  │ Auto on protected:     0.8%  (target <1%)   WARN │   │
│  │ Avg response time:     34s   (target <60s)  OK   │   │
│  └──────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│  Active Alerts                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │ ⚠ HIGH: agent-linux-3 auto-replied on main      │   │
│  │ ⚠ HIGH: 2 low-confidence auto-approvals in 1h   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**States:**
- **Loading:** Skeleton cards with pulsing trend placeholder.
- **Empty:** "No risk data available yet. Risk metrics appear after agents sync decision traces."
- **Error:** Inline retry banner.
- **Populated:** Full risk dashboard with drillable metrics.

**Data dependencies:**
- `GET /risk` → summary metrics
- `GET /risk/trends?window=7d` → trend data
- `GET /risk/alerts` → active alerts
- `PUT /risk/alerts/config` → threshold configuration (admin+)

---

## Screen 8 — Settings

**Purpose:** Org configuration, user management, infrastructure.

```
┌─────────────────────────────────────────────────────────┐
│  Settings                                                │
├─────────┬───────────────────────────────────────────────┤
│  Tabs:  │                                               │
│         │  [Selected tab content here]                  │
│  Org    │                                               │
│  Users  │  8a: Org name, slug, edition, plan, region    │
│  Agents │  8b: User table + invite/edit/remove          │
│  Keys   │  8c: Agent registry + revoke/rotate           │
│  Alerts │  8d: API key list + create/revoke             │
│  Retain │  8e: Alert delivery config + thresholds       │
│         │  8f: Retention periods for audit/sessions     │
└─────────┴───────────────────────────────────────────────┘
```

**Access control:** Owner for user management and org settings. Admin for agents, keys, alerts.

---

## Component Hierarchy

```
App
├── AuthProvider (JWT context)
├── TopNav
│   ├── NavLink (Fleet, Sessions, Policies, Audit, Risk)
│   ├── OrgSelector (if multi-org)
│   └── UserMenu (profile, logout)
├── Routes
│   ├── LoginPage
│   ├── FleetOverview
│   │   ├── SummaryCardRow
│   │   ├── PromptVolumeChart
│   │   ├── DecisionBreakdownPie
│   │   ├── ActivityFeed (WebSocket)
│   │   └── AgentStatusTable
│   ├── SessionsList
│   │   ├── FilterBar
│   │   ├── SessionTable
│   │   └── Pagination
│   ├── SessionDetail
│   │   ├── SessionHeader
│   │   ├── PromptTimeline
│   │   │   └── PromptEntry (expandable)
│   │   └── PTYDisclaimer
│   ├── PolicyEditor
│   │   ├── VersionList
│   │   ├── YAMLEditor (syntax highlighting)
│   │   ├── PolicyMetadata
│   │   ├── RuleTestPanel
│   │   └── ActionBar (validate, save, diff, sign)
│   ├── AuditTrail
│   │   ├── SearchBar
│   │   ├── FilterSidebar
│   │   ├── AuditEventTable
│   │   ├── ChainIntegrityBadge
│   │   └── ExportButton
│   ├── RiskDashboard
│   │   ├── RiskSummaryCards
│   │   ├── RiskTrendChart
│   │   ├── RiskFactorList
│   │   └── AlertPanel
│   └── Settings
│       ├── OrgProfileTab
│       ├── UserManagementTab
│       ├── AgentRegistryTab
│       ├── APIKeysTab
│       ├── NotificationsTab
│       └── RetentionTab
└── WebSocketProvider (live event bus)
```

---

## Accessibility and Responsiveness

**Accessibility:**
- All interactive elements keyboard-navigable (tab order, focus rings).
- ARIA labels on status indicators (●/○ → "active"/"offline").
- Color is never the sole indicator — text labels accompany all status colors.
- Minimum contrast ratio: 4.5:1 (WCAG AA).
- Screen reader announcements for live activity feed updates.

**Responsiveness:**
- **≥1280px:** Full three-panel layouts (Policy Editor), side-by-side charts.
- **768–1279px:** Stacked panels, charts full-width, collapsed sidebar navigation.
- **<768px:** Single-column, hamburger nav, simplified tables (card layout on mobile).
- Tables switch to card layout below 768px for readability.
- Charts resize responsively via container queries.

The dashboard is designed for desktop-first use (fleet operators working at
workstations), but remains functional on tablet for on-call scenarios.

---

> **Reminder:** This is a design document. No implementation exists.
> Cloud OBSERVES, local EXECUTES.
