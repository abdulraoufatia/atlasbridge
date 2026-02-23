# Documentation Index

This directory contains all design documents, reference guides, and operational documentation for AtlasBridge — a policy-driven autonomous runtime for AI CLI agents.

This index helps you find the right document fast, whether you are a new user, a policy author, or a contributor.

---

## Quick Start: Where Do I Begin?

### A) Users — I just installed AtlasBridge

1. [Channel Token Setup](channel-token-setup.md) — get Telegram or Slack credentials
2. **Per-agent quick start** — pick your AI tool:
   - [Claude Code](claude-code-getting-started.md) — `atlasbridge run claude`
   - [OpenAI Codex CLI](openai-getting-started.md) — `atlasbridge run openai`
   - [Gemini CLI](gemini-getting-started.md) — `atlasbridge run gemini`
3. [Autonomy Modes](autonomy-modes.md) — understand Off / Assist / Full
4. [Policy Authoring Guide](policy-authoring.md) — write your first policy
5. [CLI UX](cli-ux.md) — learn the commands and TUI
6. [Dashboard](dashboard.md) — local governance dashboard, SSH tunnel access, session export
7. [Setup (Non-interactive)](setup-noninteractive.md) — headless / CI deployment

### B) Power Users — writing policies and tuning autopilot

1. [Policy Cookbook](policy-cookbook.md) — copy-paste-ready patterns for common scenarios
2. [Policy DSL v0 Reference](policy-dsl.md) — full schema, evaluation semantics
3. [Policy DSL v1 Extensions](policy-dsl-v1.md) — compound conditions, session tags, inheritance
4. [Channel Message Gating](channel-message-gating.md) — how messages are accepted/rejected, rejection reasons, rate limiting
5. [Autopilot Engine](autopilot.md) — engine architecture, decision trace, kill switch
6. [QA Top 20 Failure Scenarios](qa-top-20-failure-scenarios.md) — what can go wrong and how it is tested
7. [Reliability](reliability.md) — PTY supervisor, failure modes, recovery

### C) Contributors — I want to develop AtlasBridge

1. [Architecture](architecture.md) — system design, data flow, invariants
2. [CONTRIBUTING.md](../CONTRIBUTING.md) — fork/clone, branching, PR process
3. [CLAUDE.md](../CLAUDE.md) — project context, repo layout, dev commands
4. [Policy Engine Internals](policy-engine.md) — prompt detection and routing
5. [Dev Workflow (Multi-Agent)](dev-workflow-multi-agent.md) — agent roles, branch ownership
6. [Release Process](release.md) — tagging, TestPyPI, OIDC publishing
7. [Roadmap](roadmap-90-days.md) — milestones and planned work
8. [Sprint Automation Prompt](sprint-automation-prompt.md) — portable sprint workflow for Claude Code
9. [Brand System](branding.md) — colors, typography, icon rules, CSS tokens

---

## Documentation Map

