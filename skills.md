# AtlasBridge Engineering Maturity Ledger

> Long-term engineering growth tracker. Updated after each skill-development cycle.

---

## Scorecard

| Area | Score | Trend | Last Updated |
|------|-------|-------|--------------|
| Architecture | 9/10 | +1 | 2026-02-21 |
| Reliability | 9/10 | +1 | 2026-02-21 |
| DB Discipline | 9/10 | +2 | 2026-02-21 |
| DX | 9/10 | +1 | 2026-02-21 |
| Observability | 9/10 | -- | 2026-02-21 |
| Testing | 9/10 | +2 | 2026-02-21 |
| Security | 9/10 | +1 | 2026-02-21 |
| Product Thinking | 9/10 | +1 | 2026-02-21 |

**Overall: 9.0 / 10**

---

## Area Details

### Architecture (9/10)

**Strengths**
- Zero circular imports; strict layered dependency graph (`core/prompt/` is a pure leaf)
- Clean ABC hierarchy (`BaseAdapter`, `BaseChannel`) with full `@abstractmethod` contracts
- Deferred imports in `daemon/manager.py` — daemon starts even with missing optional deps
- `AdapterRegistry` metaclass with `@register()` decorator — clean discovery pattern
- Top-level `adapters` command reuses same registry; no hardcoded adapter names anywhere

**Evidence**: `adapters/base.py`, `channels/base.py`, `daemon/manager.py`, `cli/main.py`

**Gaps**
- `daemon/manager.py:240` accesses `adapter._detectors` (private field across boundary)

**Milestones**
- [x] Top-level `adapters` command reusing registry (Sprint 2026-02-21)
- [ ] Expose `detectors` via a public adapter method to remove private access
- [ ] Add an `ArchitectureTest` that asserts import layering rules (no channel→adapter imports)

---

### Reliability (9/10)

**Strengths**
- Exponential backoff in Telegram polling (1s → 60s, reset on success)
- OS-level singleton via `fcntl.flock()` with PID diagnostics and dead-lock cleanup
- `MultiChannel` uses `gather(return_exceptions=True)` — one channel failing doesn't break others
- Signal handlers (SIGTERM/SIGINT) → asyncio Event → clean task cancellation
- TTL sweeper runs every 10s; prompts never silently hang
- Schema migration crash recovery: idempotent migrations, rollback on failure, recovery CLI output

**Evidence**: `channels/telegram/channel.py`, `channels/multi.py`, `core/poller_lock.py`, `core/store/migrations.py`

**Gaps**
- Pending prompt re-notify on daemon restart has a `TODO` — prompts reloaded but not re-sent

**Milestones**
- [x] Crash-safe DB migration with rollback + recovery message (Sprint 2026-02-21)
- [ ] Implement re-notify path for pending prompts after daemon restart
- [ ] Add circuit breaker for channel send failures (3 failures → pause → health probe → resume)

---

### DB Discipline (9/10)

**Strengths**
- `PRAGMA user_version` for atomic schema versioning (no extra table)
- Idempotent migrations with `_add_column_if_missing()` — handles fresh, upgrade, and partial-crash
- `decide_prompt()` — single atomic UPDATE enforces nonce dedup + TTL + status in one statement
- Hash-chained audit log (SHA-256); truncation is detectable
- WAL mode enabled before any DDL; foreign keys enforced
- Explicit timestamp in `append_audit_event()` (not reliant on column DEFAULT)
- Atomic config writes via `.tmp` → `rename()`
- Migration errors include DB path and recovery command

**Evidence**: `core/store/database.py`, `core/store/migrations.py`

**Gaps**
- Only 1 schema version so far (will grow as features add columns)

**Milestones**
- [x] Schema migration system with `PRAGMA user_version` (Sprint 2026-02-21)
- [x] Idempotent column additions for old→new upgrades (Sprint 2026-02-21)
- [x] Drop legacy `schema_version` table during migration (Sprint 2026-02-21)
- [ ] Add migration 1→2 when next schema change is needed
- [ ] Add a `db migrate --dry-run` CLI command for operators

---

### DX (9/10)

