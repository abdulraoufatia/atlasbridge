# Aegis Architecture

**Version:** 0.2.0
**Status:** Implemented
**Last updated:** 2026-02-20

---

## Overview

Aegis is a remote interactive prompt relay. It runs an AI CLI tool (or any interactive CLI) inside a PTY, monitors the output stream for prompts that require human input, forwards those prompts to your phone via Telegram, and injects your reply back into the process's stdin.

It is not a firewall, policy engine, or risk classifier.

---

## System diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  Your Machine                                                    │
│                                                                  │
│  ┌─────────────┐   PTY stdout   ┌──────────────────────────┐    │
│  │ AI Agent    │──────────────► │  PTY Supervisor          │    │
│  │ (claude)    │                │                          │    │
│  │             │◄────────────── │  ┌──────────┐            │    │
│  └─────────────┘   PTY stdin    │  │ Detector │            │    │
│                    (injected)   │  └─────┬────┘            │    │
│                                 │        │ prompt detected  │    │
│  ┌─────────────┐                │  ┌─────▼────┐            │    │
│  │ Your        │                │  │ Telegram │            │    │
│  │ Terminal    │◄── forwarded ──│  │   Bot    │            │    │
│  │             │    output      │  └─────┬────┘            │    │
│  └─────────────┘                │        │ response queue  │    │
│                                 │  ┌─────▼────┐            │    │
│                                 │  │ Injector │            │    │
│                                 │  └──────────┘            │    │
│                                 └──────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
           │                                         ▲
           │ Telegram (HTTPS, long poll)              │
           ▼                                         │
    ┌──────────────┐                          ┌──────────────┐
    │ Telegram API │                          │  Your Phone  │
    │  (servers)   │─────────────────────────►│  (Telegram)  │
    └──────────────┘                          └──────────────┘
```

---

## Core event loop

`aegis run <tool>` starts a single asyncio event loop with four concurrent tasks:

```
┌─────────────────────────────────────────────────┐
│  asyncio event loop                             │
│                                                 │
│  pty_reader ──► PromptDetector ──► send_prompt  │
│  stdin_relay ──► PTY stdin                      │
│  stall_watchdog ──► detect_blocking             │
│  response_consumer ──► inject into PTY stdin    │
└─────────────────────────────────────────────────┘
```

### pty_reader

- Reads from the PTY master fd using `select.select` (non-blocking, 50ms poll)
- Forwards every byte to the host terminal unchanged
- Accumulates a 4096-byte rolling output buffer
- Feeds the buffer to `PromptDetector` after each chunk

### stdin_relay

- Reads from host stdin and writes to PTY master
- Paused while Aegis is injecting a response

### stall_watchdog

- Fires if the child produces no output for `stuck_timeout_seconds` (default 2.0)
- Triggers the blocking heuristic (confidence 0.60)
- Only fires if no pattern-based detection already occurred

### response_consumer

- Blocks on `asyncio.Queue[tuple[str, str]]` (prompt_id, normalized_value)
- When a response arrives, writes the appropriate bytes to PTY stdin
- Updates the DB record and audit log

---

## Prompt detection

### Layer 1 — Structured events (confidence 1.0)

If the tool emits machine-readable events indicating it is awaiting input, the adapter can call `detect_structured()` directly. Not yet implemented for any tool; reserved as an extension point.

### Layer 2 — Regex patterns (confidence 0.65–0.95)

`PromptDetector` matches the rolling output buffer against pattern sets for each prompt type:

| Type | Example patterns |
|------|-----------------|
| `TYPE_YES_NO` | `(y/n)`, `[Y/N]`, `(yes/no)`, `Press y to...` |
| `TYPE_CONFIRM_ENTER` | `Press Enter to continue`, `[Press Enter]` |
| `TYPE_MULTIPLE_CHOICE` | Numbered list `1) ... 2) ...`, `Enter choice [1-4]` |
| `TYPE_FREE_TEXT` | `Enter your name:`, `Password:`, `API key:` |

Confidence increases slightly when multiple patterns match.

### Layer 3 — Blocking heuristic (confidence 0.60)

If the process produces no output for `stuck_timeout_seconds` and the buffer ends with a non-empty line, Aegis treats it as an unknown prompt type and forwards it.

---

## Telegram channel

### Sending prompts

Each detected prompt results in a Telegram message with an inline keyboard. Button callback data encodes `ans:<prompt_id>:<nonce>:<value>`.

### Receiving replies

The bot long-polls `getUpdates` (30s timeout). On `callback_query`, it parses the callback data, looks up the prompt in SQLite, and calls `decide_prompt()`.

### Idempotency

`decide_prompt()` is an atomic SQL update:

```sql
UPDATE prompts
SET status = :status, ...
WHERE id = :id
  AND status IN ('awaiting_response', 'telegram_sent')
  AND nonce = :nonce
  AND nonce_used = 0
  AND expires_at > :now
```

Replayed callbacks or duplicate taps produce 0 rows affected and are ignored.

### Free-text replies

For `TYPE_FREE_TEXT` prompts, the Telegram message instructs the user to reply to the message. The bot detects `reply_to_message` and routes it to the right prompt.

---

## Persistence

### SQLite (`~/.aegis/aegis.db`)

Three tables:

- `sessions` — one row per `aegis run` invocation
- `prompts` — one row per detected prompt; nonce + expiry guard prevents replays
- `audit_events` — append-only; used for the audit log replica (see below)

WAL mode is enabled for concurrent reads during long-poll.

### Audit log (`~/.aegis/audit.log`)

JSON Lines file. Each entry includes a SHA-256 hash of the previous entry, forming a tamper-evident chain. `aegis audit verify` checks the chain.

---

## Module layout

```
aegis/
├── cli/
│   └── main.py              — all Click commands
├── core/
│   ├── config.py            — Pydantic AegisConfig, load/save
│   ├── constants.py         — enums, defaults, inject bytes
│   └── exceptions.py        — exception hierarchy
├── policy/
│   ├── detector.py          — PromptDetector (3-layer)
│   └── engine.py            — routing decision
├── bridge/
│   └── pty_supervisor.py    — PTY lifecycle, detection loop, injection
├── store/
│   ├── models.py            — Session, PromptRecord, AuditEvent
│   └── database.py          — SQLite wrapper + repositories
├── audit/
│   └── writer.py            — AuditWriter, verify_chain
└── channels/
    ├── base.py              — BaseChannel ABC
    └── telegram/
        ├── bot.py           — TelegramBot (long poll, callback handler)
        └── templates.py     — message formatters, keyboard builders
```

---

## Tech stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| PTY | `ptyprocess` | macOS/Linux PTY with resize support |
| HTTP | `httpx` async | Telegram long polling |
| Config | `pydantic` v2 + TOML | Typed, validated, file-backed |
| Persistence | `sqlite3` stdlib | No ORM overhead; WAL for safety |
| CLI | `click` | Composable, testable |
| Terminal UI | `rich` | Status tables, spinner |
| Async | `asyncio` | Single event loop; no threads needed |
| Logging | stdlib `logging` | Simple; `structlog` optional for JSON |

---

## Roadmap

- **Linux** — PTY code is portable; needs CI testing on Linux
- **WhatsApp / Slack** — implement `BaseChannel`; no core changes needed
- **`aegis wrap` alias** — transparent passthrough: `claude` → `aegis run claude`
- **GUI notifications** — out of scope for v0.x
