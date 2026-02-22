# Project Automation Prompt — Sprint-Driven Development with Claude Code

> Drop this into your project's `CLAUDE.md` or use it as a system prompt.
> Replace all `{{PLACEHOLDER}}` values with your project's specifics before use.
> Delete this header block after customizing.

---

## CLAUDE.md Section: Sprint Automation & Project Governance

### What This Project Uses

This project follows a sprint-driven, tier-ordered development workflow managed via:
- **GitHub Issues** — all work tracked as issues, no work happens without an issue
- **GitHub Projects v2** — project board for sprint planning, status tracking, and prioritization
- **GitHub Wiki** — living documentation updated with every completed issue
- **Feature branches** — every issue gets its own branch, squash-merged via PR
- **Persistent memory** — Claude Code memory files capture engineering knowledge across sessions
- **Tiered execution** — issues worked in strict priority order, never randomly
- **Test-gated progression** — cannot move to next issue until all tests pass

---

### Engineering Memory System (MANDATORY)

You have persistent memory files. **Update them continuously while working — not at the end.**

| Trigger | Action |
|---------|--------|
| Architecture decision made | Update `memory-decisions.md` with date, context, tradeoffs |
| Phase/milestone reached | Update `memory-roadmap.md` |
| Bug root cause identified | Update `memory-debugging.md` |
| New subsystem introduced | Update `memory-architecture.md` |
| Workflow improvement | Update `memory-devex.md` |
| Completing substantive work | Update `memory-sessions.md` |
| Testing strategy change | Update `memory-testing.md` |
| Sprint progress change | Update `memory-sprint-execution-order.md` |
| New issue discovered during work | Update `memory-sprint-execution-order.md` with new issue in correct tier |
| Coverage or CI change | Update `MEMORY.md` quick reference |

**Memory file structure** (create these in your auto-memory directory):

| File | Purpose |
|------|---------|
| `MEMORY.md` | Index + quick reference (version, test count, coverage, CI status, project board ID) |
| `memory-architecture.md` | Subsystem descriptions, component boundaries, data flow |
| `memory-decisions.md` | Dated architecture and design decisions with tradeoffs |
| `memory-debugging.md` | Root cause analyses, recurring error patterns, fix strategies |
| `memory-devex.md` | Developer workflow improvements, tooling notes, CI learnings |
| `memory-testing.md` | Testing strategy, coverage patterns, mock techniques |
| `memory-roadmap.md` | Phase progress, milestone tracking, version history |
| `memory-sessions.md` | Engineering session log — substantive work per session |
| `memory-sprint-execution-order.md` | **Issue priority framework — tier order for sprints** |

**Principles:**
- Capture WHY decisions were made, not just WHAT changed
- Write for future sessions — you will lose context between conversations
- Never store secrets, tokens, or personal data
- Date all decision entries
- **DO NOT ASK. Update memory files automatically when engineering knowledge is gained.**

---

### Branching Model

- `main` — always releasable, only PRs land here
- `feature/<issue-number>-<short-description>` — feature work (e.g., `feature/42-add-auth`)
- `fix/<issue-number>-<short-description>` — bug fixes (e.g., `fix/55-null-pointer`)
- `docs/<issue-number>-<short-description>` — docs-only changes
- `chore/<issue-number>-<short-description>` — CI, config, dependency changes
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
- PRs squash-merge to main after CI green
- **Never push directly to main**
- **Never force-push to main**
- **One issue per branch** — do NOT fix unrelated things in the same branch (see Scope Discipline)

---

### Tier-Ordered Issue Execution

Issues are organized into tiers. **NEVER pick issues randomly.** Always follow tier order.

```
Tier 1: Quick Wins        — < 1 hour, unblock other work, fix drift, version bumps
Tier 2: CI & Test Infra   — improves the safety net all future PRs run through
Tier 3: Code Quality      — reduces tech debt, type safety, linting, refactors
Tier 4: Core Features     — the main deliverables for the current phase
Tier 5: Documentation     — document what's shipped, not what's planned
Tier 6: Release Prep      — freeze window, version tag, publish, release notes
```

**Rules:**
- Complete ALL items in current tier before moving to next
- Within a tier, follow the defined order number
- If an issue is blocked by an incomplete dependency, skip it and take the next one in the same tier
- Foundation before features, dependencies before dependents
- Quick wins (Tier 1) should be cleared in every sprint, even if focus is elsewhere
- **Post-v1.0 / future-phase issues are NEVER pulled into current-phase sprints**

