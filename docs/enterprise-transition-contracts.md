# Enterprise Transition Contracts

**Maturity: Design Document — No Implementation**

This document defines the contracts that govern how AtlasBridge components evolve across phases. Each phase builds on the previous one. These contracts ensure that transitions are safe, backward-compatible, and non-breaking.

---

## Table of Contents

- [Phase Overview](#phase-overview)
- [Phase A to Phase B Transition](#phase-a-to-phase-b-transition)
- [Phase B to Phase C Transition](#phase-b-to-phase-c-transition)
- [Frozen Protocol and Schema Invariants](#frozen-protocol-and-schema-invariants)
- [Backward Compatibility Guarantees](#backward-compatibility-guarantees)
- [Data Schema Evolution Plan](#data-schema-evolution-plan)

---

## Phase Overview

| Phase | Scope | Key Components |
|-------|-------|----------------|
| **Phase A** | Local runtime (current) | Policy DSL, autopilot engine, decision trace, audit log, adapters, channels |
| **Phase B** | Enterprise local extensions | Cloud client injection points, enhanced trace schema (V2), control message protocol stubs, signed policy support |
| **Phase C** | Enterprise dashboard tier | Governance API, Web Dashboard, policy signing service, audit aggregation, WebSocket channel |

Each phase is additive. No phase removes functionality from a previous phase. A runtime operating at Phase A continues to work identically if Phase B or Phase C components are unavailable.

---

## Phase A to Phase B Transition

### What Phase A Has

Phase A is the current open-source local runtime:

- `AutopilotEngine` — evaluates policy locally, produces `DecisionTrace` entries.
- `AuditWriter` — writes hash-chained audit events to local SQLite.
- `PolicyParser` / `PolicyEvaluator` — loads and evaluates YAML policy files.
- `DaemonManager` — orchestrates all subsystems.
- Adapters and channels operate independently.

### What Phase B Adds

Phase B introduces enterprise-ready extension points without changing Phase A behavior.

#### 1. Cloud Client Injection Points

The `DaemonManager` gains an optional `cloud_client` dependency:

```python
class DaemonManager:
    def __init__(
        self,
        ...,
        cloud_client: CloudClient | None = None,  # Phase B addition
    ):
```

- When `cloud_client is None` (Phase A mode): all behavior is identical to today.
- When `cloud_client` is provided (Phase B mode): decision traces and audit events are also forwarded to the cloud client for async upload.

**Contract:** The `cloud_client` parameter is always optional. Passing `None` produces identical behavior to Phase A. This is tested in CI.

#### 2. DecisionTrace V2

Phase A currently writes `DecisionTrace` entries as JSONL. Phase B introduces a versioned schema:

```python
class DecisionTraceEntryV2:
    version: Literal[2]
    trace_id: str           # UUID
    org_id: str | None      # None in Phase A; populated in Phase B+
    runtime_id: str | None  # None in Phase A; populated in Phase B+
    timestamp: str          # ISO 8601 UTC
    session_id: str
    prompt_nonce: str
    prompt_type: str
    confidence: str
    matched_rule: str | None
    decision: str
    action: str
    latency_ms: float
    policy_version: str | None
    policy_hash: str | None # SHA-256 of policy YAML
    tags: dict[str, str]    # Extensible metadata
```

**Contract:** `DecisionTraceEntryV2` is backward-compatible with V1. All V1 fields are preserved. New fields (`org_id`, `runtime_id`, `policy_hash`, `tags`) default to `None` or empty when not available.

#### 3. ControlMessage Protocol Stubs

Phase B defines the `ControlMessage` protocol as local stubs:

```python
class ControlMessage:
    message_id: str         # UUID
    message_type: str       # e.g., "policy_update", "status_request", "heartbeat"
    org_id: str
    runtime_id: str
    timestamp: str          # ISO 8601 UTC
    payload: dict
    signature: str          # Ed25519 signature (empty in stub mode)
```

In Phase B, `ControlMessage` is defined but only used locally for testing and protocol validation. No network transport exists yet.

**Contract:** The `ControlMessage` schema is frozen once shipped in Phase B. Phase C implements the transport layer but does not alter the message schema.

#### 4. Signed Policy Support

Phase B adds signature verification to the policy parser:

```python
def load_policy(
    path: Path,
    *,
    verify_signature: bool = False,       # Phase B addition
    trusted_public_key: bytes | None = None,  # Phase B addition
) -> Policy:
```

- When `verify_signature=False` (default): identical to Phase A. Unsigned local YAML files work as before.
- When `verify_signature=True`: the policy file must include a signature envelope. Verification uses the `trusted_public_key`.

**Contract:** `verify_signature` defaults to `False`. Phase A behavior is always available. Signature verification is opt-in.

#### 5. Phase B Extension Summary

| Component | Phase A | Phase B Addition | Breaking Change? |
|-----------|---------|------------------|------------------|
| `DaemonManager` | No cloud awareness | Optional `cloud_client` parameter | No — `None` preserves Phase A behavior |
| `DecisionTrace` | V1 JSONL | V2 schema (superset of V1) | No — V1 fields preserved; new fields default to None |
| `ControlMessage` | Not present | Stub protocol definition | No — new code only; not called by Phase A paths |
| `PolicyParser` | Loads unsigned YAML | Optional signature verification | No — `verify_signature=False` is default |
| `AuditWriter` | Local SQLite only | Optional cloud forwarding via `cloud_client` | No — local-only when `cloud_client is None` |

---

## Phase B to Phase C Transition

### What Phase B Has

Phase B provides the local enterprise extensions described above: cloud client injection points, V2 trace schema, control message stubs, and signed policy support.

### What Phase C Adds

Phase C implements the enterprise dashboard tier. Phase B stubs become real clients.

#### 1. Cloud Client Stubs Become Real HTTP Clients

Phase B defines `CloudClient` as an abstract base:

```python
class CloudClient(ABC):
    @abstractmethod
    async def upload_trace(self, entry: DecisionTraceEntryV2) -> None: ...

    @abstractmethod
    async def upload_audit(self, event: AuditEvent) -> None: ...

    @abstractmethod
    async def fetch_policy(self) -> SignedPolicy | None: ...

    @abstractmethod
    async def connect_control_channel(self) -> None: ...
```

Phase C provides the concrete implementation:

```python
class AtlasBridgeCloudClient(CloudClient):
    """Real HTTP/WSS client for AtlasBridge Cloud."""

    def __init__(
        self,
        api_url: str,
        runtime_private_key: Ed25519PrivateKey,
        cloud_public_key: Ed25519PublicKey,
        org_id: str,
    ): ...
```

**Contract:** `AtlasBridgeCloudClient` implements the `CloudClient` ABC defined in Phase B. No changes to the ABC are permitted. New capabilities are added via new optional methods with default implementations in the ABC.

#### 2. Dashboard Consumes API

The Web Dashboard (React SPA) consumes the REST API and WebSocket endpoints defined in Phase C. The dashboard has no direct interaction with the local runtime. All data flows through the cloud API.

```
Runtime Agent → CloudClient → Cloud API → PostgreSQL
                                              ↓
                              Dashboard ← REST API + WSS
```

**Contract:** The dashboard is a pure consumer of the cloud API. It does not define new data formats. The API contract (request/response schemas) is the interface boundary.

#### 3. Control Channel Goes Live

Phase B's `ControlMessage` stubs are transported over WSS in Phase C:

- Runtime connects via WSS after handshake.
- Messages are serialized as JSON, signed with Ed25519.
- The `ControlMessage` schema from Phase B is used without modification.

**Contract:** The `ControlMessage` schema defined in Phase B is used verbatim. Phase C adds transport, not schema changes.

#### 4. Phase C Extension Summary

| Component | Phase B | Phase C Addition | Breaking Change? |
|-----------|---------|------------------|------------------|
| `CloudClient` | ABC (abstract) | Concrete `AtlasBridgeCloudClient` | No — implements existing ABC |
| `ControlMessage` | Stub (local only) | WSS transport | No — same schema over network |
| Policy signing | Local verification only | Cloud-side signing + distribution | No — verification unchanged |
| Audit | Local + optional forwarding | Cloud storage + integrity checks | No — forwarding path unchanged |
| Dashboard | Not present | React SPA consuming API | No — new component; no runtime changes |

---

## Frozen Protocol and Schema Invariants

### DecisionTraceEntryV2 — Frozen Once Shipped

Once `DecisionTraceEntryV2` ships in Phase B, the schema is frozen. The following rules apply:

1. **No field removal.** Every field in V2 remains in all future versions.
2. **No field type changes.** A field that is `str` stays `str`. A field that is `str | None` stays `str | None`.
3. **No field rename.** Field names are permanent.
4. **Additive changes only.** New fields may be added to future versions (V3, V4, ...). New fields must default to `None`, empty string, empty dict, or zero.
5. **Version field is mandatory.** Every trace entry includes `version: int`. Consumers must handle unknown versions gracefully (read known fields, ignore unknown fields).

### ControlMessage Protocol — Frozen Once Shipped

Once `ControlMessage` ships in Phase B, the protocol is frozen:

1. **No field removal** from the base `ControlMessage` structure.
2. **No field type changes** in the base structure.
3. **New message types** may be added by defining new `message_type` values with new `payload` schemas.
4. **Existing message types** retain their payload schema permanently. Payload evolution follows additive-only rules.
5. **Unknown message types** must be handled gracefully — logged and ignored, never causing errors.

### What "Frozen" Means

"Frozen" means:
- The schema is a public contract between the local runtime and the cloud tier.
- Any change that would break a consumer of the current schema is prohibited.
- This is enforced by schema validation tests in CI that verify backward compatibility.
- If a fundamentally new structure is needed, it ships as a new version (V3) alongside the old one, not as a modification.

---

## Backward Compatibility Guarantees

### V1 Traces Alongside V2

When Phase B ships V2 traces, existing V1 traces are not migrated or invalidated:

1. V1 JSONL files remain readable by the runtime and any tooling.
2. The cloud tier (Phase C) accepts both V1 and V2 trace uploads.
3. The dashboard displays V1 and V2 traces identically, with V2 showing additional fields when available.
4. No migration step is required. V1 files are read as-is.

### Cloud Disabled Is Always Safe

Disabling cloud connectivity at any phase is always safe and non-breaking:

| Scenario | Behavior |
|----------|----------|
| Phase A (no cloud code) | Full functionality. |
| Phase B (cloud_client=None) | Full Phase A functionality. Enterprise extension points are dormant. |
| Phase B (cloud_client set, cloud unreachable) | Full local functionality. Traces/audit queue locally. |
| Phase C (cloud connected) | Full functionality + cloud features. |
| Phase C (cloud disconnected) | Full local functionality. Cloud features degrade gracefully. Dashboard goes stale. |
| Phase C (cloud explicitly disabled in config) | Identical to Phase A. No cloud code paths execute. |

**Contract:** There is no state in which a runtime requires cloud connectivity to function. This is tested in CI with a dedicated "offline mode" test suite.

### Version Compatibility Matrix

| Runtime Version | Cloud Version | Compatible? | Notes |
|----------------|---------------|-------------|-------|
| Phase A | None | Yes | No cloud awareness |
| Phase B | None | Yes | Cloud stubs dormant |
| Phase B | Phase C | Yes | Full functionality |
| Phase A | Phase C | No | Runtime lacks cloud client; cloud cannot connect |
| Phase C runtime | Phase C cloud, older | Yes | Cloud must accept V2 traces; additive-only guarantees this |

---

## Data Schema Evolution Plan

### Governing Principles

1. **Additive-only.** New fields may be added. Existing fields are never removed or renamed.
2. **New fields default to empty/zero.** Any new field must have a default value that is safe to ignore: `None`, `""`, `{}`, `[]`, `0`, `false`.
3. **No field removal.** Once a field ships in a released version, it exists forever in that schema version.
4. **No type narrowing.** A field typed as `str | None` cannot become `str` (removing the None option). A field typed as `str` cannot become `int`.
5. **Type widening is permitted cautiously.** A field typed as `str` can become `str | None` if all consumers already handle None gracefully. This is rare and requires explicit approval.
6. **Version-gated features.** If a new field is only meaningful for Phase C, it defaults to `None` in Phase B and is only populated when cloud is connected.

### Schema Versioning Strategy

| Schema | Version Field | Current | Next |
|--------|--------------|---------|------|
| DecisionTrace | `version: int` | V1 (Phase A) | V2 (Phase B) |
| AuditEvent | `schema_version: int` | 1 (Phase A) | 2 (Phase B, adds org_id) |
| ControlMessage | `protocol_version: int` | — | 1 (Phase B) |
| Policy | `dsl_version: str` | "v1" (Phase A) | "v1" (unchanged in Phase B; signing is envelope, not schema) |

### Migration Strategy

There are no migrations. Old data is read as-is. New data is written in the latest schema. Consumers are expected to:

1. Check the version field.
2. Read known fields.
3. Ignore unknown fields.
4. Use defaults for missing optional fields.

This is the same strategy used by Protocol Buffers and similar systems. It is simple, safe, and does not require coordinated upgrades.

### Example: Adding a Field to DecisionTraceEntryV2

Suppose Phase C needs to add a `cloud_received_at` timestamp:

```python
class DecisionTraceEntryV2:
    ...
    cloud_received_at: str | None = None  # Added in Phase C; None when cloud not connected
```

This is safe because:
- Existing V2 consumers ignore the new field (they don't read it).
- New consumers check for `None` and handle the offline case.
- No existing data is invalidated.
- No migration is needed.

If the change were instead "remove the `latency_ms` field," it would be rejected. That field is frozen.

---

> **Reminder:** These contracts exist to ensure that transitions between phases are safe and non-breaking.
> Phase A is shipped and stable. Phase B and Phase C are design-only.
> No contract defined here requires implementation until its target phase begins.
