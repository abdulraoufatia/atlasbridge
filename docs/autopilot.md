# Autopilot Engine — Design Document

**Project:** AtlasBridge
**Status:** Design (pre-implementation)
**Target version:** v0.6.0
**Date:** 2026-02-21

---

## Overview

The Autopilot Engine is an optional subsystem that sits between the `PromptDetector` and the `PromptRouter`. When enabled, it evaluates every `PromptEvent` against a Policy DSL and decides whether to auto-reply on the user's behalf, escalate to the human, deny the action, or send a notification without acting.

The Autopilot Engine does not replace the relay. It is an additional decision layer that short-circuits the human-in-the-loop path when policy permits it.

---

## Architecture

### Component diagram

```
                         atlasbridge run claude
                               │
                               ▼
                         DaemonManager
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
     ClaudeCodeAdapter   TelegramChannel    SQLiteStore
              │
              ▼
       PromptDetector
       (tri-signal)
              │
              │  PromptEvent
              ▼
      ┌───────────────┐
      │ AutopilotEngine│   ◄─── PolicyLoader (TOML DSL)
      │               │
      │  ┌──────────┐ │
      │  │ Ingestion│ │   ◄─── event queue (asyncio.Queue)
      │  └────┬─────┘ │
      │       │       │
      │  ┌────▼─────┐ │
      │  │ Evaluator│ │   ◄─── compiled policy rules
      │  └────┬─────┘ │
      │       │       │
      │  ┌────▼─────┐ │
      │  │ Executor │ │   ◄─── action: auto_reply | require_human | deny | notify_only
      │  └────┬─────┘ │
      │       │       │
      │  ┌────▼─────┐ │
      │  │  Tracer  │ │   ──►  ~/.atlasbridge/autopilot_decisions.jsonl
      │  └──────────┘ │
      └───────┬───────┘
              │
       ┌──────┴───────┐
       │              │
       ▼              ▼
  inject_reply   PromptRouter
  (direct PTY)   (→ Telegram/Slack)
```

### Component responsibilities

| Component | Responsibility |
|-----------|---------------|
| `AutopilotEngine` | Top-level coordinator; owns the async event loop task |
| `PolicyLoader` | Reads, parses, and compiles TOML policy rules at startup and on SIGHUP |
| `PolicyEvaluator` | Matches a `PromptEvent` against compiled rules; returns `PolicyDecision` |
| `ActionExecutor` | Executes the decided action: injects reply or delegates to `PromptRouter` |
| `DecisionTracer` | Appends every `PolicyDecision` to the JSONL trace file |
| `KillSwitch` | Manages engine state (RUNNING / PAUSED / STOPPED) and persists it |
| `PromptQueue` | Bounded per-session queue of pending `PromptEvent` objects |

---

## Event flow

```
PromptEvent arrives from PromptDetector
        │
        ▼
AutopilotEngine.ingest(event)
        │
        ├─ KillSwitch.state == PAUSED?
        │       │
        │       YES ──► escalate_to_human(reason="kill_switch_paused")
        │
        ├─ KillSwitch.state == STOPPED?
        │       │
        │       YES ──► drop event, log warning
        │
        ▼
PolicyEvaluator.evaluate(event)
        │
        ├─ result.action == AUTO_REPLY
        │       │
        │       ├─ mode == FULL  ──► ActionExecutor.inject(event, reply_value)
        │       │                          │
        │       │                          └──► DecisionTracer.append(decision)
        │       │
        │       └─ mode == ASSIST ──► send_suggestion(event, reply_value)
        │                                  └──► wait 10s for human override
        │                                  └──► if no override: inject(event, reply_value)
        │
        ├─ result.action == REQUIRE_HUMAN
        │       │
        │       └──► PromptRouter.route_event(event)
        │                 └──► Telegram/Slack message to user
        │
        ├─ result.action == DENY
        │       │
        │       └──► inject synthetic "n" / Ctrl-C (configurable per adapter)
        │            └──► DecisionTracer.append(decision)
        │
        └─ result.action == NOTIFY_ONLY
                │
                └──► PromptRouter.route_event(event, notify_only=True)
                     └──► message sent; no reply expected
```

---

## AutopilotEngine components

### Event ingestion

The engine runs as a dedicated `asyncio.Task` inside the `DaemonManager` run loop. The `PromptDetector` calls `engine.ingest(event)`, which places the event onto a per-session `asyncio.Queue`. Each session has its own queue with a hard cap of 64 pending prompts (configurable via `[autopilot] max_queue_depth`).

