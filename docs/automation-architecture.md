# Automation Architecture — Safe Project Self-Management

> This document describes the GitHub Actions automation layer for the AtlasBridge project board. All automation is metadata-only: it classifies issues, syncs statuses, rotates sprints, and enforces governance gates. It never auto-merges, never writes code, and never pushes to main.

---

## Purpose

Manual project management creates overhead and drift. This automation layer keeps the "AtlasBridge — Master Roadmap" project board accurate with zero human toil for routine operations:

1. **Issue triage** — new issues are classified and added to the project board automatically
2. **PR status sync** — when a PR is opened/merged/closed, the linked issue's status updates
3. **Sprint rotation** — when all sprint items are Done, the next sprint is populated from Backlog
4. **Governance guard** — PRs that touch governed paths must acknowledge governance gates

---

## Architecture

```
Event Sources                Workflows                 Scripts                    GitHub Projects v2
─────────────               ─────────────             ─────────────              ──────────────────
Issue opened/edited ──────► issue-triage.yml ────────► triage.py ──────────────► Set fields
PR opened/closed ─────────► pr-status-sync.yml ──────► triage.py --set-status ─► Update Status
                      └───► governance-guard.yml ────► governance_check.py ────► Pass/Fail check
Cron (Monday 9am) ───────► sprint-rotation.yml ──────► sprint_rotate.py ───────► Rotate sprint
PR merged (sprint done) ─► pr-status-sync.yml ───────► sprint_rotate.py ──────► Trigger rotation
```

All scripts live in `scripts/automation/` and share `project_fields.py` for constants and GraphQL helpers.

---

## Classification Rules

Issue classification uses first-match-wins rules (same pattern as the Policy DSL evaluator). Each field is assigned independently.

### Phase

| Signal | Phase |
|--------|-------|
| Label `phase:A` through `phase:G` | Corresponding phase |
| Title contains `ConPTY`, `Windows` | E |
| Title contains `WebSocket`, `heartbeat`, `cloud sync` | F |
| Title contains `dashboard`, `SSO`, `governance API` | G |
| Title contains `adapter`, `PTY`, `detector` | E |
| Title contains `policy`, `DSL`, `autopilot` | E |

### Priority

| Signal | Priority |
|--------|----------|
| Label `priority:P0` through `priority:P3` | Corresponding priority |
| Title contains `crash`, `data loss`, `corruption` | P0 |
| Title contains `security`, `secret`, `CVE` | P1 |
| Default | P2 |

### Category

| Signal | Category |
|--------|----------|
| Label `category:core` through `category:docs` | Corresponding category |
| Title contains `security`, `secret`, `CVE`, `scan` | Security |
| Title contains `policy`, `DSL`, `governance`, `audit` | Governance |
| Title contains `adapter`, `PTY`, `detector`, `session` | Core |
| Title contains `docs`, `readme`, `guide`, `changelog` | Docs |
| Title contains `tui`, `ux`, `wizard`, `dashboard` | UX |
| Title contains `websocket`, `heartbeat`, `cloud` | SaaS |
| Title contains `test`, `coverage`, `ci`, `lint` | Hardening |

### Risk Level

| Signal | Risk |
|--------|------|
| Title contains `security`, `secret`, `CVE`, `auth` | High |
| Title contains `refactor`, `migration`, `breaking` | Medium |
| Default | Low |

---

## Sprint Model

### Naming Convention

Sprints are named `S1`, `S2`, `S3`, etc. The Sprint field is a text field on the project.

### Current Sprint

The current sprint is the highest `SN` that has at least one non-Done item.

### Auto-Chain (Sprint Rotation)

When all items in the current sprint reach Done:

1. The sprint is marked complete
2. Up to 8 items are pulled from Backlog (no Sprint assigned)
3. Items are selected by Priority (P0 first, then P1, P2, P3)
4. Selected items get Sprint = `S(N+1)` and Status = Planned

### Triggers

- **Weekly cron**: Every Monday at 9am UTC
- **PR merge**: When a PR merge causes all sprint items to be Done, `pr-status-sync` triggers `sprint-rotation` via `workflow_dispatch`

---

## Kill Switches

| Level | Mechanism | Effect |
|-------|-----------|--------|
| Per-issue | `automation:ignore` label | Triage skips this issue entirely |
| Global | `DISABLE_PROJECT_AUTOMATION=true` repo variable | All automation workflows skip |
| Per-run | `--dry-run` flag | Scripts log actions but do not mutate |

To disable all automation immediately: set the `DISABLE_PROJECT_AUTOMATION` repository variable to `true` in Settings > Variables > Actions.

---