**Strengths**
- 20+ CLI subcommands, all with `--json` for scripting
- Top-level `atlasbridge adapters` shortcut — ergonomic, no subgroup nesting required
- `--json` output includes `enabled` field (checks if tool binary is on PATH)
- `atlasbridge doctor --fix` creates skeleton config with annotated comments
- `atlasbridge setup --non-interactive --from-env` for CI environments
- `atlasbridge policy test --explain` with per-criterion match reasons
- Prompt Lab: 20 QA scenarios runnable via `atlasbridge lab run --all`
- ruff (E/W/F/I/B/C4/UP/S/N/ANN), mypy strict mode, pytest asyncio auto-mode
- Dev deps properly declared in `pyproject.toml` `[project.optional-dependencies] dev`

**Evidence**: `cli/main.py`, `cli/_doctor.py`, `pyproject.toml`

**Gaps**
- mypy has `ignore_errors = true` blanket on 10+ modules

**Milestones**
- [x] Top-level `atlasbridge adapters` command with `--json` (Sprint 2026-02-21)
- [ ] Remove `ignore_errors = true` from mypy config, fix type errors module by module

---

### Observability (9/10)

**Strengths**
- 14 structured audit event types (every critical path instrumented)
- PII hygiene: `value_length` stored instead of actual reply value
- JSONL decision trace with 10 MB rotation and 3 archives
- Per-criterion explain output (`✓`/`✗` per match criterion)
- `atlasbridge logs --tail --json` for streaming audit events
- `atlasbridge status --json` for daemon/session state
- `BaseAdapter.healthcheck()` and `BaseChannel.healthcheck()` for probing

**Evidence**: `core/audit/writer.py`, `core/autopilot/trace.py`, `core/policy/evaluator.py`

**Gaps**
- No real-time streaming beyond `tail`; no webhook/push notification for operators
- Metrics (latency histograms, prompt throughput) are not tracked

**Milestones**
- [ ] Add prompt-to-injection latency metric to audit events
- [ ] Add optional Prometheus `/metrics` endpoint or StatsD push

---

### Testing (9/10)

**Strengths**
- 5 test tiers: unit, integration, policy, prompt_lab, e2e
- 685 tests passing across 56 test files
- Exhaustive migration tests (18 tests covering fresh, upgrade, partial, idempotency, CRUD)
- 8 integration tests for the `adapters` CLI command (exit codes, JSON schema, field validation, sorting)
- 20 Prompt Lab scenarios with deterministic PTY mock
- Policy v1 matching tests: 748 lines covering `any_of`, `none_of`, `session_tag`
- Every new CLI feature ships with corresponding tests

**Evidence**: `tests/unit/test_migrations.py`, `tests/integration/test_cli.py`, `tests/policy/test_policy_v1_matching.py`, `tests/prompt_lab/`

**Gaps**
- `fail_under = 50` is a low floor (should raise to 65)
- `e2e/` directory is empty (only `__init__.py`)

**Milestones**
- [x] Add exhaustive schema migration tests (Sprint 2026-02-21)
- [x] Add CLI integration tests for `adapters` command (Sprint 2026-02-21)
- [ ] Raise `fail_under` to 65, then 75
- [ ] Write at least 3 e2e tests (daemon startup + prompt + reply cycle)
- [ ] Add router integration test with real SQLite and mocked channel

---

### Security (9/10)

**Strengths**
- `SecretStr` for all tokens in Pydantic models (no accidental logging)
- Token format validation at config-load time (regex for Telegram, prefix for Slack)
- `reject_auto_approve()` — model-level prohibition of `yes_no_safe_default = "y"`
- File permissions: config `0o600`, data dirs `0o700`
- Keyring integration (macOS Keychain / Linux Secret Service)
- Regex safety timeout via `signal.SIGALRM` (100ms) in policy evaluator
- Identity allowlist enforced at channel level AND router level (defense in depth)
- All SQL uses parameterized bindings; bandit runs in CI
- Migration errors never leak DB contents — only path and version info

**Evidence**: `core/config.py`, `core/keyring_store.py`, `core/policy/evaluator.py`, `core/store/migrations.py`

**Gaps**
- `update_session(**kwargs)` builds column names from caller-supplied keys (trusted internal, but no allowlist)

**Milestones**
- [x] Migration errors expose only safe metadata (path, version) not DB contents (Sprint 2026-02-21)
- [ ] Add column allowlist to `update_session()` to prevent accidental SQL column injection
- [ ] Add `detect-secrets` to pre-commit hook (already a dependency)

---

### Product Thinking (9/10)

