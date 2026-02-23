# AtlasBridge Enterprise Evolution — 90-Day Roadmap

> This document extends the core product roadmap at [docs/roadmap-90-days.md](roadmap-90-days.md).
> It covers the enterprise evolution from local runtime governance to cloud-connected governance platform.

---

## Guiding Principles

- **Execution stays local in all phases.** Cloud observes, does not execute. The local runtime is always the source of truth for policy evaluation and action execution. The cloud layer provides visibility, policy distribution, and audit aggregation — never command execution.
- **Open Source model.** Phase A and Phase B local features are public (open source). Phase C cloud server and dashboard are experimental (open source).
- **Ship value early.** Phase A delivers immediate governance value with zero infrastructure cost. Every milestone is independently useful.

---

## ROI Ranking

| Phase | ROI | Rationale |
|-------|-----|-----------|
| **Phase A** | **Highest** | Immediate governance value. Tamper-evident audit, risk classification, policy pinning. No infrastructure cost. Ships to every user. |
| **Phase B** | High | Enables centralized visibility without changing local behavior. Moderate infrastructure cost (WebSocket server). |
| **Phase C** | Medium | Full cloud governance platform. Highest infrastructure and maintenance cost. Requires Phase A + B maturity. |

---

## Dependency Chain

```
DecisionTraceEntryV2 schema
    └─> Hash chaining + migration
         └─> Risk classifier
              └─> Policy pinning
                   └─> Auth (API key + JWT)
                        └─> Control channel transport
                             └─> Cloud API clients
                                  └─> Governance API server
                                       └─> Web Dashboard
```

Every layer depends only on the layer above it. No circular dependencies. Each layer can be tested independently by mocking the layer below.

---

## Phase A — Local-First Enterprise Runtime (Ship First)

**Target:** v0.9.0-enterprise
**Status:** In Progress (scaffolding complete)
**Infrastructure cost:** None — everything runs locally

Phase A adds enterprise governance capabilities to the existing local runtime. No network calls, no cloud dependencies, no new infrastructure. All features are gated behind feature flags resolved from the edition.

### Milestones

| Version | Deliverable | Status |
|---------|------------|--------|
| **v0.8.3** | Enterprise module scaffolding + edition detection | THIS PR |
| | - `src/atlasbridge/enterprise/` package with edition.py, features.py | |
| | - CLI commands: `atlasbridge edition`, `atlasbridge features` | |
| | - Feature flags resolved from edition + env var overrides | |
| | - Zero changes to core/ modules | |
| **v0.8.4** | Decision trace v2 + hash chaining integrated | Planned |
| | - DecisionTraceEntryV2 with entry_id, prev_hash, entry_hash, risk_level | |
| | - Hash chain: SHA-256 over canonical JSON of key fields | |
| | - v1 to v2 migration tool (`atlasbridge trace migrate`) | |
| | - v1/v2 coexistence (flag-gated, v1 remains default) | |
| **v0.8.5** | Risk classifier + policy pinning wired in | Planned |
| | - Deterministic risk classification on every policy decision | |
| | - Risk levels: NONE, LOW, MEDIUM, HIGH, CRITICAL | |
| | - Session tag overrides (critical_session, safe_session) | |
| | - Policy pinning: lock agent to specific policy version | |
| **v0.9.0** | Enterprise CLI commands complete | Planned |
| | - `atlasbridge policy diff` — structural diff of two policy files | |
| | - `atlasbridge policy hash` — SHA-256 content hash for policy identity | |
| | - `atlasbridge audit verify` — hash chain integrity verification | |
| | - `atlasbridge trace integrity-check` — decision trace chain verification | |

### What ships

- Edition detection (community / pro / enterprise)
- Feature flags with env var overrides
- Decision trace v2 with tamper-evident hash chains
- Deterministic risk classification on every decision
- Policy pinning (lock agent to a policy version)
- Structural policy diff and content hashing
- Audit log and decision trace integrity verification
- All features gated behind flags, disabled by default in community edition

---

## Phase B — Hybrid Governance (Spec + Scaffold)

**Target:** v0.10.0
**Status:** Specification Complete
**Infrastructure cost:** WebSocket server + minimal cloud endpoint

Phase B connects the local runtime to a cloud governance endpoint. The local runtime remains authoritative for all decisions. The cloud layer receives telemetry (heartbeats, decisions, audit events) and can distribute policy updates. All cloud features degrade gracefully — if the cloud is unreachable, the local runtime continues operating identically.