| Document | Audience | What you'll learn | When to read it | Status |
|----------|----------|-------------------|-----------------|--------|
| [architecture.md](architecture.md) | Contributor | System design: PTY supervisor, tri-signal detection, state machine, routing, adapters, channels, audit, invariants | Before making structural changes | Current |
| [branding.md](branding.md) | Contributor | Brand system v1: color palette, typography, icon rules, CSS tokens, dark/light mode | When modifying UI surfaces | Current |
| [claude-code-getting-started.md](claude-code-getting-started.md) | User | Claude Code setup, prompt patterns, policy examples, troubleshooting | When starting with Claude Code | Current |
| [openai-getting-started.md](openai-getting-started.md) | User | OpenAI Codex CLI setup, prompt patterns, policy examples, troubleshooting | When starting with Codex CLI | Current |
| [gemini-getting-started.md](gemini-getting-started.md) | User | Gemini CLI setup, prompt patterns, policy examples, troubleshooting | When starting with Gemini CLI | Current |
| [autonomy-modes.md](autonomy-modes.md) | Both | The three operational modes (Off / Assist / Full) and when each applies | After install, before choosing a mode | Current |
| [autopilot.md](autopilot.md) | Both | Autopilot engine architecture, policy evaluation flow, decision trace, kill switch | Before enabling autopilot | Current |
| [adapters.md](adapters.md) | Contributor | BaseAdapter interface, contract spec, vendor-neutral philosophy | When writing or modifying an adapter | Current |
| [approval-lifecycle.md](approval-lifecycle.md) | Contributor | Prompt approval state machine (CREATED → PENDING → APPROVED/DENIED/EXPIRED) | When working on prompt routing or approval logic | Current |
| [channel-token-setup.md](channel-token-setup.md) | User | Step-by-step Telegram and Slack token acquisition | During first-time setup | Current |
| [channels.md](channels.md) | Contributor | BaseChannel interface, multi-channel routing, extensibility | When writing or modifying a channel | Current |
| [channel-message-gating.md](channel-message-gating.md) | Both | Channel message gating: evaluation order, session states, rejection reasons, rate limiting, binary menu normalization, troubleshooting | When understanding how channel messages are accepted/rejected | Current |
| [chat-session-mode.md](chat-session-mode.md) | Both | Chat mode, session states, STREAMING state, message queuing, conversation registry | When understanding chat session lifecycle | Current |
| [conversation-ux-v2.md](conversation-ux-v2.md) | Both | Interaction pipeline: classifier, plans, executor, chat mode, output forwarding | When understanding or extending conversation UX | Current |
| [claude-adapter-spec.md](claude-adapter-spec.md) | Contributor | Claude Code adapter: launch model, three-layer detection, injection, prompt patterns | When debugging Claude Code integration | Current |
| [cli-ux.md](cli-ux.md) | Both | CLI design principles, command overview, TUI behavior | When learning or extending CLI commands | Current |
| [data-model.md](data-model.md) | Contributor | SQLite schema design, migration strategy, audit log schema | When modifying the database layer | Current |
| [dev-workflow-multi-agent.md](dev-workflow-multi-agent.md) | Contributor | Multi-agent team structure, branch model, agent roles and ownership | When onboarding as a contributor | Current |
| [policy-cookbook.md](policy-cookbook.md) | User | Copy-paste-ready policy patterns: git, CI/CD, Dependabot, rate limits, session scoping | When looking for real-world policy examples | Current |
| [policy-authoring.md](policy-authoring.md) | User | Quick start guide for writing policies: syntax, patterns, debugging, FAQ | When writing your first policy | Current |
| [policy-dsl.md](policy-dsl.md) | Both | Full DSL v0 reference: schema, match fields, action types, regex safety, validation | When you need precise DSL semantics | Current |
| [policy-dsl-v1.md](policy-dsl-v1.md) | Both | DSL v1 extensions: `any_of`/`none_of`, `session_tag`, `max_confidence`, `extends`, trace rotation | When using compound conditions or policy inheritance | Current |
| [policy-engine.md](policy-engine.md) | Contributor | Prompt detection internals: structured / regex / blocking-heuristic layers, routing dispatch | When debugging prompt detection or routing | Current |
| [qa-top-20-failure-scenarios.md](qa-top-20-failure-scenarios.md) | Contributor | 20 canonical failure scenarios (QA-001 through QA-020), Prompt Lab, CI gating matrix | When writing tests or investigating failures | Current |
| [red-team-report.md](red-team-report.md) | Contributor | Relay misuse analysis under original "firewall" framing; retained for implementation reference | For historical context on correctness invariants | Reference |
| [release.md](release.md) | Contributor | Release process: tag patterns (rc vs stable), TestPyPI vs PyPI, version bumping, OIDC | When cutting a release | Current |
| [reliability.md](reliability.md) | Both | Reliability philosophy, core invariants, failure modes, PTY supervisor architecture | When diagnosing PTY or prompt detection issues | Current |
| [roadmap-90-days.md](roadmap-90-days.md) | Both | Project milestones from v0.1 through v1.0 | To understand project direction | Current |
| [setup-flow.md](setup-flow.md) | Contributor | Setup command design: flow diagram, pre-flight checks, config collection, validation | When modifying the setup wizard | Current |
| [setup-noninteractive.md](setup-noninteractive.md) | User | Headless / CI deployment: env vars, `--from-env`, Docker example | When deploying without a TTY | Current |
| [threat-model.md](threat-model.md) | Contributor | STRIDE-based relay correctness analysis, trust boundaries, threat scenarios | For correctness review or architecture audits | Current |
| [tool-adapter.md](tool-adapter.md) | Contributor | Adapter abstraction design goals and interface (early design doc) | For historical context on adapter design decisions | Reference |
| [tool-interception-design.md](tool-interception-design.md) | Contributor | Strategy analysis: wrapper vs PTY interception; rationale for PTY approach | For historical context on interception strategy | Reference |
| [telegram-setup.md](telegram-setup.md) | User | Step-by-step Telegram bot setup: BotFather, /start, chat_id, verification | During first-time Telegram setup | Current |
| [troubleshooting.md](troubleshooting.md) | User | Common issues and solutions: adapters, Telegram 409/400, doctor, upgrade | When something goes wrong | Current |
| [upgrade.md](upgrade.md) | User | Upgrading safely: config preservation, migration, verification | Before or after `pip install -U` | Current |
| [cloud-spec.md](cloud-spec.md) | Contributor | Phase B cloud governance interfaces: auth, transport, protocol, audit stream | When implementing cloud features (Phase B) | Design Only |
| [enterprise-architecture.md](enterprise-architecture.md) | Contributor | Enterprise architecture overview: editions, RBAC, risk, governance | When working on enterprise features | Experimental |
| [enterprise-saas-architecture.md](enterprise-saas-architecture.md) | Contributor | Phase C SaaS design: multi-tenant, dashboard, trust boundaries | For future cloud planning | Design Only |
| [enterprise-transition-contracts.md](enterprise-transition-contracts.md) | Contributor | Phase A→B→C transition contracts and migration paths | When planning phase transitions | Design Only |
| [enterprise-trust-boundaries.md](enterprise-trust-boundaries.md) | Contributor | 6 trust domains, secret handling, transport security | For security review | Design Only |
| [enterprise-prompts.md](enterprise-prompts.md) | Contributor | Enterprise prompt patterns and escalation workflows | When working on enterprise escalation | Design Only |
| [ethics-and-safety-guarantees.md](ethics-and-safety-guarantees.md) | Both | Safety invariants, CI enforcement, ethics gate | Before modifying safety-critical code | Current |
| [roadmap-enterprise-90-days.md](roadmap-enterprise-90-days.md) | Contributor | 90-day enterprise roadmap: Phase A/B/C milestones | For enterprise planning context | Current |
| [enterprise-dashboard-product-spec.md](enterprise-dashboard-product-spec.md) | Contributor | Phase C dashboard: personas, feature matrix, MVP scope, success metrics | For Phase C planning | Design Only |
| [enterprise-dashboard-ui-map.md](enterprise-dashboard-ui-map.md) | Contributor | Phase C dashboard: 8 screens with wireframes, navigation flow, component hierarchy | For Phase C UI design | Design Only |
| [enterprise-governance-api-spec.md](enterprise-governance-api-spec.md) | Contributor | Phase C API: REST endpoints, auth model, error catalog, WebSocket events | For Phase C API design | Design Only |
| [enterprise-data-model.md](enterprise-data-model.md) | Contributor | Phase C data model: ER diagram, 10 tables, RLS tenancy, sync protocol | For Phase C data design | Design Only |
| [enterprise-dashboard-threat-model.md](enterprise-dashboard-threat-model.md) | Contributor | Phase C security: STRIDE analysis, trust boundaries, incident response | For Phase C security review | Design Only |
| [api-stability-policy.md](api-stability-policy.md) | Contributor | Stability levels, deprecation rules, breaking change policy | Before modifying frozen APIs | Current |
| [contract-surfaces.md](contract-surfaces.md) | Contributor | Formal spec of all 8 frozen contract surfaces | Before modifying any contract surface | Current |
| [console.md](console.md) | Both | Operator console: process management, keybindings, status polling | When using `atlasbridge console` | Current |
| [dashboard.md](dashboard.md) | Both | Dashboard deployment: SSH tunnel, reverse proxy, export, mobile access | When accessing dashboard remotely | Current |
| [invariants.md](invariants.md) | Both | Correctness invariants: relay, policy, audit, dashboard, console | Before modifying safety-critical code | Current |
| [releasing.md](releasing.md) | Contributor | Release process: tag-only publishing, version bumping, CI gates | When cutting a release | Current |
| [automation-architecture.md](automation-architecture.md) | Contributor | GitHub Actions automation: issue triage, PR status sync, sprint rotation, governance guard | When modifying or extending project automation | Current |
| [sprint-automation-prompt.md](sprint-automation-prompt.md) | Contributor | Portable sprint-driven development prompt for Claude Code: tier-ordered execution, test-gated progression, memory system, wiki/project board automation | When setting up sprint automation on a new project | Current |
| [streaming-behavior.md](streaming-behavior.md) | Both | Streaming architecture: OutputForwarder, secret redaction, plan detection, StreamingConfig | When understanding or configuring streaming behavior | Current |
| [project-hygiene.md](project-hygiene.md) | Contributor | Operating protocol for project board hygiene: Done evidence rules, sprint convention, status definitions | When updating project board after merging work | Current |
| [positioning-v1.md](positioning-v1.md) | Both | v1.0 positioning: what AtlasBridge is/is not, target audience, invariants, compatibility | Before v1.0 launch | Current |
| [ga-readiness-checklist.md](ga-readiness-checklist.md) | Contributor | GA readiness audit: contract freeze, coverage, threat model, CI matrix, verdict | Before tagging v1.0 | Current |
| [saas-alpha-roadmap.md](saas-alpha-roadmap.md) | Contributor | 90-day SaaS Alpha path: stabilization, observe-only cloud, multi-tenant alpha | For post-v1.0 planning | Design Only |
| [versioning-policy.md](versioning-policy.md) | Both | SemVer, deprecation policy, breaking change protocol, tag-only releases | Before modifying frozen APIs | Current |
| [phone-first-interaction.md](phone-first-interaction.md) | Both | Phone-first UX: text-only interaction, synonym normalization, boundary messages, Enter semantics | When understanding mobile operator workflow | Current |

