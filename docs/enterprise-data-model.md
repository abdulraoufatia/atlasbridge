# DESIGN ONLY — NO IMPLEMENTATION IN THIS RELEASE

# Enterprise Data Model

**Maturity:** Design Document — No Implementation
**Phase:** C (Enterprise Dashboard)
**Trust model:** Cloud OBSERVES, local EXECUTES.
**Database (design):** PostgreSQL 16+ with Row-Level Security

---

## Entity-Relationship Diagram

```
┌──────────────────┐
│  organizations   │
│  (tenant root)   │
└──┬───┬───┬───┬───┘
   │   │   │   │
   │   │   │   └──────────────┐
   │   │   │                  │
   v   │   v                  v
┌──────┐  ┌──────┐      ┌──────────────┐
│users │  │teams │      │ policy_      │
└──┬───┘  └──┬───┘      │ versions     │
   │         │           └──────────────┘
   │    N:M via
   │  team_members
   │
   └──────────────┐
                  │
   ┌──────────────┘
   │
   v
┌──────┐         ┌──────────┐
│agents│────1:N──>│ sessions │
└──┬───┘         └──┬───┬───┘
   │                │   │
   │                │   └───────────┐
   │                v               v
   │          ┌─────────┐    ┌───────────┐
   │          │ prompts  │    │  audit_   │
   │          └──┬───┬───┘    │  events   │
   │             │   │        └───────────┘
   │             v   v
   │       ┌───────┐ ┌──────────┐
   │       │replies│ │decisions │
   │       └───────┘ └──────────┘
   │
   └─────────> audit_events (also FK)

┌──────────┐
│ api_keys │──> users (creator FK)
└──────────┘
```

**Key relationships:**
- `organizations` is the tenant root. Every other table has `org_id` FK.
- `agents` represent registered local runtimes (1:N from org).
- `sessions` are owned by agents (1:N from agent).
- `prompts` belong to sessions (1:N). Each prompt has 0-1 `decisions` and 0-N `replies`.
- `audit_events` are hash-chained per agent, belong to sessions.
- `policy_versions` are content-addressed and immutable once signed.
- `users` join `teams` via a `team_members` join table (N:M).

---

## Table Definitions

### organizations

Tenant root. One row per customer organization.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | Immutable tenant ID |
| `slug` | VARCHAR(63) | UNIQUE, NOT NULL | URL-safe org name |
| `display_name` | VARCHAR(255) | NOT NULL | |
| `edition` | VARCHAR(20) | NOT NULL, DEFAULT 'community' | community / pro / enterprise |
| `plan` | VARCHAR(20) | NOT NULL, DEFAULT 'free' | free / team / enterprise |
| `max_agents` | INTEGER | NOT NULL, DEFAULT 3 | |
| `max_users` | INTEGER | NOT NULL, DEFAULT 1 | |
| `data_region` | VARCHAR(20) | NOT NULL, DEFAULT 'us-east-1' | Immutable after provisioning |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

### users

Dashboard users. Authenticated via OIDC or API key.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → organizations, NOT NULL | Tenant scope |
| `email` | VARCHAR(255) | NOT NULL | Login identity |
| `display_name` | VARCHAR(255) | NOT NULL | |
| `role` | VARCHAR(20) | NOT NULL, DEFAULT 'viewer' | Mirrors local Role enum |
| `auth_provider` | VARCHAR(50) | NOT NULL, DEFAULT 'oidc' | oidc / api_key / saml |
| `auth_subject` | VARCHAR(255) | NOT NULL | External identity (OIDC sub) |
| `channel_identity` | VARCHAR(255) | NULLABLE | Maps to local RBAC (e.g., "telegram:123456") |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Soft disable |
| `last_login_at` | TIMESTAMPTZ | NULLABLE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**RLS:** `WHERE org_id = current_setting('app.current_org_id')::UUID`

### teams

