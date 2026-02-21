# AtlasBridge Approval Lifecycle Design

**Version:** 0.1.0
**Status:** Design
**Last updated:** 2026-02-20

---

## Overview

An "approval" is the central unit of work in AtlasBridge. Every tool call that the policy engine marks as `require_approval` creates an approval record that must be resolved before the tool call proceeds or is blocked.

This document defines the complete approval state machine, lifecycle events, timeout behavior, and concurrent access handling.

---

## Approval States

```
                     ┌─────────────────────────────────────────────────────┐
                     │                                                     │
                     ▼                                                     │
               ┌──────────┐                                               │
   tool call   │          │   policy: allow                               │
   intercepted │ CREATED  │──────────────────────────────────────────────►│ (no approval record)
               │          │   policy: deny                                │ execute directly
               └──────────┘──────────────────────────────────────────────►│ block directly
                     │                                                     │
                     │ policy: require_approval                            │
                     ▼                                                     │
               ┌──────────┐                                               │
               │          │                                               │
               │ PENDING  │◄──────────────────────────────────────────────┘
               │          │    (written to DB; Telegram notified)
               └──────────┘
                  │  │  │
       ┌──────────┘  │  └──────────────┐
       │             │                 │
       │ user        │ user            │ timer expires
       │ approves    │ denies          │ (no response)
       ▼             ▼                 ▼
  ┌──────────┐ ┌──────────┐    ┌──────────────┐
  │          │ │          │    │              │
  │ APPROVED │ │  DENIED  │    │   EXPIRED    │
  │          │ │          │    │ (auto-denied)│
  └──────────┘ └──────────┘    └──────────────┘
       │
       │ tool call begins execution
       ▼
  ┌──────────┐
  │          │
  │EXECUTING │
  │          │
  └──────────┘
       │  │
       │  └─────── execution fails
       │                │
       │ execution       ▼
       │ succeeds   ┌──────────┐
       │            │  FAILED  │
       ▼            └──────────┘
  ┌──────────┐
  │          │
  │COMPLETED │
  │          │
  └──────────┘
```

---

## State Definitions

| State | Description |
|-------|-------------|
| `PENDING` | Created, Telegram notified. Awaiting user decision. Tool call suspended. |
| `APPROVED` | User approved via Telegram or CLI. Tool call will execute. |
| `DENIED` | User denied via Telegram or CLI. Tool call blocked. Error returned to agent. |
| `EXPIRED` | Timeout elapsed with no response. Auto-denied. |
| `EXECUTING` | Approved tool call is currently executing. |
| `COMPLETED` | Tool call executed successfully. |
| `FAILED` | Tool call execution failed after approval. |

---

## State Transitions

| From | To | Trigger | Guard |
|------|----|---------|-------|
| *(create)* | `PENDING` | Policy returns `require_approval` | Tool call valid |
| `PENDING` | `APPROVED` | User taps Approve in Telegram | User in whitelist; nonce valid; not expired |
| `PENDING` | `APPROVED` | `atlasbridge approvals approve <id>` | Not expired |
| `PENDING` | `DENIED` | User taps Deny in Telegram | User in whitelist; nonce valid |
| `PENDING` | `DENIED` | `atlasbridge approvals deny <id>` | Always allowed |
| `PENDING` | `EXPIRED` | Expiry timer fires | `now >= expires_at` |
| `APPROVED` | `EXECUTING` | Tool call execution begins | — |
| `EXECUTING` | `COMPLETED` | Tool call returns success | — |
| `EXECUTING` | `FAILED` | Tool call returns error | — |

**Invalid transitions (guarded by DB constraint):**
- `APPROVED → DENIED` (decision already made)
- `DENIED → APPROVED` (decision already made)
- `EXPIRED → APPROVED` (expired cannot be un-expired)
- `COMPLETED → any` (terminal state)
- `FAILED → any` (terminal state)

---

## Concurrent Access and Race Prevention

### Race: Two simultaneous Telegram responses for the same approval

Both `approve` and `deny` callbacks may arrive nearly simultaneously if the user taps twice or if there's a retry.

**Solution:** Atomic status transition using SQLite's serialized writes:

```sql
UPDATE approvals
SET status = ?, decided_at = ?, decided_by = ?, nonce_used = 1
WHERE id = ?
  AND status = 'pending'
  AND nonce = ?
  AND nonce_used = 0
  AND expires_at > datetime('now')
```

