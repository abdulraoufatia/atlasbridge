# AtlasBridge Multi-Agent Development Workflow

**Version:** 0.2.0
**Status:** Design
**Last updated:** 2026-02-21

---

## 1. Overview

AtlasBridge is built using a multi-agent engineering organization. Each agent has a defined role, a specific set of owned files, and a defined interface for handing off work to adjacent roles. This document describes how the organization works and how to operate within it effectively.

The multi-agent model exists because different parts of the codebase have fundamentally different concerns. OS-level PTY mechanics are not the same problem as Telegram bot formatting, and both are different from writing clear CLI help text. By assigning each concern to a specialist role, we prevent cross-cutting changes from creating confusion about ownership and we make it easier to review work at each boundary.

### Agent roles

| Role | Short name | Primary concerns |
|---|---|---|
| Principal Systems Architect | Architect | Architecture, PRD, cross-cutting design decisions, interface specs |
| Staff Platform Engineer | Platform | `src/atlasbridge/os/`, `src/atlasbridge/core/`, daemon lifecycle, CI pipeline |
| Staff Integrations Engineer | Integrations | `src/atlasbridge/adapters/`, CLI tool compatibility, adapter testing |
| Staff Channel Engineer | Channel | `src/atlasbridge/channels/`, Telegram, Slack, WhatsApp channel implementations |
| QA/Reliability Engineer | QA | `tests/`, Prompt Lab, CI gating matrix, coverage enforcement |
| Docs/DX Engineer | Docs | `docs/`, `README.md`, `CLAUDE.md`, CLI help text, changelog |

No role owns production code outside its primary concern. Cross-cutting changes (e.g., a new field on `AtlasBridgeConfig`) go through the Architect, who drafts the interface spec before any implementation begins.

---

## 2. Branch Model

### Branch naming

| Branch pattern | Purpose |
|---|---|
| `main` | Always releasable; protected; direct pushes blocked |
| `design/v*` | Design releases only: docs, interface stubs, no production code |
| `feature/*` | One active feature implementation at a time |
| `fix/*` | Hotfixes targeting `main` |
| `test/*` | Isolated test additions (no production code changes) |
| `chore/*` | Dependency bumps, CI config, tooling |

### main is always releasable

`main` is the only branch that can be tagged for release. It must pass all CI checks at all times. The rule is simple: if you cannot tag `main` right now and ship it, something is wrong.

No work-in-progress code merges to `main`. A feature branch that is 80% done stays on the feature branch. The feature only lands on `main` when it is complete, tested, and documented.

### design/* branches

Design branches carry design artifacts only: Markdown documents, architecture diagrams, updated `CLAUDE.md`, and interface stubs (Python files with `raise NotImplementedError` bodies and complete docstrings). They do not carry any production logic.

Design branches can be merged to `main` as soon as CI passes (lint, type check on stubs, and docs build). This allows the team to make design decisions visible and reviewable without blocking on implementation.

### One active feature branch

Only one `feature/*` branch is active at a time. This is not a technical constraint; it is a workflow constraint. Multiple concurrent feature branches create merge conflicts that slow everyone down and make it harder to reason about what is in `main`.

When a feature branch lands, the next feature branch is created from the new `main`. Feature branches branch from `main`, not from each other.

### Commit convention

All commits use Conventional Commits:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Types:
- `feat`: new capability visible to users
- `fix`: bug fix
- `docs`: documentation only
- `chore`: tooling, CI, dependencies — no user-visible changes
- `test`: adding or updating tests — no production code changes
- `refactor`: code restructure with no behavior change

Scope examples: `pty`, `detector`, `telegram`, `cli`, `config`, `audit`, `lab`, `ci`.

Examples:
```
feat(detector): add MED-confidence structural pattern for numbered lists
fix(pty): release injection gate on write timeout to prevent deadlock
docs(cli): add atlasbridge run --dry-run example to cli-ux.md
test(lab): add QA-019 echo loop regression scenario
chore(ci): pin ubuntu-latest to ubuntu-22.04 for reproducibility
```

### PR requirements

