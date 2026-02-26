# CLAUDE.md — AtlasBridge Project Context

This file is read by Claude Code automatically. It provides project context for working on this codebase. Detailed reference material lives in `.claude/rules/`.

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

## Reference (see `.claude/rules/`)

Detailed reference material is in `.claude/rules/repo-reference.md`:
- Repository layout (full directory tree)
- Key files table (30+ entries)
- Architecture data flow diagram
- Policy module layout
- Version roadmap

Additional rules files:
- `.claude/rules/memory-profile.md` — project identity and technical profile
- `.claude/rules/memory-preferences.md` — confirmed user workflow preferences
- `.claude/rules/memory-decisions.md` — decision logging format and standards
- `.claude/rules/memory-sessions.md` — session logging format and standards

---

## UI module

`src/atlasbridge/ui/` is the canonical UI module. It contains state types (`state.py`), services (`services.py`), screens, components, CSS, and the Textual app. The legacy `tui/` indirection layer was removed.

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

Full policy module layout → `.claude/rules/repo-reference.md`

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

Formatting rules for each memory type → `.claude/rules/memory-*.md`
