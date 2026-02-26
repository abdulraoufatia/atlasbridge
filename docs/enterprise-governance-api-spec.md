# DESIGN ONLY — NO IMPLEMENTATION IN THIS RELEASE

# Enterprise Governance API — Specification

**Maturity:** Design Document — No Implementation
**Phase:** C (Enterprise Dashboard)
**Trust model:** Cloud OBSERVES, local EXECUTES.
**Base URL (design):** `https://api.atlasbridge.io/v1`

---

## Conventions

| Convention | Pattern |
|------------|---------|
| Pagination | `?page=1&per_page=50` (max 100). Response header: `X-Total-Count`. |
| Sorting | `?sort=-created_at` (prefix `-` for descending). |
| Filtering | `?filter[status]=running&filter[agent_id]=<uuid>` |
| Date ranges | `?range=24h` or `?from=<ISO8601>&to=<ISO8601>` |
| Request IDs | Every response includes `X-Request-Id` header. |
| Content-Type | `application/json` for all request and response bodies. |

---

## Authentication Model (Design)

> **Note:** Authentication implementation is deferred. This section defines the
> target design only.

### Auth Methods

| Method | Use Case | Token Format |
|--------|----------|--------------|
| OIDC / OAuth 2.0 | Dashboard users (SSO) | JWT (1h TTL, refresh 30d) |
| API key | Runtime agents, CI/CD | Bearer token, SHA-256 hashed at rest |
| Ed25519 handshake | Runtime agent identity | Challenge-response → session JWT |

### JWT Claims

```json
{
  "sub": "<user_id>",
  "org_id": "<org_uuid>",
  "role": "admin",
  "team_id": "<team_uuid or null>",
  "iat": 1706000000,
  "exp": 1706003600
}
```

`org_id` is extracted from the JWT by every API handler. No API endpoint
accepts `org_id` as a query parameter. RLS in PostgreSQL provides
defense-in-depth: even if application code has a bug, the database enforces
tenant boundaries.

### RBAC Enforcement

| Role | Shorthand | Description |
|------|-----------|-------------|
| `viewer` | viewer+ | Read-only access to sessions, audit, risk, policies. |
| `operator` | operator+ | Viewer + pause/resume autopilot (if cloud-routed). |
| `admin` | admin+ | Operator + edit policies, manage agents/keys/alerts. |
| `owner` | owner | Admin + manage users, roles, billing, org settings. |

Roles mirror the local `Role` enum exactly. No cloud-specific roles.

---

## Error Response Format

All errors return a consistent JSON envelope:

```json
{
  "error": "Human-readable message",
  "code": "ERROR_CODE",
  "request_id": "uuid",
  "details": {}
}
```

### Error Code Catalog

| HTTP | Code | Description |
|------|------|-------------|
| 400 | `INVALID_REQUEST` | Malformed request body or query parameters. |
| 400 | `INVALID_POLICY_YAML` | Policy YAML fails schema validation. |
| 400 | `DUPLICATE_POLICY` | Policy with identical content_hash already exists. |
| 401 | `UNAUTHORIZED` | Missing or invalid authentication token. |
| 401 | `TOKEN_EXPIRED` | JWT has expired. Client should refresh. |
| 403 | `FORBIDDEN` | Authenticated but insufficient role for this action. |
| 404 | `NOT_FOUND` | Resource does not exist or is not in this org. |
| 409 | `CONFLICT` | Concurrent modification (e.g., two policy edits). |
| 422 | `VALIDATION_ERROR` | Request body fails validation. `details` has field-level errors. |
| 429 | `RATE_LIMITED` | Rate limit exceeded. Response includes `Retry-After` header. |
| 500 | `INTERNAL_ERROR` | Server error. `request_id` should be reported. |
| 502 | `UPSTREAM_ERROR` | Dependency failure (database, cache). |
| 503 | `SERVICE_UNAVAILABLE` | Maintenance window or overload. |

---

## Rate Limiting

| Plan | Requests/min | WebSocket conns | Audit events/day | Policy versions |
|------|-------------|-----------------|-------------------|-----------------|
| Free | 60 | 1 | 10,000 | 10 |
| Team | 600 | 10 | 500,000 | 100 |
| Enterprise | 6,000 | Unlimited | Unlimited | Unlimited |