```python
async def ingest(self, event: PromptEvent) -> None:
    queue = self._session_queues.setdefault(
        event.session_id, asyncio.Queue(maxsize=64)
    )
    await queue.put(event)
```

A dedicated consumer coroutine drains each queue sequentially (one active prompt per session at a time).

### Policy evaluator

Rules are evaluated in declaration order. The first matching rule wins. If no rule matches, the default action is `require_human` (safe default).

Rule matching conditions (all must be true):

- `prompt_type`: exact match or wildcard `"*"`
- `confidence`: minimum threshold (`HIGH`, `MED`, `LOW`)
- `excerpt_pattern`: optional regex matched against `event.excerpt`
- `session_tag`: optional session label match

```toml
[[autopilot.rules]]
id          = "confirm-test-run"
description = "Auto-confirm pytest runs"
prompt_type = "TYPE_YES_NO"
confidence  = "HIGH"
excerpt_pattern = "Run \\d+ tests\\?"
action      = "auto_reply"
reply_value = "y"

[[autopilot.rules]]
id          = "deny-force-push"
description = "Always deny git push --force"
prompt_type = "TYPE_YES_NO"
confidence  = "MED"
excerpt_pattern = "force.push"
action      = "deny"
```

### Action executor

The executor translates a `PolicyDecision` into a PTY write or a channel message.

```
AUTO_REPLY  ──► adapter.inject_reply(Reply(prompt_id, value, source="autopilot"))
REQUIRE_HUMAN ► router.route_event(event)
DENY        ──► adapter.inject_reply(Reply(prompt_id, "n", source="autopilot_deny"))
NOTIFY_ONLY ──► router.route_event(event, notify_only=True)
```

All injections go through the existing `inject_reply()` path, which enforces the `decide_prompt()` atomic SQL guard. The `source` field distinguishes autopilot injections from human replies in the audit log.

### Decision trace

Every `PolicyDecision` is appended to:

```
~/.atlasbridge/autopilot_decisions.jsonl
```

Each line is a self-contained JSON object:

```json
{
  "idempotency_key": "a3f1b8c2d9e04f7a",
  "timestamp": "2026-02-21T14:23:01.004Z",
  "prompt_id": "pr_01HXYZ",
  "session_id": "se_01HABC",
  "prompt_type": "TYPE_YES_NO",
  "confidence": "HIGH",
  "excerpt": "Run 47 tests? [y/n]",
  "rule_id": "confirm-test-run",
  "action": "auto_reply",
  "reply_value": "y",
  "policy_hash": "sha256:7f3a...",
  "mode": "full",
  "kill_switch_state": "RUNNING"
}
```

The trace file is append-only. It is never truncated by the engine. Rotation is left to the operator (logrotate or manual deletion). The `atlasbridge autopilot trace` command tails the file with structured output.

---

## Integration with DaemonManager

The `AutopilotEngine` is instantiated inside `DaemonManager.__init__()` when `[autopilot] enabled = true`. It is wired into the run loop as follows:

```python
# DaemonManager.run()
async with asyncio.TaskGroup() as tg:
    tg.create_task(self.adapter.run())          # PTY supervisor
    tg.create_task(self.channel.run())          # Telegram long-poll
    tg.create_task(self.router.run())           # reply consumer
    if self.autopilot:
        tg.create_task(self.autopilot.run())   # policy engine
```

The `PromptDetector` calls `engine.ingest(event)` instead of (or before) `router.route_event(event)`. The engine either handles the event autonomously or delegates to the router.

Signal wiring:

```
SIGTERM ──► DaemonManager.shutdown()
                └──► engine.kill_switch.stop()   (drains in-flight, then exits)

SIGHUP  ──► engine.policy_loader.reload()
                └──► new rules take effect on next prompt evaluation
```

---

## Decision lifecycle

### Idempotency key

Every `PolicyDecision` carries an idempotency key derived from the policy state, the prompt, and the session:

```
idempotency_key = SHA-256(policy_hash + ":" + prompt_id + ":" + session_id)[:16]
```

Where `policy_hash` is the SHA-256 of the serialised policy TOML at load time. If the policy is reloaded (SIGHUP), the hash changes and new decisions are treated as distinct.

The key is stored in the `autopilot_decisions` SQLite table alongside the existing `prompts` table. Before executing any action, the executor checks:

```sql
SELECT 1 FROM autopilot_decisions WHERE idempotency_key = ? AND status = 'committed'
```