Optional grouping within an org.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → organizations, NOT NULL | |
| `name` | VARCHAR(255) | NOT NULL | |
| `description` | TEXT | DEFAULT '' | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** `(org_id, name)`

### agents

Registered local runtime installations. Each `atlasbridge` instance that
connects to the cloud is an agent.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | Cloud-assigned |
| `org_id` | UUID | FK → organizations, NOT NULL | |
| `runtime_id` | VARCHAR(255) | NOT NULL | Ed25519 public key |
| `hostname` | VARCHAR(255) | NOT NULL | Machine hostname |
| `label` | VARCHAR(255) | DEFAULT '' | User-assigned |
| `agent_version` | VARCHAR(20) | NOT NULL | e.g., "0.8.6" |
| `platform` | VARCHAR(50) | NOT NULL | darwin / linux / windows |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'active' | active / inactive / revoked |
| `last_seen_at` | TIMESTAMPTZ | NULLABLE | Last heartbeat |
| `registered_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** `(org_id, runtime_id)`

### sessions

Mirrors local `sessions` table. Synced from runtime agents.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | VARCHAR(36) | PK | From local runtime |
| `org_id` | UUID | FK → organizations, NOT NULL | |
| `agent_id` | UUID | FK → agents, NOT NULL | |
| `tool` | VARCHAR(50) | NOT NULL, DEFAULT '' | Adapter name |
| `command` | TEXT | NOT NULL, DEFAULT '' | |
| `cwd` | TEXT | NOT NULL, DEFAULT '' | |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'starting' | |
| `pid` | INTEGER | NULLABLE | Local PID |
| `started_at` | TIMESTAMPTZ | NOT NULL | |
| `ended_at` | TIMESTAMPTZ | NULLABLE | |
| `exit_code` | INTEGER | NULLABLE | |
| `label` | VARCHAR(255) | NOT NULL, DEFAULT '' | |
| `prompt_count` | INTEGER | NOT NULL, DEFAULT 0 | |
| `metadata` | JSONB | NOT NULL, DEFAULT '{}' | |
| `synced_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Index:** `(org_id, started_at DESC)`

### prompts

Mirrors local `prompts` table.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | VARCHAR(36) | PK | From local runtime |
| `org_id` | UUID | FK → organizations, NOT NULL | |
| `session_id` | VARCHAR(36) | FK → sessions, NOT NULL | |
| `prompt_type` | VARCHAR(30) | NOT NULL | yes_no / confirm_enter / multiple_choice / free_text |
| `confidence` | VARCHAR(10) | NOT NULL | high / medium / low |
| `excerpt` | TEXT | NOT NULL, DEFAULT '' | Max 200 chars. No PTY output. |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'created' | Full state machine |
| `nonce` | VARCHAR(36) | NOT NULL | Idempotency key |
| `expires_at` | TIMESTAMPTZ | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `resolved_at` | TIMESTAMPTZ | NULLABLE | |
| `response_normalized` | TEXT | NULLABLE | |
| `channel_identity` | VARCHAR(255) | NULLABLE | Responder |
| `metadata` | JSONB | NOT NULL, DEFAULT '{}' | |

**Index:** `(org_id, session_id, status)`

### decisions