## Token Requirements

| Workflow | Token | Scopes |
|----------|-------|--------|
| issue-triage | `PROJECT_AUTOMATION_TOKEN` | `project: read/write`, `issues: read` |
| pr-status-sync | `PROJECT_AUTOMATION_TOKEN` | `project: read/write`, `issues: read` |
| sprint-rotation | `PROJECT_AUTOMATION_TOKEN` | `project: read/write` |
| governance-guard | `github.token` (built-in) | `contents: read`, `pull-requests: read` |

`PROJECT_AUTOMATION_TOKEN` is a Fine-Grained PAT. The built-in `GITHUB_TOKEN` cannot mutate GitHub Projects v2 — this is a GitHub platform limitation.

### Setup

1. Create a Fine-Grained PAT at `github.com/settings/tokens`
2. Grant scopes: `project: read/write`, `issues: read` for the `atlasbridge-cli` repository
3. Add as repository secret: Settings > Secrets and variables > Actions > `PROJECT_AUTOMATION_TOKEN`

---

## Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| `PROJECT_AUTOMATION_TOKEN` expired | All project mutations fail silently | Rotate the PAT and update the secret |
| Rate limit (5000 req/hr) | Mutations delayed or fail | Scripts include 1s delay between mutations |
| Field schema changed | `set_field_value` fails with unknown option ID | Update `project_fields.py` with new IDs |
| `gh` CLI not available | All scripts fail | Runners use `actions/checkout` which includes `gh` |
| Issue has no title | Classification returns all defaults | Defaults are safe (Backlog, P2, Low risk) |

---

## Files

| File | Purpose |
|------|---------|
| `scripts/automation/__init__.py` | Package marker |
| `scripts/automation/project_fields.py` | Field IDs, GraphQL helpers, rate limiting |
| `scripts/automation/triage.py` | Deterministic issue classification |
| `scripts/automation/sprint_rotate.py` | Sprint rotation + auto-chain |
| `scripts/automation/governance_check.py` | PR governance gate validation |
| `.github/workflows/issue-triage.yml` | Issue opened/edited → classify |
| `.github/workflows/pr-status-sync.yml` | PR lifecycle → issue status sync |
| `.github/workflows/sprint-rotation.yml` | Weekly cron + auto-chain trigger |
| `.github/workflows/governance-guard.yml` | PR governance check |

---

## Starting and Managing Sprints

### Starting Sprint 1 (first time)

No sprint exists initially. All 29 issues start in Backlog with no Sprint value. To kick off S1:

```bash
# Preview what will be pulled in
python scripts/automation/sprint_rotate.py --rotate --dry-run

# Execute — pulls top 8 Backlog items (by priority) into S1
python scripts/automation/sprint_rotate.py --rotate

# Pull more or fewer items
python scripts/automation/sprint_rotate.py --rotate --max-items 5
```

This sets Sprint = `S1` and Status = `Planned` on the selected items.

### During a sprint

Work items as normal. When a PR closes an issue (via `Closes #N` in the PR body), the automation sets the issue's Status to `Done`.

Check progress at any time:

```bash
python scripts/automation/sprint_rotate.py --check
```

Output:
```
Sprint Status:
  Current: S1
  Status:  in_progress
  Items:   3/8 done
  Backlog: 21 items available
```

### When a sprint completes

When all items in the current sprint are Done, the next sprint starts automatically:

- **On PR merge**: `pr-status-sync` detects the last item is Done and triggers `sprint-rotation`
- **Weekly cron**: Every Monday at 9am UTC, `sprint-rotation` checks and rotates if complete
- **Manual**: Run `python scripts/automation/sprint_rotate.py --rotate`

The auto-chain pulls the next batch of items from Backlog into `S(N+1)`.

### Manual sprint management

```bash
# Force-start next sprint even if current isn't complete
python scripts/automation/sprint_rotate.py --rotate

# Trigger rotation from GitHub Actions UI
# Go to Actions → Sprint Rotation → Run workflow → set dry_run=false

# Check status without mutating
python scripts/automation/sprint_rotate.py --check
```

---

## Adding New Classification Rules

1. Edit `scripts/automation/triage.py`
2. Add rules to the `classify()` function following the first-match-wins pattern
3. Rules higher in the list take priority
4. Test with `--dry-run`: `python scripts/automation/triage.py --issue-number <N> --dry-run`

---

## Monitoring

- **Workflow run logs**: Actions tab → filter by workflow name
- **Dry-run testing**: Manually trigger `sprint-rotation` with `dry_run=true`
- **Local testing**: All scripts accept `--dry-run` and can be run locally with `gh` CLI authenticated