**Strengths**
- 5 annotated policy presets with deployment checklists and `WARNING:` comments
- 35+ docs covering architecture, threat model, red-team, troubleshooting
- Versioned policy DSL (v0 → v1) with migration path
- Backwards compatibility: `AegisError` alias, `AEGIS_CONFIG` env var, auto-migration
- 16-release roadmap with logical progression (correctness → UX → autonomy → hardening)
- Enterprise module stubs with architecture docs (deliberate signaling without shipping half-baked)
- Ergonomic CLI: top-level shortcuts for common operations (`adapters`, `pause`, `resume`)
- `skills.md` engineering maturity ledger for tracking growth across sprints

**Evidence**: `config/policies/`, `docs/threat-model.md`, `docs/red-team-report.md`, `skills.md`

**Gaps**
- Enterprise modules are all stubs (expected for pre-1.0)

**Milestones**
- [x] Engineering maturity ledger (`skills.md`) for cross-sprint tracking (Sprint 2026-02-21)
- [ ] Add CHANGELOG.md following Keep a Changelog format
- [ ] Ship at least one enterprise module to production (audit integrity or RBAC)

---

## Sprint Log

### Sprint 2026-02-21: Schema Migration System

**Trigger**: `sqlite3.OperationalError: no such column: timestamp` crash on upgrade

**Changes**
- Created `src/atlasbridge/core/store/migrations.py` — migration framework using `PRAGMA user_version`
- Rewrote `database.py` `connect()` — removed inline DDL, delegates to `run_migrations()`
- Fixed `append_audit_event()` — explicit timestamp (ALTER TABLE can't use expression defaults)
- Added `tests/unit/test_migrations.py` — 18 tests covering all upgrade scenarios

**Scores moved**
- DB Discipline: 7 → 9 (+2) — proper migration system, idempotent upgrades, crash recovery
- Testing: 6 → 7 (+1) — exhaustive migration test coverage added

**Lessons learned**
1. `CREATE TABLE IF NOT EXISTS` does NOT add missing columns to existing tables — it's a no-op when the table exists. Never rely on it for schema evolution.
2. `ALTER TABLE ADD COLUMN` only supports constant defaults, not expression defaults like `datetime('now')`. Always provide computed values explicitly in INSERT statements.
3. `PRAGMA user_version` is superior to a `schema_version` table: it's atomic, doesn't require a transaction, and can't get corrupted by partial DDL.
4. Migration order matters: check for future versions (`>`) before checking for current version (`==`), otherwise the equality check swallows the error case.

### Sprint 2026-02-21b: Adapters Command + Test Coverage Push

**Trigger**: `atlasbridge adapters` command missing; test coverage gap

**Changes**
- Added top-level `atlasbridge adapters` command to `cli/main.py` — reuses `AdapterRegistry.list_all()`
- `--json` output includes `enabled` (checks if tool binary is on PATH), `source`, `kind` fields
- Human-readable output shows sorted adapters with PATH status and count
- Added 8 integration tests to `tests/integration/test_cli.py` covering:
  - Help text includes `adapters`; exit code 0; all builtins listed
  - `--json` valid; field schema; claude present; sorted output; count >= 5
- Updated `skills.md` with sprint log and score adjustments

**Scores moved**
- Architecture: 8 → 9 (+1) — registry-driven command, no hardcoded names
- Reliability: 8 → 9 (+1) — crash-safe migration with recovery
- DX: 8 → 9 (+1) — ergonomic top-level shortcut, proper dev deps
- Testing: 7 → 9 (+2) — 685 tests, new CLI integration suite
- Security: 8 → 9 (+1) — safe error surfaces in migration
- Product Thinking: 8 → 9 (+1) — skills ledger, CLI ergonomics

**Lessons learned**
1. CLI subgroup nesting (`adapter list`) hurts discoverability — top-level shortcuts improve DX.
2. `shutil.which()` is a cheap, portable way to check if a tool binary is available for the `enabled` field.
3. Sorted JSON output is important for deterministic tests and scripting.

---

## Next Focus Area

**All areas at 9/10.** Next push toward 10/10:
1. **Testing**: Raise `fail_under` to 65; write e2e tests for daemon lifecycle
2. **Architecture**: Expose adapter `detectors` via public method
3. **DX**: Remove mypy `ignore_errors = true` blanket
