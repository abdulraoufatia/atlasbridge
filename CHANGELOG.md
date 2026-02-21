# Changelog

All notable changes to AtlasBridge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

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

- `update_session()` enforces column allowlist — rejects unknown column names
- Reduced mypy `ignore_errors = true` blanket from 13 to 9 modules
- Raised test coverage `fail_under` from 50% to 65%

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

[Unreleased]: https://github.com/abdulraoufatia/atlasbridge/compare/v0.8.5...HEAD
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
