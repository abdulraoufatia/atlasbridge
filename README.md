# AtlasBridge

> **Universal human-in-the-loop control plane for AI developer agents.**

[![CI](https://github.com/abdulraoufatia/atlasbridge/actions/workflows/ci.yml/badge.svg)](https://github.com/abdulraoufatia/atlasbridge/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/atlasbridge.svg)](https://pypi.org/project/atlasbridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

---

AtlasBridge sits between you and your AI coding agent. Whenever your agent pauses and requires human input — approval, confirmation, a choice, or clarification — AtlasBridge forwards that prompt to your phone.

You respond from your phone via Telegram or Slack. AtlasBridge relays your decision back to the CLI. Execution resumes.

No walking back to your desk. No missed prompts. You stay in control.

```
┌──────────────┐        ┌───────────────┐        ┌─────────────────┐
│  AI Agent    │──────► │  AtlasBridge  │──────► │   Your Phone    │
│ (Claude CLI) │        │  Prompt Relay │        │ (Telegram/Slack)│
│              │◄────── │               │◄────── │                 │
└──────────────┘        └───────────────┘        └─────────────────┘
   paused waiting           detects &                you reply
   for input                forwards prompt          from anywhere
```

---

## Install

```bash
pip install atlasbridge

# With Slack support:
pip install "atlasbridge[slack]"
```

Requires Python 3.11+. Works on macOS and Linux.

---

## Quick start

### Option A — Interactive TUI (v0.5.0+)

Run `atlasbridge` with no arguments in your terminal to launch the interactive control panel:

```bash
atlasbridge
```

The TUI guides you through setup, shows live status, and provides quick access to sessions, logs, and doctor checks — all in your terminal.

```
┌─ AtlasBridge ──────────────────────────────────────────────────────┐
│  AtlasBridge                                                        │
│  Human-in-the-loop control plane for AI developer agents           │
│                                                                     │
│  AtlasBridge is ready.                                              │
│    Config:           Loaded                                         │
│    Daemon:           Running                                        │
│    Channel:          telegram                                       │
│    Sessions:         2                                              │
│    Pending prompts:  0                                              │
│                                                                     │
│  [R] Run a tool      [S] Sessions                                   │
│  [L] Logs (tail)     [D] Doctor                                     │
│  [T] Start/Stop daemon                                              │
│  [Q] Quit                                                           │
│                                                                     │
│  [S] Setup  [D] Doctor  [Q] Quit                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Option B — CLI commands

### 1. Set up your channel

**Telegram** (recommended for getting started):

```bash
atlasbridge setup --channel telegram
```

You'll be prompted for your Telegram bot token (get one from [@BotFather](https://t.me/BotFather)) and your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot)).

**Slack:**

```bash
atlasbridge setup --channel slack
```

You'll need a Slack App with Socket Mode enabled, a bot token (`xoxb-*`), and an app-level token (`xapp-*`).

### 2. Run your AI agent under supervision

```bash
atlasbridge run claude
```

AtlasBridge wraps Claude Code in a PTY supervisor. When it detects a prompt waiting for input, it forwards it to your phone. Tap a button or send a reply — AtlasBridge injects your answer and the agent continues.

### 3. Check status

```bash
atlasbridge status
atlasbridge sessions
```

---

## How it works

1. `atlasbridge run claude` wraps your AI CLI in a PTY supervisor
2. The **tri-signal prompt detector** watches the output stream
3. When a prompt is detected, AtlasBridge sends it to your Telegram or Slack
4. You tap a button or send a reply on your phone
5. AtlasBridge injects your answer into the CLI's stdin
6. The agent continues

AtlasBridge is a relay, not a firewall. It does not interpret commands, score risks, or block actions. It asks you — and only you — at the exact moment the agent needs human input.

---

## Supported agents

| Agent | Command |
|-------|---------|
| Claude Code | `atlasbridge run claude` |
| OpenAI Codex CLI | `atlasbridge run openai` |
| Google Gemini CLI | `atlasbridge run gemini` |

---

## Supported channels

| Channel | Status |
|---------|--------|
| Telegram | Supported |
| Slack | Supported (`atlasbridge[slack]`) |

---

## Status

| Version | Status | Description |
|---------|--------|-------------|
| v0.1.0 | Released | Architecture, docs, and code stubs |
| v0.2.0 | Released | macOS MVP — working Telegram relay |
| v0.3.0 | Released | Linux support, systemd integration |
| **v0.4.0** | **Released** | Slack channel, MultiChannel fan-out, renamed to AtlasBridge |
| v0.5.0 | Planned | Windows (ConPTY, experimental) |

---

## Design

See the `docs/` directory:

| Document | What it covers |
|----------|---------------|
| [architecture.md](docs/architecture.md) | System diagram, component overview, sequence diagrams |
| [reliability.md](docs/reliability.md) | PTY supervisor, tri-signal detector, Prompt Lab |
| [adapters.md](docs/adapters.md) | BaseAdapter interface, Claude Code adapter |
| [channels.md](docs/channels.md) | BaseChannel interface, Telegram and Slack implementations |
| [cli-ux.md](docs/cli-ux.md) | All CLI commands, output formats, exit codes |
| [roadmap-90-days.md](docs/roadmap-90-days.md) | 6-phase roadmap |
| [qa-top-20-failure-scenarios.md](docs/qa-top-20-failure-scenarios.md) | 20 mandatory QA scenarios |
| [dev-workflow-multi-agent.md](docs/dev-workflow-multi-agent.md) | Branch model, agent roles, CI pipeline |

---

## Repository structure

```
src/atlasbridge/
  core/
    prompt/     — detector, state machine, models
    session/    — session manager and lifecycle
    routing/    — prompt router (events → channel, replies → PTY)
    store/      — SQLite database
    audit/      — append-only audit log with hash chaining
    daemon/     — daemon manager (orchestrates all subsystems)
  os/tty/       — PTY supervisors (macOS, Linux, Windows stub)
  os/systemd/   — Linux systemd user service integration
  adapters/     — CLI tool adapters (Claude Code, OpenAI CLI, Gemini CLI)
  channels/     — notification channels (Telegram, Slack, MultiChannel)
  cli/          — Click CLI entry point and subcommands
tests/
  unit/         — pure unit tests (no I/O)
  integration/  — SQLite + mocked HTTP
  prompt_lab/   — deterministic QA scenario runner
    scenarios/  — QA-001 through QA-020 scenario implementations
docs/           — design documents
```

---

## Core invariants

AtlasBridge guarantees the following regardless of channel, adapter, or concurrency:

1. **No duplicate injection** — nonce idempotency via atomic SQL guard
2. **No expired injection** — TTL enforced in the database WHERE clause
3. **No cross-session injection** — prompt_id + session_id binding checked
4. **No unauthorised injection** — allowlisted identities only
5. **No echo loops** — 500ms suppression window after every injection
6. **No lost prompts** — daemon restart reloads pending prompts from SQLite
7. **Bounded memory** — rolling 4096-byte buffer, never unbounded growth

---

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -q

# Run a Prompt Lab scenario
atlasbridge lab run partial-line-prompt

# Lint and format
ruff check . && ruff format --check .

# Type check
mypy src/atlasbridge/

# Full CI equivalent (local)
ruff check . && ruff format --check . && mypy src/atlasbridge/ && pytest tests/ --cov=atlasbridge
```

---

## Troubleshooting

**Wrong binary in PATH?**

```bash
atlasbridge version --verbose
```

This shows the exact install path, config path, Python version, and platform — useful for detecting stale installs or multiple versions.

**`atlasbridge: command not found` after `pip install`**

Ensure your Python scripts directory is on PATH:

```bash
python3 -m site --user-scripts   # shows user scripts dir
# or for venv:
which atlasbridge
```

**Config not found**

```bash
atlasbridge doctor
```

Shows where AtlasBridge expects its config file. Run `atlasbridge setup` to create it.

**Upgrading from Aegis?**

AtlasBridge automatically migrates `~/.aegis/config.toml` on first run. Your tokens and settings are preserved.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions require:
- Existing tests to remain green
- New code to have unit tests
- Prompt Lab scenarios for any PTY/detection changes

---

## License

MIT — see [LICENSE](LICENSE).
