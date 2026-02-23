# AtlasBridge

> **v1.0 — Local Governance Runtime for AI CLI Agents**

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

# Upgrade to latest version:
pip install --upgrade atlasbridge
```

Requires Python 3.11+. Works on macOS and Linux.

---

## Quick Start — Fastest Path (Telegram)

### 1. Install

```bash
pip install atlasbridge
```

### 2. Set up Telegram

```bash
atlasbridge setup --channel telegram
```

You'll be prompted for:
- **Bot token** — get one from [@BotFather](https://t.me/BotFather)
- **Your user ID** — get it from [@userinfobot](https://t.me/userinfobot)

### 3. Start the bot chat

**Open Telegram, find your bot, and send `/start`.**
This is required — Telegram bots cannot message you until you initiate the conversation.

### 4. Verify setup

```bash
atlasbridge doctor
```

Confirms config is loaded, channel is reachable, and your bot can send you messages.

### 5. Run your AI agent

```bash
atlasbridge run claude
```

AtlasBridge wraps Claude Code in a PTY supervisor. When it detects a prompt waiting for input, it forwards the prompt to your phone. You reply from Telegram. AtlasBridge injects your answer into the CLI. Execution resumes.

### 6. Enable autopilot (optional)

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

See [Policy Authoring Guide](docs/policy-authoring.md) for patterns and debugging.

### Alternative setup paths

**Interactive TUI** — run `atlasbridge` or `atlasbridge ui` to launch the terminal UI with guided setup, live status, sessions, logs, and doctor checks.

**Slack** — `atlasbridge setup --channel slack` (requires `pip install "atlasbridge[slack]"`). You'll need a Slack App with Socket Mode, a bot token (`xoxb-*`), and an app-level token (`xapp-*`).

**Non-interactive (CI/Docker):**

```bash
export ATLASBRIDGE_TELEGRAM_BOT_TOKEN="your-token"
export ATLASBRIDGE_TELEGRAM_ALLOWED_USERS="your-user-id"
atlasbridge setup --from-env
```

See [Non-Interactive Setup Guide](docs/setup-noninteractive.md) and [Channel Token Setup Guide](docs/channel-token-setup.md).

### Useful commands

```bash
atlasbridge status                   # daemon + channel status
atlasbridge sessions                 # active and recent sessions
atlasbridge autopilot status         # autopilot state + recent decisions
atlasbridge autopilot explain        # last 20 decisions with explanations
atlasbridge pause                    # pause autopilot — all prompts go to you
atlasbridge resume                   # re-enable autopilot
```

You can also send `/pause` or `/resume` from Telegram or Slack.

---

## Using AtlasBridge as an autonomous runtime

### Running an agent under supervision

```bash
atlasbridge run claude          # wraps Claude Code in a PTY supervisor
atlasbridge run openai          # OpenAI Codex CLI
atlasbridge run gemini          # Google Gemini CLI
atlasbridge run custom -- cmd   # any interactive CLI
```

When the supervised agent pauses for input, AtlasBridge detects the prompt and forwards it to your phone via Telegram or Slack. The message includes the prompt text, session context, and expiry countdown.

**Telegram:** Yes/No and confirmation prompts show inline buttons (`[Yes]` `[No]`, `[Send Enter]`). Multiple-choice prompts show numbered buttons. Free-text prompts accept any reply message.

**Slack:** Prompts appear as Block Kit messages with buttons for structured responses and a text input for free-form replies.

Your reply is injected into the CLI's stdin. Execution resumes.

### Autopilot operating loop

Autopilot lets policy rules handle prompts automatically instead of routing every one to your phone.

```bash
atlasbridge autopilot enable              # start the autopilot engine
atlasbridge autopilot mode off            # all prompts → human (no automation)
atlasbridge autopilot mode assist         # policy suggests replies; you confirm or override
atlasbridge autopilot mode full           # policy auto-replies when a rule matches; no-match → human
atlasbridge autopilot disable             # stop the autopilot engine
```

- **Off** — every prompt goes to your phone. Use this when you want full control.
- **Assist** — the policy evaluates each prompt and suggests a reply. You confirm or override from your phone within the TTL window.
- **Full** — matching prompts are auto-handled. Prompts with no matching rule, low confidence, or an explicit `require_human` action are escalated to your phone.

In all modes, the `defaults.no_match` and `defaults.low_confidence` settings in your policy file control what happens when no rule matches. The safe default is `require_human`.

### Observability

```bash
atlasbridge autopilot status              # current state, active policy, autonomy mode
atlasbridge autopilot explain             # last 20 decisions with rule, action, confidence
atlasbridge autopilot explain -n 50       # last 50 decisions
atlasbridge autopilot explain --json      # raw JSONL output for scripting
```

Every autopilot decision is recorded in a hash-chained decision trace (`autopilot_decisions.jsonl` in your config directory). Every prompt lifecycle event is recorded in the SQLite audit log (`atlasbridge.db`).

Run `atlasbridge doctor` to see your config directory path.

### Safe rollout guidance

1. **Start with Off.** Run `atlasbridge autopilot mode off` and operate purely via your phone. Get comfortable with the prompt relay.
2. **Move to Assist.** Write a minimal policy (see `config/policies/minimal.yaml`) and switch to `atlasbridge autopilot mode assist`. Review suggestions before confirming.
3. **Graduate to Full.** Once your policy handles common prompts correctly, switch to `atlasbridge autopilot mode full`. Keep `defaults.no_match: require_human` so unexpected prompts still reach you.

Always validate and test your policy before going live:

```bash
atlasbridge policy validate policy.yaml
atlasbridge policy test policy.yaml --prompt "Continue? [y/n]" --type yes_no --explain
```

### Next steps

- [Policy Authoring Guide](docs/policy-authoring.md) — write your first policy, patterns, debugging
- [Policy DSL Reference](docs/policy-dsl.md) — full schema, match fields, action types
- [Autopilot Engine](docs/autopilot.md) — engine architecture, decision trace, kill switch
- [Troubleshooting](docs/troubleshooting.md) — common issues and solutions
- [Full Documentation Index](docs/README.md) — all docs organized by audience

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

## Supported Agents

| Agent | Command | Notes |
|-------|---------|-------|
| Claude Code | `atlasbridge run claude-code` | `claude` is an alias |
| OpenAI Codex CLI | `atlasbridge run openai` | |
| Google Gemini CLI | `atlasbridge run gemini` | |
| Any interactive CLI | `atlasbridge run custom -- <cmd>` | Generic PTY wrapper |

Run `atlasbridge adapters` to see all registered adapters and their status.

---

## Supported Channels

| Channel | Install | Status |
|---------|---------|--------|
| Telegram | `pip install atlasbridge` | Stable |
| Slack | `pip install "atlasbridge[slack]"` | Stable |

> **Not getting Telegram notifications?** Make sure you sent `/start` to your bot in Telegram. Bots cannot message you until you initiate the conversation. Also check that notifications are unmuted for the bot chat in your Telegram app settings.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history, or [GitHub Releases](https://github.com/abdulraoufatia/atlasbridge/releases) for release notes and assets.

---

## Enterprise Governance (Experimental)

AtlasBridge follows an **open-core** model:

- **Community** (public, MIT) — policy engine, PTY supervisor, prompt detection, channel relay, audit log, hash-chained decision trace. Fully functional. Always free.
- **Pro** (public, MIT) — deterministic risk classifier, decision trace v2, policy pinning, RBAC. Phase A — local governance, shipping now.
- **Enterprise** (private, future) — SaaS backend, multi-tenant policy management, web dashboard. Phase B is scaffolding only; Phase C is design only.

| Feature | Edition | Maturity |
|---------|---------|----------|
| Policy DSL v1 | Community | Stable |
| Autopilot engine | Community | Stable |
| Hash-chained decision trace | Community | Stable |
| Hash-chained audit log | Community | Stable |
| Deterministic risk classifier | Pro | Experimental |
| Policy pinning (session-level) | Pro | Experimental |
| RBAC (local) | Pro | Experimental |
| Cloud policy sync | Enterprise | Specification |
| Web dashboard | Enterprise | Design only |

**Key principles:**

- **Execution stays local.** The AI CLI agent always runs on your machine. Cloud features observe; they never execute.
- **Deterministic, not heuristic.** Risk classification uses a fixed decision table. No ML. No guesswork.
- **Offline-first.** The runtime works without any cloud connection. Cloud features degrade gracefully.

```bash
atlasbridge edition       # Show current edition (community/pro/enterprise)
atlasbridge features      # List all feature flags
atlasbridge cloud status  # Cloud integration status (Phase B: scaffolding only)
```

See [Enterprise Architecture](docs/enterprise-architecture.md) and [Enterprise Roadmap](docs/roadmap-enterprise-90-days.md).

---

## Versioning and Support

AtlasBridge follows [Semantic Versioning](https://semver.org/). All 8 contract surfaces (Adapter API, Channel API, Policy DSL, CLI, Dashboard, Console, Audit, Config) are frozen and enforced by safety tests in CI. See [versioning-policy.md](docs/versioning-policy.md).

**Invariants** — these hold at all times:
- **Cloud OBSERVES, local EXECUTES** — all execution happens on your machine
- No remote execution control
- Read-only dashboard (localhost-only by default)
- Deterministic policy evaluation before every injection
- Append-only, hash-chained audit log

> **Future roadmap** includes SaaS, multi-tenant, authentication, cloud control, enterprise SSO — but v1.0 is strictly local-first. See [saas-alpha-roadmap.md](docs/saas-alpha-roadmap.md).

## Status

See [CHANGELOG.md](CHANGELOG.md) for full version history.

| Milestone | Status | Highlights |
|-----------|--------|------------|
| v0.1–v0.3 | Released | Architecture, macOS MVP, Linux + systemd |
| v0.4 | Released | Slack channel, MultiChannel, renamed to AtlasBridge |
| v0.5 | Released | Interactive terminal UI, setup wizard, doctor |
| v0.6 | Released | Policy DSL v0, autopilot engine, kill switch |
| v0.7.x | Released | Per-rule rate limits, hot-reload, adapter auto-registration |
| v0.8.x | Released | Zero-touch setup, Policy DSL v1, enterprise scaffolding |
| v0.9.0 | Released | Contract freeze — 8 frozen surfaces, 155 safety tests |
| v0.9.1–v0.9.3 | Released | Local dashboard MVP, hardening, remote-ready UX |
| v0.9.4 | Released | Platform automation — CI hardening, release pipeline |
| v0.9.5 | Released | Operator console — `atlasbridge console` process management TUI |
| v0.9.6 | Released | GA hard freeze, release pipeline, project automation, 1336 tests |
| v0.9.7 | Released | Sprint S1 — mypy strict, audit rotation, circuit breaker, cloud spec extraction |
| v0.9.8 | Released | Conversation UX v2 — interaction pipeline, ML classifier protocol, session binding, output router |
| v0.9.9 | Released | Chat mode UX — per-plan escalation, folder trust detection, no more "arrow keys" messages |
| v0.10.0 | Released | Full conversational agent mode — streaming state, plan detection, secret redaction |
| v1.0.0 | Planned | GA — stable APIs, 2-week freeze window, then tag |

---

## Documentation

See [docs/README.md](docs/README.md) for the full documentation index — organized by audience (users, policy authors, contributors) with a searchable documentation map.

Key starting points:

| Document | What it covers |
|----------|---------------|
| [channel-token-setup.md](docs/channel-token-setup.md) | Step-by-step Telegram and Slack token setup |
| [policy-authoring.md](docs/policy-authoring.md) | Policy authoring guide — quick start, patterns, debugging |
| [autonomy-modes.md](docs/autonomy-modes.md) | Off / Assist / Full mode specs |
| [architecture.md](docs/architecture.md) | System design, data flow, invariants |
| [troubleshooting.md](docs/troubleshooting.md) | Common issues and solutions |
| [ethics-and-safety-guarantees.md](docs/ethics-and-safety-guarantees.md) | Safety invariants and CI enforcement |
| [enterprise-architecture.md](docs/enterprise-architecture.md) | Enterprise governance overview (Phase A) |
| [enterprise-dashboard-product-spec.md](docs/enterprise-dashboard-product-spec.md) | Phase C dashboard product spec (design only) |
| [enterprise-dashboard-ui-map.md](docs/enterprise-dashboard-ui-map.md) | Phase C dashboard UI wireframes (design only) |
| [enterprise-governance-api-spec.md](docs/enterprise-governance-api-spec.md) | Phase C governance API spec (design only) |
| [enterprise-data-model.md](docs/enterprise-data-model.md) | Phase C cloud data model (design only) |
| [enterprise-dashboard-threat-model.md](docs/enterprise-dashboard-threat-model.md) | Phase C dashboard threat model (design only) |

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
    policy/     — Policy DSL v0/v1: model, parser, evaluator, explain
    autopilot/  — AutopilotEngine, kill switch, decision trace
  os/tty/       — PTY supervisors (macOS, Linux, Windows stub)
  os/systemd/   — Linux systemd user service integration
  adapters/     — CLI tool adapters (Claude Code, OpenAI CLI, Gemini CLI)
  channels/     — notification channels (Telegram, Slack, MultiChannel)
  enterprise/   — enterprise governance (Phase A: local risk, RBAC, trace v2)
  cloud/        — cloud integration interfaces (Phase B: spec only, no implementation)
  cli/          — Click CLI entry point and subcommands
tests/
  unit/         — pure unit tests (no I/O)
  policy/       — policy model, parser, evaluator tests + fixtures
  integration/  — SQLite + mocked HTTP
  prompt_lab/   — deterministic QA scenario runner
    scenarios/  — QA-001 through QA-023 scenario implementations
  safety/       — ethics & safety invariant tests (CI-gated)
docs/           — design documents (see docs/README.md for index)
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

**Wrong binary or version?**

```bash
atlasbridge version --verbose
```

Shows the exact install path, config path, Python version, and platform.

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

**Telegram: "chat not found" or bot not sending messages**

Your bot cannot message you until you open the bot chat in Telegram and send `/start`. This is a Telegram requirement, not an AtlasBridge limitation.

**Telegram: 409 Conflict error**

Another AtlasBridge instance (or poller) is already running. Stop it first:

```bash
atlasbridge stop
```

Ensure only one instance is running at a time.

**Upgrading from Aegis?**

AtlasBridge automatically migrates `~/.aegis/config.toml` on first run. Your tokens and settings are preserved.

See [docs/troubleshooting.md](docs/troubleshooting.md) for more solutions.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions require:
- Existing tests to remain green
- New code to have unit tests
- Prompt Lab scenarios for any PTY/detection changes

---

## License

MIT — see [LICENSE](LICENSE).
