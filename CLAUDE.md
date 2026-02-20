# CLAUDE.md — Aegis Project Context

This file is read by Claude Code automatically. It provides project context for working on this codebase.

---

## What Aegis is

Aegis is a **remote interactive prompt relay** for AI CLI tools.

When an AI agent (e.g. Claude Code) pauses and waits for user input, Aegis:
1. Detects the pause and captures the prompt text
2. Forwards it to your phone via Telegram
3. Receives your reply
4. Injects your reply into the CLI's stdin
5. The agent resumes

That's the entire product. It is NOT a security tool, firewall, policy engine, or risk classifier.

---

## What Aegis is NOT

- Not a security product
- Not a CLI firewall
- Not an operation risk classifier
- Not a "dangerous command" gatekeeper
- Not a cloud service

---

## Minimal invariants (correctness, not security posture)

These exist to keep the relay working correctly:

- Only configured Telegram user IDs can send replies (prevents random people from controlling your session)
- Replies are bound to an active `prompt_id` + `nonce` (prevents stale/duplicate injections)
- Nonces are single-use (prevents replay of callbacks)
- No arbitrary shell execution from Telegram (only stdin injection while process is waiting)
- Prompt excerpts capped at 200 chars (limits exposure of long outputs)

Do NOT frame these as "security features" in docs or code comments. They are correctness invariants.

---

## Architecture summary

```
aegis run claude
    │
    ▼
PTYSupervisor          ← spawns process in PTY, raw terminal mode
    │
    ├── pty_reader     ← reads output, feeds PromptDetector
    ├── stdin_relay    ← forwards host stdin → child PTY
    ├── stall_watchdog ← fires blocking heuristic after N seconds of silence
    └── response_consumer ← dequeues Telegram replies, injects into PTY
          ▲
          │
    TelegramBot         ← long-polls getUpdates, handles callbacks + replies
          │
    asyncio.Queue       ← (prompt_id, normalized_value)
```

**Prompt detection layers:**
1. Structured JSON from tool (confidence 1.0) — future extension point
2. Regex pattern matching on terminal output (confidence 0.65–0.95)
3. Blocking heuristic: no output for N seconds (confidence 0.60)

---

## Key files

| Path | Purpose |
|------|---------|
| `aegis/cli/main.py` | All CLI commands |
| `aegis/bridge/pty_supervisor.py` | PTY launch, detection, injection loop |
| `aegis/channels/telegram/bot.py` | Telegram long-poll bot |
| `aegis/channels/telegram/templates.py` | Message formatters, keyboard builders |
| `aegis/policy/detector.py` | Prompt type classifier (regex patterns) |
| `aegis/policy/engine.py` | Routing decision (route to user vs auto-inject) |
| `aegis/store/database.py` | SQLite WAL wrapper + repositories |
| `aegis/audit/writer.py` | Append-only hash-chained audit log |
| `aegis/core/config.py` | Pydantic config, load/save, env overrides |

---

## Dev commands

```bash
# Install
uv venv && uv pip install -e ".[dev]"

# Test
pytest tests/ -v

# Lint
ruff check . && ruff format --check .

# Type check
mypy aegis/
```

---

## Branching

- `main` — stable, tagged releases
- `feature/mvp-core-implementation` — current active development branch
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`

---

## Current scope (v0.x)

- macOS only (PTY + launchd)
- Telegram channel only
- Four prompt types: YES_NO, CONFIRM_ENTER, MULTIPLE_CHOICE, FREE_TEXT

## Future direction

- Linux support
- WhatsApp / Slack channels (BaseChannel is already abstracted)
- `aegis wrap` passthrough alias
