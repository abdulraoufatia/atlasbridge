# AtlasBridge Data Model Design

**Version:** 0.1.0
**Status:** Design
**Last updated:** 2026-02-20

---

## Overview

AtlasBridge uses SQLite as its local state store. All state is stored in `~/.atlasbridge/atlasbridge.db`. The audit log is a separate append-only file (`~/.atlasbridge/audit.log`) to ensure tamper-evidence independence.

---

## Design Principles

- **Local-only**: No external database. SQLite is the only persistence layer for operational data.
- **WAL mode**: SQLite Write-Ahead Logging for crash-safe concurrent reads/writes.
- **Explicit migrations**: Schema changes are versioned SQL migration files.
- **No ORM**: Pure `sqlite3` module (stdlib) with typed dataclasses. No SQLAlchemy dependency.
- **Separate audit log**: The audit log lives outside the DB for tamper-evidence isolation.

---

## Database Schema

### `schema_version`

Tracks applied migrations.

```sql
CREATE TABLE schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL,  -- ISO 8601
    description TEXT    NOT NULL
);
```

---

### `sessions`

Represents a single `atlasbridge run <tool>` invocation.

```sql
CREATE TABLE sessions (
    id              TEXT    NOT NULL PRIMARY KEY,  -- UUID v4
    tool            TEXT    NOT NULL,              -- e.g., "claude", "openai"
    pid             INTEGER NOT NULL,              -- PID of the wrapped process
    started_at      TEXT    NOT NULL,              -- ISO 8601
    ended_at        TEXT,                          -- NULL if still active
    exit_code       INTEGER,                       -- NULL if still active
    status          TEXT    NOT NULL DEFAULT 'active',
                    -- active | completed | crashed | terminated
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    approved_count  INTEGER NOT NULL DEFAULT 0,
    denied_count    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_started_at ON sessions(started_at);
```

---

### `approvals`

The central record for every tool call that required policy evaluation.

```sql
CREATE TABLE approvals (
    id              TEXT    NOT NULL PRIMARY KEY,  -- UUID v4 (short 8-char prefix shown to user)
    session_id      TEXT    NOT NULL REFERENCES sessions(id),
    tool            TEXT    NOT NULL,              -- tool name: "read_file", "bash", etc.
    arguments       TEXT    NOT NULL,              -- JSON-serialized tool arguments (redacted sensitive values)
    arguments_hash  TEXT    NOT NULL,              -- SHA-256 of full (unredacted) arguments
    risk_tier       TEXT    NOT NULL,              -- low | medium | high | critical
    policy_rule     TEXT    NOT NULL,              -- name of matching policy rule
    action          TEXT    NOT NULL,              -- allow | deny | require_approval
    status          TEXT    NOT NULL DEFAULT 'pending',
                    -- pending | approved | denied | expired | executing | completed | failed
    created_at      TEXT    NOT NULL,              -- ISO 8601
    expires_at      TEXT    NOT NULL,              -- ISO 8601 (created_at + timeout)
    decided_at      TEXT,                          -- ISO 8601, NULL until decision
    decided_by      TEXT,                          -- "telegram:<user_id>" | "cli:<username>" | "auto:timeout"
    decision_reason TEXT,                          -- User-provided reason on deny
    executed_at     TEXT,                          -- ISO 8601, NULL until execution completes
    execution_result TEXT,                         -- "success" | "error:<message>"
    telegram_msg_id INTEGER,                       -- Telegram message ID of approval request
    nonce           TEXT    NOT NULL,              -- One-time nonce for Telegram callback
    nonce_used      INTEGER NOT NULL DEFAULT 0     -- 0 = unused, 1 = used
);

CREATE INDEX idx_approvals_session ON approvals(session_id);
CREATE INDEX idx_approvals_status ON approvals(status);
CREATE INDEX idx_approvals_created_at ON approvals(created_at);
CREATE INDEX idx_approvals_expires_at ON approvals(expires_at);
```

---

### `policy_events`

Records every policy reload event for auditability.

```sql
CREATE TABLE policy_events (
    id              TEXT    NOT NULL PRIMARY KEY,  -- UUID v4
    event_type      TEXT    NOT NULL,              -- loaded | reloaded | rejected | hardcoded_override
    policy_hash     TEXT    NOT NULL,              -- SHA-256 of policy file contents
    rule_count      INTEGER NOT NULL,
    source          TEXT    NOT NULL,              -- file path
    timestamp       TEXT    NOT NULL,              -- ISO 8601
    detail          TEXT                           -- human-readable detail (e.g., diff summary)
);
```

---

### `daemon_events`

Records daemon lifecycle events.

```sql
CREATE TABLE daemon_events (
    id          TEXT    NOT NULL PRIMARY KEY,  -- UUID v4
    event_type  TEXT    NOT NULL,              -- started | stopped | crashed | config_reloaded
    pid         INTEGER,
    timestamp   TEXT    NOT NULL,              -- ISO 8601
    detail      TEXT
);
```

