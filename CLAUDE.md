# CLAUDE.md — AtlasBridge Project Context

This file is read by Claude Code automatically. It provides project context for working on this codebase.

---

## What AtlasBridge is

AtlasBridge is a **policy-driven autonomous runtime for AI CLI agents**.

It is a deterministic, policy-governed runtime that allows AI CLI agents to operate autonomously within defined boundaries. Humans define the rules via a YAML Policy DSL. AtlasBridge evaluates them on every prompt and executes only what is explicitly permitted. When no rule matches, confidence is low, or a rule says `require_human`, AtlasBridge escalates to a human via Telegram or Slack.

**Autonomy first. Human override when required.**

Three autonomy modes:
- **Off** — all prompts forwarded to human; no automatic decisions
- **Assist** — policy handles explicitly allowed prompts; all others escalated
- **Full** — policy auto-executes permitted prompts; no-match/low-confidence escalated safely

AtlasBridge is not a wrapper around a CLI tool. It is a runtime that governs how AI agents execute.

---

## Safety by design

AtlasBridge is built around strict invariants — not as security posture but as correctness guarantees:

- No freestyle decisions — every action must match a policy rule
- No bypassing CI checks — merge gating is enforced
- Default-safe escalation on no-match or low-confidence
- Append-only audit log for every decision

---

## Core correctness invariants

These exist to keep the relay working correctly:

1. **No duplicate injection** — nonce idempotency via atomic SQL guard (`decide_prompt()`)
2. **No expired injection** — TTL enforced in the database WHERE clause
3. **No cross-session injection** — prompt_id + session_id binding checked
4. **No unauthorised injection** — allowlisted channel identities only
5. **No echo loops** — 500ms suppression window after every injection
6. **No lost prompts** — daemon restart reloads pending prompts from SQLite
7. **Bounded memory** — rolling 4096-byte buffer, never unbounded growth

Do NOT frame these as "security features" in docs or code comments. They are correctness invariants.

---

## Repository layout

```
src/atlasbridge/         ← installed package (where = ["src"])
  core/
    prompt/              — detector.py, state.py, models.py
    session/             — models.py, manager.py
    routing/             — router.py
    store/               — database.py (SQLite WAL)
    audit/               — writer.py (hash-chained audit log)
    daemon/              — manager.py (orchestrates everything)
    scheduler/           — TTL sweeper (future)
  os/tty/                — base.py, macos.py, linux.py, windows.py
  os/systemd/            — service.py (Linux systemd user service)
  adapters/              — base.py, claude_code.py, openai_cli.py, gemini_cli.py
  channels/              — base.py, multi.py, telegram/channel.py, slack/channel.py
  tui/                   — app.py, state.py, services.py, app.tcss, screens/ (v0.5.x, preserved)
  ui/                    — app.py, state.py, polling.py, css/atlasbridge.tcss
                           components/status_cards.py
                           screens/: welcome, wizard, complete, sessions, logs, doctor
  dashboard/             — app.py, repo.py, sanitize.py, templates/, static/
  cli/                   — main.py + _setup/_daemon/_run/_status/etc.
tests/
  unit/                  — pure unit tests (no I/O)
  integration/           — SQLite + mocked HTTP
  e2e/                   — real PTY + mocked Telegram
  prompt_lab/            — deterministic QA simulator
    simulator.py         — Simulator, TelegramStub, PTYSimulator, LabScenario
    scenarios/           — QA-001 through QA-020 implementations
docs/                    — all design documents
```

---

## Key files