Enforced per `org_id` at the API gateway. HTTP 429 response includes:

```
Retry-After: 30
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1706000030
```

---

## Endpoints

### Sessions

#### `GET /sessions`

List sessions for the org. Paginated and filterable.

**Auth:** viewer+

**Query parameters:**
- `page`, `per_page`, `sort` (standard)
- `filter[agent_id]` — UUID
- `filter[status]` — `running`, `completed`, `crashed`, `canceled`
- `filter[adapter]` — `claude`, `openai`, `gemini`, `custom`
- `range` or `from`/`to` — date range

**Response (200):**

```json
{
  "data": [
    {
      "id": "abc-123",
      "agent_id": "uuid",
      "agent_hostname": "mac-01",
      "tool": "claude",
      "status": "completed",
      "started_at": "2026-01-15T14:00:00Z",
      "ended_at": "2026-01-15T14:22:00Z",
      "prompt_count": 8,
      "escalation_count": 1,
      "exit_code": 0,
      "label": "feature-branch-work"
    }
  ],
  "page": 1,
  "per_page": 50,
  "total": 234
}
```

#### `GET /sessions/:id`

Single session detail.

**Auth:** viewer+

**Response (200):**

```json
{
  "id": "abc-123",
  "agent_id": "uuid",
  "agent_hostname": "mac-01",
  "tool": "claude",
  "command": "claude",
  "cwd": "/home/user/project",
  "status": "completed",
  "started_at": "2026-01-15T14:00:00Z",
  "ended_at": "2026-01-15T14:22:00Z",
  "prompt_count": 8,
  "escalation_count": 1,
  "exit_code": 0,
  "label": "feature-branch-work",
  "metadata": {}
}
```

#### `GET /sessions/:id/events`

Paginated event timeline for a session. Includes prompts, decisions, and audit events interleaved chronologically.

**Auth:** viewer+

**Response (200):**

```json
{
  "data": [
    {
      "type": "prompt",
      "timestamp": "2026-01-15T14:02:00Z",
      "prompt_type": "yes_no",
      "confidence": "high",
      "excerpt": "Continue? [y/n]",
      "decision": "auto_reply",
      "matched_rule": "allow-tests",
      "risk_level": "low",
      "latency_ms": 12
    },
    {
      "type": "escalation",
      "timestamp": "2026-01-15T14:05:00Z",
      "prompt_type": "free_text",
      "confidence": "medium",
      "excerpt": "Enter the API key:",
      "channel": "telegram",
      "resolved_in_seconds": 45,
      "responder": "telegram:123456789"
    }
  ],
  "page": 1,
  "per_page": 100,
  "total": 8
}
```

---

### Policies

#### `GET /policies`

List policy versions. Most recent first.

**Auth:** viewer+

**Response (200):**

```json
{
  "data": [
    {
      "version": 13,
      "name": "production",
      "content_hash": "sha256:abc123...",
      "rule_count": 10,
      "dsl_version": "1",
      "is_active": true,
      "signed": true,
      "created_at": "2026-01-15T10:00:00Z"
    }
  ]
}
```

#### `POST /policies`

Create a new policy version.

**Auth:** admin+

**Request:**

```json
{
  "name": "production",
  "yaml_content": "version: \"1\"\nrules:\n  - name: allow-tests\n    ...",
  "description": "Added rule for CI prompts"
}
```

**Response (201):**

```json
{
  "version": 14,
  "content_hash": "sha256:def456...",
  "rule_count": 11,
  "validation_errors": [],
  "is_active": false,
  "signed": false
}
```

**Errors:** `INVALID_POLICY_YAML` (400), `DUPLICATE_POLICY` (400)

#### `POST /policies/:version/distribute`

Sign a policy version with the cloud Ed25519 key and push to all connected agents.

**Auth:** admin+

**Response (200):**

```json
{
  "version": 14,
  "signature": "ed25519:<base64>",
  "distributed_to": 8,
  "pending": 4,
  "failed": 0
}
```

Agents that are offline receive the policy on next sync via `GET /sync/policy`.