### Milestones

| Version | Deliverable | Status |
|---------|------------|--------|
| **v0.10.0-alpha** | Control channel transport + heartbeat | Planned |
| | - WebSocket transport with exponential backoff reconnection | |
| | - Heartbeat manager (30s interval, stale connection detection) | |
| | - Connection states: DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING | |
| | - `atlasbridge cloud status` CLI command | |
| | - Cloud disabled by default — zero network calls when off | |
| **v0.10.0-beta** | Cloud policy sync + audit streaming | Planned |
| | - PolicyRegistryClient: push/pull policies, version diff, pin management | |
| | - AuditStreamClient: batch event streaming with local buffer (10k events) | |
| | - AuthClient: API key authentication, JWT token refresh | |
| | - Graceful degradation: buffer locally when disconnected, flush on reconnect | |
| **v0.10.0** | Cloud CLI commands + graceful degradation | Planned |
| | - `atlasbridge cloud setup` — interactive cloud configuration | |
| | - `atlasbridge cloud status` — full state (health, auth, sync, buffer) | |
| | - All clients degrade gracefully (no crashes on network failure) | |
| | - 429/503 retry logic with Retry-After header respect | |

### What ships

- Secure WebSocket control channel with automatic reconnection
- Heartbeat protocol for agent liveness monitoring
- Policy distribution from cloud to agents
- Audit event streaming with local buffering
- Cloud configuration CLI
- Full graceful degradation (cloud-optional, never cloud-required)

---

## Phase C — Full SaaS Governance Platform (Design Only)

**Target:** v1.x (post-GA)
**Status:** Design Document
**Infrastructure cost:** Full cloud stack (PostgreSQL, Redis, Kubernetes, CDN)

Phase C is the full cloud governance platform — API server, web dashboard, SSO, multi-tenant organization management. This phase is design-only in the 90-day window. Implementation begins after GA (v1.0.0) when Phase A and B are stable and battle-tested.

### Milestones

| Version | Deliverable | Status |
|---------|------------|--------|
| **v1.1.0** | Governance API server (design to implementation) | Design |
| | - FastAPI server with PostgreSQL + Redis | |
| | - Auth: API key for agents, OAuth2/SSO for humans | |
| | - Decision ingestion, policy CRUD, audit query | |
| | - WebSocket streaming for real-time dashboard updates | |
| **v1.2.0** | Web Dashboard MVP (sessions + audit trail) | Design |
| | - Organization overview, agent list, session detail | |
| | - Searchable audit trail with hash chain verification indicator | |
| | - Login via SSO (Google, GitHub, SAML) | |
| **v1.3.0** | Full Dashboard (policy editor + risk overview + real-time) | Design |
| | - YAML policy editor with syntax highlighting and validation | |
| | - Risk heat map across agents and time | |
| | - Real-time decision stream via WebSocket | |
| | - One-click policy deployment to agents | |

### What ships (post-90-day)

- Multi-tenant Governance API server
- Web dashboard with real-time agent monitoring
- Policy editor with validation and one-click deploy
- Risk overview with heat maps and drill-down
- Searchable, verifiable audit trail
- SSO integration (Google, GitHub, SAML)
- Self-hosted deployment option (Docker Compose + Helm)

---

## Open Source Boundary

> Current version is fully open source under MIT. Future licensing may change.

| Component | License | Rationale |
|-----------|---------|-----------|
| `src/atlasbridge/core/` | Open source (MIT) | Core runtime, always free |
| `src/atlasbridge/enterprise/` | Open source (MIT) | Local enterprise features, ships to all users |
| `src/atlasbridge/cloud/` (client) | Open source (MIT) | Client-side cloud integration, ships to all users |
| Governance API server | Open source (experimental) | Server-side cloud platform, not yet implemented |
| Web Dashboard | Open source (experimental) | Cloud dashboard, not yet implemented |

The boundary is clear: everything that runs on the user's machine is open source. Server-side cloud components are experimental and not yet implemented.

---

## Timeline Summary

```
Week 1-4:   Phase A — v0.8.3 through v0.8.5
Week 5-8:   Phase A — v0.9.0 (enterprise CLI complete)
Week 5-8:   Phase B — specification + scaffold (parallel with A)
Week 9-12:  Phase B — v0.10.0-alpha through v0.10.0
Week 9-12:  Phase C — design documents (parallel with B)
```

All dates are targets. Phase A is the priority. Phase B begins when A is stable. Phase C design runs in parallel but implementation is post-GA.