| Path | Purpose |
|------|---------|
| `src/atlasbridge/cli/main.py` | All CLI commands (Click group) + TUI launch |
| `src/atlasbridge/ui/app.py` | AtlasBridgeApp (Textual App + `run()` entry) — active TUI |
| `src/atlasbridge/ui/state.py` | Re-exports AppState, WizardState from tui.state |
| `src/atlasbridge/ui/polling.py` | poll_state() → AppState, POLL_INTERVAL_SECONDS=5.0 |
| `src/atlasbridge/ui/components/status_cards.py` | StatusCards widget (4-card row) |
| `src/atlasbridge/ui/css/atlasbridge.tcss` | Global TCSS for all 6 screens |
| `src/atlasbridge/tui/state.py` | AppState, WizardState — pure Python, testable without Textual |
| `src/atlasbridge/tui/services.py` | ConfigService, DoctorService, DaemonService, SessionService, LogsService |
| `src/atlasbridge/core/prompt/detector.py` | Tri-signal prompt detector |
| `src/atlasbridge/core/prompt/models.py` | PromptEvent, Reply, PromptType, Confidence |
| `src/atlasbridge/core/prompt/state.py` | PromptStateMachine, VALID_TRANSITIONS |
| `src/atlasbridge/core/routing/router.py` | PromptRouter (forward + return path) |
| `src/atlasbridge/core/session/manager.py` | SessionManager (in-memory registry) |
| `src/atlasbridge/core/store/database.py` | SQLite WAL store + decide_prompt() guard |
| `src/atlasbridge/core/audit/writer.py` | Hash-chained audit event writer |
| `src/atlasbridge/core/daemon/manager.py` | DaemonManager (top-level orchestrator) |
| `src/atlasbridge/os/tty/base.py` | BaseTTY abstract PTY supervisor |
| `src/atlasbridge/os/tty/macos.py` | MacOSTTY (ptyprocess) |
| `src/atlasbridge/os/systemd/service.py` | Linux systemd user service integration |
| `src/atlasbridge/adapters/base.py` | BaseAdapter ABC + AdapterRegistry |
| `src/atlasbridge/adapters/claude_code.py` | ClaudeCodeAdapter |
| `src/atlasbridge/channels/base.py` | BaseChannel ABC |
| `src/atlasbridge/channels/telegram/channel.py` | TelegramChannel (httpx, long-poll) |
| `src/atlasbridge/channels/slack/channel.py` | SlackChannel (Socket Mode + Block Kit) |
| `src/atlasbridge/channels/multi.py` | MultiChannel fan-out |
| `src/atlasbridge/dashboard/app.py` | FastAPI dashboard app factory + routes + `start_server()` |
| `src/atlasbridge/dashboard/repo.py` | DashboardRepo — read-only SQLite + JSONL access |
| `src/atlasbridge/dashboard/sanitize.py` | `strip_ansi()`, `redact_tokens()`, `sanitize_for_display()` |
| `src/atlasbridge/cli/_dashboard.py` | `dashboard start/status` CLI commands |
| `tests/prompt_lab/simulator.py` | Simulator, TelegramStub, PTYSimulator |

---

## Architecture: data flow

```
atlasbridge run claude
    │
    ▼
DaemonManager                  ← orchestrates all subsystems
    │
    ▼
ClaudeCodeAdapter              ← wraps `claude` in PTY supervisor
    │
    ├── pty_reader             ← reads output, calls PromptDetector.analyse()
    ├── stdin_relay            ← forwards host stdin → child PTY
    ├── stall_watchdog         ← calls PromptDetector.check_silence()
    └── response_consumer      ← dequeues Reply objects, calls inject_reply()
          ▲
          │
    PromptRouter               ← routes events → channel, routes replies → adapter
          │             │
    TelegramChannel    SQLite  ← atomic decide_prompt() idempotency guard
          │
    User's phone (Telegram)
```

**Tri-signal prompt detection:**
1. Signal 1 — Pattern match on ANSI-stripped output → HIGH confidence
2. Signal 2 — TTY blocked-on-read inference → MED confidence
3. Signal 3 — Silence threshold (stall watchdog) → LOW confidence

**Prompt state machine:**
CREATED → ROUTED → AWAITING_REPLY → REPLY_RECEIVED → INJECTED → RESOLVED
                                                              ↓
                                              EXPIRED / CANCELED / FAILED

---

## Dev commands

```bash
# Install
pip install -e ".[dev]"   # or: uv pip install -e ".[dev]"

# Run all tests
pytest tests/ -q

# Run a specific test file
pytest tests/unit/test_prompt_detector.py -v

# Launch TUI
atlasbridge         # (must be a TTY)
atlasbridge ui

# Run Prompt Lab scenarios (via CLI)
atlasbridge lab list
atlasbridge lab run partial-line-prompt
atlasbridge lab run --all

# Lint and format
ruff check . && ruff format --check .

# Type check
mypy src/atlasbridge/

# Full CI equivalent (local)
ruff check . && ruff format --check . && mypy src/atlasbridge/ && pytest tests/ --cov=atlasbridge
```