Before a PR can be merged to `main`:
1. All CI checks must be green (see Section 7).
2. At least one review approval.
3. No unresolved review comments.
4. Squash merge only — the PR becomes a single commit on `main`. The PR title becomes the commit message, so it must follow Conventional Commits.

---

## 3. Agent Role Assignments

### Principal Systems Architect

**Owns:** `docs/architecture.md`, `docs/reliability.md`, `docs/data-model.md`, `docs/threat-model.md`, `docs/policy-engine.md`, `docs/tool-interception-design.md`, `docs/approval-lifecycle.md`, PRD

**Responsibilities:**
- Draft interface specs for new features before any implementation begins.
- Own major design decisions and document them in `docs/architecture.md` or a new doc.
- Review PRs that touch interfaces between subsystems (e.g., changes to `PromptDetector` API, new fields on `AtlasBridgeConfig`, changes to the SQLite schema).
- Maintain the roadmap and milestone definitions.

**Does not own:** Any file in `src/` or `tests/`.

### Staff Platform Engineer

**Owns:** `src/atlasbridge/os/` (PTY backend, OS abstraction), `src/atlasbridge/core/` (config, constants, exceptions), `src/atlasbridge/bridge/pty_supervisor.py`, daemon lifecycle, `.github/workflows/`

**Responsibilities:**
- Implement and maintain the PTY supervisor and OS backend.
- Own the asyncio event loop, injection gate, echo suppression, and stall_watchdog.
- Maintain the CI pipeline (GitHub Actions workflow files).
- Respond to Prompt Lab failures caused by PTY-layer bugs.

**Interface with Architect:** Receives interface specs via `docs/`. Does not change the interface unilaterally.

### Staff Integrations Engineer

**Owns:** `src/atlasbridge/adapters/`, adapter test fixtures under `tests/adapters/`

**Responsibilities:**
- Implement and maintain tool adapters (Claude, OpenAI, Gemini CLI, etc.).
- Test compatibility of `atlasbridge run` with each supported CLI tool.
- Maintain the `atlasbridge adapter list` output and adapter capability matrix.
- Coordinate with the Platform Engineer when a new tool requires PTY-layer changes.

### Staff Channel Engineer

**Owns:** `src/atlasbridge/channels/`, `tests/channels/`

**Responsibilities:**
- Implement and maintain channel integrations: Telegram, Slack, WhatsApp.
- Own the `BaseChannel` abstract class and its contract.
- Implement message formatting, keyboard building, and reply routing for each channel.
- Maintain QA-010 through QA-017 (channel-specific Prompt Lab scenarios).

**Interface with Platform:** Receives `PromptEvent` objects from the PTY supervisor via an asyncio queue. Does not read from the PTY directly.

### QA/Reliability Engineer

**Owns:** `tests/` (all test files), `tests/prompt_lab/`, CI gating matrix in `docs/reliability.md`

**Responsibilities:**
- Write and maintain the Prompt Lab scenario suite.
- Set and enforce coverage targets.
- Own the CI gating matrix; decide which scenarios gate which releases.
- Investigate and triage CI failures.
- Write regression scenarios for every bug fix (see regression protocol in `docs/reliability.md`).

**Does not own:** Production code in `src/`. The QA engineer writes tests that call production code through its public API.

### Docs/DX Engineer

**Owns:** `docs/cli-ux.md`, `docs/setup-flow.md`, `README.md`, `CLAUDE.md`, CLI help text strings in `src/atlasbridge/cli/main.py`

**Responsibilities:**
- Keep `CLAUDE.md` current as the source of truth for AI agents working on the codebase.
- Update `docs/cli-ux.md` whenever a command is added, changed, or removed.
- Write and maintain the `README.md` quick-start.
- Ensure CLI help text (`--help`) matches the UX spec.
- Maintain the `CHANGELOG.md`.

---

## 4. Feature Development Workflow

The following five-step workflow applies to every feature that is non-trivial (more than a single-file change):

### Step 1: Architect drafts the interface spec