---

## Key Concepts Glossary

**Session** — A supervised run of an AI CLI tool (e.g., `atlasbridge run claude`). Each session has an isolated PTY, prompt state machine, and audit trail.

**PromptEvent** — A detected prompt from the supervised tool. Contains the prompt text, type, confidence level, timestamps, and lifecycle state.

**Prompt Types:**
- **YES_NO** — Binary confirmation (e.g., "Continue? [y/n]")
- **ENTER** — Press-enter-to-continue prompts
- **CHOICE** — Multiple-choice selection
- **TEXT** — Free-form text input

**Channel** — A notification/communication backend (Telegram or Slack) used to relay prompts to humans and receive replies.

**Adapter** — A vendor-specific wrapper that launches an AI CLI tool inside a PTY supervisor and implements prompt detection and reply injection (e.g., `ClaudeCodeAdapter`).

**Autonomy Modes:**
- **Off** — All prompts forwarded to human; no automatic decisions
- **Assist** — Policy handles explicitly allowed prompts; all others escalated
- **Full** — Policy auto-executes permitted prompts; no-match / low-confidence escalated safely

**Policy DSL** — A YAML-based rule language for defining what the autopilot can do. v0 provides core match/action semantics; v1 adds compound conditions (`any_of`/`none_of`), session scoping (`session_tag`), confidence bounds (`max_confidence`), and policy inheritance (`extends`).

