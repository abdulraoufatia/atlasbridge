# Repository Reference — AtlasBridge

Detailed structural reference for the AtlasBridge codebase. CLAUDE.md points here for full layouts and tables.

---

## Repository Layout

```
src/atlasbridge/         ← installed package (where = ["src"])
  core/
    prompt/              — detector.py, state.py, models.py
    session/             — models.py, manager.py
    routing/             — router.py
    interaction/         — classifier.py, plan.py, executor.py, engine.py, output_forwarder.py
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
  console/               — app.py, supervisor.py, css/console.tcss (operator console TUI)
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

## Key Files

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
| `src/atlasbridge/core/interaction/classifier.py` | InteractionClassifier — refines PromptType to InteractionClass |
| `src/atlasbridge/core/interaction/plan.py` | InteractionPlan + build_plan() — execution strategy per class |
| `src/atlasbridge/core/interaction/executor.py` | InteractionExecutor — injection, retry, advance verification |
| `src/atlasbridge/core/interaction/engine.py` | InteractionEngine — per-session classify → plan → execute orchestrator |
| `src/atlasbridge/core/interaction/output_forwarder.py` | OutputForwarder — batched PTY output → channel messages |
| `src/atlasbridge/core/interaction/ml_classifier.py` | MLClassifier protocol + NullMLClassifier default |
| `src/atlasbridge/core/interaction/fuser.py` | ClassificationFuser — deterministic + ML fusion rules |
| `src/atlasbridge/core/interaction/output_router.py` | OutputRouter — agent prose vs CLI output classification |
| `src/atlasbridge/core/conversation/session_binding.py` | ConversationRegistry — thread→session binding + state machine |
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

## Architecture: Data Flow

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

## Policy Module Layout

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
| v0.9.4 | Phase D | Released | Platform automation — CI hardening, secret scan, coverage governance, release automation |
| v0.9.5 | Phase C.X | Released | Operator console — `atlasbridge console` single-screen process management TUI |
| v0.9.6 | Phase H | Released | Hard freeze — contract surface audit, tag-only publish, coverage governance, 1336 tests |
| v0.9.7 | Phase C.Y | Released | Conversation UX v2 — interaction pipeline (classify→plan→execute), chat mode, output forwarding |
| v0.9.8 | Phase C.Y2 | Released | Conversation session binding, ML classifier protocol, classification fuser, output router |
| v1.0.0 | GA | Planned | Stable adapter + channel API, all platforms, all agents |