If found, the decision is skipped and the cached result is returned. This prevents double-injection after a crash-restart cycle.

### Restart safety

On `DaemonManager` startup, the engine reloads all prompts with `status = 'ROUTED'` or `status = 'AWAITING_REPLY'` from SQLite. For each:

1. If the prompt was previously decided (row exists in `autopilot_decisions`): skip re-evaluation, re-execute the committed action.
2. If no prior decision: re-evaluate against the current policy (which may have changed since the crash).
3. If TTL has expired: mark as `EXPIRED`; do not re-evaluate.

This ensures that a daemon restart never loses a prompt and never injects a reply twice.

---

## Kill switch

### State machine

```
               atlasbridge autopilot pause
                        │
          ┌─────────────▼─────────────┐
          │                           │
     ┌────┴──────┐             ┌──────┴────┐
     │  RUNNING  │             │  PAUSED   │
     └────┬──────┘             └──────┬────┘
          │                           │
          │   atlasbridge autopilot   │
          │   resume                  │
          └─────────────┬─────────────┘
                        │
                        │  atlasbridge autopilot stop
                        ▼
                   ┌──────────┐
                   │ STOPPED  │
                   └──────────┘
                  (no recovery; restart daemon)
```

### Transitions

| From | Trigger | To | Effect |
|------|---------|----|--------|
| RUNNING | `/pause` command or `atlasbridge autopilot pause` | PAUSED | All new prompts routed to human; in-flight auto-reply completes |
| PAUSED | `/resume` command or `atlasbridge autopilot resume` | RUNNING | Auto-reply resumes from next prompt |
| RUNNING | `/stop` command or `atlasbridge autopilot stop` | STOPPED | Engine exits; daemon continues in relay-only mode |
| PAUSED | `/stop` | STOPPED | Same as above |

### In-flight behaviour

The kill switch is checked at the top of `ingest()`, not inside `execute()`. This means:

- A kill switch transition to PAUSED takes effect on the **next prompt** to enter the engine.
- Any auto-reply already in `execute()` (i.e., the PTY write has been issued) completes normally.
- There is no rollback of an in-flight injection.

This is intentional: partial injections are worse than completed ones.

### State persistence

The kill switch state is written to:

```
~/.atlasbridge/autopilot_state.json
```

```json
{
  "state": "PAUSED",
  "changed_at": "2026-02-21T14:23:01.004Z",
  "changed_by": "telegram:/pause",
  "session_id": "se_01HABC"
}
```

On daemon restart, the state is restored from this file. If the file is absent or corrupt, the engine defaults to `RUNNING`. The state file is written atomically (write to `.tmp`, then `os.replace()`).

### Telegram/Slack commands

The kill switch is controlled via channel messages from allowlisted identities:

| Command | Action |
|---------|--------|
| `/pause` | Transition to PAUSED |
| `/resume` | Transition to RUNNING |
| `/stop` | Transition to STOPPED (daemon continues, engine exits) |
| `/status` | Reply with current state + queue depth |

These are handled by `TelegramChannel.handle_command()` before the message is checked for prompt replies.

---

## Human escalation protocol

### Trigger conditions

A prompt is escalated to the human (via `PromptRouter`) under any of the following conditions:

1. No policy rule matched the prompt (safe default: `require_human`).
2. Prompt confidence is `LOW` and no rule explicitly matches `confidence = "LOW"`.
3. A matched rule specifies `action = "require_human"`.
4. The kill switch state is `PAUSED`.
5. The active mode is `OFF` (engine not loaded; all prompts go to human).

### Escalation message template

```
⚡ AtlasBridge — Input Required
Session: {session_id[:8]}
Type: {prompt_type}
Confidence: {confidence}

{excerpt}

[Buttons: YES / NO / ENTER / Custom...]

Prompt ID: {prompt_id[:8]}
Reason: {escalation_reason}
```

Where `escalation_reason` is one of:

| Reason | Meaning |
|--------|---------|
| `no_policy_match` | No rule matched this prompt |
| `low_confidence` | Confidence below threshold; no explicit low-conf rule |
| `rule_require_human` | Matched rule action is `require_human` |
| `kill_switch_paused` | Engine is paused |
| `mode_off` | Autopilot disabled |

### Reply correlation

Telegram inline keyboard buttons carry `callback_data` structured as:

```
atlasbridge:reply:{prompt_id}:{value}
```

For example:

```
atlasbridge:reply:pr_01HXYZ:y
atlasbridge:reply:pr_01HXYZ:n
```

Text replies without buttons must include the prompt ID prefix:

