# Decision Record: SaaS Program Gate

**Date:** 2026-02-23
**Status:** Accepted
**Author:** AtlasBridge Engineering

---

## Context

AtlasBridge v1.0 is a local-first governance runtime. SaaS features (cloud dashboard, multi-tenant, remote observability) are on the roadmap but must not be implemented until explicit program gate criteria are met.

This decision establishes what must be true before any SaaS or cloud-execution code can be merged to main.

## Decision

SaaS implementation requires an explicit program gate. Before any code that enables cloud execution, remote policy evaluation, or multi-tenant data handling can be merged:

### Gate Criteria

1. **Threat model update** — `docs/threat-model.md` must be updated with cloud-specific attack surfaces, including remote code execution paths, cross-tenant data leakage, and API authentication bypass.

2. **RBAC design** — A role-based access control design must be documented and reviewed. Roles must include at minimum: viewer (read traces), operator (manage agents), admin (manage tenant settings).

3. **Data residency policy** — A policy defining where tenant data is stored, how long it is retained, and how deletion requests are handled.

4. **Audit readiness assessment** — A gap analysis against trust service criteria (security, availability, processing integrity, confidentiality, privacy).

5. **Safety tests updated** — All existing safety tests must continue to pass. New safety tests must verify that the "cloud observes, local executes" invariant is maintained.

6. **CI governance guard** — PRs with `saas` or `cloud-exec` labels must have a linked decision record documenting the program gate approval.

### What This Means in Practice

- `src/atlasbridge/cloud/` exists as a placeholder — it must have **zero network imports** (enforced by AST safety test)
- `src/atlasbridge/enterprise/` contains design stubs only — no production code paths
- The `docs/saas-alpha-roadmap.md` is a design document, not an implementation plan
- Phase G (SaaS Observe-Only) and Phase H (Enterprise Dashboard) are post-v1.0

## Alternatives Considered

1. **No gate** — Allow SaaS code incrementally. Rejected: risk of scope creep and unreviewed cloud attack surface.
2. **Full audit certification before any cloud features** — Too slow; observe-only mode has minimal data handling. A readiness assessment (not full certification) is sufficient for Phase G.

## Consequences

**Positive:**
- Clear boundary between local runtime and cloud features
- Forced threat model review before cloud code ships
- No accidental cloud execution paths

**Negative:**
- Slower SaaS development cycle
- Requires discipline to not bypass the gate under deadline pressure
