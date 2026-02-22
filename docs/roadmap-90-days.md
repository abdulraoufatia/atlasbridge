# AtlasBridge Roadmap

**Version:** 0.9.7
**Status:** Active
**Last updated:** 2026-02-22

---

## Where We Are

AtlasBridge v0.9.3 is released and available on PyPI. The core autonomous runtime is production-capable on macOS and Linux with a mature policy engine, zero-touch setup, and a local governance dashboard.

Key capabilities shipped:

- **Local Dashboard** — localhost-only, read-only FastAPI dashboard with filtering, pagination, auto-refresh, light/dark theme, responsive mobile layout, session export (JSON + HTML)
- **Contract Stability** — 8 frozen API surfaces with 155 safety tests; adapter, channel, policy, audit, config schemas frozen
- **Policy DSL v1** — compound conditions (`any_of`/`none_of`), session scoping (`session_tag`), confidence bounds (`max_confidence`), policy inheritance (`extends`), trace rotation
- **Zero-touch setup** — config migration from legacy paths, `--from-env` bootstrap, keyring integration, `atlasbridge config` CLI
- **Autopilot Engine** — three autonomy modes (Off / Assist / Full) with instant kill switch, per-rule rate limits, policy hot-reload
- **PTY supervisor** — macOS and Linux, Claude Code + OpenAI + Gemini adapters with auto-registration
- **Telegram + Slack** — dual-channel notification with inline keyboard responses, Slack kill switch parity
- **Interactive TUI** — setup wizard, sessions, logs, doctor, dynamic guidance panel
- **Audit infrastructure** — hash-chained audit log + append-only decision trace (JSONL) with configurable rotation

The positioning is settled: **policy-driven autonomous runtime for AI CLI agents**. Autonomy first. Human override when required.

---

## Shipped Milestones

| Version | Theme | Status |
|---------|-------|--------|
| v0.2.0 | macOS MVP — working Telegram relay for Claude Code | Released |
| v0.3.0 | Linux support, systemd integration | Released |
| v0.4.0 | Slack, MultiChannel fan-out, renamed to AtlasBridge | Released |
| v0.5.0 | Interactive TUI — setup wizard, sessions, logs, doctor | Released |
| v0.5.2 | Production UI skeleton — 6 screens, StatusCards, polling, TCSS | Released |
| v0.5.3 | CSS packaging hotfix — `.tcss` via `importlib.resources` | Released |
| v0.6.0 | Autonomous Agent Runtime — Policy DSL v0, autopilot, kill switch | Released |
| v0.6.1 | Policy authoring guide + 5 ready-to-use presets | Released |
| v0.6.2 | Product positioning — pyproject.toml, keywords, tagline | Released |
| v0.7.1 | Policy engine hardening — per-rule rate limits, hot-reload, Slack kill switch | Released |
| v0.7.2 | Doctor + polling path fixes, config path normalization | Released |
| v0.7.3 | Adapter auto-registration, `run claude-code` alias | Released |
| v0.7.4 | Telegram singleton poller (no 409 conflicts) | Released |
| v0.7.5 | Dynamic guidance panel on welcome screen | Released |
| v0.8.0 | Zero-touch setup — config migration, env bootstrap, keyring, config CLI | Released |
| v0.8.1 | Policy DSL v1 — any_of/none_of, session_tag, max_confidence, extends, trace rotation | Released |
| v0.8.2 | Redesigned Telegram + Slack prompt messages with structured layout | Released |
| v0.8.3 | Enterprise architecture foundation — Phase A scaffold + Phase B/C specs | Released |
| v0.8.4 | Core product stability fixes — adapter resilience, Telegram error handling, UX | Released |
| v0.8.5 | Phase 1 Core Runtime Kernel — all exit criteria pass | Released |
| v0.8.6 | Phase B — Hybrid Governance Scaffolding (spec only) | Released |
| v0.9.0 | Contract freeze + safety guards — 155 safety tests, 8 frozen surfaces | Released |
| v0.9.1 | Phase C.1 — Local Dashboard MVP (localhost-only, read-only) | Released |
| v0.9.2 | Phase C.2 — Dashboard Hardening (filtering, pagination, themes) | Released |
| v0.9.3 | Phase C.3 — Remote-Ready Local UX (export, mobile, SSH/proxy docs) | Released |
| v0.9.4 | Phase D — Platform Automation & Governance Hardening | Released |
| v0.9.7 | Sprint S1 — Code Quality & Maintenance Debt Reduction | Released |

### v0.9.7 — Sprint S1: Code Quality & Maintenance Debt (Released)