```
pr_01HXYZ: yes
```

The channel strips the prefix before passing the value to `PromptRouter.deliver_reply()`.

### Idempotency of replies

Duplicate replies (same `prompt_id`, same or different `value`) are rejected by the `decide_prompt()` SQL guard:

```sql
UPDATE prompts
SET    nonce_used = 1, reply_value = ?, status = 'REPLY_RECEIVED'
WHERE  prompt_id  = ?
  AND  nonce_used = 0
  AND  expires_at > strftime('%s','now')
```

If zero rows are updated, the reply is a duplicate or the prompt has expired. The engine returns the previously committed result without re-executing.

### Decision notification (Full mode)

After a successful auto-reply in Full mode, the engine sends a non-blocking notification to the channel:

```
✓ AutoPilot: Responded {value!r} to {prompt_type} (Rule: {rule_id})
```

This notification is fire-and-forget. A send failure does not affect the injection or the decision trace. In Assist mode this notification is suppressed (the user already saw the suggestion).

---

## Queue management

### Per-session queue

Each session has exactly one `asyncio.Queue`. The queue is drained sequentially: the engine processes one prompt at a time per session. Parallel sessions are independent.

```
Session A: [prompt_1] → processing ... → [prompt_2] waiting → [prompt_3] waiting
Session B: [prompt_1] → processing ...
```

### Dequeue rules

| Action | Dequeue trigger |
|--------|----------------|
| `auto_reply` (Full) | Immediately after injection confirmed by `decide_prompt()` |
| `auto_reply` (Assist) | After 10s override window closes or human confirms |
| `require_human` | After human reply received and injected |
| `deny` | Immediately after synthetic "n" injected |
| `notify_only` | Immediately after notification sent |

### Queue overflow

If the per-session queue reaches `max_queue_depth` (default: 64), new prompts are rejected with a warning logged at `ERROR` level. This condition indicates the engine is not keeping up; the operator should investigate stuck prompts or increase `max_queue_depth`.

### Prompt expiry

Prompts have a TTL (default: 300 seconds) enforced in the `decide_prompt()` SQL guard. Queued prompts that expire before they are processed are discarded. The engine logs a warning per expired prompt. Expiry does not block the queue; the next prompt is dequeued immediately.

---

## Configuration reference

```toml
[autopilot]
enabled        = true
mode           = "full"          # "off" | "assist" | "full"
max_queue_depth = 64
trace_file     = "~/.atlasbridge/autopilot_decisions.jsonl"
state_file     = "~/.atlasbridge/autopilot_state.json"

# Assist mode override window (seconds)
assist_override_window = 10

# Notification channel (for decision notifications in Full mode)
notify_channel = "telegram"      # channel ID used in [channels] block

[[autopilot.rules]]
id              = "confirm-test-run"
description     = "Auto-confirm pytest invocations"
prompt_type     = "TYPE_YES_NO"
confidence      = "HIGH"
excerpt_pattern = "Run \\d+ tests\\?"
action          = "auto_reply"
reply_value     = "y"

[[autopilot.rules]]
id              = "deny-force-push"
description     = "Deny git force-push without review"
prompt_type     = "TYPE_YES_NO"
confidence      = "MED"
excerpt_pattern = "(?i)force.push"
action          = "deny"
```

---

## Audit log integration

All autopilot injections are written to the hash-chained audit log (`~/.atlasbridge/audit.jsonl`) with `source = "autopilot"`. This allows the audit verifier (`atlasbridge logs verify`) to distinguish autopilot injections from human replies.

Audit entries for autopilot injections include:

```json
{
  "event": "reply_injected",
  "source": "autopilot",
  "rule_id": "confirm-test-run",
  "idempotency_key": "a3f1b8c2d9e04f7a",
  "prompt_id": "pr_01HXYZ",
  "session_id": "se_01HABC",
  "reply_value": "y",
  "prev_hash": "sha256:...",
  "hash": "sha256:..."
}
```

---

## Future work

| Item | Target version |
|------|---------------|
| Policy hot-reload via SIGHUP without daemon restart | v0.6.1 |
| `atlasbridge policy test` — dry-run evaluator | v0.6.0 |
| `atlasbridge autopilot trace` — tail JSONL with structured output | v0.6.0 |
| Per-rule `max_auto_replies` rate limit | v0.7.0 |
| Slack channel kill-switch commands | v0.7.0 |
| Multi-session kill switch (pause all sessions) | v0.7.0 |
| Decision trace rotation and archival | v0.8.0 |
