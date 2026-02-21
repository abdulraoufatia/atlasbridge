# Phase C — Enterprise SaaS Dashboard Architecture

**Maturity: Design Document — No Implementation**

> **Disclaimer:** Phase C — Design Only. Not implemented. Execution stays local.
> This document describes the target-state SaaS architecture for AtlasBridge Enterprise.
> No cloud components exist today. The local runtime is the only execution environment.
> All cloud functionality described here is planned design, not shipped software.

**Last updated:** 2026-02-21
**Depends on:** Phase A (shipped), Phase B (scaffold only)
**Local codebase version:** v0.8.6

---

## Table of Contents

- [Overview](#overview)
- [Design Principles](#design-principles)
- [Multi-Tenant Architecture](#multi-tenant-architecture)
- [Data Model](#data-model)
- [Trust Boundaries](#trust-boundaries)
- [Authentication and Authorization](#authentication-and-authorization)
- [Local Runtime Agent to Cloud Handshake Protocol](#local-runtime-agent-to-cloud-handshake-protocol)
- [Policy Signing Strategy](#policy-signing-strategy)
- [Dashboard UI Screens](#dashboard-ui-screens)
- [API Endpoints](#api-endpoints)
- [Real-Time WebSocket Protocol](#real-time-websocket-protocol)
- [Offline-First Architecture](#offline-first-architecture)
- [Technology Choices](#technology-choices)
- [Operational Considerations](#operational-considerations)
- [Open Questions](#open-questions)
- [End-State Dataflow Diagram](#end-state-dataflow-diagram)

---

## Overview

AtlasBridge Enterprise extends the open-source local runtime with optional cloud governance capabilities. The fundamental design principle is:

**Execution stays local. The cloud observes and advises. It never executes.**

The cloud tier provides centralized policy management, audit aggregation, risk dashboards, and team-wide session visibility. It does not gain PTY access, shell execution authority, or any path to inject commands into a local runtime.

### Phase Context

| Phase | Status | Scope |
|-------|--------|-------|
| **Phase A** — Local Enterprise Runtime | **Shipped** (v0.8.3+) | Edition gating, RBAC, risk classifier, policy pinning, DecisionTraceV2, audit integrity |
| **Phase B** — Hybrid Governance | **Scaffold only** | Cloud interfaces (all disabled), transport stubs, auth stubs — zero HTTP calls |
| **Phase C** — SaaS Dashboard | **This document** | Web GUI, REST API, PostgreSQL, agent sync, policy distribution |

Phase C composes exclusively on Phase A and Phase B interfaces. It does not modify core runtime behavior.

---

## Design Principles

1. **Local-first** — The runtime operates independently. Cloud is additive and degradable.
2. **Observation only** — Cloud receives metadata copies. It never executes commands or injects replies.
3. **Tenant isolation** — Every data path is scoped to `org_id`. No cross-tenant access exists.
4. **Offline-safe** — Cloud unreachable does not block, pause, or degrade local runtime.
5. **Schema alignment** — Cloud data model mirrors the local SQLite schema. No semantic divergence.
6. **Edition-gated** — Dashboard features require Enterprise edition. Feature flags enforce this.

---

## Multi-Tenant Architecture

### Tenant Hierarchy

```
Tenant (org_id)
  └── Organization
        ├── Teams (optional grouping)
        │     └── Members
        └── Runtime Agents
              └── Sessions
                    └── Prompts → Decisions → Audit Events
```

### Tenant Identity

| Field | Type | Description |
|-------|------|-------------|
| `org_id` | UUID v4 | Immutable tenant identifier, assigned at provisioning |
| `org_slug` | string | Human-readable org name (unique, URL-safe, max 63 chars) |
| `display_name` | string | Organization display name |
| `edition` | enum | `community`, `pro`, `enterprise` — mirrors local `Edition` enum |
| `plan` | enum | `free`, `team`, `enterprise` — billing plan |
| `created_at` | timestamp | Provisioning timestamp (UTC) |
| `max_agents` | integer | Agent limit per plan (free: 3, team: 25, enterprise: unlimited) |
| `max_users` | integer | User limit per plan (free: 1, team: 25, enterprise: unlimited) |

### Isolation via org_id

- Every database table includes an `org_id` column.
- Every API request is scoped to `org_id` extracted from the bearer token.
- No API endpoint permits cross-org queries. There is no superuser query path that returns data across tenants in the application layer.
- Database-level row security policies (PostgreSQL RLS) enforce `org_id` filtering as a second layer, independent of application logic.
- Background jobs (aggregation, retention) are partitioned by `org_id`.

### Tenant Provisioning

1. Organization created via admin API or self-service signup.
2. `org_id` generated and stored.
3. Dedicated audit partition created in PostgreSQL.
4. Initial owner user created, bound to org_id.
5. API keys issued, scoped to org_id.
6. First runtime agent registered via handshake protocol.

### Rate Limiting

| Plan | API requests/min | WebSocket connections | Audit events/day | Policy versions |
|------|------------------|-----------------------|-------------------|-----------------|
| Free | 60 | 1 | 10,000 | 10 |
| Team | 600 | 10 | 500,000 | 100 |
| Enterprise | 6,000 | unlimited | unlimited | unlimited |

Rate limits are enforced per `org_id` at the API gateway layer. Exceeding limits returns HTTP 429 with a `Retry-After` header.

### Data Residency

- Default region: `us-east-1` (or equivalent).
- Enterprise plan supports region selection at provisioning: `us-east-1`, `eu-west-1`, `ap-southeast-1`.
- Once set, data residency region is immutable for the org (data migration requires support intervention).
- All data for an org is stored in its designated region. No cross-region replication unless explicitly requested.

---

## Data Model

The cloud data model mirrors the local SQLite schema with additions for multi-tenancy, user management, and agent registration. All cloud tables include `org_id` for tenant isolation.

### Entity-Relationship Overview

```
organizations ──1:N──> users
organizations ──1:N──> teams
organizations ──1:N──> agents
organizations ──1:N──> policies
teams ──N:M──> users (via team_members)
agents ──1:N──> sessions
sessions ──1:N──> prompts
prompts ──1:N──> replies
prompts ──1:1──> decisions
sessions ──1:N──> audit_events
policies ──1:N──> policy_versions
```

### Core Tables

#### organizations

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Immutable org identifier |
| `slug` | VARCHAR(63) | UNIQUE, NOT NULL | URL-safe org name |
| `display_name` | VARCHAR(255) | NOT NULL | Human-readable name |
| `edition` | VARCHAR(20) | NOT NULL, DEFAULT 'community' | community / pro / enterprise |
| `plan` | VARCHAR(20) | NOT NULL, DEFAULT 'free' | free / team / enterprise |
| `max_agents` | INTEGER | NOT NULL, DEFAULT 3 | Agent limit |
| `max_users` | INTEGER | NOT NULL, DEFAULT 1 | User limit |
| `data_region` | VARCHAR(20) | NOT NULL, DEFAULT 'us-east-1' | Data residency region |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

#### users

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → organizations.id, NOT NULL | Tenant scope |
| `email` | VARCHAR(255) | NOT NULL | Login identity |
| `display_name` | VARCHAR(255) | NOT NULL | |
| `role` | VARCHAR(20) | NOT NULL, DEFAULT 'viewer' | viewer / operator / admin / owner — mirrors local `Role` enum |
| `team_id` | UUID | FK → teams.id, NULLABLE | Optional team membership |
| `auth_provider` | VARCHAR(50) | NOT NULL, DEFAULT 'oidc' | oidc / api_key / saml |
| `auth_subject` | VARCHAR(255) | NOT NULL | External identity (OIDC sub claim) |
| `channel_identity` | VARCHAR(255) | NULLABLE | Maps to local RBAC identity (e.g. "telegram:123456789") |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Soft disable |
| `last_login_at` | TIMESTAMPTZ | NULLABLE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**RLS policy:** `WHERE org_id = current_setting('app.current_org_id')::UUID`

#### teams

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `name` | VARCHAR(255) | NOT NULL | |
| `description` | TEXT | DEFAULT '' | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** `(org_id, name)`

#### agents

Mirrors a registered local runtime. Each `atlasbridge` installation that connects to the cloud is an agent.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Cloud-assigned agent ID |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `runtime_id` | VARCHAR(255) | NOT NULL | Ed25519 public key (`ed25519:<base64>`) |
| `hostname` | VARCHAR(255) | NOT NULL | Machine hostname |
| `label` | VARCHAR(255) | DEFAULT '' | User-assigned label |
| `agent_version` | VARCHAR(20) | NOT NULL | e.g. "0.8.6" |
| `platform` | VARCHAR(50) | NOT NULL | darwin / linux / windows |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'active' | active / inactive / revoked |
| `last_seen_at` | TIMESTAMPTZ | NULLABLE | Last heartbeat timestamp |
| `registered_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** `(org_id, runtime_id)`

#### sessions

Mirrors the local `sessions` table. Synced from runtime agents.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR(36) | PK | Session UUID (from local runtime) |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `agent_id` | UUID | FK → agents.id, NOT NULL | Which runtime agent |
| `tool` | VARCHAR(50) | NOT NULL, DEFAULT '' | Adapter name (claude, openai, gemini) |
| `command` | TEXT | NOT NULL, DEFAULT '' | Command line |
| `cwd` | TEXT | NOT NULL, DEFAULT '' | Working directory |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'starting' | starting / running / awaiting_reply / completed / crashed / canceled |
| `pid` | INTEGER | NULLABLE | Local process ID |
| `started_at` | TIMESTAMPTZ | NOT NULL | |
| `ended_at` | TIMESTAMPTZ | NULLABLE | |
| `exit_code` | INTEGER | NULLABLE | |
| `label` | VARCHAR(255) | NOT NULL, DEFAULT '' | |
| `prompt_count` | INTEGER | NOT NULL, DEFAULT 0 | Prompt counter |
| `metadata` | JSONB | NOT NULL, DEFAULT '{}' | |
| `synced_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last sync from runtime |

**Index:** `(org_id, started_at DESC)`

#### prompts

Mirrors the local `prompts` table.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR(36) | PK | Prompt ID (from local runtime) |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `session_id` | VARCHAR(36) | FK → sessions.id, NOT NULL | |
| `prompt_type` | VARCHAR(30) | NOT NULL | yes_no / confirm_enter / multiple_choice / free_text |
| `confidence` | VARCHAR(10) | NOT NULL | high / medium / low |
| `excerpt` | TEXT | NOT NULL, DEFAULT '' | Prompt text (max 200 chars; **no PTY output**) |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'created' | created / routed / awaiting_reply / reply_received / injected / resolved / expired / canceled / failed |
| `nonce` | VARCHAR(36) | NOT NULL | Idempotency key |
| `expires_at` | TIMESTAMPTZ | NOT NULL | TTL expiry |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `resolved_at` | TIMESTAMPTZ | NULLABLE | |
| `response_normalized` | TEXT | NULLABLE | Normalized response value |
| `channel_identity` | VARCHAR(255) | NULLABLE | Responder identity |
| `metadata` | JSONB | NOT NULL, DEFAULT '{}' | |

**Index:** `(org_id, session_id, status)`

#### replies

Mirrors the local `replies` table.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR(36) | PK | |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `prompt_id` | VARCHAR(36) | FK → prompts.id, NOT NULL | |
| `session_id` | VARCHAR(36) | NOT NULL | |
| `value` | TEXT | NOT NULL | Response value |
| `channel_identity` | VARCHAR(255) | NOT NULL | Responder (e.g. "telegram:123456789") |
| `timestamp` | TIMESTAMPTZ | NOT NULL | |
| `nonce` | VARCHAR(36) | NOT NULL | Idempotency guard |

#### decisions

Cloud-side storage for `DecisionTraceEntryV2` records. Not present in local SQLite — these are synced from the local JSONL trace.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Cloud-assigned ID |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `session_id` | VARCHAR(36) | NOT NULL | |
| `prompt_id` | VARCHAR(36) | NOT NULL | |
| `timestamp` | TIMESTAMPTZ | NOT NULL | |
| `policy_version` | VARCHAR(50) | NOT NULL, DEFAULT '' | |
| `policy_hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | sha256:<hex> |
| `matched_rule` | VARCHAR(255) | NOT NULL, DEFAULT '' | |
| `evaluation_details` | TEXT | NOT NULL, DEFAULT '' | |
| `risk_level` | VARCHAR(10) | NOT NULL, DEFAULT 'low' | low / medium / high / critical |
| `confidence` | VARCHAR(10) | NOT NULL, DEFAULT '' | |
| `action_taken` | VARCHAR(30) | NOT NULL, DEFAULT '' | auto_reply / require_human / deny / notify_only |
| `idempotency_key` | VARCHAR(36) | NOT NULL, DEFAULT '' | |
| `escalation_status` | VARCHAR(20) | NOT NULL, DEFAULT '' | "" / escalated / resolved / timeout |
| `human_actor` | VARCHAR(255) | NOT NULL, DEFAULT '' | Channel identity of responder |
| `ci_status_snapshot` | VARCHAR(20) | NOT NULL, DEFAULT '' | passing / failing / unknown |
| `replay_safe` | BOOLEAN | NOT NULL, DEFAULT TRUE | |
| `previous_hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | Hash chain link |
| `current_hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | SHA-256 of this entry |
| `trace_version` | VARCHAR(5) | NOT NULL, DEFAULT '2' | |

**Index:** `(org_id, session_id, timestamp)`
**Index:** `(org_id, risk_level)` — for risk dashboard queries

#### audit_events

Mirrors the local `audit_events` table. Hash-chained per org.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR(36) | PK | Event ID (from local runtime) |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `agent_id` | UUID | FK → agents.id, NOT NULL | Source runtime |
| `event_type` | VARCHAR(50) | NOT NULL | prompt_detected / policy_evaluated / reply_injected / escalated / ... |
| `session_id` | VARCHAR(36) | NOT NULL, DEFAULT '' | |
| `prompt_id` | VARCHAR(36) | NOT NULL, DEFAULT '' | |
| `payload` | JSONB | NOT NULL, DEFAULT '{}' | Event-specific data |
| `timestamp` | TIMESTAMPTZ | NOT NULL | |
| `prev_hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | Previous event hash |
| `hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | SHA-256 of this event |
| `synced_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Partitioned by:** `org_id` (range on `timestamp` within each org)
**Index:** `(org_id, timestamp DESC)`
**Index:** `(org_id, event_type)`

#### policy_versions

Content-addressed policy storage. Each version is immutable once signed.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `version` | INTEGER | NOT NULL | Monotonic version number per org |
| `name` | VARCHAR(255) | NOT NULL, DEFAULT '' | Policy name |
| `description` | TEXT | NOT NULL, DEFAULT '' | |
| `content_hash` | VARCHAR(71) | NOT NULL | sha256:<hex> of canonical YAML |
| `yaml_content` | TEXT | NOT NULL | Full policy YAML |
| `rule_count` | INTEGER | NOT NULL | Number of rules |
| `dsl_version` | VARCHAR(5) | NOT NULL, DEFAULT '1' | v0 or v1 |
| `signature` | TEXT | NOT NULL, DEFAULT '' | Ed25519 signature envelope (JSON) |
| `signed_by` | UUID | FK → users.id, NULLABLE | User who signed |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT FALSE | Currently distributed policy |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** `(org_id, version)`
**Unique:** `(org_id, content_hash)` — prevents duplicate content

#### api_keys

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → organizations.id, NOT NULL | |
| `user_id` | UUID | FK → users.id, NOT NULL | Creator |
| `name` | VARCHAR(255) | NOT NULL | Key label |
| `key_hash` | VARCHAR(71) | NOT NULL | SHA-256 of the key (key itself never stored) |
| `key_prefix` | VARCHAR(8) | NOT NULL | First 8 chars for identification |
| `scopes` | TEXT[] | NOT NULL | Permitted API scopes |
| `expires_at` | TIMESTAMPTZ | NULLABLE | Optional expiry |
| `last_used_at` | TIMESTAMPTZ | NULLABLE | |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### Data Categories

| Category | Stored in Cloud | Contains Secrets | Retention |
|----------|----------------|-----------------|-----------|
| Decision traces | Yes (metadata only) | No | Configurable per org (default 90 days) |
| Audit events | Yes (hash-chained) | No | Configurable per org (default 1 year) |
| Session metadata | Yes | No | Configurable per org (default 90 days) |
| Policy YAML | Yes (signed) | No | All versions retained |
| PTY output | **No** — never leaves local runtime | May contain secrets | Local only |
| Prompt text | Excerpt only (max 200 chars) | Possibly | Stored with prompt record |
| Private keys | **No** — local keyring only | Yes | Local only |

### Non-Negotiable Data Rules

- PTY output never leaves the local runtime.
- Private keys never leave the local machine.
- No secrets appear in audit events or decision traces.
- Prompt excerpts are truncated to 200 characters before sync.

---

## Trust Boundaries

Two trust domains interact in Phase C:

| Domain | Trust Level | Authority |
|--------|-------------|-----------|
| Local Runtime | **Trusted execution** | Full PTY access, shell execution, policy evaluation, prompt detection, reply injection |
| Cloud Tier | **Trusted observation only** | Receives metadata copies, stores audit, serves dashboard, distributes signed policies |

The cloud tier has no execution authority. It cannot:
- Send commands to the local runtime for execution.
- Modify the local policy cache without a valid Ed25519 signature.
- Access the local PTY, filesystem, or shell environment.
- Override a local policy decision.
- Inject prompts or replies into the runtime.

The local runtime is the sole execution environment. The cloud is an optional, degradable extension.

---

## Authentication and Authorization

### Authentication Providers

| Provider | Use Case | Mechanism |
|----------|----------|-----------|
| **OIDC / OAuth 2.0** | Dashboard users (SSO) | Authorization code flow with PKCE |
| **SAML 2.0** | Enterprise SSO | Service provider initiated |
| **API keys** | Runtime agents, CI/CD | Bearer token, scoped to org_id |
| **Ed25519 keypair** | Runtime agent identity | Challenge-response handshake |

### User Authentication Flow (Dashboard)

1. User navigates to dashboard login.
2. Redirected to OIDC provider (Google, Okta, Azure AD, etc.).
3. On callback, cloud validates ID token, extracts `sub` claim.
4. Maps `sub` to `users.auth_subject`. If no match and org allows auto-provisioning, creates user with `viewer` role.
5. Issues session JWT (1-hour TTL, refresh token for 30 days).
6. JWT claims include: `org_id`, `user_id`, `role`, `team_id`.

### RBAC: Local to Cloud Mapping

The cloud RBAC mirrors the local `Role` enum exactly. No new roles are introduced.

| Local Role | Cloud Role | Dashboard Permissions |
|------------|------------|----------------------|
| `viewer` | `viewer` | View sessions, audit logs, risk metrics. Read-only dashboard access. |
| `operator` | `operator` | All viewer permissions + reply to prompts (if routed through cloud), pause/resume autopilot. |
| `admin` | `admin` | All operator permissions + edit policies, manage channels, manage agents, configure alerts. |
| `owner` | `owner` | All admin permissions + manage users/teams, manage RBAC, manage API keys, manage billing, delete org. |

### Permission Matrix (Cloud API)

| Permission | Viewer | Operator | Admin | Owner |
|------------|--------|----------|-------|-------|
| `GET /sessions` | yes | yes | yes | yes |
| `GET /audit` | yes | yes | yes | yes |
| `GET /risk` | yes | yes | yes | yes |
| `GET /policies` | yes | yes | yes | yes |
| `POST /policies` | — | — | yes | yes |
| `POST /policies/distribute` | — | — | yes | yes |
| `GET /agents` | yes | yes | yes | yes |
| `DELETE /agents/{id}` | — | — | yes | yes |
| `GET /users` | — | — | yes | yes |
| `POST /users` | — | — | — | yes |
| `PUT /users/{id}/role` | — | — | — | yes |
| `DELETE /users/{id}` | — | — | — | yes |
| `GET /api-keys` | — | — | yes | yes |
| `POST /api-keys` | — | — | yes | yes |
| `DELETE /api-keys/{id}` | — | — | yes | yes |
| `PUT /settings` | — | — | — | yes |

### Tenant Isolation in Auth

- JWT `org_id` claim is set at login and cannot be overridden by the client.
- All API handlers extract `org_id` from the JWT, not from request parameters.
- RLS policies in PostgreSQL provide defense-in-depth: even if application code has a bug, the database enforces tenant boundaries.

---

## Local Runtime Agent to Cloud Handshake Protocol

### Overview

When a local runtime agent connects to the cloud tier, a mutual authentication handshake establishes identity and trust.

### Handshake Sequence

```
Runtime Agent                         Cloud Governance API
     |                                        |
     |  1. WSS connect (TLS 1.3)              |
     |--------------------------------------->|
     |                                        |
     |  2. Challenge (32-byte random nonce)   |
     |<---------------------------------------|
     |                                        |
     |  3. ChallengeResponse {                |
     |       runtime_id: <public key>,        |
     |       org_id: <org UUID>,              |
     |       nonce_signature: Ed25519(nonce), |
     |       agent_version: "0.8.6",          |
     |       timestamp: <ISO 8601 UTC>        |
     |     }                                  |
     |--------------------------------------->|
     |                                        |
     |  4. Cloud verifies:                    |
     |     - runtime_id registered to org_id  |
     |     - nonce_signature valid            |
     |     - timestamp within 30s skew        |
     |                                        |
     |  5. HandshakeAck {                     |
     |       session_token: <JWT, 1hr TTL>,   |
     |       cloud_signature: Ed25519(ack),   |
     |       policy_version: <hash>           |
     |     }                                  |
     |<---------------------------------------|
     |                                        |
     |  6. Runtime verifies:                  |
     |     - cloud_signature against pinned   |
     |       cloud public key                 |
     |     - session_token claims match       |
     |                                        |
     |  === Secure channel established ===    |
```

### Heartbeat Protocol

After handshake, the agent sends periodic heartbeats:

| Field | Value |
|-------|-------|
| Interval | 60 seconds |
| Payload | `{ agent_id, active_sessions, prompt_count_since_last, timestamp }` |
| Timeout | 3 missed heartbeats (180s) → agent status set to `inactive` |
| Recovery | Next heartbeat restores `active` status automatically |

### Transport Security

- All cloud communication uses TLS 1.3 (minimum). TLS 1.2 is not accepted.
- WebSocket Secure (WSS) is the only permitted transport for the control channel.
- Certificate pinning is recommended for enterprise deployments.

### Message Signing

- Every control message from cloud to runtime is signed with Ed25519.
- The runtime holds a pinned copy of the cloud's public key (distributed at provisioning).
- Messages with invalid or missing signatures are dropped silently and logged locally.

---

## Policy Signing Strategy

### Signing Authority

The cloud tier is the signing authority for enterprise policies. Policies are signed server-side using the cloud's Ed25519 private key.

### Signing Flow

```
Policy Author (Dashboard)
      |
      v
Cloud API validates YAML schema
      |
      v
Cloud signs policy bundle:
  Ed25519(SHA-256(canonical_yaml) || org_id || version || timestamp)
      |
      v
Signed policy distributed to runtime agents
      |
      v
Runtime verifies signature against pinned cloud public key
      |
      v
If valid: replace local policy cache
If invalid: reject, log warning, continue with previous policy
```

### Key Management

| Key | Location | Purpose |
|-----|----------|---------|
| Cloud signing private key | Cloud HSM / secrets vault | Signs policies and control messages |
| Cloud signing public key | Pinned in runtime config | Verifies policy signatures and control messages |
| Runtime private key | Local keyring only | Signs handshake responses and audit submissions |
| Runtime public key | Registered in cloud | Identifies runtime agent; verifies audit provenance |

### Signature Envelope

```json
{
  "policy_hash": "sha256:<hex>",
  "org_id": "uuid",
  "version": 42,
  "timestamp": "2026-01-15T10:30:00Z",
  "signature": "ed25519:<base64>"
}
```

### Rejection Behavior

If the runtime receives a policy with an invalid signature:
1. The policy is rejected entirely.
2. The previous valid policy remains active.
3. A local audit event is written: `policy_signature_rejected`.
4. The cloud is notified (if reachable) that the policy was rejected.
5. No partial policy application occurs. Policies are atomic.

---

## Dashboard UI Screens

### Screen 1 — Login

**Purpose:** Authenticate users and establish org context.

**Layout:**
- Centered card with org logo (if configured) and "AtlasBridge" branding.
- "Sign in with SSO" button (OIDC/SAML flow).
- Email/password fallback for team plan.
- Org selector dropdown if user belongs to multiple orgs.
- MFA challenge (TOTP) after primary auth if enabled.

**Data requirements:** None (pre-auth).

---

### Screen 2 — Fleet Overview (Dashboard Home)

**Purpose:** At-a-glance health of all managed agents across the organization.

**Layout:**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Fleet Overview                                     [Last 24h ▾]   │
├──────────┬──────────┬──────────┬──────────┬────────────────────────┤
│  Agents  │ Sessions │ Prompts  │ Escalate │   Escalation Rate      │
│    12    │    47    │   1,204  │    38    │   ████████░░ 3.2%      │
│  active  │  today   │  today   │  today   │   (target: <5%)        │
├──────────┴──────────┴──────────┴──────────┴────────────────────────┤
│                                                                     │
│  Prompt Volume (24h)              │  Decision Breakdown             │
│  ┌─────────────────────────────┐  │  ┌───────────────────────────┐ │
│  │  ▂▃▅▇█▇▅▃▂▁ ▂▃▅▇█▇▅▃▂▁   │  │  │  Auto-approve   72%      │ │
│  │  12a  6a  12p  6p  12a     │  │  │  Escalated      25%      │ │
│  └─────────────────────────────┘  │  │  Denied          3%      │ │
│                                   │  └───────────────────────────┘ │
├───────────────────────────────────┴────────────────────────────────┤
│  Recent Activity                                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  14:22  agent-mac-01   prompt resolved   yes_no   auto      │   │
│  │  14:21  agent-linux-3  escalated         free_text human    │   │
│  │  14:20  agent-mac-01   session started   claude             │   │
│  │  14:18  agent-mac-02   policy updated    v12 → v13         │   │
│  │  ...                                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  Agent Status                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  ● agent-mac-01     claude   v0.8.6   2 sessions   14:22   │   │
│  │  ● agent-linux-3    openai   v0.8.6   1 session    14:21   │   │
│  │  ● agent-mac-02     claude   v0.8.5   idle         14:18   │   │
│  │  ○ agent-ci-runner  gemini   v0.8.6   offline      12:00   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Summary cards:** Active agents, total sessions today, prompts today, escalation count.
**Trend charts:** Prompt volume over selected time window, auto-approve vs. escalate ratio.
**Activity feed:** Last 20 events across all agents (live-updated via WebSocket).
**Agent table:** All registered agents with status indicator, adapter, version, session count, last seen.

**API calls:** `GET /agents`, `GET /sessions?range=24h`, `GET /audit?range=24h&limit=20`, `WS /live`

---

### Screen 3 — Sessions List

**Purpose:** Browse and filter all sessions across the fleet.

**Layout:**
- Filterable table with columns: Session ID (short), Agent hostname, Adapter, Started, Duration, Status, Prompt count, Escalation count.
- Filters: date range picker, agent selector, adapter type, status (running/completed/crashed).
- Sort by any column.
- Click row to drill into session detail.
- Bulk export (CSV) for compliance reporting.

**API calls:** `GET /sessions?page=1&per_page=50&sort=-started_at&filter[agent_id]=...`

---

### Screen 4 — Session Detail

**Purpose:** Full prompt-by-prompt timeline of a single session.

**Layout:**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Session abc12345                                    [Export JSON]  │
│  Agent: agent-mac-01 (claude) │ Started: 14:00 │ Duration: 22min  │
│  Status: completed │ Exit code: 0 │ Prompts: 8 │ Escalated: 1    │
├─────────────────────────────────────────────────────────────────────┤
│  Prompt Timeline                                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 14:02  yes_no     HIGH   auto_approve  rule: allow-tests   │   │
│  │        "Continue? [y/n]"                                    │   │
│  │        Decision: auto_reply → "y"   Risk: LOW   12ms       │   │
│  │                                                              │   │
│  │ 14:05  free_text  MED    escalated     rule: (no match)    │   │
│  │        "Enter the API key:"                                 │   │
│  │        Escalated → Telegram   Resolved in 45s               │   │
│  │        Human: telegram:123456789                             │   │
│  │                                                              │   │
│  │ 14:08  yes_no     HIGH   auto_approve  rule: allow-tests   │   │
│  │        "Run tests? [y/n]"                                   │   │
│  │        Decision: auto_reply → "y"   Risk: LOW   8ms        │   │
│  │  ...                                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ⚠ No PTY output displayed. PTY output never leaves the runtime.  │
└─────────────────────────────────────────────────────────────────────┘
```

**Per-prompt detail:** Prompt type, confidence, policy rule matched, decision, risk level, latency.
**Escalation events:** Channel used, response time, human responder identity.
**Explicit callout:** "No PTY output displayed. PTY output never leaves the local runtime."

**API calls:** `GET /sessions/{id}`, `GET /sessions/{id}/events?per_page=100`

---

### Screen 5 — Policy Editor

**Purpose:** View, edit, validate, and distribute policies to runtime agents.

**Layout:**
- Left panel: policy version list (version number, hash, created date, active indicator).
- Center panel: YAML editor with syntax highlighting, line numbers, inline validation errors.
- Right panel: policy metadata (name, rule count, DSL version, signature status).
- Bottom panel: "Test Rule" simulator — enter a mock prompt (type, confidence, content), see which rule matches and what decision would be made.
- Action buttons:
  - **Validate** — parse and schema-check without saving.
  - **Save Draft** — store new version without signing.
  - **Sign & Distribute** — sign with cloud key, push to all connected agents.
  - **Diff** — compare two versions side by side (mirrors `EnterprisePolicyLifecycle.diff_policies()`).
- Per-rule hit count statistics from synced decision traces.

**Access control:** `admin` or `owner` role required for edit/sign/distribute. `viewer` and `operator` can view and test.

**API calls:** `GET /policies`, `POST /policies`, `POST /policies/{version}/distribute`, `POST /policies/test`

---

### Screen 6 — Audit Trail

**Purpose:** Searchable, filterable audit event log with integrity verification.

**Layout:**
- Search bar with full-text search across event types and payloads.
- Filter sidebar: date range, agent, event type, session, decision type.
- Event table: timestamp, agent, event type, session ID, decision, hash chain status.
- Hash chain integrity indicator per event (green check = verified, yellow warning = gap detected, red = broken chain).
- Gap detection: offline periods flagged visually with "sync gap" markers.
- Export: CSV, JSON, or full chain for external verification.

**API calls:** `GET /audit?search=...&event_type=...&range=...`, `GET /audit/integrity`, `GET /audit/export`

---

### Screen 7 — Risk Dashboard

**Purpose:** Aggregated risk metrics, trend analysis, and alert configuration.

**Layout:**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Risk Overview                                      [Last 7d ▾]    │
├───────────┬───────────┬───────────┬────────────────────────────────┤
│  CRITICAL │   HIGH    │  MEDIUM   │  Risk Trend (7d)               │
│     0     │     3     │    42     │  ┌──────────────────────────┐  │
│           │           │           │  │  ▂▃▃▂▂▃▅  (declining)   │  │
│           │           │           │  └──────────────────────────┘  │
├───────────┴───────────┴───────────┴────────────────────────────────┤
│                                                                     │
│  Risk Breakdown by Factor                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Escalation rate:          3.2%   (target: <5%)       OK   │   │
│  │  Low-confidence prompts:   12%    (target: <15%)      OK   │   │
│  │  Policy miss rate:         2.1%   (target: <3%)       OK   │   │
│  │  Auto-reply on protected:  0.8%   (target: <1%)      WARN │   │
│  │  Avg response time:        34s    (target: <60s)      OK   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Active Alerts                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  ⚠ HIGH risk: agent-linux-3 auto-replied on main branch    │   │
│  │  ⚠ HIGH risk: 2 low-confidence auto-approvals in 1 hour   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Metrics:** Escalation rate, low-confidence prompt rate, policy miss rate, auto-reply on protected branches, average human response time.
**Trends:** Configurable time windows (24h, 7d, 30d).
**Alerts:** Threshold-based alerts configurable per metric. Notification channels: email, Slack webhook, PagerDuty.
**Per-agent breakdown:** Risk metrics drillable by agent.

**API calls:** `GET /risk`, `GET /risk/trends?window=7d`, `GET /risk/alerts`, `PUT /risk/alerts/config`

---

### Screen 8 — Settings

**Purpose:** Organization configuration, user management, and infrastructure settings.

**Tabs:**

#### 8a — Organization Profile
- Org name, slug, edition display, plan display.
- Data region (read-only after provisioning).
- Agent limit and current count.

#### 8b — User Management
- User table: email, display name, role, team, last login, status.
- Invite user (email + role assignment).
- Edit role, deactivate, remove.
- Bulk import (CSV).

#### 8c — Agent Registry
- Registered agents: hostname, runtime_id, version, platform, status, last seen.
- Revoke agent (immediately invalidates handshake credentials).
- Initiate key rotation for an agent.

#### 8d — API Keys
- Key list: name, prefix, scopes, created, last used, expiry.
- Create new key (scoped to specific API groups).
- Revoke key.

#### 8e — Notifications
- Alert delivery preferences: email, Slack webhook URL, PagerDuty integration key.
- Per-metric threshold configuration.
- Test notification button.

#### 8f — Retention
- Audit event retention period (default 1 year).
- Session/decision retention period (default 90 days).
- Policy version retention (all versions retained by default).

**Access control:** `owner` role for user management and settings. `admin` for agent and API key management.

**API calls:** `GET/PUT /settings`, `GET/POST/DELETE /users`, `GET/DELETE /agents`, `GET/POST/DELETE /api-keys`

---

## API Endpoints

All endpoints require authentication via JWT bearer token (dashboard users) or API key (runtime agents). All responses include `X-Request-Id` header for tracing.

### Conventions

- Base URL: `https://api.atlasbridge.io/v1`
- Pagination: `?page=1&per_page=50` (max 100). Response includes `X-Total-Count` header.
- Sorting: `?sort=-created_at` (prefix `-` for descending).
- Filtering: `?filter[status]=running&filter[agent_id]=<uuid>`
- Date ranges: `?range=24h` or `?from=2026-01-01T00:00:00Z&to=2026-01-31T23:59:59Z`
- Errors: JSON `{ "error": "message", "code": "ERROR_CODE", "request_id": "uuid" }`

### Sessions

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/sessions` | viewer+ | List sessions (paginated, filterable by agent, status, date) |
| GET | `/sessions/{id}` | viewer+ | Session detail with summary metrics |
| GET | `/sessions/{id}/events` | viewer+ | Paginated event timeline for session |
| GET | `/sessions/{id}/decisions` | viewer+ | Decision trace entries for session |

### Prompts

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/sessions/{session_id}/prompts` | viewer+ | List prompts for a session |
| GET | `/prompts/{id}` | viewer+ | Prompt detail with decision and reply |

### Policies

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/policies` | viewer+ | List policy versions (paginated) |
| GET | `/policies/{version}` | viewer+ | Get specific version with YAML content |
| GET | `/policies/active` | viewer+ | Get currently active policy |
| POST | `/policies` | admin+ | Create new policy version (validates YAML schema) |
| POST | `/policies/{version}/sign` | admin+ | Sign a draft policy with cloud key |
| POST | `/policies/{version}/distribute` | admin+ | Push signed policy to connected agents |
| POST | `/policies/test` | viewer+ | Simulate a prompt against a policy version |
| GET | `/policies/{v1}/diff/{v2}` | viewer+ | Diff two policy versions |

### Audit

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/audit` | viewer+ | Query audit events (paginated, filterable) |
| GET | `/audit/integrity` | viewer+ | Hash chain integrity report (per-agent) |
| GET | `/audit/export` | admin+ | Export audit events (CSV/JSON) with integrity metadata |
| GET | `/audit/gaps` | viewer+ | List sync gaps (offline periods) |

### Risk

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/risk` | viewer+ | Current risk summary (org-wide) |
| GET | `/risk/agents/{id}` | viewer+ | Risk metrics for a specific agent |
| GET | `/risk/trends` | viewer+ | Risk metrics over configurable time window |
| GET | `/risk/alerts` | viewer+ | Active risk alerts |
| PUT | `/risk/alerts/config` | admin+ | Configure alert thresholds and notifications |

### Agents

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/agents` | viewer+ | List registered runtime agents |
| GET | `/agents/{id}` | viewer+ | Agent detail (status, version, sessions) |
| GET | `/agents/{id}/status` | viewer+ | Live status (last seen, active sessions) |
| DELETE | `/agents/{id}` | admin+ | Revoke agent (invalidates credentials) |
| POST | `/agents/{id}/rotate-key` | admin+ | Initiate key rotation |

### Users and Teams

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/users` | admin+ | List org users |
| POST | `/users` | owner | Invite new user (email + role) |
| GET | `/users/{id}` | admin+ | User detail |
| PUT | `/users/{id}/role` | owner | Change user role |
| DELETE | `/users/{id}` | owner | Remove user from org |
| GET | `/teams` | admin+ | List teams |
| POST | `/teams` | admin+ | Create team |
| PUT | `/teams/{id}/members` | admin+ | Add/remove team members |

### Edition and Features

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/edition` | viewer+ | Current org edition and plan |
| GET | `/features` | viewer+ | Feature flag status (mirrors local `atlasbridge features`) |

### API Keys

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api-keys` | admin+ | List API keys (prefix only, no secrets) |
| POST | `/api-keys` | admin+ | Create new API key (returns full key once) |
| DELETE | `/api-keys/{id}` | admin+ | Revoke API key |

### Settings

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/settings` | admin+ | Org settings (retention, notifications) |
| PUT | `/settings` | owner | Update org settings |
| GET | `/settings/notifications` | admin+ | Notification channel config |
| PUT | `/settings/notifications` | admin+ | Update notification config |
| POST | `/settings/notifications/test` | admin+ | Send test notification |

### Agent Sync Endpoints (Runtime-to-Cloud)

These endpoints are called by runtime agents, authenticated via agent API key or handshake JWT.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/sync/sessions` | agent | Upsert session metadata (batch) |
| POST | `/sync/prompts` | agent | Upsert prompt records (batch) |
| POST | `/sync/decisions` | agent | Upload decision trace entries (batch, hash-chain validated) |
| POST | `/sync/audit` | agent | Upload audit events (batch, hash-chain validated) |
| POST | `/sync/heartbeat` | agent | Agent heartbeat with status summary |
| GET | `/sync/policy` | agent | Check for policy updates (returns latest signed policy if newer) |

**Offline-fallback semantics on sync endpoints:**
- All sync endpoints are idempotent. Replaying the same batch is safe (deduplication by event ID).
- Agents queue data locally during disconnection and replay on reconnection.
- Partial batches are accepted; the server returns per-item status in the response.
- Cloud never blocks or errors in a way that would cause the local runtime to pause or fail.

---

## Real-Time WebSocket Protocol

The dashboard connects via WSS to receive live updates:

```
wss://api.atlasbridge.io/ws/v1/live?token=<JWT>
```

### Event Types

| Event | Payload | Trigger |
|-------|---------|---------|
| `session.started` | session metadata | Runtime starts a new session |
| `session.ended` | session metadata + summary | Runtime session ends |
| `prompt.detected` | prompt event (no PTY content) | Prompt detected by runtime |
| `prompt.decided` | decision + rule matched | Policy evaluation complete |
| `prompt.escalated` | escalation metadata | Prompt forwarded to human |
| `prompt.resolved` | resolution metadata | Reply injected |
| `agent.connected` | agent metadata | Handshake complete |
| `agent.disconnected` | agent_id + last_seen | Connection lost |
| `agent.heartbeat` | agent_id + summary | Heartbeat received |
| `policy.distributed` | policy version + target agents | Policy push initiated |
| `policy.accepted` | agent_id + policy_hash | Agent accepted new policy |
| `policy.rejected` | agent_id + reason | Agent rejected policy (bad signature) |
| `risk.alert` | alert details | Risk threshold breached |

### Scoping

All WebSocket events are scoped to the authenticated `org_id`. No cross-tenant events are delivered. Events can be further filtered client-side by agent_id or session_id.

### Reconnection

If the WebSocket disconnects, the client reconnects with exponential backoff (1s, 2s, 4s, max 30s). On reconnection, the client requests missed events since the last received timestamp via a `replay` message.

---

## Offline-First Architecture

### Core Guarantee

The local runtime operates independently of the cloud at all times. Cloud connectivity is additive, never required.

### Fallback Behavior Matrix

| Cloud State | Policy Evaluation | Prompt Detection | Reply Injection | Audit Logging | Dashboard |
|-------------|-------------------|------------------|-----------------|---------------|-----------|
| Connected | Local (signed policy from cloud) | Local | Local | Local + cloud sync | Live |
| Disconnected | Local (cached policy) | Local | Local | Local only (queued) | Stale |
| Never connected | Local (local policy file) | Local | Local | Local only | Unavailable |

### Conflict Resolution: Policy Sync

When a runtime reconnects and a new policy is available:

1. Cloud sends signed policy with version number and hash.
2. Runtime verifies Ed25519 signature.
3. If signature is valid and version > local version: replace local cache.
4. If signature is invalid: reject, log `policy_signature_rejected`, keep current policy.
5. If runtime has local policy edits (manual file changes): **local wins**. Cloud policy is stored as "pending" and flagged in dashboard. Admin must explicitly resolve the conflict.
6. The cloud never force-overwrites a local policy. The runtime is authoritative over its own execution.

### Eventual Consistency for Audit Trail

1. Runtime writes audit events to local SQLite (authoritative source).
2. Sync worker batches events and uploads to cloud via `POST /sync/audit`.
3. Cloud validates hash chain continuity on ingestion.
4. Gaps (from offline periods) are flagged but accepted.
5. When missing segments arrive (reconnection), the cloud fills gaps and re-validates the chain.
6. Audit events are append-only everywhere. No mutation or deletion via any API.

### Degradation Summary

| Feature | Online | Offline |
|---------|--------|---------|
| Policy evaluation | Full | Full (cached policy) |
| Prompt detection | Full | Full |
| Telegram/Slack relay | Full | Full (independent of cloud) |
| Audit logging | Local + cloud | Local only (queued for sync) |
| Dashboard visibility | Real-time | Stale until reconnect |
| Policy distribution | Push from cloud | Manual local file |
| Risk scoring | Cloud-computed + local | Local classifier only |

### Offline Behavior Guarantees

These guarantees are absolute and non-negotiable:

1. **The local runtime never blocks on cloud availability.** All execution paths that touch the cloud are asynchronous and timeout-protected.
2. **Policy evaluation is always local.** Even cloud-distributed policies are cached locally and evaluated locally. The cloud never evaluates a policy on behalf of the runtime.
3. **Audit events are never lost.** If the cloud is unreachable, events queue locally in SQLite and sync on reconnection.
4. **The channel relay (Telegram/Slack) operates independently of the cloud tier.** Cloud downtime does not affect human escalation.
5. **No cloud feature, when unavailable, causes the runtime to enter an error state, pause, or degrade its core functionality.**

---

## Technology Choices

These are recommendations with tradeoff analysis. Final choices are deferred to implementation.

### Frontend

| Candidate | Pros | Cons | Recommendation |
|-----------|------|------|----------------|
| **React + TypeScript** | Largest ecosystem, TypeScript support, rich component libraries (Radix, shadcn/ui), React Query for server state | Bundle size, complexity for small teams | **Recommended** — best long-term ecosystem |
| **Next.js (App Router)** | SSR/SSG, built on React, file-based routing, API routes | More opinionated, may be heavier than needed for SPA | Strong alternative if SEO/SSR matters |
| **Vue 3 + TypeScript** | Simpler mental model, smaller bundle, Composition API | Smaller ecosystem than React | Viable for smaller teams |

### Backend API

| Candidate | Pros | Cons | Recommendation |
|-----------|------|------|----------------|
| **FastAPI (Python)** | Same language as runtime, Pydantic validation (already used in local codebase), async support, auto OpenAPI docs | Python performance ceiling for high-throughput | **Recommended** — language alignment with runtime codebase |
| **Node.js (Fastify/Express)** | High throughput, JavaScript full-stack | Language split from Python runtime | Alternative if team prefers JS |
| **Go (Chi/Fiber)** | Excellent performance, small binary, strong concurrency | Language split, less rapid prototyping | Alternative for high-scale deployments |

### Database (Cloud-Side)

| Candidate | Pros | Cons | Recommendation |
|-----------|------|------|----------------|
| **PostgreSQL 16+** | RLS for tenant isolation, JSONB for flexible payloads, partitioning for audit tables, mature ecosystem | Operational complexity at scale | **Recommended** — RLS is critical for multi-tenancy |
| **CockroachDB** | PostgreSQL-compatible, built-in multi-region | Operational overhead, cost | Alternative for multi-region requirements |

### Cache / Pub-Sub

| Candidate | Pros | Cons | Recommendation |
|-----------|------|------|----------------|
| **Redis 7+** | Rate limiting, session cache, pub/sub for WebSocket fan-out, well understood | Single-threaded, persistence concerns | **Recommended** — proven for this use case |
| **Valkey** | Redis-compatible, open-source fork | Younger ecosystem | Drop-in replacement if Redis licensing is a concern |

### Message Queue (Async Sync)

| Candidate | Pros | Cons | Recommendation |
|-----------|------|------|----------------|
| **PostgreSQL LISTEN/NOTIFY** | No additional infrastructure, transactional consistency | Limited throughput, no persistence | **Recommended for MVP** — simplicity |
| **NATS** | Lightweight, high throughput, JetStream for persistence | Additional infrastructure | Upgrade path when scale demands it |
| **Apache Kafka** | Proven at scale, log-based, replayable | Heavy infrastructure, complex | Overkill for initial deployment |

### Infrastructure

| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| Container orchestration | Kubernetes (EKS/GKE) | Standard for SaaS, auto-scaling |
| CI/CD | GitHub Actions | Already used by AtlasBridge CLI repo |
| Secrets management | AWS Secrets Manager / HashiCorp Vault | HSM-backed for Ed25519 signing keys |
| Observability | OpenTelemetry → Grafana stack | Traces, metrics, logs in one pipeline |
| CDN | Cloudflare / CloudFront | Static dashboard assets, DDoS protection |

---

## Operational Considerations

### Monitoring

| Metric | Alert Threshold | Description |
|--------|-----------------|-------------|
| API latency (p99) | > 500ms | Backend response time |
| Error rate (5xx) | > 1% | Server-side failures |
| WebSocket connections | > 80% of limit | Connection capacity |
| Audit sync lag | > 5 minutes | Time since last sync from any active agent |
| Hash chain breaks | > 0 | Audit integrity violations |
| Certificate expiry | < 30 days | TLS cert renewal |

### Backup and Recovery

- PostgreSQL: continuous WAL archiving + daily logical backups.
- Point-in-time recovery to any second within retention window.
- Backup retention: 30 days.
- Recovery time objective (RTO): < 1 hour.
- Recovery point objective (RPO): < 1 minute.

### Compliance

- SOC 2 Type II alignment (access controls, audit logging, encryption at rest).
- GDPR: tenant data export via `GET /settings/export` (all org data as JSON archive).
- Data deletion: org deletion removes all data within 30 days (soft delete → hard delete pipeline).
- Encryption at rest: AES-256 for PostgreSQL (managed service encryption), S3 bucket encryption.
- Encryption in transit: TLS 1.3 minimum.

---

## Open Questions

These are unresolved design questions for Phase C. They do not block Phase A or Phase B work.

1. **Multi-region deployment** — Should cloud tier be multi-region? If so, how is audit chain integrity maintained across regions? Recommendation: single-region MVP, multi-region as enterprise add-on.
2. **Tenant data export format** — JSON archive vs. structured SQL dump for GDPR compliance?
3. **Runtime agent groups** — Should runtimes be groupable (e.g., "production" vs. "development") for policy targeting? The `teams` concept may extend to agents.
4. **Policy approval workflow** — Should policy changes require approval from a second admin before signing? Useful for enterprise compliance but adds latency.
5. **Audit cold storage** — S3-compatible object storage vs. PostgreSQL partitioning for long-term audit retention? Recommendation: PostgreSQL partitioning for hot data (90 days), S3 for cold archive.
6. **Dashboard notification fatigue** — How to prevent alert storms? Recommendation: alert deduplication window (e.g., same alert type suppressed for 15 minutes).
7. **Billing integration** — Stripe vs. custom billing? When does billing gate enforcement happen relative to API rate limits?
8. **Runtime version enforcement** — Should the cloud reject agents below a minimum version? Recommendation: warn in dashboard, don't reject (offline-safe principle).

---

## End-State Dataflow Diagram

```
Local Runtime Agent (execution authority)
      |
      | Decision traces, audit events, session metadata
      | Prompt excerpts (max 200 chars), no PTY output, no secrets
      |
      v
Sync Worker (local, async, queues on disconnect)
      |
      | POST /sync/* endpoints (idempotent, batch)
      | Heartbeat every 60s
      |
      v
Cloud Governance API (observation authority only)
      |
      ├── Stores metadata in PostgreSQL (org_id scoped, RLS enforced)
      ├── Validates audit hash chain integrity on ingestion
      ├── Computes risk metrics from decision traces
      ├── Signs and distributes policies via Ed25519
      ├── Publishes WebSocket events to dashboard clients
      |
      v
Web Dashboard (React SPA)
      |
      | Read-only view of cloud data
      | Policy editing triggers sign + distribute
      | No execution path to local runtime
      | WebSocket for live updates
      |
      v
Human Operators (dashboard users)
      |
      | View sessions, audit, risk
      | Edit and distribute policies
      | Manage agents, users, teams
      | Configure alerts and retention
      |
      | NOTE: Prompt replies still go through Telegram/Slack
      | The dashboard does NOT relay prompts or inject replies
```

---

> **Reminder:** Phase C — Design Only. Not implemented. Execution stays local.
> The local runtime is fully functional without any cloud component.
> Cloud features are additive and degradable. They never become required.