---

## CI pipeline

1. **CLI Smoke Tests** — verifies all 15 subcommands exist (gates everything)
2. **Security Scan** — bandit on `src/`
3. **Lint + Type Check** — ruff check, ruff format --check, mypy src/atlasbridge/
4. **Tests** — pytest on Python 3.11 + 3.12, macOS + ubuntu
5. **Build** — twine check

---

## Branching model

- `main` — always releasable; only tagged releases land here
- `feature/*` — feature development
- `fix/*` — bug fixes
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
- PRs squash-merge to main after CI green

---

## Config paths

| Platform | Default config directory |
|----------|--------------------------|
| macOS | `~/Library/Application Support/atlasbridge/` |
| Linux | `$XDG_CONFIG_HOME/atlasbridge/` (default `~/.config/atlasbridge/`) |
| Other | `~/.atlasbridge/` |

Override with `ATLASBRIDGE_CONFIG` env var. Legacy `AEGIS_CONFIG` is also honoured.

---

## Policy development

```bash
# Validate a policy file
atlasbridge policy validate config/policy.example.yaml

# Run policy against a simulated prompt (primary debugging tool)
atlasbridge policy test config/policy.example.yaml \
  --prompt "Continue? [y/n]" --type yes_no --confidence high --explain

# Run all policy unit tests
pytest tests/policy/ -v

# Check recent autopilot decisions
atlasbridge autopilot explain --last 20
tail -n 20 ~/.atlasbridge/autopilot_decisions.jsonl | python3 -m json.tool
```

Policy module layout:

| Path | Purpose |
|------|---------|
| `src/atlasbridge/core/policy/model.py` | Pydantic v2 models: Policy, PolicyRule, MatchCriteria, actions |
| `src/atlasbridge/core/policy/parser.py` | load_policy(), parse_policy(), validate_policy_file() |
| `src/atlasbridge/core/policy/evaluator.py` | evaluate() → PolicyDecision; first-match-wins; regex safety timeout |
| `src/atlasbridge/core/policy/explain.py` | explain_decision(), explain_policy() for --explain output |
| `src/atlasbridge/core/autopilot/engine.py` | AutopilotEngine, AutopilotState (RUNNING/PAUSED/STOPPED) |
| `src/atlasbridge/core/autopilot/trace.py` | DecisionTrace — append-only JSONL |
| `src/atlasbridge/core/autopilot/actions.py` | execute_action() dispatcher for all 4 action types |
| `src/atlasbridge/cli/_policy_cmd.py` | policy validate / policy test commands |
| `src/atlasbridge/cli/_autopilot.py` | autopilot enable/disable/status/mode/explain commands |
| `tests/policy/fixtures/` | YAML policy fixtures for unit tests |
| `config/policy.example.yaml` | Annotated full-featured example (10 rules) |
| `config/policies/` | Ready-to-use policy presets (5 files) |
| `docs/policy-authoring.md` | Authoring guide — quick start, patterns, debugging, FAQ |
| `docs/policy-dsl.md` | Full DSL reference — schema, evaluation semantics, idempotency |

---

## Roadmap

