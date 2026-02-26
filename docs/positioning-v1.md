# AtlasBridge v1.0 — Positioning

## What AtlasBridge v1.0 IS

AtlasBridge v1.0 is a **local-first AI governance runtime**.

It is a deterministic, policy-enforced execution layer for AI CLI agents. Operators define rules in a YAML Policy DSL. AtlasBridge evaluates them on every prompt and executes only what is explicitly permitted. When no rule matches, confidence is low, or a rule says `require_human`, AtlasBridge escalates to a human via Telegram or Slack.

**Core attributes:**

- **Local-first** — all execution happens on the operator's machine
- **Deterministic** — same input always produces same output; no ML, no heuristics
- **Policy-enforced** — every action must match a policy rule; no freestyle decisions
- **Operator-grade** — operator console, process management, live status, diagnostics
- **Audit-capable** — hash-chained append-only audit log and decision trace
- **Invariant-guarded** — 7 correctness invariants enforced at all times
- **Cloud observes, local executes** — cloud components (if any) observe state; they never execute actions

---

## What AtlasBridge v1.0 IS NOT

- **Not hosted** — there is no hosted service; the runtime runs on your machine
- **Not multi-tenant** — there is one operator, one machine, one policy
- **Not authenticated** — the dashboard has no login; network isolation is the access control
- **Not remotely controlled** — no remote entity can trigger execution or override policy
- **Not SSO-integrated** — there is no identity provider integration
- **Not enterprise-ready (yet)** — enterprise features (RBAC, multi-tenant) are experimental or design-only

These are roadmap items, not v1.0 deliverables.

---

## Target Audience

- **Security engineers** evaluating AI agent governance solutions
- **AI platform teams** deploying autonomous coding agents in controlled environments
- **DevOps teams** automating AI-assisted workflows with policy guardrails
- **Governance researchers** studying deterministic policy enforcement for AI systems

---

## Invariants

AtlasBridge v1.0 enforces these invariants at all times:

| Invariant | Enforcement |
|-----------|-------------|
| Cloud OBSERVES, local EXECUTES | Cloud module contains zero network imports (AST-verified) |
| No remote execution control | Injection logic is local-only; no remote trigger path exists |
| Read-only dashboard | SQLite `?mode=ro`; no PUT/DELETE/PATCH routes |
| No policy enforcement in cloud | Policy evaluator runs locally; cloud has no evaluate() path |
| Deterministic evaluation before injection | `decide_prompt()` atomic SQL guard; nonce idempotency |
| Localhost-only dashboard by default | Non-loopback binding requires `--i-understand-risk` flag |
| Bounded memory | Rolling 4096-byte buffer; never unbounded growth |

---

## Compatibility Guarantees

### SemVer Compliance

AtlasBridge follows [Semantic Versioning 2.0.0](https://semver.org/):

- **Major** (X.0.0) — breaking changes to frozen contract surfaces
- **Minor** (0.X.0) — new features, backwards-compatible
- **Patch** (0.0.X) — bug fixes, documentation updates

### Contract Surface Freeze

The following surfaces are frozen and enforced by safety tests:

1. BaseAdapter ABC — abstract method set and signatures
2. BaseChannel ABC — abstract method set and signatures
3. Policy DSL schema — v0 + v1 field sets, enum values, defaults
4. CLI command tree — 27 top-level commands, all subcommand groups
5. Dashboard routes — 11 frozen routes (HTML + JSON API + OpenAPI)
6. Console surface — command options and defaults
7. Audit schema — database tables and columns
8. Config schema — top-level fields and environment variables

Changes to any frozen surface require updating the corresponding safety test, incrementing the major version, and documenting the change as breaking.

### Backwards Compatibility

- Deprecated features receive a `DeprecationWarning` for at least one minor version before removal.
- Config files are forwards-compatible within a major version.
- Policy files with `policy_version: "0"` and `"1"` are both supported.

---

## Future Roadmap

Future direction includes multi-tenant support, authentication, enterprise SSO, and an extended dashboard — but these are roadmap phases, not part of v1.0.

The v1.0 release is strictly local-first.
