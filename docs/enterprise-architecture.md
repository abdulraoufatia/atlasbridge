# AtlasBridge Enterprise Architecture

This document defines the end-state enterprise architecture, module boundaries, data schemas, and gating model for the AtlasBridge enterprise evolution.

---

## End-State Dataflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER'S MACHINE (local)                       │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────────┐  │
│  │ AI CLI Agent  │───>│  AtlasBridge  │───>│  Enterprise Modules   │  │
│  │ (claude, etc) │    │  Core Runtime │    │  (risk, trace, pin)   │  │
│  └──────────────┘    └──────┬───────┘    └───────────┬───────────┘  │
│                             │                         │              │
│                             │  policy eval + audit    │  v2 trace    │
│                             │                         │  risk level  │
│                             ▼                         ▼              │
│                      ┌──────────────────────────┐                   │
│                      │  SQLite WAL + JSONL Trace │                   │
│                      │  (local, authoritative)   │                   │
│                      └────────────┬─────────────┘                   │
│                                   │                                  │
│                      ┌────────────▼─────────────┐                   │
│                      │  Cloud Client (optional)  │                   │
│                      │  transport + API clients  │                   │
│                      └────────────┬─────────────┘                   │
└───────────────────────────────────┼─────────────────────────────────┘
                                    │
                          WebSocket + HTTPS
                        (encrypted, authenticated)
                                    │
┌───────────────────────────────────┼─────────────────────────────────┐
│                      CLOUD (observes, does not execute)             │
│                                   │                                  │
│                      ┌────────────▼─────────────┐                   │
│                      │  Control Channel Server   │                   │
│                      │  (WebSocket endpoint)     │                   │
│                      └────────────┬─────────────┘                   │
│                                   │                                  │
│                      ┌────────────▼─────────────┐                   │
│                      │  Governance API Server    │                   │
│                      │  (FastAPI + PostgreSQL)   │                   │
│                      └────────────┬─────────────┘                   │
│                                   │                                  │
│                      ┌────────────▼─────────────┐                   │
│                      │  Web Dashboard            │                   │
│                      │  (sessions, audit, risk)  │                   │
│                      └──────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Invariant:** Execution stays local in all phases. The cloud layer observes, aggregates, and distributes policy — it never issues execution commands to agents.

---

## Phase A Architecture — Enterprise Modules on Core

Phase A adds enterprise capabilities by composing new modules on top of the existing core. No core modules are modified. Enterprise modules import from core; core never imports from enterprise.

```
┌─────────────────────────────────────────┐
│           CLI Layer (cli/)              │
│  edition, features, policy diff/hash,  │
│  audit verify, trace integrity-check   │
└──────────────┬──────────────────────────┘
               │ uses
┌──────────────▼──────────────────────────┐
│        Enterprise Layer                  │
│        (enterprise/)                     │
│                                          │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ edition.py │  │ features.py      │   │
│  │ Edition    │  │ FeatureFlags     │   │
│  │ enum +     │  │ dataclass +      │   │
│  │ detection  │  │ resolution       │   │
│  └────────────┘  └──────────────────┘   │
│                                          │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ risk.py    │  │ trace_v2.py      │   │
│  │ RiskLevel  │  │ TraceEntryV2     │   │
│  │ + classify │  │ + hash chain     │   │
│  └────────────┘  └──────────────────┘   │
│                                          │
│  ┌─────────────────────────────────────┐ │
│  │ trace_migration.py                  │ │
│  │ v1→v2 migration + version detect   │ │
│  └─────────────────────────────────────┘ │
└──────────────┬──────────────────────────┘
               │ imports from (read-only)
┌──────────────▼──────────────────────────┐
│          Core Layer (core/)              │
│                                          │
│  policy/     ← evaluator gains optional  │
│                risk_level annotation     │
│  autopilot/  ← engine gains optional    │
│                v2 trace writing          │
│  audit/      ← writer unchanged         │
│  store/      ← database unchanged       │
│  routing/    ← router unchanged         │
│  prompt/     ← detector unchanged       │
└─────────────────────────────────────────┘
```

