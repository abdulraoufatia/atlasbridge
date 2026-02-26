# v1.0 GA Scope Boundary — Deterministic Core Only

This document defines the hard boundary for AtlasBridge v1.0 GA. Everything inside ships. Everything outside is explicitly deferred to the Enterprise Expansion Phase.

---

## GA Includes (MANDATORY)

These six capabilities constitute the v1.0 GA surface. All must be functional, tested, and documented before the GA tag.

### 1. Deterministic Replay Engine
- Re-run any session with identical inputs, policy version, and risk engine state
- Replay produces identical decision trace (hash-verified)
- Replay under modified policy shows decision diff
- No side effects: no audit mutations, no channel notifications
- CLI: `atlasbridge replay <session_id>`

### 2. Structured Policy Engine (v1 Stable)
- Deterministic evaluation with first-match-wins semantics
- Explicit priority ordering, no ambiguous rule resolution
- Deterministic conflict resolution for overlapping match criteria
- Rule coverage analysis and hit frequency metrics
- Policy evaluation idempotency guaranteed
- Contract tests freeze GA evaluation behavior

### 3. Immutable Audit Hash Chain
- Hash chaining across all governance event types
- Session boundary protection (start/end as chain anchors)
- Tamper detection: insertion, deletion, and modification detected
- Break point identification on verification failure
- CLI: `atlasbridge audit verify`
- Performance: < 10s verification for 10,000 events

### 4. Risk Classification Engine (Deterministic)
- Weighted rule-based classifier (no ML dependency)
- File scope sensitivity, command impact scoring, environment awareness
- Risk score (0-100) with category mapping (Low/Medium/High/Critical)
- Every risk factor traceable in explanation
- Identical input always produces identical risk assessment

### 5. Policy Debug / Explain Mode
- For any decision: matched rule, failed rules, risk factors, environment context
- Confidence level traced to source signals
- Alternative outcomes computed
- No secret leakage in explanations
- CLI: `atlasbridge policy explain --session <id>`

### 6. Session Trace Timeline
- Chronological governance event sequence per session
- All event types: prompt detected, policy evaluated, decision made, escalated, injected, resolved
- Risk overlay with spike highlighting
- Compatible with replay engine (replayed sessions produce comparable timelines)
- CLI: `atlasbridge session trace <session_id>`

---

## GA Explicitly Excludes

These features are deferred to the Enterprise Expansion Phase (Post-GA). They will build on the deterministic core without weakening its invariants.

| Feature | Phase | Reason for Exclusion |
|---------|-------|---------------------|
| RBAC / GBAC | H | Requires stable core; stateful access control |
| SSO (OIDC) | H | Integration concern, not governance primitive |
| Multi-workspace isolation | H | Scaling feature, not core governance |
| Compliance export packs | H | Consumption feature, requires stable audit chain |
| Remote execution layer | Never | Violates local execution principle |
| Remote management layer | Never | Violates local execution principle |
| ML-based classification | Post-GA | Deterministic classification is GA requirement |
| Dashboard-first features | H | CLI and primitives first |

---

## GA Checklist

- [ ] Deterministic Replay Engine: session replay produces identical trace
- [ ] Deterministic Replay Engine: policy diff mode functional
- [ ] Policy Engine: no non-deterministic rule resolution
- [ ] Policy Engine: evaluation idempotency verified
- [ ] Policy Engine: contract tests frozen
- [ ] Audit Hash Chain: all event types in chain
- [ ] Audit Hash Chain: tamper detection functional
- [ ] Audit Hash Chain: `atlasbridge audit verify` works
- [ ] Risk Classification: deterministic equality verified
- [ ] Risk Classification: all factor types covered
- [ ] Policy Explain: full reasoning chain for any decision
- [ ] Policy Explain: no secret leakage
- [ ] Session Trace: all event types rendered
- [ ] Session Trace: replay-compatible timelines
- [ ] All GA contract surfaces have frozen tests
- [ ] No GA-excluded features in active sprints

---

## Boundary Enforcement

- This boundary is enforced by scope review during sprint planning
- CI gates ensure GA surface contracts are not broken
- Any feature not listed in GA Includes requires explicit approval
- Excluded features are tracked in the Enterprise Expansion Phase milestone
