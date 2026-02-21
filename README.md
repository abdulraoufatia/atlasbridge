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

### Option A — Interactive Mode (v0.5.0+)

Run `atlasbridge` with no arguments in your terminal to launch the interactive control panel:

```bash
atlasbridge          # auto-launches TUI when stdout is a TTY
atlasbridge ui       # explicit TUI launch
```

The interactive UI guides you through setup, shows live status, and provides quick access to sessions, logs, and doctor checks — all in your terminal.

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

## Changelog

### v0.5.3 — CSS packaging hotfix

- **fix(ui):** `atlasbridge ui` no longer crashes with `StylesheetError` when installed from a wheel
- Root cause: `.tcss` files were not included in the package distribution, and CSS was loaded via filesystem path instead of `importlib.resources`
- Both `ui/app.py` and `tui/app.py` now load CSS via `importlib.resources` (works in editable and wheel installs)
- Added `[tool.setuptools.package-data]` for `*.tcss` inclusion
- Added `__init__.py` to `ui/css/` so `importlib.resources` can locate assets
- `atlasbridge doctor` now checks that UI assets are loadable
- 4 new regression tests for CSS resource loading

### v0.5.2 — Production UI skeleton

- New `atlasbridge.ui` package: 6 screens with exact widget IDs, `StatusCards` component, `polling.py` (`poll_state()`), and full TCSS
- `atlasbridge` / `atlasbridge ui` now launch the production UI skeleton (separate from the original `tui/` package, which is preserved for compatibility)
- WelcomeScreen shows live status cards when configured (Config / Daemon / Channel / Sessions)
- SetupWizardScreen navigates to a dedicated `SetupCompleteScreen` on finish
- 12 new smoke tests; 285 total

### v0.5.1 — Branding fix + lab import fix

- All CLI output now shows "AtlasBridge" — `doctor`, `status`, `setup`, `daemon`, `sessions`, `run`, and `lab` were still printing "Aegis" / "aegis"
- `atlasbridge lab list/run` no longer crashes with `ModuleNotFoundError` when installed from PyPI; now shows a clear message pointing to editable install

### v0.5.0 — Interactive Terminal UI

- **`atlasbridge` (no args)** — launches the built-in TUI when run in an interactive terminal; prints help otherwise
- **`atlasbridge ui`** — explicit TUI launch command
- **Welcome screen** — shows live status (daemon, channel, sessions) when configured; onboarding copy when not
- **Setup Wizard** — 4-step guided flow: choose channel → enter credentials (masked) → allowlist user IDs → confirm and save
- **Doctor screen** — environment health checks with ✓/⚠/✗ icons, re-runnable with `R`
- **Sessions screen** — DataTable of active and recent sessions
- **Logs screen** — tail of the hash-chained audit log (last 100 events)
- **Bug fix** — `channel_summary` now returns `"none"` when channels exist but none are configured
- 74 new unit tests; 273 total

### v0.4.0 — Slack + AtlasBridge rename

- Full Slack channel implementation (Web API + Socket Mode + Block Kit buttons)
- MultiChannel fan-out — broadcast to Telegram and Slack simultaneously
- Renamed from Aegis to AtlasBridge; auto-migration from `~/.aegis/` on first run
- Added `GeminiAdapter` for Google Gemini CLI

### v0.3.0 — Linux

- Linux PTY supervisor (same `ptyprocess` backend as macOS)
- systemd user service integration (`atlasbridge start` installs and enables the unit)
- 20 QA scenarios in the Prompt Lab

### v0.2.0 — macOS MVP

- Working end-to-end Telegram relay for Claude Code
- Tri-signal prompt detector (pattern match + TTY block inference + silence watchdog)
- Atomic SQL idempotency guard (`decide_prompt()`)
- Hash-chained audit log

### v0.1.0 — Design

- Architecture docs, code stubs, Prompt Lab simulator infrastructure

---

## Status

| Version | Status | Description |
|---------|--------|-------------|
| v0.1.0 | Released | Architecture, docs, and code stubs |
| v0.2.0 | Released | macOS MVP — working Telegram relay |
| v0.3.0 | Released | Linux support, systemd integration |
| v0.4.0 | Released | Slack channel, MultiChannel fan-out, renamed to AtlasBridge |
| v0.5.0 | Released | Interactive terminal UI — setup wizard, sessions, logs, doctor |
| v0.5.1 | Released | Branding fix (Aegis→AtlasBridge in CLI output) + lab import fix |
| **v0.5.2** | **Released** | Production UI skeleton — 6 screens, StatusCards, polling, TCSS |
| v0.6.0 | Planned | Windows (ConPTY, experimental) |

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