The `WHERE status = 'pending' AND nonce_used = 0` guard ensures only the first response succeeds. The update returns affected row count; if 0, the response is rejected (nonce already used or approval already decided).

### Race: Timeout fires simultaneously with user response

The expiry loop checks `status = 'pending'` before acting. Same atomic update pattern ensures exactly one transition wins.

### Race: Multiple `atlasbridge approvals approve` CLI calls

Same DB guard applies.

---

## Notification Content

### Telegram approval request message

```
⚠️ AtlasBridge Approval Request

Operation:  write_file
Path:       /Users/ara/project/src/main.py
Risk:       🟡 MEDIUM
Rule:       require-approval-writes

Session:    claude (PID 9876, started 19:10:05)
Approval:   #a1b2c3
Expires:    5 minutes (19:19:32)

───────────────────────────────
[✅ Approve]  [❌ Deny]
```

### On approval

```
✅ Approved — write_file /src/main.py
Approval #a1b2c3 — executed successfully.
```

### On denial

```
❌ Denied — write_file /src/main.py
Approval #a1b2c3 — blocked. Agent received an error.
```

### On timeout

```
⏱️ Timed Out — write_file /src/main.py
Approval #a1b2c3 — auto-denied (no response in 5 minutes).
```

### On rate limit warning

```
⚠️ AtlasBridge Rate Limit Alert

Your AI session (claude, PID 9876) has requested 10 approvals
in the last 60 seconds. This may be unusual activity.

The session has been paused. Resume it with:
  atlasbridge approvals resume <session_id>

Or deny all pending:
  atlasbridge approvals deny-all
```

---

## Approval Timeout Behavior

Default timeout: 300 seconds (5 minutes). Configurable.

**Timeout phases:**

| Time | Action |
|------|--------|
| `T+0` | Approval created, Telegram notified |
| `T+120` | First reminder sent (if configured) |
| `T+240` | Second reminder sent (60s warning) |
| `T+300` | Auto-denied. Agent receives error. |

Reminders are optional and configurable:

```toml
[approvals]
timeout_seconds = 300
remind_at = [120, 240]   # seconds after creation; empty = no reminders
```

---

## Approval ID Format

- Full ID: UUID v4 (e.g., `550e8400-e29b-41d4-a716-446655440000`)
- Short display ID: first 6 characters of UUID hex (e.g., `a1b2c3`)
- Short ID used in CLI output, Telegram messages, and `atlasbridge approvals show`

---

## Nonce Protocol

Each approval has a one-time nonce to prevent replay attacks:

1. On approval creation: `nonce = secrets.token_hex(16)` (128 bits of randomness)
2. Embedded in Telegram callback data: `"approve:a1b2c3:nonce_value"` and `"deny:a1b2c3:nonce_value"`
3. On response received:
   - Validate `approval_id` exists
   - Validate `nonce` matches stored nonce
   - Validate `nonce_used = 0`
   - Validate `expires_at > now`
   - If all pass: mark `nonce_used = 1`, update status atomically
   - If any fail: reject response, log warning

---

## Lifecycle Hooks (Future, Phase 4)

The approval lifecycle will support hooks:

```toml
[hooks]
on_approval_created = "~/.atlasbridge/hooks/on_approval_created.sh"
on_approved = "~/.atlasbridge/hooks/on_approved.sh"
on_denied = "~/.atlasbridge/hooks/on_denied.sh"
on_expired = "~/.atlasbridge/hooks/on_expired.sh"
```

Hook scripts receive the approval record as a JSON file via `$ATLASBRIDGE_APPROVAL_JSON`.

---

## Stuck Approval Recovery

`atlasbridge doctor` detects stuck approvals:
- Status = `PENDING` but `expires_at` in the past
- Status = `EXECUTING` for longer than the execution timeout (default: 10 minutes)

Doctor can auto-fix stuck approvals with `--fix`:
- Stuck `PENDING` → transition to `EXPIRED`
- Stuck `EXECUTING` → transition to `FAILED` with reason "execution timeout"

---

## Approval History Retention

Approvals are retained for 90 days by default. The daily cleanup job:

```python
async def cleanup_old_approvals(db: Database, retention_days: int = 90) -> int:
    result = await db.execute("""
        DELETE FROM approvals
        WHERE created_at < datetime('now', ?)
          AND status IN ('completed', 'failed', 'denied', 'expired')
    """, (f"-{retention_days} days",))
    return result.rowcount
```

`PENDING` and `EXECUTING` approvals are never deleted by cleanup (only by explicit decision or expiry).