The Architect writes a design document or updates an existing one in `docs/`. The spec must define:
- The public Python API (function signatures, return types, exceptions raised)
- The SQLite schema changes (if any)
- The Telegram message format (if any)
- The CLI command or flag (if any)
- The configuration keys (if any)

The spec is committed to a `design/v*` branch and merged to `main` before any implementation begins. This ensures all engineers are working against the same interface.

### Step 2: Engineers implement in parallel on sub-branches

Once the interface spec is merged, the Platform Engineer, Integrations Engineer, and Channel Engineer can work in parallel on their respective pieces. Each creates a sub-branch from `main` (e.g., `feature/pty-echo-suppression`).

Where the pieces must be integrated, they agree on the exact interface (Python types, asyncio queue format, database table names) from the spec. They do not change the interface without going back to Step 1.

### Step 3: QA engineer writes tests; they gate the PR

The QA engineer creates tests in parallel with the implementation. Tests are written against the interface spec, not against the implementation. This means the QA engineer can write tests before the implementation is complete.

The PR that implements the feature cannot be merged until the QA engineer's tests pass against it. The QA engineer reviews the implementation PR and asserts that the tests are sufficient.

### Step 4: Docs engineer updates affected documentation

When the implementation PR is ready for final review, the Docs engineer:
- Updates `docs/cli-ux.md` if a command changed.
- Updates `CLAUDE.md` if the architecture summary or key file table changed.
- Updates `README.md` if the quick-start example changed.
- Adds a `CHANGELOG.md` entry under the next version.

The Docs engineer's changes can be included in the feature PR or in a follow-up `docs/*` branch that merges immediately after the feature lands.

### Step 5: PR created, CI green, squash merge to main

The feature PR is created from the `feature/*` branch to `main`. It must:
- Pass all CI checks (see Section 7).
- Have a review approval from the Architect (for interface changes) or the Platform Engineer (for PTY-layer changes).
- Have a review approval from the QA engineer confirming test coverage.

The PR is squash-merged. The resulting commit message is the PR title in Conventional Commits format.

---

## 5. CLAUDE.md as the Source of Truth

`CLAUDE.md` is the first file any AI agent reads when starting a session on this codebase. It must be accurate at all times.

### What CLAUDE.md contains

- What AtlasBridge is (one paragraph, precise)
- What AtlasBridge is not (explicit anti-scope list)
- The minimal correctness invariants
- The architecture summary with ASCII diagram
- The key file table
- Dev commands (install, test, lint, type check)
- The current branching model and active branches
- The current scope (what is implemented vs. planned)

### Ownership and update discipline

The Docs engineer owns `CLAUDE.md`. Any other engineer who makes a change that affects the architecture summary, key file table, dev commands, or scope must file a follow-up PR or include `CLAUDE.md` changes in their own PR.

The rule: if you add a new key file, add it to `CLAUDE.md`. If you rename a module, update `CLAUDE.md`. If you change the dev commands (e.g., switch from `pip install` to `uv pip install`), update `CLAUDE.md`.

### What CLAUDE.md does not contain

- Detailed implementation notes (those go in module docstrings or `docs/`)
- Full API reference (that goes in `docs/`)
- Tutorial content (that goes in `README.md`)

`CLAUDE.md` is a briefing document, not a reference manual. It should be readable in under five minutes.

---

## 6. Testing Discipline

### Unit tests

Unit tests live in `tests/unit/`. They:
- Test pure functions and state machines only.
- Have no filesystem I/O (no real files, no real SQLite databases).
- Have no network I/O (no real Telegram calls).
- Have no PTY operations.
- Run in under 1ms each.
- Use `pytest` and `unittest.mock` only.

Examples of unit-testable code: `PromptDetector.feed()`, `decide_prompt()` SQL logic (mocked), config validation, ANSI strip function, audit log hash chain logic.

### Integration tests

Integration tests live in `tests/integration/`. They:
- Use a real SQLite database (in a `tmp_path` fixture; deleted after each test).
- Use mocked HTTP (via `respx` or `pytest-httpx`) for Telegram calls.
- Use the Prompt Lab simulator for PTY operations (no real processes).
- Run in under 1s each.

