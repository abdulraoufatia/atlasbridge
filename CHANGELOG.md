# Changelog

All notable changes to AtlasBridge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.1.1] — 2026-02-24

### Fixed
- **Dashboard full-width layout** — removed 1400px max-width constraint, dashboard now fills full viewport with responsive padding

---

## [1.1.0] — 2026-02-24

### Added
- **Node.js/React dashboard** — full-stack replacement for the Python FastAPI dashboard. React 18 + Express 5 + TypeScript with TailwindCSS and shadcn/ui components. Dual-database architecture: `dashboard.db` (read-write) for RBAC/settings, `atlasbridge.db` (read-only) for live operational data.
- **AtlasBridgeRepo** — TypeScript read-only data access layer for AtlasBridge SQLite DB and JSONL trace file. Serves sessions, prompts, audit events, traces, integrity verification, and overview metrics from real data.
- **Dashboard sanitization** — TypeScript port of ANSI stripping and token redaction (Telegram, Slack, GitHub PAT, AWS keys).
- **CLI dashboard integration** — `atlasbridge dashboard start` now spawns the Node.js dashboard (port 5000) by default. `--legacy` flag preserves the old Python FastAPI dashboard (port 8787).

### Removed
- **Windows support** — removed Windows ConPTY adapter, `--experimental` flag, `pywinpty` optional dependency, and Windows CI matrix entry. AtlasBridge now supports macOS and Linux only.

---

## [1.0.1] — 2026-02-23

### Fixed