Create a `memory-sprint-execution-order.md` file that lists all issues by tier with order numbers. Update it whenever issues are created, completed, re-prioritized, or discovered during work.

---

### "start sprint" / "continue sprint" Workflow

When the user says **"start sprint"** or **"continue sprint"**, execute this exact sequence:

#### Phase 1: Preparation
1. Read `memory-sprint-execution-order.md` — identify next issues by tier order
2. `git checkout main && git pull` — ensure you're on latest main
3. Check for any open PRs that need merging first:
   ```
   gh pr list --state open
   ```
4. Merge all open PRs sequentially:
   - `gh pr checks <N>` — ALL CI checks must be green
   - Verify no merge conflicts
   - Fix any failing checks before proceeding
   - `gh pr merge <N> --squash`
   - `git checkout main && git pull`
   - Wait for main CI to pass before merging next PR
5. Confirm clean state:
   ```
   git status                    # must be clean
   git log --oneline -5          # verify latest commits
   {{TEST_COMMAND}}              # all tests pass on main before starting
   ```

#### Phase 2: Execute Issues (in tier order)

**Max items per sprint:** 10. Stop after 10 issues or when the user says stop.

For each issue, in order:

---

**Step 1 — Setup**
```
git checkout main && git pull
git checkout -b feature/<issue-number>-<short-name>
```

**Step 2 — Read & Plan**
- Read the full issue description from GitHub: `gh issue view <N>`
- Understand scope, acceptance criteria, and required tests
- If the issue is unclear, ask the user before starting implementation
- If the issue depends on another incomplete issue, skip it and note in sprint log

**Step 3 — Implement**
- Write the code changes
- **Write new tests for every change** (see Testing Rules — this is non-negotiable)
- Follow existing code patterns and conventions in the codebase
- **Scope discipline:** Only fix what the issue describes. If you discover something else that needs fixing, create a new issue (see Discovered Issues below) — do NOT fix it in this branch

**Step 4 — Verify (HARD GATE — do NOT proceed if this fails)**
```
{{LINT_COMMAND}}              # e.g., ruff check .
{{FORMAT_COMMAND}}            # e.g., ruff format --check .
{{TYPE_CHECK_COMMAND}}        # e.g., mypy src/
{{TEST_COMMAND}}              # e.g., pytest -q
{{COVERAGE_COMMAND}}          # e.g., pytest --cov=mypackage -q
```
**ALL checks must pass. If ANY fail:**
1. Fix the failure
2. Re-run ALL checks (not just the one that failed)
3. Only proceed once everything is green
4. **Do NOT move to the next issue with failing tests. Ever.**

**Step 5 — Ship**
```
git add <specific files>
git commit -m "<type>(scope): <description>

Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin feature/<issue-number>-<short-name>
gh pr create --title "<conventional commit title>" --body "$(cat <<'EOF'
## Summary
<1-3 bullet points>

## Tests added
<List new test files/classes/methods>

## Verification
<Commands to verify>

Closes #<issue-number>
EOF
)"
```
Wait for CI:
- `gh pr checks <N>` — all must pass
- If CI fails, fix locally, push, wait again
- Once ALL green:
```
gh pr merge <N> --squash
git checkout main && git pull
```

**Step 6 — Close & Update (MANDATORY — do this after EVERY issue)**

1. **GitHub Issue** — verify closed (auto-closes via `Closes #N` in PR body). If not, close manually with summary comment:
   ```
   gh issue close <N> --comment "Fixed in #<PR>. <One-line summary of what changed.>"
   ```

2. **GitHub Project Board** — verify status is `Done`. Set fields if needed:
   ```
   # Find item ID
   gh project item-list {{PROJECT_NUMBER}} --owner {{GITHUB_USER}} --format json | python3 -c "..."
   # Update status to Done if not auto-updated
   ```

3. **GitHub Wiki** — update relevant pages:
   ```
   cd /tmp && rm -rf {{PROJECT}}.wiki
   git clone {{WIKI_CLONE_URL}} /tmp/{{PROJECT}}.wiki
   # Update: Project-Status, Sprint-Board, Changelog, and any affected pages
   cd /tmp/{{PROJECT}}.wiki && git add -A && git commit -m "docs: update for #<issue>" && git push
   ```

4. **CHANGELOG.md** — add entry under current version:
   ```markdown
   ### [Unreleased]
   - <type>: <description> (#<issue>)
   ```

5. **README.md** — update if version, test count, coverage, or milestone changed

