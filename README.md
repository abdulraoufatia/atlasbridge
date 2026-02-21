# AtlasBridge

> **Policy-driven autonomous runtime for AI CLI agents.**

[![CI](https://github.com/abdulraoufatia/atlasbridge/actions/workflows/ci.yml/badge.svg)](https://github.com/abdulraoufatia/atlasbridge/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/atlasbridge.svg)](https://pypi.org/project/atlasbridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

---

AtlasBridge is a deterministic, policy-governed runtime that allows AI CLI agents to operate autonomously within defined boundaries. Humans define the rules. AtlasBridge enforces them.

Instead of manually approving every prompt, AtlasBridge evaluates each decision against a strict Policy DSL and executes only what is explicitly permitted. When uncertainty, ambiguity, or high-impact actions arise, AtlasBridge escalates safely to a human.

Autonomy first. Human override when required.

---

## What AtlasBridge Is

AtlasBridge is an autonomous execution layer that sits between you and your AI developer agents.

It provides:

- Policy-driven prompt responses
- Deterministic rule evaluation
- Autonomous workflow execution (plan → execute → fix → PR → merge)
- CI-enforced merge gating
- Built-in human escalation
- Structured audit logs and decision traces

AtlasBridge is not a wrapper around a CLI tool.
It is a runtime that governs how AI agents execute.

---

## How It Works

1. An AI CLI agent emits a prompt or reaches a decision boundary.
2. AtlasBridge classifies the prompt (type + confidence).
3. The Policy DSL is evaluated deterministically.
4. If a rule matches:
   - The action is executed automatically.
5. If no rule matches or confidence is low:
   - The prompt is escalated to a human.
6. Execution resumes.

Every decision is logged, traceable, and idempotent.

---

## Autonomy Modes

AtlasBridge supports three operating modes:

### Off

All prompts are routed to a human.
No automatic decisions.

### Assist

AtlasBridge automatically handles explicitly allowed prompts.
All others are escalated.

### Full

AtlasBridge automatically executes permitted prompts and workflows.
No-match, low-confidence, or high-impact actions are escalated safely.

Full autonomy never means uncontrolled execution.
Policy always defines the boundary.

---

## Human Escalation (Built-In)

Whenever your agent pauses and requires human input — approval, confirmation, a choice, or clarification — AtlasBridge forwards that prompt to your phone.

You respond from Telegram or Slack. AtlasBridge relays your decision back to the CLI. Execution resumes.

Human intervention is always available when policy requires it.

---

## Safety by Design

AtlasBridge is built around strict invariants:

- No freestyle decisions
- No bypassing CI checks
- No merging unless all required checks pass
- No force-pushing protected branches
- Default-safe escalation on uncertainty
- Append-only audit log for every decision

Autonomy is powerful — but bounded, deterministic, and reviewable.

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

> **Need help getting tokens?** See the [Channel Token Setup Guide](docs/channel-token-setup.md) for step-by-step instructions, or press **H** inside the TUI setup wizard.

### 2. Run your AI agent under supervision

```bash
atlasbridge run claude
```

AtlasBridge wraps Claude Code in a PTY supervisor. When it detects a prompt waiting for input, it either forwards it to your phone or handles it per your policy. Tap a button, send a reply, or let autopilot take care of it.

### 3. Enable autopilot (optional)

Create a policy file to tell AtlasBridge which prompts to handle automatically:

```yaml
# ~/.atlasbridge/policy.yaml
policy_version: "0"
name: my-policy
autonomy_mode: full

rules:
  - id: auto-approve-yes-no
    description: Auto-reply 'y' to yes/no prompts
    match:
      prompt_type: [yes_no]
      min_confidence: medium
    action:
      type: auto_reply
      value: "y"

  - id: auto-confirm-enter
    description: Auto-press Enter on confirmation prompts
    match:
      prompt_type: [confirm_enter]
    action:
      type: auto_reply
      value: "\n"

defaults:
  no_match: require_human
  low_confidence: require_human
```

Then enable it:

```bash
atlasbridge autopilot enable
atlasbridge autopilot mode full      # or: assist, off
```

Validate and test your policy before going live:

```bash
atlasbridge policy validate policy.yaml
atlasbridge policy test policy.yaml --prompt "Continue? [y/n]" --type yes_no --explain
```

### 4. Check status

```bash
atlasbridge status                   # daemon + channel status
atlasbridge sessions                 # active and recent sessions
atlasbridge autopilot status         # autopilot state + recent decisions
atlasbridge autopilot explain        # last 20 decisions with explanations
```

### 5. Pause and resume

Instantly pause autopilot and route all prompts to your phone:

```bash
atlasbridge pause                    # from your terminal
atlasbridge resume                   # re-enable autopilot
```

You can also send `/pause` or `/resume` from Telegram or Slack.

---

## How it works

1. `atlasbridge run claude` wraps your AI CLI in a PTY supervisor
2. The **tri-signal prompt detector** watches the output stream
3. When a prompt is detected:
   - **Autopilot off** — prompt is forwarded to Telegram/Slack; you reply from your phone
   - **Autopilot assist** — policy suggests a reply; you confirm or override from your phone
   - **Autopilot full** — policy auto-replies if a rule matches; unmatched prompts escalate to your phone
4. AtlasBridge injects the answer (yours or the policy's) into the CLI's stdin
5. Every decision is recorded in an append-only audit log

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

### v0.6.1 — Policy Authoring Documentation

- **New**: [`docs/policy-authoring.md`](docs/policy-authoring.md) — 10-section guide: quick start (5 min), core concepts, syntax reference, CLI usage, 8 authoring patterns, debugging, FAQ, and safety notes
- **New**: `config/policies/` — 5 ready-to-use policy presets (`minimal`, `assist-mode`, `full-mode-safe`, `pr-remediation-dependabot`, `escalation-only`)
- **Updated**: `docs/policy-dsl.md` — status updated to Implemented (v0.6.0+)

### v0.6.0 — Autonomous Agent Runtime (Policy-Driven)

- **Policy DSL v0** — YAML-based, strictly typed, first-match-wins rule engine; `atlasbridge policy validate` and `atlasbridge policy test --explain`
- **Autopilot Engine** — policy-driven prompt handler with three autonomy modes: Off / Assist / Full
- **Kill switch** — `atlasbridge pause` / `atlasbridge resume` (or `/pause`, `/resume` from Telegram/Slack)
- **Decision trace** — append-only JSONL audit log at `~/.atlasbridge/autopilot_decisions.jsonl`
- **Autopilot CLI** — `atlasbridge autopilot enable|disable|status|mode|explain`
- **56 new tests** (policy model, parser, evaluator, decision trace); 341 total
- New design docs: `docs/autopilot.md`, `docs/policy-dsl.md`, `docs/autonomy-modes.md`

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
| v0.5.2 | Released | Production UI skeleton — 6 screens, StatusCards, polling, TCSS |
| v0.6.0 | Released | Autonomous Agent Runtime — Policy DSL v0, autopilot engine, kill switch |
| **v0.6.1** | **Released** | Policy authoring guide, 5 policy presets, docs/policy-authoring.md |
| v0.7.0 | Planned | Windows (ConPTY, experimental) |

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
| [autopilot.md](docs/autopilot.md) | Autopilot engine architecture, kill switch, escalation protocol |
| [policy-authoring.md](docs/policy-authoring.md) | Policy authoring guide — quick start, patterns, debugging, FAQ |
| [policy-dsl.md](docs/policy-dsl.md) | AtlasBridge Policy DSL v0 full reference |
| [autonomy-modes.md](docs/autonomy-modes.md) | Off / Assist / Full mode specs and behavior |
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
    policy/     — Policy DSL v0: model, parser, evaluator, explain
    autopilot/  — AutopilotEngine, kill switch, decision trace
  os/tty/       — PTY supervisors (macOS, Linux, Windows stub)
  os/systemd/   — Linux systemd user service integration
  adapters/     — CLI tool adapters (Claude Code, OpenAI CLI, Gemini CLI)
  channels/     — notification channels (Telegram, Slack, MultiChannel)
  cli/          — Click CLI entry point and subcommands
tests/
  unit/         — pure unit tests (no I/O)
  policy/       — policy model, parser, evaluator tests + fixtures
  integration/  — SQLite + mocked HTTP
  prompt_lab/   — deterministic QA scenario runner
    scenarios/  — QA-001 through QA-020 scenario implementations
docs/           — design documents
config/
  policy.example.yaml     — annotated full-featured example policy
  policy.schema.json      — JSON Schema for IDE validation
  policies/               — ready-to-use policy presets
    minimal.yaml          — safe start: only Enter confirmations auto-handled
    assist-mode.yaml      — assist mode with common automation rules
    full-mode-safe.yaml   — full mode with deny guards for dangerous operations
    pr-remediation-dependabot.yaml  — auto-approve Dependabot PR prompts
    escalation-only.yaml  — all prompts routed to human (no automation)
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