| Version | Target | Status | Key deliverable |
|---------|--------|--------|----------------|
| v0.1.0 | Design | Released | Architecture docs + code stubs |
| v0.2.0 | macOS  | Released | Working Telegram relay for Claude Code |
| v0.3.0 | Linux  | Released | Linux PTY, systemd integration |
| v0.4.0 | Slack  | Released | Slack channel, multi-channel routing, renamed to AtlasBridge |
| v0.5.0 | TUI    | Released | Interactive Textual TUI — setup wizard, sessions, logs, doctor |
| v0.6.0 | Autopilot | Released | Policy DSL v0, autopilot engine, kill switch, decision trace |
| v0.6.1 | Docs | Released | Policy authoring guide + 5 preset policies |
| v0.6.2 | Positioning | Released | Product tagline, pyproject.toml description/keywords |
| v0.7.1 | Hardening | Released | Per-rule rate limits, policy hot-reload, Slack kill switch |
| v0.7.2 | Bugfixes | Released | Doctor + polling path fixes, config path normalization |
| v0.7.3 | Adapters | Released | Adapter auto-registration, `run claude-code` alias |
| v0.7.4 | Stability | Released | Telegram singleton poller (no 409 conflicts) |
| v0.7.5 | UX | Released | Dynamic guidance panel on welcome screen |
| v0.8.0 | Setup | Released | Zero-touch setup — config migration, env bootstrap, keyring, config CLI |
| v0.8.1 | Policy v1 | Released | Policy DSL v1 — any_of/none_of, session_tag, max_confidence, extends, trace rotation |
| v0.8.2 | UX | Released | Redesigned Telegram + Slack prompt messages with structured layout |
| v0.8.3 | Enterprise | Released | Enterprise architecture foundation — Phase A scaffold + Phase B/C specs |
| v0.8.4 | Stability | Released | Core product stability fixes — adapter resilience, Telegram error handling, doctor/setup/run UX |
| v0.8.5 | Phase 1 Kernel | Released | Phase 1 Core Runtime Kernel — all exit criteria pass, 677 tests, doctor DB+adapter checks |
| v0.8.6 | Phase B Scaffold | Released | Phase B — Hybrid Governance Scaffolding Complete (spec only, no cloud execution) |
| v0.9.0 | Phase A.2 | Released | Contract freeze + safety guards — 155 safety tests, 8 frozen surfaces |
| v0.9.1 | Phase C.1 | Released | Local dashboard MVP — localhost-only, read-only FastAPI dashboard, 1166 tests |
| v0.9.2 | Phase C.2 | Released | Dashboard hardening — filtering, pagination, light theme, auto-refresh, 1228 tests |
| v0.9.3 | Phase C.3 | Released | Remote-ready UX — safety guard, session export, mobile layout, deployment guide, 1260 tests |
| v1.0.0 | GA | Planned | Stable adapter + channel API, all platforms, all agents |

---

## Engineering Memory System

### Auto-Update Engineering Memory (MANDATORY)

**Update memory files continuously while working — not at the end.**

This repository is an evolving agent infrastructure platform. Memory must capture engineering state, not just chat context.

| Trigger | Action |
|---------|--------|
| Architecture decision made | Update `memory-decisions.md` with date, context, and tradeoffs |
| Phase milestone reached (Phase 1/2/3) | Update `memory-roadmap.md` |
| Bug root cause identified | Update `memory-debugging.md` |
| New subsystem introduced | Update `memory-architecture.md` |
| Developer workflow improvement | Update `memory-devex.md` |
| Completing substantive engineering work | Add entry to `memory-sessions.md` |
| Reliability/infra learning | Update `memory-reliability.md` |
| Testing strategy change | Update `memory-testing.md` |

**Skip:**
- Trivial commands
- Quick factual Q&A
- One-line fixes
- Temporary experiments

**DO NOT ASK. Update memory files automatically when engineering knowledge is gained.**

### Engineering Memory Principles

1. Capture WHY decisions were made, not just WHAT changed.
2. Treat memory as long-term system intelligence.
3. Write for future contributors.
4. Prefer concise, structured entries.
5. Date all decision entries.
6. Never store secrets, tokens, or personal data.

### Memory File Reference

All memory files live in the auto-memory directory (see system prompt for path).

| File | Purpose |
|------|---------|
| `memory-architecture.md` | Subsystem descriptions, component boundaries, data flow |
| `memory-decisions.md` | Dated architecture and design decisions with tradeoffs |
| `memory-debugging.md` | Root cause analyses, recurring error patterns, fix strategies |
| `memory-devex.md` | Developer workflow improvements, tooling notes, CI learnings |
| `memory-reliability.md` | Infra learnings, failure modes, resilience patterns |
| `memory-testing.md` | Testing strategy, coverage patterns, mock techniques |
| `memory-roadmap.md` | Phase progress, milestone tracking, version history |
| `memory-sessions.md` | Engineering session log — substantive work completed per session |