6. **docs/** — update if the change affects architecture, setup, CLI, or user-facing behavior

7. **Memory files** — update ALL relevant files:
   - `memory-sessions.md` — log what was done
   - `memory-sprint-execution-order.md` — mark issue as complete, note any new issues added
   - `MEMORY.md` — update test count, coverage, version if changed
   - Any other relevant memory file (decisions, debugging, architecture, etc.)

**Step 7 — Next issue**
Return to Step 1 for the next issue in tier order. Stop after 10 issues or when told to stop.

---

### Discovered Issues (CRITICAL — handle during implementation)

While working on any issue, you WILL discover things that need fixing but are out of scope. **Do NOT fix them in the current branch.** Instead:

1. **Create a new GitHub issue immediately:**
   ```
   gh issue create --title "<type>: <description>" --body "$(cat <<'EOF'
   ## Context
   Discovered while working on #<current-issue>. Out of scope for that fix.

   ## Problem
   <What's wrong or missing>

   ## Suggested fix
   <Brief description of the fix>

   ## Tests Required
   <What tests should be added>

   ## Scope
   <XS/S/M/L effort estimate>
   EOF
   )" --label "<appropriate-label>"
   ```

2. **Add it to the project board as Backlog:**
   ```
   gh project item-add {{PROJECT_NUMBER}} --owner {{GITHUB_USER}} --url <new-issue-url>
   ```

3. **Set project board fields** (Priority, Phase, Effort):
   ```
   # Get the item ID and set fields appropriately
   ```

4. **Add it to the sprint execution order** — place it in the correct tier in `memory-sprint-execution-order.md`

5. **Continue working on the current issue** — do not context-switch

**Examples of discovered issues:**
- You find a function with no error handling while adding tests → create issue "fix: add error handling to X"
- You notice a TODO comment that should be addressed → create issue "chore: resolve TODO in Y"
- You see an undocumented function while reading code → create issue "docs: document Z"
- A test reveals a bug in unrelated code → create issue "fix: bug in W discovered via test"
- CI config is missing a check → create issue "chore(ci): add X check to pipeline"
- You notice a dependency is outdated → create issue "chore(deps): update X"
- Coverage report shows a gap in an unrelated module → create issue "test: improve coverage for X"

**Rule: Every piece of work must have an issue. No orphan fixes. No drive-by changes.**

---

### Blocked Issues

If an issue is blocked:

1. **Identify the blocker** — is it a dependency on another issue, a missing tool, or unclear requirements?
2. **If blocked by another issue:** Skip it, note the dependency in the issue comment, move to the next issue in tier order
3. **If blocked by unclear requirements:** Ask the user immediately. Do not guess.
4. **If blocked by a bug you just found:** Create a new issue for the bug (see Discovered Issues), add it as a blocker, skip the current issue
5. **Update the project board:** Add `Blocked By` field if available, or note in the issue comment
6. **Update `memory-sprint-execution-order.md`:** Note the block and any re-ordering needed

---

### Scope Discipline (CRITICAL)

**One issue = one branch = one PR = one concern.**

- Do NOT fix unrelated things you notice while working on an issue
- Do NOT refactor surrounding code unless the issue specifically asks for it
- Do NOT add features beyond what the issue describes
- Do NOT update docs unrelated to the current issue
- Do NOT "while I'm here" anything — create a new issue instead

**The only exception:** If your change breaks an existing test, you must fix the test in the same PR. But if you find a test that was ALREADY broken, that's a discovered issue.

---

### Testing Rules (NON-NEGOTIABLE)

**Every issue MUST include new tests.** The only exception is pure docs-only issues with no code changes.

| Change Type | Required Tests |
|-------------|---------------|
| New function/method | Unit tests covering happy path + at least 2 edge cases |
| New class | Unit tests for construction, public methods, edge cases |
| Bug fix | Regression test that FAILS without the fix, PASSES with it |
| Config/CI change | Test that verifies new config is applied correctly |
| CLI command change | Smoke test or integration test for the command |
| API endpoint | Request/response test for happy path + error cases |
| Refactor | Existing tests must pass; add tests if coverage drops |
| Dependency update | Verify existing tests still pass; add test if behavior changed |
| Docs-only | No code tests required, but verify code examples compile/run if applicable |

**Test quality standards:**
- Tests must be deterministic — no flaky tests, no time-dependent assertions
- Tests must be fast — unit tests < 1s each, total suite < 60s ideally
- Tests must be independent — no test should depend on another test's state
- Test names must describe what they verify: `test_<what>_<condition>_<expected>`
- Mock external dependencies (network, filesystem, OS) — don't rely on environment

**Coverage gate:**
```
# After EVERY change, verify:
{{TEST_COMMAND}}              # All tests pass
{{COVERAGE_COMMAND}}          # Coverage meets or exceeds floor
```

**If coverage drops below the floor:**
1. Add tests to bring it back up
2. Do NOT merge until coverage is restored
3. Do NOT add `# pragma: no cover` to skip coverage — that's gaming the metric

**If a test fails that you didn't change:**
1. Investigate whether your change caused it
2. If yes: fix it in this branch
3. If no: it was already broken — create a discovered issue, do NOT fix it here

---

### Issue Creation Standards

When creating new issues (including discovered issues), always include:

```markdown
## Context
<Why this issue exists — what problem does it solve? If discovered during another issue, reference it.>

## Problem
<What's currently wrong or missing>

## Changes Required
<Specific files and changes needed, as detailed as possible>

## Tests Required
<What new tests must be written — be specific about test names/scenarios>

## Verification
<Exact commands to verify the fix locally>

## Scope
<Effort estimate: XS (< 30 min) / S (< 2 hours) / M (< 1 day) / L (multi-day)>
```

**After creating every issue:**

1. **Label it** with phase + category:
   - Phase: `{{PHASE_LABEL_PREFIX}}:1-core`, `{{PHASE_LABEL_PREFIX}}:2-features`, etc.
   - Category: `bug`, `enhancement`, `documentation`, `hardening`

2. **Add to project board:**
   ```
   gh project item-add {{PROJECT_NUMBER}} --owner {{GITHUB_USER}} --url <issue-url>
   ```

3. **Set project board fields** (Priority, Phase, Effort) using the project field IDs

4. **Add to sprint execution order** — update `memory-sprint-execution-order.md` with the new issue in the correct tier and position

---

### Hotfix / Urgent Issues

If the user reports an urgent issue that must bypass tier order:

1. Create the issue as normal
2. Label it `P0 — Critical`
3. Work it immediately (it jumps the queue)
4. Follow the same branch → test → PR → merge → update flow
5. After merging, return to the normal tier order

**Only the user can declare something P0.** Never self-promote an issue to P0.

---

### Version Bumping

- **Patch bump** (0.0.X): bug fixes, config changes, docs
- **Minor bump** (0.X.0): new features, new commands, new modules
- **Major bump** (X.0.0): breaking changes (only user can approve)

When bumping a version:
1. Update version in all locations (check `__init__.py`, `pyproject.toml`, and any other version references)
2. Update `CHANGELOG.md` — move `[Unreleased]` entries to the new version heading
3. Commit: `chore: bump version to X.Y.Z`
4. **Do NOT tag unless the user explicitly asks** — tagging triggers publish pipelines

---

### Sprint End / Retrospective

When the sprint is complete (all planned issues done, or user says stop):

1. **Update `memory-sessions.md`** with sprint summary:
   ```markdown
   ## YYYY-MM-DD: Sprint SN — <theme>
   **Issues completed:** #X, #Y, #Z
   **Issues discovered:** #A, #B (added to backlog)
   **Issues blocked:** #C (blocked by #D)
   **Test count:** before → after
   **Coverage:** before → after
   ```

2. **Update `MEMORY.md`** quick reference with current stats

3. **Update the wiki** Sprint-Board page with final sprint status

4. **Report to user:**
   - Issues completed (count + list)
   - Issues discovered and added to backlog (count + list)
   - Issues blocked (count + list with reasons)
   - Test count before/after
   - Coverage before/after
   - Any decisions made or risks identified

---

### Post-Issue Completion Checklist (CRITICAL)

After completing ANY issue, ALWAYS verify ALL of the following:

- [ ] **All tests pass locally** — `{{TEST_COMMAND}}` is green
- [ ] **Coverage floor met** — `{{COVERAGE_COMMAND}}` meets threshold
- [ ] **CI green on PR** — `gh pr checks <N>` all pass
- [ ] **PR merged** — squash-merged to main
- [ ] **GitHub Issue closed** — with summary comment
- [ ] **GitHub Project Board** — status is `Done`
- [ ] **GitHub Wiki updated** — Project-Status, Sprint-Board, and affected pages
- [ ] **CHANGELOG.md** — entry added
- [ ] **README.md** — updated if version/test count/coverage/milestone changed
- [ ] **docs/** — updated if change affects architecture, setup, or user-facing behavior
- [ ] **Memory files** — session log, sprint execution order, and relevant memory files updated
- [ ] **No leftover branches** — delete the feature branch after merge

**If any item is missed, go back and complete it before starting the next issue.**

---

### Project Board Setup

GitHub Projects v2 board with these fields:

| Field | Type | Options |
|-------|------|---------|
| Status | Single Select | `Backlog`, `Planned`, `In Progress`, `In Review`, `Done` |
| Priority | Single Select | `P0 — Critical`, `P1 — High`, `P2 — Normal`, `P3 — Low` |
| Phase | Single Select | Your project's phases (e.g., `1. Core`, `2. Features`, `3. Polish`, `4. Release`) |
| Effort | Single Select | `XS` (< 30 min), `S` (< 2 hr), `M` (< 1 day), `L` (multi-day) |
| Sprint | Text | `S1`, `S2`, `S3`, ... |
| Blocked By | Text | Issue numbers that block this item |

**Field updates during sprint:**
- When starting an issue: set Status = `In Progress`
- When PR is created: set Status = `In Review`
- When PR is merged: set Status = `Done`
- When a new issue is discovered: set Status = `Backlog`, set Priority/Phase/Effort

---

### Wiki Structure

Maintain these wiki pages (create if they don't exist):

| Page | Content |
|------|---------|
| `Home` | Project overview, quick links, how to contribute |
| `Project-Status` | Current version, test count, coverage, CI status, last updated date |
| `Sprint-Board` | Current sprint number, issues in progress, completed, blocked |
| `Roadmap` | Phase descriptions, milestone tracking, what's next |
| `Architecture` | System design, component boundaries, data flow |
| `Changelog` | Release history (mirrors CHANGELOG.md) |
| `Testing` | How to run tests, coverage policy, test patterns |

**Update the wiki after every issue completion**, not at the end of a sprint.

Wiki workflow:
```bash
# Clone (or pull if already cloned)
cd /tmp && rm -rf {{PROJECT}}.wiki
git clone {{WIKI_CLONE_URL}} /tmp/{{PROJECT}}.wiki

# Make updates to relevant .md files

# Push
cd /tmp/{{PROJECT}}.wiki && git add -A && git commit -m "docs: update for #<issue>" && git push
```

---

### Security Rules

- **Never commit secrets** — no API keys, tokens, passwords, or credentials in code or config
- **Never commit `.env` files** — add to `.gitignore`
- **Use `git add <specific files>`** — never `git add .` or `git add -A` blindly
- **Review diffs before committing** — `git diff --staged` to verify no secrets
- **If a secret is accidentally committed:** alert the user immediately, do NOT try to fix it silently

---

### Configuration — Replace These Placeholders

Before using this prompt, find-and-replace all placeholders:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{LINT_COMMAND}}` | Linter command | `ruff check .` |
| `{{FORMAT_COMMAND}}` | Formatter check command | `ruff format --check .` |
| `{{TYPE_CHECK_COMMAND}}` | Type checker command | `mypy src/` |
| `{{TEST_COMMAND}}` | Test runner command | `pytest -q` |
| `{{COVERAGE_COMMAND}}` | Coverage command with floor | `pytest --cov=mypackage -q` |
| `{{WIKI_CLONE_URL}}` | Wiki git URL | `https://github.com/user/repo.wiki.git` |
| `{{PROJECT}}` | Project short name | `myproject` |
| `{{PROJECT_NUMBER}}` | GitHub Projects v2 number | `17` |
| `{{GITHUB_USER}}` | GitHub username or org | `abdulraoufatia` |
| `{{PHASE_LABEL_PREFIX}}` | Label prefix for phases | `phase` |

---

### Summary: What Makes This Work

1. **Tiers enforce order** — no cherry-picking easy issues while hard ones rot
2. **Tests on every issue** — quality ratchets up, never down
3. **CI gate before merge** — broken code never lands on main
4. **Discovered issues go to backlog** — nothing is lost, nothing is out-of-scope-fixed
5. **Memory files** — knowledge persists across sessions, no repeated discovery
6. **Wiki updates inline** — documentation stays current, not a sprint-end chore
7. **Branch per issue** — clean history, easy reverts, isolated work
8. **Scope discipline** — one issue, one branch, one concern
9. **Post-completion checklist** — nothing falls through the cracks
10. **Sprint retrospective** — progress is visible and measurable