The core layer changes are minimal and flag-gated:
- `policy/evaluator.py`: after `evaluate()`, optionally annotates `PolicyDecision` with `risk_level`
- `autopilot/engine.py`: optionally writes v2 trace entries instead of v1
- `autopilot/trace.py`: gains `write_v2()` method alongside existing `write()`

All changes are conditional on feature flags. When flags are disabled, behavior is identical to the current codebase.

---

## Module Dependency Graph

```
core/                    ← depends on nothing enterprise or cloud
  policy/
  autopilot/
  audit/
  store/
  routing/
  prompt/
  session/
  daemon/

enterprise/              ← depends on core/ (read-only imports)
  edition.py             ← no dependencies beyond stdlib
  features.py            ← depends on edition.py
  risk.py                ← depends on core/policy/evaluator (types only)
  trace_v2.py            ← depends on core/autopilot/trace (types only)
  trace_migration.py     ← depends on trace_v2.py

cloud/                   ← depends on enterprise/ and core/
  config.py              ← depends on enterprise/features.py
  transport.py           ← depends on config.py; optional websockets
  heartbeat.py           ← depends on transport.py
  api/
    base.py              ← depends on config.py; uses httpx
    policy_registry.py   ← depends on base.py
    audit_stream.py      ← depends on base.py
    auth.py              ← depends on base.py
```

**Rules:**
1. `core/` never imports from `enterprise/` or `cloud/`
2. `enterprise/` imports from `core/` but never from `cloud/`
3. `cloud/` imports from both `enterprise/` and `core/`
4. All optional dependencies (websockets, httpx for cloud) are guarded with try/except
5. Missing optional dependencies produce a clear error message, not an import traceback

---

## Edition Gating Model

Three editions control feature availability:

| Edition | Feature Flags Enabled | Target User |
|---------|----------------------|-------------|
| **COMMUNITY** | None (all flags False) | Individual developers, open source users |
| **PRO** | decision_trace_v2, risk_classification, policy_pinning, audit_hash_chain | Teams needing governance and compliance |
| **ENTERPRISE** | All PRO flags + cloud_sync, dashboard_api | Organizations needing centralized visibility |

### Resolution Order

Feature flags are resolved in this priority order (highest priority first):

1. **Explicit env var override:** `ATLASBRIDGE_FEATURE_DECISION_TRACE_V2=true` (per-flag)
2. **Edition default:** flags enabled by edition (see table above)
3. **Fallback:** False (feature disabled)

This means:
- A COMMUNITY user can enable individual features via env vars (for testing)
- An ENTERPRISE user cannot disable features via env vars (edition sets the floor)
- Unknown feature flag names in env vars are silently ignored

### Edition Detection

```python
# Priority order:
1. ATLASBRIDGE_EDITION env var (explicit override)
2. Installed extras (pip install atlasbridge[pro] or atlasbridge[enterprise])
3. Default: COMMUNITY
```

---

## DecisionTraceEntryV2 Schema

```python
class DecisionTraceEntryV2(BaseModel):
    """V2 decision trace entry with hash chaining for tamper evidence."""

    # Identity
    entry_id: UUID                    # Unique entry identifier (UUID4)
    schema_version: str = "2.0"       # Always "2.0" for v2 entries

    # Timestamp
    timestamp: datetime               # UTC, ISO 8601 format

    # Prompt context
    prompt_text: str                  # ANSI-stripped prompt text
    prompt_type: str                  # PromptType enum value
    confidence: str                   # Confidence enum value

    # Decision
    action: str                       # PolicyAction: auto_respond, require_human, etc.
    response: str | None              # Auto-response text (None if escalated)
    matched_rule: str | None          # Rule name that matched (None if no match)

    # Enterprise fields (new in v2)
    risk_level: str                   # RiskLevel: NONE, LOW, MEDIUM, HIGH, CRITICAL
    policy_version: str               # SHA-256 hash of the policy file at eval time
    session_tags: list[str]           # Tags from session context
    evaluation_duration_ms: int       # Time spent in evaluate() call

    # Hash chain
    prev_hash: str                    # SHA-256 hex of previous entry (empty string for first)
    entry_hash: str                   # SHA-256 hex of this entry

    # Session context
    session_id: str                   # Session identifier
    agent_adapter: str                # Adapter name (claude_code, openai_cli, etc.)
```

