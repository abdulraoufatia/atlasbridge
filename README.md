# Aegis (AegisCLI)

> **Remote interactive prompt relay for AI CLI tools.**

[![CI](https://github.com/abdulraoufatia/aegis-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/abdulraoufatia/aegis-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-0.1.0-green.svg)](CHANGELOG.md)

---

Aegis sits between you and your AI coding agent. Whenever your agent pauses and requires human input — approval, confirmation, a choice, or clarification — Aegis forwards that prompt to your phone.

You respond from your phone, from a channel such as Telegram or WhatsApp, Slack or others. Aegis relays your decision back to the CLI. Execution resumes.

No walking back to your desk. No missed prompts. You stay in control.

```
┌──────────────┐        ┌───────────────┐        ┌─────────────────┐
│  AI Agent    │──────► │     Aegis     │──────► │   Your Phone    │
│ (Claude CLI) │        │  Prompt Relay │        │   (Telegram)    │
│              │◄────── │               │◄────── │                 │
└──────────────┘        └───────────────┘        └─────────────────┘
   paused waiting           detects &                you reply
   for input                forwards prompt          from anywhere
```

---

## Table of Contents

- [How it works](#how-it-works)
- [Prompt types supported](#prompt-types-supported)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands reference](#commands-reference)
- [Configuration](#configuration)
- [Channels](#channels)
- [Implementation notes](#implementation-notes)
- [Development](#development)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## How it works

1. You run your AI CLI through Aegis: `aegis run claude`
2. Aegis wraps the process in a PTY so it behaves exactly like a normal terminal session — full colour, readline, everything.
3. While your AI agent works, Aegis monitors its output.
4. When the agent pauses and waits for your input, Aegis captures the prompt text and sends it to your phone via Telegram.
5. You reply from your phone.
6. Aegis injects your reply into the CLI's stdin. The agent continues.
7. All output streams to your local terminal in real time.

That's it. Aegis is a transparent relay. It doesn't classify operations as dangerous, block tool calls, or enforce policies. It simply keeps you in the loop when your agent needs a human answer.

---

## Prompt types supported

| Type | Example | How you reply |
|------|---------|---------------|
| Yes / No | `Overwrite existing file? (y/n)` | Tap ✅ Yes or ❌ No |
| Confirm / Enter | `Press Enter to continue` | Tap ↩️ Press Enter |
| Multiple choice | `1) Install  2) Skip  3) Abort` | Tap the option |
| Short free text | `Enter commit message:` | Reply with text (≤200 chars) |

If Aegis can't classify the prompt, it sends it anyway with Yes / No / Enter options and the raw text so you can decide.

---

## Requirements

- Python 3.11+
- macOS (Linux support planned — see [Roadmap](#roadmap))
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Your Telegram user ID (from [@userinfobot](https://t.me/userinfobot))

---

## Installation

```bash
pip install aegis-cli
```

Or from source:

```bash
git clone https://github.com/abdulraoufatia/aegis-cli.git
cd aegis-cli
pip install -e ".[dev]"
```

---

## Quick Start

### 1. Configure

```bash
aegis setup
```

You'll be prompted for your Telegram bot token and user ID. Config is saved to `~/.aegis/config.toml` (mode 0600).

### 2. Run your agent through Aegis

```bash
aegis run claude
```

This launches Claude Code inside a PTY. Everything looks and works exactly as normal. When Claude pauses for input, you get a Telegram message.

### 3. Reply from your phone

Tap a button (Yes / No / Enter / option number) or type a free-text reply. Aegis injects your answer and Claude resumes.

### 4. Verify

```bash
aegis doctor     # check config, deps, connectivity
aegis status     # show active sessions
aegis approvals  # list pending or recent prompts
```

---

## Commands reference

| Command | Description |
|---------|-------------|
| `aegis setup` | Interactive setup: Telegram token, user ID, timeout |
| `aegis run <cmd>` | Run a command under Aegis supervision |
| `aegis status` | Show active sessions |
| `aegis doctor` | Environment and config health checks |
| `aegis approvals` | List pending / recent prompts |
| `aegis logs [-f]` | View Aegis log output |
| `aegis audit verify` | Verify audit log integrity |
| `aegis install-service` | Install macOS launchd service |
| `aegis uninstall-service` | Remove macOS launchd service |

### `aegis run`

```bash
aegis run claude
aegis run -- claude --model opus
aegis run bash          # works with any interactive CLI
```

Runs the given command in a PTY. All input/output is forwarded transparently. When the process is waiting on stdin, Aegis detects this and routes the prompt to Telegram.

---

## Configuration

Config file: `~/.aegis/config.toml` (created by `aegis setup`)

```toml
[telegram]
bot_token     = "123456789:AABBccdd..."
allowed_users = [12345678]

[prompts]
timeout_seconds    = 600    # how long to wait for your reply before using the default
free_text_enabled  = false  # whether to forward open-ended text prompts to Telegram
stuck_timeout_seconds = 2.0 # seconds of silence before treating as a prompt

[logging]
level  = "INFO"
format = "text"
```

### Environment variable overrides

| Variable | Effect |
|----------|--------|
| `AEGIS_TELEGRAM_BOT_TOKEN` | Override bot token |
| `AEGIS_TELEGRAM_ALLOWED_USERS` | Override allowed user IDs (comma-separated) |
| `AEGIS_APPROVAL_TIMEOUT_SECONDS` | Override prompt timeout |
| `AEGIS_LOG_LEVEL` | Override log level |
| `AEGIS_DB_PATH` | Override SQLite database path |
| `AEGIS_CONFIG` | Override config file path |

### Timeout behaviour

If you don't reply within `timeout_seconds`, Aegis injects the **safe default** for that prompt type:

| Prompt type | Default |
|-------------|---------|
| Yes / No | `n` |
| Confirm / Enter | `↵` (Enter) |
| Multiple choice | `1` |
| Free text | *(empty string)* |

The safe default for Yes/No cannot be changed to `y`. If you don't reply, the answer is always `n`.

---

## Channels

**v0.x (now):** Telegram only — long polling, no inbound ports required, runs entirely on your machine.

**Planned:** WhatsApp, Slack, SMS. The channel interface is abstracted; adding a new channel requires implementing `BaseChannel` in `aegis/channels/`.

---

## Implementation notes

Aegis is a transparent relay, not a security product. That said, a few implementation invariants exist for correctness:

- **Allowed users** — only your configured Telegram user ID(s) can send replies.
- **Prompt binding** — a Telegram reply is only accepted if it matches an active `prompt_id` + `nonce` that is still pending and unexpired. No arbitrary message injection.
- **One-time nonce** — each prompt has a single-use nonce embedded in the Telegram callback data. Replayed callbacks are ignored.
- **No shell execution** — Aegis only injects specific reply values (`y`, `n`, `↵`, `1`–`9`, or short text) into stdin while the process is actively waiting. It cannot run arbitrary commands.
- **Light redaction** — prompt excerpts are capped at 200 characters to limit accidental exposure of secrets that might appear in terminal output.

These are correctness constraints, not a claim that Aegis is a security tool.

---

## Module layout

```
aegis/
├── cli/        — Click CLI entry point and all commands
├── core/       — Config, constants, exceptions
├── policy/     — Prompt detector (pattern matching) and routing
├── bridge/     — PTY supervisor (launch, read, inject)
├── store/      — SQLite persistence
├── audit/      — Append-only audit log with hash chain
└── channels/   — Channel abstraction + Telegram implementation
```

---

## Development

```bash
# Clone and set up
git clone https://github.com/abdulraoufatia/aegis-cli.git
cd aegis-cli
uv venv && uv pip install -e ".[dev]"
source .venv/bin/activate

# Run tests
pytest tests/ -v

# Lint
ruff check .
ruff format --check .

# Type check
mypy aegis/
```

---

## Roadmap

| Phase | Status | Notes |
|-------|--------|-------|
| macOS PTY + Telegram relay | ✅ Done | `aegis run` working |
| Multiple prompt types (Y/N, Enter, choice, free-text) | ✅ Done | All four types |
| Linux support | Planned | PTY code is portable; needs testing |
| WhatsApp channel | Planned | Requires Twilio or WA Business API |
| Slack channel | Planned | Webhook or Socket Mode |
| `aegis wrap` shell alias | Planned | Transparent passthrough without `aegis run` prefix |
| GUI notifications (macOS) | Not planned for v0.x | Out of scope |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions welcome.

---

## License

[MIT](LICENSE) — free to use, fork, and modify.