#### `POST /policies/test`

Simulate a prompt against a policy version.

**Auth:** viewer+

**Request:**

```json
{
  "version": 13,
  "prompt_type": "yes_no",
  "confidence": "high",
  "excerpt": "Run tests? [y/n]"
}
```

**Response (200):**

```json
{
  "matched_rule": "allow-tests",
  "action": "auto_reply",
  "reply_value": "y",
  "risk_level": "low",
  "evaluation_path": "rule 3 of 10 matched on prompt_type + confidence"
}
```

---

### Audit

#### `GET /audit`

Query audit events. Paginated, filterable, searchable.

**Auth:** viewer+

**Query parameters:**
- `search` — full-text search across event type and payload
- `filter[event_type]` — `prompt_detected`, `policy_evaluated`, `reply_injected`, `escalated`, etc.
- `filter[agent_id]`, `filter[session_id]`
- `range` or `from`/`to`
- `page`, `per_page`, `sort`

**Response (200):**

```json
{
  "data": [
    {
      "id": "evt-uuid",
      "agent_id": "uuid",
      "event_type": "policy_evaluated",
      "session_id": "abc-123",
      "timestamp": "2026-01-15T14:02:00Z",
      "chain_status": "verified",
      "payload": {
        "rule": "allow-tests",
        "action": "auto_reply"
      }
    }
  ],
  "integrity": {
    "verified_count": 1200,
    "gap_count": 2,
    "break_count": 0
  }
}
```

#### `GET /audit/integrity`

Hash chain integrity report per agent.

**Auth:** viewer+

**Response (200):**

```json
{
  "agents": [
    {
      "agent_id": "uuid",
      "hostname": "mac-01",
      "total_events": 5000,
      "verified": 4998,
      "gaps": 2,
      "breaks": 0,
      "oldest_event": "2026-01-01T00:00:00Z",
      "newest_event": "2026-01-15T14:22:00Z"
    }
  ]
}
```

#### `GET /audit/export`

Export audit events as CSV or JSON with integrity metadata.

**Auth:** admin+

**Query parameters:** Same filters as `GET /audit` plus `format=csv|json`.

**Response:** Streaming download with `Content-Disposition: attachment`.

---

### Risk

#### `GET /risk`

Current org-wide risk summary.

**Auth:** viewer+

**Response (200):**

```json
{
  "summary": {
    "critical": 0,
    "high": 3,
    "medium": 42,
    "low": 1159
  },
  "factors": {
    "escalation_rate": 0.032,
    "low_confidence_rate": 0.12,
    "policy_miss_rate": 0.021,
    "auto_reply_protected_rate": 0.008,
    "avg_response_time_seconds": 34
  },
  "window": "7d",
  "computed_at": "2026-01-15T14:30:00Z"
}
```

#### `GET /risk/trends`

Risk metrics over a configurable time window.

**Auth:** viewer+

**Query:** `?window=7d` (options: `24h`, `7d`, `30d`)

**Response (200):**

```json
{
  "window": "7d",
  "data_points": [
    { "date": "2026-01-09", "high": 1, "medium": 8, "escalation_rate": 0.04 },
    { "date": "2026-01-10", "high": 0, "medium": 6, "escalation_rate": 0.03 }
  ]
}
```

#### `PUT /risk/alerts/config`

Configure alert thresholds and notification channels.

**Auth:** admin+

**Request:**

```json
{
  "escalation_rate_threshold": 0.05,
  "auto_reply_protected_threshold": 0.01,
  "notification_channels": ["email", "slack_webhook"],
  "slack_webhook_url": "https://hooks.slack.com/...",
  "dedup_window_minutes": 15
}
```

---

### Agents

#### `GET /agents`

List registered runtime agents.

**Auth:** viewer+

**Response (200):**

```json
{
  "data": [
    {
      "id": "uuid",
      "hostname": "mac-01",
      "runtime_id": "ed25519:<base64>",
      "agent_version": "0.8.6",
      "platform": "darwin",
      "status": "active",
      "active_sessions": 2,
      "last_seen_at": "2026-01-15T14:22:00Z",
      "registered_at": "2026-01-01T10:00:00Z"
    }
  ]
}
```