### Hash Chain Algorithm

```python
def hash_entry(entry: DecisionTraceEntryV2) -> str:
    """Compute SHA-256 hash over canonical fields."""
    canonical = json.dumps({
        "entry_id": str(entry.entry_id),
        "timestamp": entry.timestamp.isoformat(),
        "prompt_text": entry.prompt_text,
        "decision": entry.action,
        "risk_level": entry.risk_level,
        "prev_hash": entry.prev_hash,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

**Chain verification:** For a sequence of entries `[e0, e1, ..., eN]`:
1. `e0.prev_hash` must be `""` (empty string — genesis entry)
2. For `i > 0`: `ei.prev_hash` must equal `e(i-1).entry_hash`
3. For all `i`: `ei.entry_hash` must equal `hash_entry(ei)`

If any check fails, the chain is broken at that entry. The integrity check reports the first broken link.

---

## Risk Classification Decision Table

The risk classifier is purely deterministic. No ML, no heuristics. Given the same inputs, it always produces the same output.

### Base Classification

| Action | Confidence | Risk Level |
|--------|-----------|------------|
| `execute` | < HIGH | **CRITICAL** |
| `execute` | HIGH | **HIGH** |
| `auto_respond` | < HIGH | **HIGH** |
| `auto_respond` | HIGH | **MEDIUM** |
| `require_human` | < MEDIUM | **MEDIUM** |
| `require_human` | >= MEDIUM | **LOW** |
| `skip` | any | **LOW** |
| `log_only` | any | **NONE** |

Special case: `prompt_type = "destructive_confirm"` always yields **CRITICAL** regardless of action or confidence.

### Session Tag Overrides

| Tag | Effect |
|-----|--------|
| `critical_session` | Floor raised to HIGH (result is max(base, HIGH)) |
| `safe_session` | Ceiling lowered to MEDIUM (result is min(base, MEDIUM)) |
| Both present | `critical_session` wins — floor is HIGH, ceiling is ignored |

### Properties

- **Deterministic:** identical inputs always produce identical outputs
- **Monotonic with respect to action severity:** execute > auto_respond > require_human > skip > log_only
- **Observable only:** risk classification does not gate or alter policy evaluation. It is a post-evaluation annotation attached to the decision trace.

---

## Policy Pinning Lifecycle

Policy pinning locks an agent to a specific policy version. When pinned, the agent evaluates prompts against the pinned policy regardless of any updates to the policy file on disk.

### States

```
UNPINNED ──pin(policy_hash)──> PINNED
PINNED ──unpin()──> UNPINNED
PINNED ──pin(new_hash)──> PINNED (re-pin to different version)
```

### Pin Record

```python
class PolicyPin(BaseModel):
    agent_id: str               # Agent identifier
    policy_hash: str            # SHA-256 of pinned policy content
    policy_yaml: str            # Full YAML content (snapshot at pin time)
    pinned_at: datetime         # UTC timestamp
    pinned_by: str              # Identity that created the pin (user or cloud)
    source: str                 # "local" or "cloud"
