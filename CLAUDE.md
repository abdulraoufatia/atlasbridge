# CLAUDE.md — AtlasBridge Project Context

This file is read by Claude Code automatically. It provides project context for working on this codebase.

---

## What AtlasBridge is

AtlasBridge is a **policy-driven autonomous runtime for AI CLI agents** with built-in human escalation and remote prompt relay.

AtlasBridge is a deterministic, policy-governed runtime that allows AI CLI agents to operate autonomously within defined boundaries. Humans define the rules. AtlasBridge enforces them. When uncertainty, ambiguity, or high-impact actions arise, AtlasBridge escalates safely to a human via Telegram or Slack.

**Three autonomy levels:** Off (all prompts to human), Assist (policy handles allowed prompts, escalates others), Full (policy auto-executes, escalates no-match/low-confidence).

---

## What AtlasBridge is NOT

- Not a security product
- Not a CLI firewall
- Not a cloud service

---

## Core invariants (correctness, not security posture)

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
| v0.7.0 | Windows | Planned | ConPTY experimental |
| v1.0.0 | GA | Planned | Stable adapter + channel API |