#### `DELETE /agents/:id`

Revoke an agent. Invalidates handshake credentials immediately.

**Auth:** admin+

**Response (204):** No content.

---

### Agent Sync Endpoints

These are called by runtime agents, not dashboard users.

**Auth:** Agent API key or handshake JWT.

#### `POST /sync/sessions`

Batch upsert session metadata.

**Request:**

```json
{
  "sessions": [
    {
      "id": "abc-123",
      "tool": "claude",
      "status": "running",
      "started_at": "2026-01-15T14:00:00Z",
      "prompt_count": 5
    }
  ]
}
```

**Response (200):**

```json
{
  "accepted": 1,
  "rejected": 0,
  "errors": []
}
```

**Idempotency:** Deduplication by session `id`. Repeated submissions update
existing records (last-write-wins on mutable fields like `status`,
`prompt_count`).

#### `POST /sync/audit`

Batch upload audit events with hash chain validation.

**Request:**

```json
{
  "events": [
    {
      "id": "evt-uuid",
      "event_type": "policy_evaluated",
      "session_id": "abc-123",
      "timestamp": "2026-01-15T14:02:00Z",
      "prev_hash": "sha256:aaa...",
      "hash": "sha256:bbb...",
      "payload": {}
    }
  ]
}
```

**Response (200):**

```json
{
  "accepted": 1,
  "rejected": 0,
  "chain_status": "continuous",
  "errors": []
}
```

The server validates hash chain continuity on ingestion. Gaps from offline
periods are flagged but accepted. Events are append-only — no mutation or
deletion.

#### `POST /sync/heartbeat`

Agent heartbeat with status summary.

**Request:**

```json
{
  "agent_id": "uuid",
  "active_sessions": 2,
  "prompt_count_since_last": 15,
  "timestamp": "2026-01-15T14:22:00Z"
}
```

**Response (200):** `{ "ack": true }`

3 missed heartbeats (180s) → agent status set to `inactive`. Next heartbeat
restores `active` automatically.

#### `GET /sync/policy`

Check for policy updates. Returns latest signed policy if newer than the
agent's current version.

**Auth:** Agent API key or handshake JWT.

**Query:** `?current_version=12`

**Response (200):**

```json
{
  "update_available": true,
  "version": 13,
  "content_hash": "sha256:abc...",
  "yaml_content": "version: \"1\"\nrules:\n  ...",
  "signature": {
    "policy_hash": "sha256:abc...",
    "org_id": "uuid",
    "version": 13,
    "timestamp": "2026-01-15T10:00:00Z",
    "signature": "ed25519:<base64>"
  }
}
```

---

### Event Model (Real-Time)

Dashboard clients connect via WebSocket for live updates:

```
wss://api.atlasbridge.io/ws/v1/live?token=<JWT>
```

All events are scoped to the authenticated `org_id`.

| Event | Trigger | Payload |
|-------|---------|---------|
| `session.started` | Runtime starts session | Session metadata |
| `session.ended` | Session completes | Session metadata + summary |
| `prompt.detected` | Prompt detected | Prompt event (no PTY content) |
| `prompt.decided` | Policy evaluated | Decision + rule matched |
| `prompt.escalated` | Forwarded to human | Escalation metadata |
| `prompt.resolved` | Reply injected | Resolution metadata |
| `agent.connected` | Handshake complete | Agent metadata |
| `agent.disconnected` | Connection lost | agent_id + last_seen |
| `agent.heartbeat` | Heartbeat received | agent_id + summary |
| `policy.distributed` | Policy push initiated | Version + target agents |
| `policy.accepted` | Agent accepted policy | agent_id + policy_hash |
| `policy.rejected` | Signature invalid | agent_id + reason |
| `risk.alert` | Threshold breached | Alert details |

**Reconnection:** Exponential backoff (1s, 2s, 4s, max 30s). On reconnect,
client sends `{ "type": "replay", "since": "<last_event_timestamp>" }` to
receive missed events.

---

> **Reminder:** This is a design document. No HTTP server implementation exists.
> Cloud OBSERVES, local EXECUTES.
