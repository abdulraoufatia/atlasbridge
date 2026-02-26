# AtlasBridge 12-Month Product Strategy

Deterministic governance infrastructure roadmap. All features emerge from the core primitives: deterministic replay, structured policy, audit integrity, explainability, and risk classification.

---

## Months 0-3: Deterministic Core (GA Foundation)

**Objective:** Ship the six GA primitives that constitute the governance moat.

| Feature | Priority | Complexity | Risk |
|---------|----------|-----------|------|
| Deterministic Replay Engine | P0 | High | High — novel capability, no reference implementation |
| Structured Policy Engine v1 Stabilization | P0 | Medium | Medium — extends existing engine |
| Deterministic Risk Classification Engine | P0 | High | High — scoring model design critical |
| Immutable Audit Hash Chain Hardening | P0 | Medium | Medium — extends existing chain |
| Policy Debug / Explain Mode | P1 | Medium | Low — builds on existing explain infra |
| Session Trace Timeline | P1 | Medium | Medium — aggregation complexity |

**Exit criteria:** All six GA primitives functional, tested, contract-frozen.

**Strategic value:** Establishes the deterministic moat. After this phase, AtlasBridge is the only agent runtime with replayable governance and verifiable audit trails.

---

## Months 3-6: Governance Intelligence (GA Polish + Explain)

**Objective:** Make governance visible, measurable, and self-improving.