**Escalation / Route-to-human** — When no policy rule matches, confidence is low, or a rule explicitly says `require_human`, the prompt is sent to a human via the configured channel.

**Decision Trace** — An append-only JSONL log recording every autopilot decision: which rule matched, what action was taken, and why. Used for auditing and debugging (`atlasbridge autopilot explain`).

**Audit Log** — A hash-chained, append-only event log recording all prompt lifecycle events. Separate from the decision trace; covers the full relay, not just autopilot.

**Prompt Lab** — A deterministic QA simulator (`atlasbridge lab`) that replays scripted scenarios (QA-001 through QA-020) against the prompt detection and routing stack without real PTY or network I/O.

**Top 20 Failure Scenarios** — The canonical set of failure modes (duplicate injection, expired prompts, echo loops, etc.) that define AtlasBridge's correctness guarantees. Each has a Prompt Lab scenario and CI gate.

---

## Troubleshooting Entry Points

| Problem area | Where to look |
|--------------|---------------|
| Environment or config issues | Run `atlasbridge doctor --fix` and see [cli-ux.md](cli-ux.md) |
| PTY or prompt detection failures | [reliability.md](reliability.md) — failure modes and recovery |
| Policy not matching as expected | [policy-authoring.md](policy-authoring.md) — debugging section and FAQ |
| Autopilot decisions look wrong | Run `atlasbridge autopilot explain --last 20` and see [autopilot.md](autopilot.md) |
| Regression or known failure | [qa-top-20-failure-scenarios.md](qa-top-20-failure-scenarios.md) — canonical failure list |
| Generating a support bundle | Run `atlasbridge debug bundle` — see [cli-ux.md](cli-ux.md) |
| Channel token / connectivity | [channel-token-setup.md](channel-token-setup.md) |
| Telegram 400/409 errors | [telegram-setup.md](telegram-setup.md) and [troubleshooting.md](troubleshooting.md) |
| Adapter not found | [troubleshooting.md](troubleshooting.md) — Adapter Issues section |
| Upgrade problems | [upgrade.md](upgrade.md) — config preservation and verification |
| Correctness invariant violated | [threat-model.md](threat-model.md) and [architecture.md](architecture.md) — invariants section |