Cloud storage for `DecisionTraceEntryV2` records. Synced from local JSONL trace.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | Cloud-assigned |
| `org_id` | UUID | FK → organizations, NOT NULL | |
| `session_id` | VARCHAR(36) | NOT NULL | |
| `prompt_id` | VARCHAR(36) | NOT NULL | |
| `timestamp` | TIMESTAMPTZ | NOT NULL | |
| `policy_version` | VARCHAR(50) | NOT NULL, DEFAULT '' | |
| `policy_hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | sha256:<hex> |
| `matched_rule` | VARCHAR(255) | NOT NULL, DEFAULT '' | |
| `risk_level` | VARCHAR(10) | NOT NULL, DEFAULT 'low' | low / medium / high / critical |
| `action_taken` | VARCHAR(30) | NOT NULL, DEFAULT '' | auto_reply / require_human / deny / notify_only |
| `idempotency_key` | VARCHAR(36) | NOT NULL, DEFAULT '' | Dedup on sync |
| `previous_hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | Hash chain link |
| `current_hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | SHA-256 of entry |
| `trace_version` | VARCHAR(5) | NOT NULL, DEFAULT '2' | |

**Index:** `(org_id, session_id, timestamp)`
**Index:** `(org_id, risk_level)` — risk dashboard queries

### audit_events

Hash-chained audit events. Mirrors local `audit_events` table.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | VARCHAR(36) | PK | From local runtime |
| `org_id` | UUID | FK → organizations, NOT NULL | |
| `agent_id` | UUID | FK → agents, NOT NULL | Source runtime |
| `event_type` | VARCHAR(50) | NOT NULL | |
| `session_id` | VARCHAR(36) | NOT NULL, DEFAULT '' | |
| `prompt_id` | VARCHAR(36) | NOT NULL, DEFAULT '' | |
| `payload` | JSONB | NOT NULL, DEFAULT '{}' | |
| `timestamp` | TIMESTAMPTZ | NOT NULL | |
| `prev_hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | |
| `hash` | VARCHAR(71) | NOT NULL, DEFAULT '' | SHA-256 |
| `synced_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Partitioned by:** `org_id` (range on `timestamp` within each org)
**Index:** `(org_id, timestamp DESC)`
**Index:** `(org_id, event_type)`

### policy_versions

Content-addressed, immutable policy storage.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → organizations, NOT NULL | |
| `version` | INTEGER | NOT NULL | Monotonic per org |
| `name` | VARCHAR(255) | NOT NULL, DEFAULT '' | |
| `content_hash` | VARCHAR(71) | NOT NULL | sha256:<hex> of canonical YAML |
| `yaml_content` | TEXT | NOT NULL | Full policy YAML |
| `rule_count` | INTEGER | NOT NULL | |
| `dsl_version` | VARCHAR(5) | NOT NULL, DEFAULT '1' | v0 or v1 |
| `signature` | TEXT | NOT NULL, DEFAULT '' | Ed25519 signature envelope (JSON) |
| `signed_by` | UUID | FK → users, NULLABLE | |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT FALSE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

**Unique:** `(org_id, version)`
**Unique:** `(org_id, content_hash)` — prevents duplicate content

### api_keys

Scoped API keys for agents and integrations.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → organizations, NOT NULL | |
| `user_id` | UUID | FK → users, NOT NULL | Creator |
| `name` | VARCHAR(255) | NOT NULL | |
| `key_hash` | VARCHAR(71) | NOT NULL | SHA-256 (key never stored) |
| `key_prefix` | VARCHAR(8) | NOT NULL | For identification |
| `scopes` | TEXT[] | NOT NULL | Permitted API scopes |
| `expires_at` | TIMESTAMPTZ | NULLABLE | |
| `last_used_at` | TIMESTAMPTZ | NULLABLE | |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | |

---

## Multi-Tenancy Strategy

### org_id Scoping

Every table (except `organizations` itself) has an `org_id` column with a
foreign key to `organizations.id`. This is the primary tenant isolation
mechanism.

### PostgreSQL Row-Level Security

RLS policies enforce tenant isolation at the database level, independent of
application logic. This is defense-in-depth: even if the application has a bug,
the database prevents cross-tenant data access.

**Design pattern** (applied to every tenant-scoped table):

```sql
-- Enable RLS
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

-- Policy: rows visible only to current org
CREATE POLICY tenant_isolation ON sessions
  USING (org_id = current_setting('app.current_org_id')::UUID);