---

## Entity Relationship

```
sessions
  │
  │ 1:N
  ▼
approvals
  │
  ├── policy_rule ──► (runtime, not FK; rule name from policy)
  └── decided_by ──► (free text: telegram/cli/auto)

policy_events (standalone)
daemon_events (standalone)
```

---

## Dataclasses (Python)

The store layer uses typed dataclasses, not ORM models:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import enum

class ApprovalStatus(str, enum.Enum):
    PENDING    = "pending"
    APPROVED   = "approved"
    DENIED     = "denied"
    EXPIRED    = "expired"
    EXECUTING  = "executing"
    COMPLETED  = "completed"
    FAILED     = "failed"

class RiskTier(str, enum.Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"

@dataclass
class Session:
    id: str
    tool: str
    pid: int
    started_at: datetime
    status: str = "active"
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    tool_call_count: int = 0
    approved_count: int = 0
    denied_count: int = 0

@dataclass
class Approval:
    id: str
    session_id: str
    tool: str
    arguments: dict          # Redacted version (stored)
    arguments_hash: str      # SHA-256 of full args
    risk_tier: RiskTier
    policy_rule: str
    action: str
    status: ApprovalStatus
    created_at: datetime
    expires_at: datetime
    nonce: str
    nonce_used: bool = False
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None
    executed_at: Optional[datetime] = None
    execution_result: Optional[str] = None
    telegram_msg_id: Optional[int] = None
```

---

## Migrations

Migration files live in `atlasbridge/store/migrations/`:

```
001_initial.sql         — sessions, approvals, schema_version
002_policy_events.sql   — policy_events, daemon_events
```

Migration runner:

```python
def run_migrations(conn: sqlite3.Connection) -> None:
    current = get_schema_version(conn)
    for migration in load_migrations(current):
        conn.executescript(migration.sql)
        record_migration(conn, migration)
```

Migrations are always forward-only (no rollback). DB is backed up before each migration run.

---

## Audit Log (Separate File)

The audit log is stored in `~/.atlasbridge/audit.log` as JSON Lines (one event per line).

### Format

Each line is a JSON object:

```json
{
  "seq": 1847,
  "ts": "2026-02-20T19:14:32.451Z",
  "event": "tool_call_intercepted",
  "session_id": "sess_abc123",
  "approval_id": "appr_d4e5f6",
  "tool": "write_file",
  "risk_tier": "medium",
  "policy_rule": "require-approval-writes",
  "action": "require_approval",
  "prev_hash": "sha256:a3f9...",
  "hash": "sha256:b7c1..."
}
```

### Hash Chain

Each entry includes:
- `prev_hash`: SHA-256 of the previous entry (full JSON string)
- `hash`: SHA-256 of this entry's JSON string (excluding the `hash` field itself)

The first entry has `prev_hash: "genesis"`.

The hash chain allows `atlasbridge doctor` to verify the audit log has not been tampered with by recomputing the chain from entry 1.

### Event Types

| Event | Description |
|-------|-------------|
| `tool_call_intercepted` | Tool call received from AI agent |
| `policy_decision` | Policy engine decision (allow/deny/require_approval) |
| `approval_created` | Approval request created and sent to Telegram |
| `approval_decision` | User approved or denied |
| `approval_expired` | Approval timed out (auto-denied) |
| `tool_call_executed` | Tool call executed (after approval) |
| `tool_call_blocked` | Tool call blocked (deny decision) |
| `tool_call_failed` | Tool call execution failed |
| `session_started` | `atlasbridge run` session began |
| `session_ended` | `atlasbridge run` session ended |
| `policy_loaded` | Policy file loaded or reloaded |
| `daemon_started` | Daemon started |
| `daemon_stopped` | Daemon stopped |

---

## Data Retention

Default retention policy (configurable):
- `approvals`: 90 days
- `sessions`: 90 days
- `policy_events`: 365 days
- `daemon_events`: 30 days
- `audit.log`: Never deleted (append-only; archival responsibility is user's)

Retention is enforced by a daily cleanup job run by the daemon.

---

## Query Examples

```python
# Get all pending approvals
async def get_pending_approvals(db: Database) -> list[Approval]:
    rows = await db.fetchall(
        "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at ASC"
    )
    return [Approval.from_row(r) for r in rows]

# Count today's approvals
async def count_today(db: Database) -> dict[str, int]:
    rows = await db.fetchall("""
        SELECT status, COUNT(*) as count
        FROM approvals
        WHERE created_at >= date('now')
        GROUP BY status
    """)
    return {r["status"]: r["count"] for r in rows}

# Get expired pending approvals (for timeout cleanup loop)
async def get_expired_pending(db: Database) -> list[Approval]:
    rows = await db.fetchall("""
        SELECT * FROM approvals
        WHERE status = 'pending'
          AND expires_at < datetime('now')
    """)
    return [Approval.from_row(r) for r in rows]
```