---

## How Docs Stay Accurate

- **Docs must match shipped behavior.** If a command or feature is documented, it must exist in the codebase. If it doesn't exist yet, the doc must clearly label it as **Planned**.
- **Update docs alongside code.** Every PR that changes user-facing behavior should update the relevant docs in the same PR.
- **Verify before documenting.** If you are unsure whether a command or flag exists, check `src/atlasbridge/cli/main.py` and the test suite before writing.
- **Reference files:** [CLAUDE.md](../CLAUDE.md) is the canonical project context. [CONTRIBUTING.md](../CONTRIBUTING.md) covers the contribution workflow.

---

## Docs Conventions

**Naming:** Lowercase, hyphen-separated (e.g., `policy-authoring.md`). Use descriptive names that match the topic.

**Adding a new doc:**
1. Create the file in `/docs/` following the naming convention.
2. Add an entry to the Documentation Map table in this file.
3. Include the doc in the appropriate Quick Start reading track if it is user-facing.

**Examples and presets:** Policy examples live in `/config/policy.example.yaml` and `/config/policy.example_v1.yaml`. Ready-to-use policy presets live in `/config/policies/`.

**Diagrams:** Use Mermaid fenced code blocks for flow diagrams and state machines. Keep diagrams close to the prose they illustrate.

**Versioning:** Policy files use a `policy_version` field (currently `0` or `1`). When documenting version-specific behavior, state which version(s) apply.

**Historical docs:** Early design documents (`tool-adapter.md`, `tool-interception-design.md`, `red-team-report.md`) are retained for context. They are marked as **Reference** in the Documentation Map and should not be treated as current specifications.
