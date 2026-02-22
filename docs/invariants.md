# AtlasBridge Invariants

This document lists the invariants that AtlasBridge enforces at all times. These are correctness guarantees, not optional safety features.

---

## Execution Model

**Cloud OBSERVES, local EXECUTES.**

- All code execution happens on the operator's machine.
- No remote code execution. No cloud compute. No SaaS runtime.
- Cloud components (if any) are interface definitions only. They observe state; they never execute actions.
- The `cloud/` package contains zero network imports (enforced by `test_cloud_network_isolation.py`).

---

## Relay Correctness

These invariants keep the prompt relay working correctly:

| # | Invariant | Enforcement |
|---|-----------|-------------|
| 1 | No duplicate injection | Nonce idempotency via atomic `decide_prompt()` SQL guard |
| 2 | No expired injection | TTL enforced in database WHERE clause |
| 3 | No cross-session injection | `prompt_id` + `session_id` binding checked |
| 4 | No unauthorized injection | Allowlisted channel identities only |
| 5 | No echo loops | 500ms suppression window after every injection |
| 6 | No lost prompts | Daemon restart reloads pending prompts from SQLite |
| 7 | Bounded memory | Rolling 4096-byte buffer, never unbounded growth |

---

## Policy Evaluation

- Every action must match a policy rule. No freestyle decisions.
- Default on no-match: `require_human` (escalate to operator).
- Default on low-confidence: `require_human` (escalate to operator).
- `yes_no_safe_default` is `"n"` — rejects, never auto-approves.
- Policy evaluation is deterministic: same input always produces same output.

---

## Audit

- Audit log is append-only and hash-chained (SHA-256).
- Decision trace is append-only JSONL with rotation (10 MB, 3 archives).
- Every prompt lifecycle event is recorded.

---

## Dashboard

- Dashboard binds to loopback only by default (`127.0.0.1`).
- Non-loopback binding requires explicit `--i-understand-risk` flag.
- Dashboard has read-only SQLite access (`?mode=ro`).
- No PUT/DELETE/PATCH mutation routes exist.
- Dashboard has no authentication — network isolation is the access control.

---

## Console

- Console is local execution only.
- Safety banner always visible: "OPERATOR CONSOLE — LOCAL EXECUTION ONLY".
- Console manages processes via CLI subcommands (subprocess isolation).

---

## Contract Surfaces

The following surfaces are frozen and enforced by safety tests in `tests/safety/`:

1. **Adapter API** — `BaseAdapter` abstract method set
2. **Channel API** — `BaseChannel` abstract method set
3. **Policy DSL schema** — v0 + v1 field sets, enum values, defaults
4. **CLI command tree** — 27 top-level commands, all subcommand groups
5. **Dashboard routes** — 11 frozen routes (HTML + JSON API + OpenAPI)
6. **Console surface** — command options and defaults
7. **Audit schema** — database tables and columns
8. **Config schema** — top-level fields and environment variables

Changes to any frozen surface require updating the corresponding safety test and documenting the change as breaking.

---

## CI Gates

- All safety tests must pass before merge (`tests/safety/`).
- Coverage floor: 80% global, 85% core (target: 90%).
- Lint, format, and type checks must pass.
- Publishing is tag-only (`v*.*.*`). Push to main never publishes.