-- Application sets org_id from JWT on every connection
SET app.current_org_id = '<org_id_from_jwt>';
```

**Rules:**
- Every API handler extracts `org_id` from the JWT and sets the session variable.
- No API endpoint accepts `org_id` as a request parameter.
- No superuser query path returns cross-tenant data in the application layer.
- Background jobs (aggregation, retention) are partitioned by `org_id`.

---

## Data Categories and Boundaries

| Category | Stored in Cloud | Contains Secrets | Retention |
|----------|----------------|-----------------|-----------|
| Decision traces | Yes (metadata only) | No | Configurable (default 90 days) |
| Audit events | Yes (hash-chained) | No | Configurable (default 1 year) |
| Session metadata | Yes | No | Configurable (default 90 days) |
| Policy YAML | Yes (signed) | No | All versions retained |
| PTY output | **Never** — local only | May contain secrets | Local runtime only |
| Prompt excerpts | Truncated to 200 chars | Possibly | With prompt record |
| Private keys | **Never** — local keyring | Yes | Local runtime only |

---

## Retention and Archival

### Configurable Retention

Retention periods are configurable per org via the Settings screen:

| Data Type | Default | Min | Max |
|-----------|---------|-----|-----|
| Audit events | 1 year | 30 days | Unlimited (Enterprise) |
| Decision traces | 90 days | 30 days | 1 year |
| Session metadata | 90 days | 30 days | 1 year |
| Policy versions | Indefinite | — | — |

### Archival Pipeline (Design)

1. Daily job scans for records past retention window.
2. Records are exported to cold storage (S3-compatible object store) as
   compressed JSON archives, grouped by org and month.
3. Original records are soft-deleted (marked `archived_at`).
4. After 30-day grace period, hard-deleted from PostgreSQL.
5. Archives are retained per org's compliance requirements.

### Audit Partitioning

`audit_events` is partitioned by `(org_id, timestamp)` for efficient
retention management and query performance. Each org-month combination is a
separate partition, enabling fast `DROP PARTITION` for expired data.

---

## Schema Evolution Strategy

### Additive-Only

Schema changes are strictly additive:
- New columns with defaults: always safe.
- New tables: always safe.
- New indexes: always safe.

### Prohibited Changes

- Column renames or type changes on existing columns.
- Column or table drops without a deprecation cycle (min 2 versions).
- Changes to primary key structure.
- Changes to `org_id` FK relationships.

### Version Gating

New features that depend on new columns use version-gated checks:

```
IF column_exists('decisions', 'new_field') THEN
  -- use new field
ELSE
  -- fallback behavior
END IF;
```

This ensures old agents syncing to a newer cloud schema do not break.

---

## Sync Protocol: Local → Cloud

### Batch Upsert Semantics

Runtime agents sync data to the cloud via `POST /sync/*` endpoints:

1. **Batch size:** Up to 100 records per request.
2. **Idempotency:** Each record has a unique ID (session ID, event ID,
   idempotency key). Repeated submissions are safe — the server deduplicates.
3. **Last-write-wins:** For mutable fields (session `status`, `prompt_count`),
   the most recent sync overwrites.
4. **Partial acceptance:** If a batch contains 100 records and 2 fail
   validation, 98 are accepted. The response includes per-item status.
5. **Order independence:** Records can arrive out of order. The server
   sorts by timestamp on ingestion.

### Hash Chain Validation

For `audit_events` and `decisions`, the server validates hash chain continuity:

- Each record references the previous record's hash (`prev_hash`).
- On ingestion, the server verifies: `hash == SHA-256(canonical(record))`.
- If `prev_hash` doesn't match the last stored hash for this agent, it's a
  **gap** (from an offline period). Gaps are flagged but accepted.
- If `hash` doesn't match the computed hash, it's a **break**. The record is
  rejected and an alert is raised.

### Offline Queue and Reconnection

1. Runtime queues data locally in SQLite during disconnection.
2. On reconnection, the runtime replays queued records in chronological order.
3. The cloud server handles replays idempotently.
4. No data is lost — the local SQLite is the authoritative source.
5. Cloud sync failure never blocks local runtime operation.

---

> **Reminder:** This is a design document. No database has been created.
> No migrations have been executed. Cloud OBSERVES, local EXECUTES.