| Feature | Priority | Complexity | Risk |
|---------|----------|-----------|------|
| Policy Coverage Analyzer (#252) | P1 | Medium | Low — static analysis |
| Governance Score (#245) | P1 | Medium | Medium — weight calibration |
| Incident Mode (#244) | P0 | High | High — coordination complexity |
| Explain Risk (#248) | P1 | Low | Low — extends explain infra |
| Agent Sandboxing Modes (#247) | P0 | Very High | High — OS-level enforcement |

**Exit criteria:** v1.0 GA tagged and released. Governance is quantified and explainable.

**Strategic value:** Governance score and coverage analysis differentiate from "prompt-and-pray" agent frameworks. Incident mode + sandboxing complete the safety story.

---

## Months 6-9: Governance Scale (Post-GA Foundation)

**Objective:** Scale governance from single-session to organizational.

| Feature | Priority | Complexity | Risk |
|---------|----------|-----------|------|
| Performance hardening | P1 | Medium | Low — profiling and optimization |
| Governance Drift Detection (#278) | P1 | Medium | Medium — threshold tuning |
| Governance Drift Alerts (#250) | P1 | Medium | Medium — false positive management |
| Escalation Pattern Detection (#251) | P2 | Medium | Medium — pattern accuracy |
| Blast Radius Estimator (#249) | P1 | High | High — context extraction accuracy |
| Decision Replay Sandbox (#253) | P1 | Medium | Low — subset of replay engine |

**Exit criteria:** Governance operates at scale with drift monitoring and pattern detection.

**Strategic value:** Self-improving governance. Drift detection and pattern analysis close the feedback loop — governance gets better automatically.

---

## Months 9-12: Enterprise Expansion

**Objective:** Enterprise-grade access control, authentication, and multi-workspace governance.

| Feature | Priority | Complexity | Risk |
|---------|----------|-----------|------|
| RBAC + GBAC (#274) | P1 | Very High | High — access model design |
| SSO / OIDC (#275) | P1 | High | Medium — integration complexity |
| Multi-Workspace Isolation (#276) | P1 | Very High | High — isolation boundaries |
| Audit Export Packs (#277) | P1 | Medium | Low — read-only export |
| Enterprise Dashboard foundation (#255-#264) | P1 | High | Medium — UX design |

**Exit criteria:** Enterprise organizations can deploy AtlasBridge with access control, SSO, and workspace isolation.

**Strategic value:** Enterprise adoption enablement. Every enterprise feature builds on the deterministic core — GBAC uses the policy engine, audit export preserves hash verification, workspaces maintain governance isolation.

---

## Strategic Impact Ranking

Ranked by contribution to the deterministic governance moat:

| Rank | Feature | Moat Score | Strategic Rationale |
|------|---------|------------|-------------------|
| 1 | Deterministic Replay Engine | 19/20 | Only agent runtime with replayable governance |
| 2 | Risk Classification Engine | 19/20 | Reproducible, explainable risk — not probabilistic |
| 3 | Session Trace Timeline | 18/20 | Governance narrative — visible and comparable |
| 4 | Policy Engine Stabilization | 17/20 | Foundation everything else builds on |
| 5 | Policy Explain Mode | 16/20 | Third pillar of trust (after determinism + audit) |
| 6 | Audit Hash Chain Hardening | 15/20 | Enterprise trust foundation |
| 7 | Governance Drift Detection | 15/20 | Self-monitoring governance |
| 8 | GA Scope Boundary | 15/20 | Scope discipline prevents dilution |
| 9 | RBAC + GBAC | 13/20 | GBAC differentiates; RBAC is table stakes |
| 10 | Audit Export Packs | 13/20 | Portable hash verification is unique |
| 11 | Multi-Workspace Isolation | 11/20 | Scaling requirement, not moat creator |
| 12 | SSO / OIDC | 10/20 | Enterprise requirement, integration concern |

---

## Engineering Complexity Ranking

| Complexity | Features |
|-----------|---------|
| Very High | Agent Sandboxing, RBAC + GBAC, Multi-Workspace Isolation |
| High | Replay Engine, Risk Classification, Incident Mode, Blast Radius, SSO |
| Medium | Policy Stabilization, Audit Hardening, Policy Explain, Session Trace, Governance Score, Drift Detection, Drift Alerts, Escalation Patterns, Audit Export |
| Low | Explain Risk, Policy Coverage, Decision Replay Sandbox |

---

## Risk Assessment

| Risk Level | Features |
|-----------|---------|
| Critical | None at this planning level |
| High | Replay Engine (novel), Risk Classification (model design), Agent Sandboxing (OS-level), Incident Mode (coordination) |
| Medium | Policy Stabilization, Audit Hardening, Session Trace, Governance Score, Drift Detection, Multi-Workspace |
| Low | Policy Explain, Explain Risk, Coverage Analyzer, Audit Export, Decision Replay |

---

## Invariants (Never Violated)

These constraints hold across all 12 months:

1. **Local execution only** — no remote execution, no remote management
2. **No policy bypass** — every action must match a policy rule
3. **No injection guard weakening** — nonce idempotency, TTL enforcement, cross-session binding
4. **No audit mutability** — hash chain is append-only, verification always available
5. **Deterministic governance** — same inputs + same policy = same outcome

---

## Success Metrics

| Milestone | Metric |
|-----------|--------|
| Month 3 | All 6 GA primitives pass contract tests |
| Month 6 | v1.0 GA released, governance score operational |
| Month 9 | Drift detection active, pattern analysis generating suggestions |
| Month 12 | Enterprise features deployed, RBAC + SSO functional |

**North star:** AtlasBridge is the deterministic governance runtime that enterprises trust to execute AI agents safely. Every feature strengthens that position.

---

## Deterministic Governance Expansion (Infrastructure Moat)

Advanced capabilities that strengthen the deterministic governance moat. All features are consequences of the core primitives — none introduce probabilistic governance, ML-based scoring, or external service dependencies.

### Pre-GA Must Build

| Issue | Feature | Moat Score | Phase |
|-------|---------|-----------|-------|
| #290 | Structured Planning Gate | 24/25 | E |
| #268 | Deterministic Replay Engine | 19/25 | E |
| #270 | Risk Classification Engine | 19/25 | E |
| #289 | Repository Sensitivity Mapping | 18/25 | E |
| #286 | Policy Coverage Testing Framework | 17/25 | E |

### Post-GA Differentiators

| Issue | Feature | Moat Score | Phase |
|-------|---------|-----------|-------|
| #280 | Counterfactual Engine | 25/25 | G |
| #291 | Time Travel Debugger | 25/25 | G |
| #283 | Multi-Agent Orchestration | 25/25 | G |
| #288 | Incident Forensics Engine | 24/25 | G |
| #281 | Governance Diff Engine | 20/25 | G |
| #287 | Red-Team Simulation Mode | 20/25 | G |
| #284 | Formal Escalation Graph | 19/25 | G |
| #282 | Agent Behavior Contracts | 21/25 | G |
| #285 | Autonomy Confidence Metric | 18/25 | G |

### Enterprise Expansion

| Issue | Feature | Moat Score | Phase |
|-------|---------|-----------|-------|
| #292 | Governance-as-Code Marketplace | 18/25 | H |

### Prioritization Matrix

| Rank | Feature | Moat | Complexity | GA Alignment | Impact Tier |
|------|---------|------|-----------|-------------|-------------|
| 1 | Counterfactual Engine (#280) | 25/25 | Very High | Post-GA Core | Strategic |
| 2 | Time Travel Debugger (#291) | 25/25 | Very High | Post-GA Core | Strategic |
| 3 | Multi-Agent Orchestration (#283) | 25/25 | Very High | Post-GA Core | Strategic |
| 4 | Structured Planning Gate (#290) | 24/25 | High | Pre-GA Core | Strategic |
| 5 | Incident Forensics (#288) | 24/25 | High | Post-GA Core | Strategic |
| 6 | Behavior Contracts (#282) | 21/25 | Medium | Post-GA Core | Enterprise |
| 7 | Governance Diff Engine (#281) | 20/25 | Medium | Post-GA Core | Differentiator |
| 8 | Red-Team Simulation (#287) | 20/25 | Medium | Post-GA Core | Enterprise |
| 9 | Escalation Graph (#284) | 19/25 | Medium | Post-GA Core | Differentiator |
| 10 | Sensitivity Mapping (#289) | 18/25 | Low | Pre-GA Core | Differentiator |
| 11 | Autonomy Confidence (#285) | 18/25 | Low | Post-GA Core | Differentiator |
| 12 | Marketplace (#292) | 18/25 | Very High | Enterprise | Long-Term |
| 13 | Policy Coverage Testing (#286) | 17/25 | Medium | Pre-GA Core | Differentiator |

### Build Sequence

**Immediate (Pre-GA):**
1. Structured Planning Gate (#290) — intent-level governance, highest pre-GA moat
2. Repository Sensitivity Mapping (#289) — context-aware risk, low complexity
3. Policy Coverage Testing (#286) — policy quality assurance, enables diff engine

**Next (Post-GA, Months 6-9):**
4. Counterfactual Engine (#280) — apex moat capability, depends on replay engine
5. Incident Forensics (#288) — replay-verified investigation
6. Governance Diff Engine (#281) — infrastructure-grade policy management
7. Behavior Contracts (#282) — enterprise execution constraints
8. Red-Team Simulation (#287) — proactive governance testing

**Later (Post-GA, Months 9-12):**
9. Multi-Agent Orchestration (#283) — next-frontier capability
10. Time Travel Debugger (#291) — interactive counterfactual
11. Formal Escalation Graph (#284) — structural governance analysis
12. Autonomy Confidence Metric (#285) — governance quality metric

**Long-Term:**
13. Governance-as-Code Marketplace (#292) — ecosystem creation