- **Prompt spam dedup (#296)** — prevent repeated "Input Required" notifications for the same prompt (e.g., Claude folder trust). Two-layer dedup: content hash in PromptDetector (30s window) and active prompt comparison + failsafe rate limiter (5/60s) in PromptRouter

---

## [1.0.0] — 2026-02-23 — GA Release

### Highlights

AtlasBridge v1.0.0 is the first stable release. All 8 contract surfaces are frozen and enforced by CI safety tests. 2005 tests, 85.80% coverage, 30 safety test files. Supports macOS and Linux.

### Added

- **Windows ConPTY experimental adapter (#60)** — full `WindowsTTY` implementation using `pywinpty`, gated behind `--experimental` flag on `atlasbridge run`, with CRLF normalisation, Windows build validation (10 1809+), 19 unit tests, and non-blocking Windows CI matrix entry
- **Windows documentation (#106)** — troubleshooting guide for Windows ConPTY, `--experimental` flag docs, WSL2 recommendation, `pywinpty` optional dependency
- **Local-only execution boundary (Epic #145)** — 19 safety tests enforcing injection path restriction, gate evaluation ordering, cloud isolation, phone-first interaction, docs-lint, boundary message completeness, and SaaS program gate (#146, #147, #148, #149, #150)
- **Phone-first interaction docs** — `docs/phone-first-interaction.md` with text-only operation guide, synonym tables, boundary messages, and Enter/newline semantics (#147)
- **SaaS program gate** — `docs/decisions/001-saas-program-gate.md` decision record defining what must be true before any SaaS code merges, with decision record template (#150)
- **Docs-lint grep guard** — safety test preventing "cloud execution" language in user-facing docs (#148)
- **CLI main.py split** — reduced from 481 to 146 lines; all 27 commands preserved via extracted modules with Click wrappers (#125)
- **Audit rotation size-based threshold** — `AUDIT_MAX_ROWS=10000`, `archive_oldest_audit_events()` method, `--max-rows` CLI option with union semantics, 4 unit tests (#126)
- **Dashboard integration e2e test** — 11 tests verifying real HTTP server binding, route responses, and loopback-only enforcement (#101)
- **Performance benchmark tests** — 12 tests verifying detect() <5ms, 100k-line flood <50ms p99, pre-compiled regex patterns (#67)
- **Per-agent getting started guides** — Claude Code, OpenAI Codex CLI, and Gemini CLI guides with setup, prompt patterns, policy examples, and troubleshooting (#99)
- **Policy cookbook** — copy-paste-ready patterns for git, CI/CD, Dependabot, package managers, session scoping, compound conditions, and rate limiting (#100)
- **ChannelMessageGate engine** — pure, deterministic accept/reject for all channel messages with 10-step evaluation, 10 reason codes, and frozen dataclass I/O (#156)
- **Channel accept/reject UX** — phone-friendly message formatter with AcceptType enum (reply/chat_turn/interrupt) and short rejection messages (#159)
- **Channel rate limiter** — token-bucket rate limiting (10/min, burst 3) with per-user per-channel buckets and enforced floor of 1/min (#160)
- **Binary menu normalization** — detect semantic yes/no numbered menus and map natural language replies to correct option numbers (#166)
- **Channel gating safety tests** — 24 safety tests proving gate structure, injection safety, and invariant preservation (#162)
- **Channel message gating documentation** — evaluation order, session states, rejection reasons, rate limiting, troubleshooting (#163)
- **Policy DSL v1 gating rules** — `session_state`, `channel_message`, `deny_input_types` fields for channel message policy rules (#157)
- **Router gate integration** — ChannelMessageGate evaluated before any injection; all message queueing removed (#158)
- **Audit: gate decision logging** — `channel_message_accepted` / `channel_message_rejected` events with SHA-256 body hash and redacted excerpts (#161)
- **Trust folder prompt** — natural yes/no/trust/ok normalization verified end-to-end for Claude Code's startup prompt (#165)

### Changed

- **PyPI classifier** — `Development Status :: 2 - Pre-Alpha` → `Development Status :: 5 - Production/Stable`
- **Coverage floors raised to GA-grade** — global 84% → 85%, Tier 2 75% → 80% (#113)
- **Docs: removed commercial/SaaS language** — replaced "Private (commercial)" with "Open Source (experimental)" across README and enterprise docs (#115, #116, #117)

### Fixed

- **Windows poller lock** — `poller_lock.py` now uses `msvcrt.locking()` on Windows instead of POSIX-only `fcntl`, fixing test collection crash on Windows CI

---

## [0.10.1] — 2026-02-23 — Phase E: GA Preparation

### Added

- **Prompt Lab CI gate** — all 23 QA scenarios now run on both macOS and Linux as a required CI job (#61, PR #193)
- **doctor --fix: database auto-init** — creates DB and runs schema migrations (#65, PR #192)
- **doctor --fix: stale PID cleanup** — removes daemon PID files for dead processes (#65)
- **doctor --fix: permission repair** — tightens config file/dir to 0600/0700 (#65)
- **Stale PID check** — `atlasbridge doctor` now warns about stale daemon PID files (#65)
- **Config permissions check** — `atlasbridge doctor` now warns about overly permissive config (#65)
- **ADAPTER_API_VERSION = 1.0.0** — frozen adapter contract version constant (#62, PR #189)
- **CHANNEL_API_VERSION = 1.0.0** — frozen channel contract version constant (#63, PR #190)
- **28 policy completeness tests** — all presets, examples, fixtures, unknown field rejection, v0 backward compat (#64, PR #191)
- **18 doctor tests** — database, PID, permissions fixes + idempotency + safety (#65)

### Changed

- **CI matrix expanded** — macOS + Python 3.12 now runs (was excluded), all 4/4 cells green (#66, PR #188)
- **docs/adapters.md** promoted from v0.3.0 to v1.0.0 (Frozen GA) (#62)
- **docs/channels.md** promoted from v0.3.0 to v1.0.0 (Frozen GA), fixed notify() signature discrepancy (#63)
- **docs/policy-dsl-v1.md** — added field reference table, edge cases, anti-patterns, validation rules (#64)

### Fixed

- **escalation-only.yaml** — quoted `autonomy_mode: "off"` so YAML doesn't parse as boolean (#64)
- **example_v1.yaml** — changed unsafe auto_reply to require_human for free_text prompts (#64)
- **PyPI publish workflow** — idempotent (skips if version exists), tag/manual only (#164)

---

## [0.10.0] — 2026-02-23

### Added

- **STREAMING conversation state** (Phase C.Z)
  - New `ConversationState.STREAMING` in session binding state machine
  - `VALID_CONVERSATION_TRANSITIONS` — validated state transition graph
  - `transition_state()`, `get_state_for_session()`, `drain_queued_messages()` on `ConversationRegistry`
  - State-driven routing: STREAMING queues messages, RUNNING→chat, AWAITING_INPUT→prompt, STOPPED→drop

- **Streaming configuration** — `StreamingConfig` model with configurable batch interval, rate limit, message editing, and secret redaction

- **Secret redaction in output forwarding**
  - `OutputForwarder._redact()` strips Telegram bot tokens, Slack tokens, OpenAI keys, GitHub PATs, and AWS access keys
  - Applied before any output reaches a channel

- **Message editing mode** — `send_output_editable()` on channels returns message IDs for streaming edits instead of sending new messages

- **Plan detection in agent output**
  - `DetectedPlan` frozen dataclass + `detect_plan()` pure function
  - Two strategies: header + numbered steps (≥2), headerless + action verbs (≥3, ≥60% verb density)
  - `StreamingManager` with bounded 8192-char accumulator for incremental plan detection

- **Plan rendering with Execute/Modify/Cancel buttons**
  - `send_plan()` on `BaseChannel` with Telegram (inline keyboard) and Slack (Block Kit) overrides
  - Plan button responses routed via `__plan__` sentinel prompt_id
  - Execute notifies only (no PTY injection); Modify prompts for text; Cancel injects via chat handler

- **20 new safety tests** — secret redaction, plan detection safety, streaming state invariants, state-driven routing, accumulator bounds, conversation state transitions

### Changed

- `OutputForwarder` accepts optional `StreamingConfig`, `ConversationRegistry`, and `StreamingManager`
- `OutputRouter` classifies `PLAN_OUTPUT` alongside `AGENT_MESSAGE`, `CLI_OUTPUT`, and `NOISE`
- `PromptRouter` consults `ConversationState` before dispatching free-text replies
- Telegram `_handle_callback()` parses `plan:` prefix for plan button responses
- Slack socket mode handler detects `plan_` action_id prefix for plan actions

---

## [0.9.9] — 2026-02-23

### Fixed

- **Escalation message no longer says "raw keyboard interaction"** (Phase C.Y3)
  - Escalation messages are now per-plan and contextual (e.g., `CLI did not respond to "y" after retries`)
  - Added `escalation_template` field to `InteractionPlan`
  - `InteractionExecutor` uses `plan.escalation_template` instead of hardcoded message
  - Removed all "arrow keys" and "run locally once" language from user-facing messages

- **Folder trust prompt detection** — Claude Code's "Do you trust the files in this folder?" menu now detected as MULTIPLE_CHOICE
  - Added combined-buffer pattern matching for multi-line numbered lists across PTY chunks
  - Folder trust prompt correctly classified as NUMBERED_CHOICE; injection of "1" works
  - Dedicated folder trust pattern added to detector

### Changed

- `RAW_TERMINAL` display_template updated to generic "could not be handled remotely" language
- `RAW_TERMINAL`/`FOLDER_TRUST` comments cleaned up (removed "arrow-key" references)

---

## [0.9.8] — 2026-02-23

### Added

- **Conversation UX v2 — Interaction Pipeline** (Phase C.Y, PR #141)
  - `InteractionClassifier` — refines PromptType into 6 InteractionClass values (YES_NO, CONFIRM_ENTER, NUMBERED_CHOICE, FREE_TEXT, PASSWORD_INPUT, CHAT_INPUT)
  - `InteractionPlan` + `build_plan()` — frozen execution strategy per class (retry, verify, escalate, display templates)
  - `InteractionExecutor` — injection with retry, advance verification, and password redaction
  - `InteractionEngine` — per-session classify → plan → execute orchestrator
  - `OutputForwarder` — batched PTY output streaming to channels (rate-limited, ANSI-stripped)
  - `send_output()` on all channels for monospace CLI output messages
  - Chat mode — operators type naturally between prompts; messages injected to PTY stdin
  - 132 tests covering the interaction pipeline

- **Conversation Session Binding** (Phase C.Y2, PR #142)
  - `ConversationRegistry` — thread→session binding with TTL (4h default), state machine (IDLE/RUNNING/AWAITING_INPUT/STOPPED), and automatic unbind on session end
  - `MLClassifier` Protocol + `NullMLClassifier` default — clean extension point for future ML-assisted classification
  - `MLClassification` StrEnum with 9 values including ML-only types FOLDER_TRUST, RAW_TERMINAL
  - `ClassificationFuser` — deterministic + ML fusion with 6 safety-first rules (deterministic always wins at HIGH confidence)
  - `OutputRouter` — classifies PTY output as agent prose (AGENT_MESSAGE), CLI output (CLI_OUTPUT), or noise (NOISE)
  - `send_agent_message()` — non-abstract default on `BaseChannel` with rich formatting overrides (HTML on Telegram, mrkdwn on Slack)
  - `Reply.thread_id` field for channel thread binding
  - Thread ID extraction in Telegram (chat_id) and Slack (channel:message_ts)
  - Session start/stop lifecycle notifications via channel
  - New `InteractionClass` values: FOLDER_TRUST (trust-folder special case), RAW_TERMINAL (unparsable interactive prompts, always escalates)
  - Full daemon wiring: ConversationRegistry, ClassificationFuser, OutputRouter injected per session

### Changed

- `PromptRouter` accepts optional `conversation_registry` for deterministic thread→session resolution
- `OutputForwarder` accepts optional `output_router` for agent prose vs CLI output routing
- `InteractionEngine` accepts optional `fuser` for ML-assisted classification
- Safety tests updated for FOLDER_TRUST and RAW_TERMINAL interaction types

---

## [0.9.7] — 2026-02-22

### Added

- **Audit log rotation** — `atlasbridge db archive` command archives old events to separate SQLite files, preserving hash chain integrity. Supports `--days`, `--dry-run`, `--json`. Rotates up to 3 archive files (#72, PR #121)
- **Circuit breaker activation** — `guarded_send()` method on `BaseChannel` wires the existing `ChannelCircuitBreaker` into channel send paths. Structured logging on circuit open/reject. `healthcheck()` reports circuit state as ok/degraded (#71, PR #122)
- `ChannelUnavailableError` exception for circuit-open rejection
- `docs/cloud-spec.md` — Phase B cloud governance interface specification (extracted from source)
- `docs/sprint-automation-prompt.md` — portable sprint workflow prompt
- Pytest markers: `safety`, `e2e`, `optional`, `performance` — run subsets with `pytest -m safety` (#105)
- Auto-apply conftest hooks for `tests/safety/` and `tests/e2e/` directories
- `.secrets.baseline` for detect-secrets pre-commit hook (#73)
- `test_readme_status_table_includes_current_version` safety test (#93)
- Python 3.13 as non-blocking experimental CI target (#94)
- Tiered CI coverage gates: Tier 1 core >= 88%, Tier 2 core >= 75%

### Changed

- **mypy overrides narrowed** — replaced blanket `ignore_errors = true` for 6 module groups with targeted per-file `disable_error_code` and `disallow_untyped_defs = false`. 44 stale `# type: ignore` comments removed, 12 real type errors fixed. 0 mypy errors remain (#102, #69, PR #120)
- **Cloud module extracted to docs** — 7 interface-only Phase B files (415 lines) moved from `src/atlasbridge/cloud/` to `docs/cloud-spec.md`. `CloudConfig` inlined into `_enterprise.py`. Safety tests guard against re-introduction (#108, PR #123)
- **TUI cleanup** — consolidated `tui/` utilities, removed dead code, standardized imports (#104, PR #118)
- **CLI split** — extracted adapter, db, version commands from monolithic `main.py` (#103, PR #119)
- **DaemonManager types** — added type annotations to daemon orchestrator (#101, PR #118)
- Coverage floor raised from 80% to 84% (#70)
- Coverage config restructured: daemon and channel ABCs now measured (#95)
- v0.9.6 added to README.md status table (#93)

### Fixed

- Coverage omit patterns no longer hide daemon/channels from measurement (#95)

---

## [0.9.6] — 2026-02-22

### Added

- **Phase H — v1.0 GA Hard Freeze + Release Pipeline Correction**
  - `console` added to frozen CLI command set (27 top-level commands)
  - Subcommand freeze tests for dashboard, config, cloud, db, lab groups (5 new tests)
  - Console surface freeze safety test — options, defaults, help text (7 tests)
  - Console smoke test added to CI workflow
  - `docs/invariants.md` — all correctness invariants in one document
  - `docs/releasing.md` — tag-only release process, troubleshooting
  - PR template governance gates: invariant confirmation, no-auto-merge, scope declaration
- 12 new safety tests (1336 total), 22 safety test files

### Changed

- Coverage floor raised from 75% to 80% (actual: 85.92%)
- Core package coverage verification step added to CI (floor: 85%, target: 90%)
- Safety test file minimum raised from 21 to 22

### Fixed

- Publish workflow now includes pre-publish validation (lint, mypy, pytest)
- Publish workflow adds `workflow_dispatch` trigger for manual publish
- Publish workflow adds tag ref guard — non-tag refs skip publish gracefully
- Fixed YAML syntax in publish workflow step name

---

## [0.9.5] — 2026-02-22

### Added

- **Phase C.X — Operator Console Mode**
  - New `atlasbridge console` command — single-screen TUI for managing daemon, agent, and dashboard processes
  - `ProcessSupervisor` — pure Python subprocess manager for daemon/dashboard/agent lifecycle
  - `ConsoleApp` + `ConsoleScreen` — Textual TUI with status cards, process table, doctor panel, audit log
  - Keybindings: `d` (daemon), `a` (agent), `w` (dashboard), `h` (health), `r` (refresh), `q` (quit)
  - 2-second live status polling with reactive UI updates
  - Safety banner: "OPERATOR CONSOLE — LOCAL EXECUTION ONLY"
  - CLI options: `--tool` (default agent tool), `--dashboard-port` (dashboard port)
  - `docs/console.md` — full operator console documentation
- 58 new tests (1324 total): 25 supervisor, 26 app, 7 CLI

---

## [0.9.4] — 2026-02-22

### Added

- **Phase D — Platform Automation & Governance Hardening**
  - Tag-version validation in PyPI/TestPyPI publish workflows (tag must match `pyproject.toml` and `__init__.py`)
  - Dashboard route freeze safety test (10 frozen routes, CI fails on drift)
  - Docs index validation safety test (every `docs/*.md` must be linked in `docs/README.md`)
  - Secret scan CI workflow with `detect-secrets` (runs on PRs + weekly)
  - Dependency audit CI workflow with `pip-audit` (runs on dependency changes + weekly)
  - Pre-commit config (detect-secrets + ruff hooks)
  - Release checklist template (`.github/RELEASE_CHECKLIST.md`)
  - PR template updated with governance gates (contract freeze, loopback default, invariant confirmation)
- 6 new safety tests (1266 total), 21 safety test files

### Changed

- Coverage floor raised from 70% to 75% (actual: 89.84%)
- Docs index updated with 3 previously unlinked docs (dashboard.md, api-stability-policy.md, contract-surfaces.md)

---

## [0.9.3] — 2026-02-22

### Added

- **Phase C.3 — Remote-Ready Local UX**: safely usable from remote devices via SSH tunnel or reverse proxy
  - `--i-understand-risk` safety guard: non-loopback binding requires explicit, verbose flag (hidden from `--help`)
  - Loopback check now runs before fastapi dependency check for correct error ordering
  - `start_server()` gains `allow_non_loopback` keyword argument
- **Session export** — full session bundle (metadata, prompts, traces, audit events) with sanitized output
  - `atlasbridge dashboard export --session <id>` CLI command (JSON to stdout, HTML to file)
  - `--format json` (default) / `--format html` (self-contained, inline CSS, no external deps)
  - `--output <path>` option for file output
  - `GET /api/sessions/{session_id}/export` JSON API endpoint
  - `DashboardRepo.export_session()` convenience method
- **Deployment guide** — `docs/dashboard.md`
  - SSH tunnel guide (local forwarding, persistent tunnel, mobile SSH clients)
  - Reverse proxy examples (Nginx with basic auth, Caddy with basicauth)
  - Bold "DO NOT EXPOSE WITHOUT AUTH" security warnings
  - Export usage guide, mobile access notes, troubleshooting
- **Responsive mobile layout**
  - CSS breakpoints at 768px (tablet) and 480px (phone)
  - Hamburger nav toggle with `.nav-links.open` JS handler
  - `.table-responsive` wrapper with `overflow-x: auto` on all 7 tables
  - 44px minimum touch targets on buttons, links, pagination
  - Filter bar vertical stacking, stat cards 2-col / 1-col reflow
- 32 new tests (1260 total): risk flag enforcement, export JSON/HTML/API, no-secret-leakage, CLI integration

---

## [0.9.2] — 2026-02-22

### Added

- **Phase C.2 — Dashboard Hardening + Operator UX**
  - Server-side filtering: sessions by status, tool, search query
  - Pagination for decision traces with page navigation
  - `GET /api/stats` and `GET /api/sessions` JSON API endpoints
  - Auto-refresh toggle with 5-second polling and localStorage persistence
  - Light theme toggle with CSS custom properties
  - Structured access logging with secret-redacting middleware
  - `POST /api/integrity/verify` with 10-second rate limit (429 throttle)
  - `timeago` Jinja2 filter across all templates
- 62 new tests (1228 total): filter combinations, empty states, banner/nav presence, no raw tokens

---

## [0.9.1] — 2026-02-22

### Added

- **Phase C.1 — Local Dashboard MVP**: localhost-only, read-only web dashboard
  - FastAPI app with 5 HTML routes + 1 JSON API endpoint (`/api/integrity/verify`)
  - Read-only SQLite access (`file:...?mode=ro`) — no WAL contention with running daemon
  - Content sanitization: ANSI stripping, token redaction (6 patterns), truncation
  - Dark-themed server-rendered UI with stats cards, session detail, trace viewer, integrity check
  - Prompt excerpts hidden by default (`<details>/<summary>` pattern)
  - Banner on every page: "READ-ONLY GOVERNANCE VIEW — LOCAL EXECUTION ONLY"
- CLI: `atlasbridge dashboard start` / `atlasbridge dashboard status`
  - `--host` validated as loopback (rejects `0.0.0.0`, public IPs)
  - `--port` (default 8787), `--no-browser` options
  - Helpful error if `fastapi` not installed
- Optional dependency group: `pip install 'atlasbridge[dashboard]'` (fastapi, uvicorn, jinja2)
- 53 dashboard feature tests + 8 localhost-only safety tests (1166 total)

---

## [0.9.0] — 2026-02-21

### Added

- 10 new contract stability safety tests (155 safety tests total across 18 files):
  - `test_adapter_api_stability.py` — BaseAdapter ABC freeze (6 tests)
  - `test_channel_api_stability.py` — BaseChannel ABC freeze (5 tests)
  - `test_policy_schema_stability.py` — Policy DSL schema freeze (13 tests)
  - `test_audit_schema_stability.py` — audit log schema freeze (4 tests)
  - `test_config_schema_stability.py` — config schema freeze (5 tests)
  - `test_safe_defaults_immutable.py` — safety-critical defaults freeze (8 tests)
  - `test_cli_surface_stability.py` — CLI command set freeze (3 tests)
  - `test_release_artifacts.py` — release artifact validation (8 tests)
  - `test_no_injection_without_policy.py` — injection path safety (4 tests)
  - `test_version_sync.py` — version string sync guard (2 tests)
- `docs/contract-surfaces.md` — formal spec of all 8 contract surfaces
- `docs/api-stability-policy.md` — stability levels, deprecation rules, breaking change policy
- CI smoke test expanded to all 25 frozen top-level CLI commands
- `BaseAdapter.get_detector()` public method — daemon no longer accesses private `_detectors`
- `ChannelCircuitBreaker` — 3-failure threshold with 30s auto-recovery
- `db migrate` CLI command with `--dry-run` for preview
- Prompt-to-injection `latency_ms` metric in audit events and structured logs
- Pending prompt re-notify on daemon restart (previously a TODO)
- Architecture import-layering tests (prompt module stays a pure leaf)
- Router integration tests with real SQLite (no mocked DB)
- End-to-end daemon lifecycle tests
- Column allowlist test suite

### Changed

- Enterprise CLI commands (`edition`, `features`, `cloud`, `cloud status`) marked `[EXPERIMENTAL]`
- `AegisConfig` and `AegisError` aliases now emit `DeprecationWarning` (removal in v1.0)
- Synced version strings between `__init__.py` and `pyproject.toml`
- `update_session()` enforces column allowlist — rejects unknown column names
- Reduced mypy `ignore_errors = true` blanket from 13 to 9 modules
- Raised test coverage `fail_under` from 65% to 70%

### Fixed

- Removed private attribute access (`adapter._detectors`) from `daemon/manager.py`

---

## [0.8.5] — 2026-02-21

### Added

- Top-level `atlasbridge adapters` command with `--json` output
- `--json` output includes `enabled` (PATH check), `source`, `kind` fields
- 8 integration tests for the `adapters` command
- Engineering maturity ledger (`skills.md`)

---

## [0.8.1] — 2026-02-21

### Added

- Policy DSL v1 — `any_of`, `none_of`, `session_tag`, `max_confidence`, `extends`
- Decision trace rotation (10 MB, 3 archives)
- Compound conditions in policy rules

---

## [0.8.0] — 2026-02-21

### Added

- Zero-touch setup — config migration, env bootstrap, keyring integration
- `atlasbridge config` CLI subcommands (get, set, list, path)
- macOS Keychain / Linux Secret Service integration for bot tokens

---

## [0.7.5] — 2026-02-21

### Added

- Dynamic guidance panel on welcome screen

---

## [0.7.4] — 2026-02-21

### Fixed

- Telegram singleton poller (no 409 conflicts)

---

## [0.7.3] — 2026-02-21

### Added

- Adapter auto-registration via `@AdapterRegistry.register()` decorator
- `atlasbridge run claude-code` alias

---

## [0.7.2] — 2026-02-21

### Fixed

- Doctor + polling path fixes, config path normalization

---

## [0.7.1] — 2026-02-21

### Added

- Per-rule rate limits in policy DSL
- Policy hot-reload (file watcher)
- Slack kill switch

---

## [0.6.2] — 2026-02-20

### Changed

- Updated product tagline and pyproject.toml description/keywords

---

## [0.6.1] — 2026-02-20

### Added

- Policy authoring guide (`docs/policy-authoring.md`)
- 5 preset policies (permissive, strict, dev, staging, ci)

---

## [0.6.0] — 2026-02-20

### Added

- Policy DSL v0 — YAML-based rule engine with first-match-wins semantics
- Autopilot engine with 3 modes (off, assist, full)
- Kill switch (`atlasbridge pause` / `atlasbridge resume`)
- Append-only decision trace (JSONL)

---

## [0.5.0] — 2026-02-20

### Added

- Interactive Textual TUI — setup wizard, sessions, logs, doctor screens
- `atlasbridge ui` command

---

## [0.4.0] — 2026-02-20

### Added

- Slack channel (Socket Mode + Block Kit)
- Multi-channel routing (`MultiChannel` fan-out)
- Renamed from Aegis to AtlasBridge

---

## [0.3.0] — 2026-02-20

### Added

- Linux PTY supervisor
- systemd user service integration

---

## [0.2.0] — 2026-02-20

### Added

- Working Telegram relay for Claude Code on macOS
- Tri-signal prompt detection
- Hash-chained audit log

---

## [0.1.0] — 2026-02-20

### Added

- Repository scaffold and project structure
- MIT License
- SECURITY.md with responsible disclosure process
- CONTRIBUTING.md with branching and commit conventions
- CODE_OF_CONDUCT.md (Contributor Covenant v2.1)
- .env.example with all configurable parameters
- .gitignore for Python projects
- GitHub Actions CI workflow
- Dependabot configuration
- GitHub Issue templates (bug report, feature request, security)
- Pull request template
- CLI UX design (`docs/cli-ux.md`)
- Architecture design (`docs/architecture.md`)
- STRIDE threat model (`docs/threat-model.md`)
- Red team analysis report (`docs/red-team-report.md`)
- Tool interception design with Mermaid diagrams (`docs/tool-interception-design.md`)
- Policy engine design (`docs/policy-engine.md`)
- Data model design (`docs/data-model.md`)
- Approval lifecycle design (`docs/approval-lifecycle.md`)
- Setup flow design (`docs/setup-flow.md`)
- Tool adapter abstraction design (`docs/tool-adapter.md`)
- Python project scaffolding (`pyproject.toml`)
- Package stubs for all modules

### Security

- Established security-first design principles
- Defined exit codes for all failure categories
- Documented allowlist, RBAC, and audit log requirements

---

[Unreleased]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.9.6...HEAD
[0.9.6]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.9.5...v0.9.6
[0.9.5]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.8.5...v0.9.0
[0.8.5]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.8.1...v0.8.5
[0.8.1]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.7.5...v0.8.0
[0.7.5]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.7.4...v0.7.5
[0.7.4]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.7.3...v0.7.4
[0.7.3]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.6.2...v0.7.1
[0.6.2]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/abdulraoufatia/atlasbridge/releases/tag/v0.1.0