```

### Behavior

- **Pinned agent:** evaluator loads policy from pin record, not from disk
- **Unpinned agent:** evaluator loads policy from disk (current behavior)
- **Pin conflict:** if both local and cloud pins exist, local pin wins (local authority principle)
- **Pin expiry:** pins do not expire. They must be explicitly removed.
- **Pin audit:** every pin/unpin event is recorded in the audit log

### CLI Commands

```bash
atlasbridge policy pin <file>           # Pin current agent to this policy version
atlasbridge policy unpin                # Remove pin, revert to disk policy
atlasbridge policy pin-status           # Show current pin state
```

---

## Open Core Boundary

### Public (Open Source)

| Package | Contents | Rationale |
|---------|----------|-----------|
| `src/atlasbridge/core/` | Policy engine, prompt detection, session management, audit, routing, daemon | Core runtime must be fully open for trust |
| `src/atlasbridge/enterprise/` | Edition detection, feature flags, risk classifier, trace v2, policy pinning | Local governance features available to all |
| `src/atlasbridge/cloud/` (clients) | Transport, heartbeat, API clients (policy registry, audit stream, auth) | Client-side code ships with the CLI |
| `src/atlasbridge/cli/` | All CLI commands including enterprise and cloud commands | CLI is the user interface |
| `src/atlasbridge/adapters/` | All agent adapters | Adapter ecosystem must be open |
| `src/atlasbridge/channels/` | All notification channels | Channel ecosystem must be open |
| `tests/` | All tests | Tests validate the open source code |

### Experimental (Not Yet Implemented)

> Current version is fully open source under MIT. Future licensing may change.

| Component | Contents | Status |
|-----------|----------|--------|
| Governance API Server | FastAPI server, PostgreSQL schema, migrations, API logic | Design only, not implemented |
| Web Dashboard | Frontend application, dashboard API endpoints | Design only, not implemented |
| Cloud Infrastructure | Deployment configs, monitoring, scaling | Design only, not implemented |

### Boundary Rule

Everything that runs on the user's machine is open source. Server-side cloud components are experimental and not yet implemented. The user's data never leaves their machine unless they explicitly enable cloud sync.

---

## Maturity Labels

Every module in the AtlasBridge codebase carries a maturity label:

| Label | Meaning | API Stability | Test Coverage |
|-------|---------|--------------|---------------|
| **Stable** | Production-ready, breaking changes only in major versions | Guaranteed | > 90% |
| **Experimental** | Functional but API may change in minor versions | Best-effort | > 70% |
| **Specification** | Design complete, implementation not started | N/A | N/A |

### Current Module Maturity

| Module | Maturity | Notes |
|--------|----------|-------|
| `core/policy/` | Stable | Policy DSL v1 shipped in v0.8.1 |
| `core/prompt/` | Stable | Tri-signal detection, shipped in v0.2.0 |
| `core/session/` | Stable | Session management, shipped in v0.2.0 |
| `core/store/` | Stable | SQLite WAL, shipped in v0.2.0 |
| `core/audit/` | Stable | Hash-chained audit log, shipped in v0.2.0 |
| `core/routing/` | Stable | Prompt router, shipped in v0.2.0 |
| `core/daemon/` | Stable | Daemon manager, shipped in v0.2.0 |
| `core/autopilot/` | Stable | Autopilot engine + trace, shipped in v0.6.0 |
| `enterprise/edition` | Experimental | Edition detection, shipping in v0.8.3 |
| `enterprise/features` | Experimental | Feature flags, shipping in v0.8.3 |
| `enterprise/trace_v2` | Experimental | Decision trace v2, planned for v0.8.4 |
| `enterprise/risk` | Experimental | Risk classifier, planned for v0.8.5 |
| `cloud/transport` | Specification | Control channel, planned for v0.10.0 |
| `cloud/heartbeat` | Specification | Heartbeat protocol, planned for v0.10.0 |
| `cloud/api/` | Specification | API clients, planned for v0.10.0 |
| Governance API Server | Specification | Server-side, planned for v1.1.0 |
| Web Dashboard | Specification | Frontend, planned for v1.2.0 |

Maturity labels are updated in release notes when a module graduates (Specification -> Experimental -> Stable).