### E2E tests

E2E tests live in `tests/e2e/`. They:
- Start a real child process inside a real PTY.
- Use a mocked Telegram bot (the bot's HTTP client is replaced with a test double).
- Verify the full loop: process blocks → detector fires → Telegram message sent → reply injected → process resumes.
- Run in under 10s each.
- Are tagged `@pytest.mark.e2e` and can be skipped with `-m "not e2e"`.

### Coverage targets

| Module path | Coverage target |
|---|---|
| `src/atlasbridge/core/` | 80% line coverage |
| `src/atlasbridge/os/` | 80% line coverage |
| `src/atlasbridge/channels/telegram/` | 70% line coverage |
| `src/atlasbridge/adapters/` | 70% line coverage |
| `src/atlasbridge/cli/` | 60% line coverage (CLI wiring is hard to unit test) |

Coverage is measured by `pytest-cov` and reported in CI. A drop below the target is a CI failure.

### Prompt Lab gates releases

The Prompt Lab is not optional. Every PR that touches `src/atlasbridge/os/`, `src/atlasbridge/bridge/`, or `src/atlasbridge/policy/` must include a passing Prompt Lab run in CI. See `docs/reliability.md` for the full CI gating matrix.

---

## 7. CI Pipeline

The CI pipeline runs on every push to every branch. It must be green before any PR can merge. The pipeline runs on GitHub Actions.

### Jobs

#### Security Scan

```yaml
- name: Security Scan
  run: bandit -r src/atlasbridge/ -c pyproject.toml
```

Runs Bandit with the configuration in `pyproject.toml`. Findings at severity HIGH are blocking. Findings at severity MEDIUM are warnings. LOW is informational.

#### Lint and Type Check

```yaml
- name: Lint
  run: ruff check . && ruff format --check .
- name: Type Check
  run: mypy src/atlasbridge/
```

Ruff enforces the style and import rules defined in `pyproject.toml`. Mypy runs in strict mode on `src/atlasbridge/`. Type errors are blocking.

#### Tests (matrix)

The test job runs in a 2×2 matrix: Python 3.11 and 3.12, macOS and Linux.

```yaml
strategy:
  matrix:
    python-version: ["3.11", "3.12"]
    os: [macos-latest, ubuntu-22.04]
```

Each matrix cell runs:
```bash
pytest tests/unit/ tests/integration/ -q --cov=src/atlasbridge --cov-report=xml
```

Coverage is uploaded to Codecov from the macOS/3.11 cell only.

#### Build Distribution

```yaml
- name: Build
  run: python -m build
- name: Check dist
  run: twine check dist/*
```

Ensures the package builds cleanly and the metadata is valid. Does not publish.

#### Prompt Lab

```yaml
- name: Prompt Lab
  run: pytest tests/prompt_lab/ -v --tb=short
```

Runs on macOS and Linux (matching the test matrix). Runs after the test job. A failure here is blocking for any PR touching the detector, PTY supervisor, or injection logic.

---

## 8. How to Run Everything Locally

Install the project in editable mode with dev dependencies:

```bash
uv venv && uv pip install -e ".[dev]"
source .venv/bin/activate
```

Run the full test suite (unit + integration):

```bash
pytest tests/ -q
```

Run Prompt Lab scenarios:

```bash
pytest tests/prompt_lab/ -v
```

Run E2E tests:

```bash
pytest tests/e2e/ -v
```

Run Prompt Lab via the CLI:

```bash
atlasbridge lab run --all
```

Run all linting, formatting, type checking, and security scanning:

```bash
ruff check . && ruff format --check . && mypy src/atlasbridge/ && bandit -r src/atlasbridge/ -c pyproject.toml
```

Run a single Prompt Lab scenario:

```bash
atlasbridge lab run QA-004
pytest tests/prompt_lab/ -k QA-004 -v
```

Check coverage locally:

```bash
pytest tests/unit/ tests/integration/ --cov=src/atlasbridge --cov-report=term-missing
```
