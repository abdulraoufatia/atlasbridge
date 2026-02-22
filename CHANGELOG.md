# Changelog

All notable changes to AtlasBridge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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

[Unreleased]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.9.3...HEAD
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