**Theme:** Reduce technical debt, harden subsystems, improve type safety.

**Delivered:**

- **mypy strict compliance** — replaced blanket `ignore_errors = true` with targeted per-file overrides; removed 44 stale `# type: ignore` comments, fixed 12 real type errors; 0 mypy errors across 114 source files (#102, #69, PR #120)
- **Audit log rotation** — `atlasbridge db archive` command archives events older than N days to separate SQLite files, preserving hash chain integrity; rotates up to 3 archive files (#72, PR #121)
- **Circuit breaker activation** — `guarded_send()` on `BaseChannel` wires existing `ChannelCircuitBreaker` into channel send paths; structured logging on circuit open/reject; `healthcheck()` reports circuit state (#71, PR #122)
- **Cloud module extraction** — 7 Phase B interface files (415 lines) moved from source to `docs/cloud-spec.md`; safety tests guard against re-introduction (#108, PR #123)
- **TUI cleanup** — consolidated utilities, removed dead code, standardized imports (#104, PR #118)
- **CLI split** — extracted adapter, db, version commands from monolithic `main.py` (#103, PR #119)
- **DaemonManager types** — added type annotations to daemon orchestrator (#101, PR #118)
- **CI hardening** — coverage floor 84%, Python 3.13 experimental matrix, README version sync test (#112, #114)

### v0.7.1 — Policy Engine Hardening (Released)

**Theme:** Make the autonomy engine production-grade for always-on workloads.

**Delivered:**

- **Per-rule rate limits** — `max_auto_replies: N` cap per session; prevents runaway automation on looping prompts
- **Policy hot-reload** — `SIGHUP` reloads policy without daemon restart; new rules take effect on next prompt
- **Slack kill switch** — `/pause`, `/resume`, `/stop`, `/status` commands in Slack (full parity with Telegram)
- **Multi-session kill switch** — `atlasbridge pause --all` instantly pauses every active session
- **Kill switch history** — `atlasbridge autopilot history` shows state transitions with timestamps and who triggered each change

### v0.8.0 — Zero-Touch Setup (Released)

**Theme:** First-run experience that just works.

**Delivered:**

- **Config migration** — automatic detection and migration from legacy `~/.aegis/` paths
- **Environment bootstrap** — `atlasbridge setup --from-env` for headless / CI deployments
- **Keyring integration** — channel tokens stored in the OS keyring instead of plain-text config
- **Config CLI** — `atlasbridge config` subcommands for viewing and modifying configuration

### v0.8.1 — Policy DSL v1 (Released)

**Theme:** A richer, more expressive policy language for complex autonomous workflows.

**Delivered:**

- **Compound conditions** — `any_of`, `none_of` match operators for multi-field rules
- **Session context matching** — `match.session.tag` for session-scoped policy rules
- **Confidence bounds** — `max_confidence` for bounded automation windows
- **Policy inheritance** — `extends: base-policy.yaml` for composing shared rules with overrides
- **Decision trace rotation** — configurable rotation of `autopilot_decisions.jsonl` by size or age
- **Backward compatibility** — `policy_version: "0"` policies parse and evaluate identically to v0.6.x

### v0.8.2 — Redesigned Prompt Messages (Released)

**Theme:** Make channel notifications actionable at a glance.

**Delivered:**

- **Structured message layout** — Telegram and Slack prompts now show session ID, tool name, workspace path, question excerpt, response instructions, and TTL countdown in a clear, scannable format
- **Session context enrichment** — `PromptEvent` carries `tool`, `cwd`, and `session_label` fields populated by the router before dispatch
- **Per-type response instructions** — each prompt type (Yes/No, Confirm Enter, Multiple Choice, Free Text) shows specific guidance on how to respond
- **TTL visibility** — expiry countdown displayed in every prompt message
- **Slack Block Kit upgrade** — dividers, header/question/instruction sections, context block for metadata

### v0.8.3 — Enterprise Architecture Foundation (Released)

**Theme:** Open-core enterprise scaffolding with phased cloud evolution.

**Delivered:**

- **Edition gating** — `COMMUNITY` / `PRO` / `ENTERPRISE` edition enum with feature flag registry; `detect_edition()` reads `ATLASBRIDGE_EDITION` env var
- **RBAC** — local role-based access control with four roles (viewer / operator / admin / owner), permission-to-role mapping, and identity management
- **Deterministic risk classifier** — fixed decision table (LOW / MEDIUM / HIGH / CRITICAL) based on action type, confidence, branch protection, and CI state; no ML or heuristics
- **Hash-chained DecisionTraceEntryV2** — 20-field trace entries with SHA-256 chain (`previous_hash` → `current_hash`) for tamper-evident audit
- **Policy pinning** — session-level policy hash capture to detect mid-session drift
- **Policy governance lifecycle** — hash computation, snapshot diffing, and pin validation
- **Cloud interfaces (Phase B spec)** — abstract ABCs for policy registry, escalation relay, audit streaming, auth, and control channel transport; all have `Disabled*` no-op stubs *(later extracted to `docs/cloud-spec.md` in #108)*
- **Cloud protocol spec (Phase C design)** — WSS + Ed25519 signed messages, advisory-only control channel, multi-tenant SaaS architecture docs
- **CLI commands** — `atlasbridge edition`, `atlasbridge features`, `atlasbridge cloud status`
- **66 new tests** — edition detection, risk classification, trace integrity, policy pinning, cloud disabled stubs
- **6 design documents** — enterprise architecture, SaaS architecture, transition contracts, trust boundaries, implementation prompts, enterprise roadmap

### v0.8.4 — Stability Fixes (Released)

**Theme:** Harden the core product for day-to-day reliability.

**Delivered:**

- **Resilient adapter discovery** — each built-in adapter import wrapped in try/except; one broken module no longer prevents all adapters from loading
- **Telegram chat-not-found handling** — 400 "chat not found" errors now log an actionable message telling the user to send `/start` to the bot
- **Telegram 409 conflict handling** — `TelegramConflictError` raised on 409 with method name and error code in log output
- **Silent stale/unknown reply handling** — replies for unknown, duplicate, or already-resolved prompts dropped at debug level (no channel spam); added free-text reply resolution to active prompt
- **Doctor path handling** — `_config_path()` always returns `pathlib.Path`; improved next-steps output when checks fail
- **Setup config preservation** — `atlasbridge setup` detects existing `config.toml` and offers "Keep existing" before reconfiguring
- **On-screen run instructions** — `atlasbridge run` prints how-it-works summary, channel info, and useful commands
- **New documentation** — `telegram-setup.md`, `troubleshooting.md`, `upgrade.md`; docs index updated
- **22 regression tests** — adapter discovery, Telegram errors, stale reply handling, doctor paths, setup detection, poller lock

### v0.8.5 — Phase 1 Core Runtime Kernel (Released)

**Theme:** Complete all Phase 1 exit criteria — fresh install, upgrade safety, deterministic subsystems, clean output.

**Delivered:**

- **Doctor database check** — `atlasbridge doctor` validates SQLite schema version via `PRAGMA user_version` and reports pass/warn/fail
- **Doctor adapter check** — verifies adapter registry has at least one registered adapter
- **`atlasbridge db info` command** — shows database path, schema version, file size, and per-table row counts; supports `--json` output
- **`datetime.utcnow()` eliminated** — `PromptStateMachine` uses `datetime.now(UTC)`; zero deprecation warnings
- **Python 3.14 test compatibility** — 8 tests converted from `asyncio.get_event_loop().run_until_complete()` to `@pytest.mark.asyncio` async methods
- **Phase 1 kernel test suite** — 17 new tests covering fresh install (DB + indexes + CRUD), upgrade safety (auto-migration + data preservation + idempotency), adapter registry (registration + error messages + required attributes), prompt correlation (stable IDs + nonce guard + expiry guard), doctor checks, and deprecation freedom
- **Smoke test script** — `scripts/smoke_test_phase1.sh` validates all exit criteria in one run
- **677 tests passing** — zero failures, zero deprecation warnings, lint clean

### v0.8.6 — Phase B: Hybrid Governance Scaffolding (Released)

**Theme:** Enterprise governance scaffolding (spec only, no cloud execution).

**Delivered:**

- Enterprise edition gating, RBAC, deterministic risk classifier
- Hash-chained DecisionTraceEntryV2, policy pinning and governance lifecycle
- Cloud interface ABCs with disabled no-op stubs
- 66 new tests

### v0.9.0 — Contract Freeze + Safety Guards (Released)

**Theme:** Freeze all 8 contract surfaces and add comprehensive safety tests.

**Delivered:**

- **155 safety tests** across 18 files — adapter, channel, policy, audit, config, CLI, release artifacts, injection path safety
- **Contract surfaces frozen** — `BaseAdapter` ABC, `BaseChannel` ABC, Policy DSL schema, audit log schema, config schema, safety-critical defaults, CLI surface, release artifacts
- **`BaseAdapter.get_detector()`** — public method replacing private `_detectors` access
- **`ChannelCircuitBreaker`** — 3-failure threshold with 30s auto-recovery
- **`db migrate`** CLI command with `--dry-run` for preview
- **Prompt-to-injection `latency_ms`** metric in audit events and structured logs
- Import-layering tests, router integration tests with real SQLite, end-to-end daemon lifecycle tests

### v0.9.1 — Phase C.1: Local Dashboard MVP (Released)

**Theme:** Localhost-only, read-only web dashboard for governance visibility.

**Delivered:**

- **FastAPI app** with 5 HTML routes + 1 JSON API endpoint (`/api/integrity/verify`)
- **Read-only SQLite** access (`file:...?mode=ro`) — no WAL contention
- **Content sanitization** — ANSI stripping, token redaction (6 patterns), truncation
- **Dark-themed server-rendered UI** — stats cards, session detail, trace viewer, integrity check
- CLI: `atlasbridge dashboard start` / `atlasbridge dashboard status`
- Optional dependency group: `pip install 'atlasbridge[dashboard]'`
- 53 dashboard feature tests + 8 localhost-only safety tests (1166 total)

### v0.9.2 — Phase C.2: Dashboard Hardening (Released)

**Theme:** Production-grade filtering, pagination, and operator UX.

**Delivered:**

- **Server-side filtering** — sessions by status, tool, search query
- **Pagination** for decision traces with page navigation
- **JSON API endpoints** — `GET /api/stats`, `GET /api/sessions`
- **Auto-refresh toggle** with 5-second polling and localStorage persistence
- **Light theme toggle** with CSS custom properties
- **Structured access logging** with secret-redacting middleware
- **Rate-limited integrity verify** — `POST /api/integrity/verify` with 10-second throttle
- 62 new tests (1228 total)

### v0.9.3 — Phase C.3: Remote-Ready Local UX (Released)

**Theme:** Safely usable from remote devices via SSH tunnel or reverse proxy.

**Delivered:**

- **`--i-understand-risk` safety guard** — non-loopback binding requires explicit, verbose flag (hidden from `--help`)
- **Session export** — `atlasbridge dashboard export --session <id>` (JSON to stdout, HTML to file)
- **Export API** — `GET /api/sessions/{session_id}/export` JSON endpoint
- **Deployment guide** — `docs/dashboard.md` with SSH tunnel, Nginx/Caddy reverse proxy, security warnings
- **Responsive mobile layout** — CSS breakpoints at 768px/480px, hamburger nav, touch targets, table scrolling
- 32 new tests (1260 total)

### v0.9.4 — Phase D: Platform Automation & Governance Hardening (Released)

**Theme:** Automate platform lifecycle without altering runtime behavior.

**Delivered:**

- **Tag-version validation** — publish workflows fail if git tag doesn't match pyproject.toml and __init__.py
- **Dashboard route freeze** — 10 frozen routes; CI fails on drift
- **Docs index validation** — every docs/*.md must be linked in docs/README.md
- **Secret scan** — detect-secrets pre-commit hook + CI workflow (weekly + PRs)
- **Dependency audit** — pip-audit CI workflow (weekly + dependency changes)
- **Coverage floor** — raised from 70% to 75% (actual: 89.84%)
- **Release checklist** — .github/RELEASE_CHECKLIST.md template
- **PR governance gates** — contract freeze, loopback default, invariant confirmation in PR template
- 6 new safety tests (1266 total), 21 safety test files

---

## Upcoming Milestones

---

### v1.0.0 — GA

**Theme:** Stable, production-grade, multi-platform autonomous runtime. Safe to run unattended on mission-critical workflows.

**GA criteria:**

- Stable `BaseAdapter` + `BaseChannel` APIs (breaking changes require a major version bump from this point)
- Policy DSL v1 stable and fully documented
- All platforms: macOS, Linux, Windows ConPTY
- Both channels: Telegram + Slack with full feature parity across all prompt types
- At least 3 first-party adapters: Claude Code, OpenAI CLI, Gemini CLI
- 20 Prompt Lab scenarios all passing on macOS and Linux
- `atlasbridge doctor --fix` handles all known failure modes on a clean install
- Performance: zero event-loop latency spikes under 100k-line output flood (QA-018)
- CI matrix: macOS + Linux, Python 3.11 + 3.12 — 4/4 green

**Definition of done:**

- [ ] All 20 Prompt Lab scenarios pass on `macos-latest` and `ubuntu-latest`
- [ ] `BaseAdapter` interface documented and versioned in `docs/adapters.md`
- [ ] `BaseChannel` interface documented and versioned in `docs/channels.md`
- [ ] Policy DSL v1 spec complete in `docs/policy-dsl.md`
- [ ] `atlasbridge doctor --fix` passes on clean macOS 14+ and Ubuntu 22.04 LTS
- [ ] CI: 4/4 matrix green (2 OS × 2 Python)
- [ ] `v1.0.0` git tag created; release notes published

---

## Ongoing Work

These items are continuously improved across releases with no fixed version target:

### Observability

| Item | Description |
|------|-------------|
| `atlasbridge sessions` | Live session list with prompt counts, duration, and outcome |
| `atlasbridge logs --tail` | Structured real-time audit event stream with session and event-type filtering |
| `atlasbridge debug bundle` | Redacted diagnostic archive (`config.toml` + last 500 audit lines + doctor output) |
| `atlasbridge autopilot trace` | Tail `autopilot_decisions.jsonl` with structured, colourised output |

### Prompt Lab

- QA-001 through QA-020 form the core regression suite — run on every PR
- New scenarios added whenever a detection or injection bug is found and fixed
- Scenarios run as `pytest` markers in CI, not just via `atlasbridge lab run`

### Documentation

- Getting started guides per agent (Claude Code, OpenAI, Gemini)
- Platform-specific setup guides (macOS, Linux, WSL2, Windows)
- Policy cookbook — real-world examples for common autonomous workflows
- Troubleshooting guide linked from `atlasbridge doctor` output

---

## Risk Register

### Risk 1: ConPTY API Instability on Windows

**Likelihood:** High
**Impact:** v0.9.0 ships with unresolved platform bugs

Windows ConPTY has known behavioural differences across Windows builds. Third-party wrappers have historically had version-specific issues.

**Mitigation:**

- Entire Windows adapter ships behind `--experimental` flag — no production-readiness pressure
- WSL2 documented as the recommended path; ConPTY is optional
- Windows CI runner is best-effort (non-blocking on the release)
- QA-020 gates correctness only; performance is a post-GA concern

---

### Risk 2: Event Loop Latency Under High-Volume Output

**Likelihood:** Low
**Impact:** QA-018 fails; real Claude Code workloads see latency spikes

Under high-volume output (100k+ lines/session), `PromptDetector.detect()` could block the asyncio event loop and delay Telegram long-poll responses.

**Mitigation:**

- All regex patterns pre-compiled at module load time (not in the hot path)
- `detect()` has a 5 ms max-time guard: if exceeded, log a warning and fall through to the stall watchdog
- QA-018 measures event-loop lag directly, not just detection accuracy

---

## Version Naming

| Version | Theme | Status |
|---------|-------|--------|
| v0.7.1 | Policy engine hardening | Released |
| v0.7.2 | Doctor + polling bugfixes | Released |
| v0.7.3 | Adapter auto-registration | Released |
| v0.7.4 | Telegram singleton poller | Released |
| v0.7.5 | Dynamic guidance panel | Released |
| v0.8.0 | Zero-touch setup | Released |
| v0.8.1 | Policy DSL v1 | Released |
| v0.8.2 | Redesigned prompt messages | Released |
| v0.8.3 | Enterprise architecture foundation | Released |
| v0.8.4 | Core product stability fixes | Released |
| v0.8.5 | Phase 1 Core Runtime Kernel | Released |
| v0.8.6 | Phase B — Hybrid Governance Scaffolding | Released |
| v0.9.0 | Contract freeze + safety guards | Released |
| v0.9.1 | Phase C.1 — Local Dashboard MVP | Released |
| v0.9.2 | Phase C.2 — Dashboard Hardening | Released |
| v0.9.3 | Phase C.3 — Remote-Ready Local UX | Released |
| v0.9.4 | Phase D — Platform Automation & Governance Hardening | Released |
| v1.0.0 | GA — stable, multi-platform, multi-agent | Planned |

Versions follow SemVer. Breaking changes to `BaseAdapter` or `BaseChannel` require a minor version bump in v0.x and a major bump at v1.0+.

---

## Definition of "CI Green"

A CI job is considered green when all of the following pass:

1. `ruff check .` — zero lint violations
2. `ruff format --check .` — zero formatting violations
3. `mypy src/atlasbridge/` — zero type errors (with configured `ignore_errors` overrides)
4. `pytest tests/ --cov=atlasbridge` — zero failures, coverage ≥ 50%
5. `atlasbridge version` — exits 0 without error
6. `atlasbridge doctor` — exits 0 on a configured install

Platform parity: all jobs pass on `macos-latest` and `ubuntu-latest`, Python 3.11 and 3.12.

The Windows CI runner on `windows-latest` is best-effort through v0.9.0 — failures are reported but do not block releases.
