# Contract Surfaces

This document inventories every public contract surface in AtlasBridge, its stability status, and the safety test that guards it.

---

## Surface 1: Adapter API

**Source:** `src/atlasbridge/adapters/base.py`
**Guard:** `tests/safety/test_adapter_api_stability.py`
**Status:** Stable

### Abstract Methods (5)

| Method | Signature |
|--------|-----------|
| `start_session` | `(self) -> str` |
| `terminate_session` | `(self, session_id: str) -> None` |
| `read_stream` | `(self) -> AsyncIterator[bytes]` |
| `inject_reply` | `(self, text: str) -> None` |
| `await_input_state` | `(self) -> bool` |

### Optional Methods (3)

| Method | Default Behavior |
|--------|-----------------|
| `snapshot_context` | Returns `{}` |
| `get_detector` | Returns `None` |
| `healthcheck` | Returns `{"status": "ok"}` |

### AdapterRegistry

- `register(name, cls)` — Register an adapter class by name.
- `get(name)` — Retrieve a registered adapter class.
- `list_all()` — Return all registered adapter names.

### Registered Adapters (5)

`claude`, `claude-code`, `openai`, `gemini`, `custom`

---

## Surface 2: Channel API

**Source:** `src/atlasbridge/channels/base.py`
**Guard:** `tests/safety/test_channel_api_stability.py`
**Status:** Stable

### Abstract Methods (7)

| Method | Purpose |
|--------|---------|
| `start` | Initialize the channel connection |
| `close` | Tear down the channel |
| `send_prompt` | Send a prompt to the human |
| `notify` | Send a notification message |
| `edit_prompt_message` | Edit a previously sent prompt |
| `receive_replies` | Async generator yielding Reply objects |
| `is_allowed` | Check if a user identity is allowed |

### Optional Methods (1)

| Method | Default Behavior |
|--------|-----------------|
| `healthcheck` | Returns `{"status": "ok"}` |

### ChannelCircuitBreaker

| Parameter | Frozen Value |
|-----------|-------------|
| `threshold` | `3` |
| `recovery_seconds` | `30.0` |

### MultiChannel

Fan-out to multiple channels. Message ID format: `{channel}:{id}`.

---

## Surface 3: Policy DSL v0

**Source:** `src/atlasbridge/core/policy/model.py`
**Guard:** `tests/safety/test_policy_schema_stability.py`
**Status:** Stable

### Enums

| Enum | Members |
|------|---------|
| `AutonomyMode` | `OFF`, `ASSIST`, `FULL` |
| `PromptTypeFilter` | `yes_no`, `confirm_enter`, `multiple_choice`, `free_text`, `unknown` |
| `ConfidenceLevel` | `LOW`, `MED`, `HIGH` |

### Action Types (4)

| Type | Model | Key Field |
|------|-------|-----------|
| `auto_reply` | `AutoReplyAction` | `value: str` |
| `require_human` | `RequireHumanAction` | — |
| `deny` | `DenyAction` | `reason: str` (optional) |
| `notify_only` | `NotifyOnlyAction` | — |

### PolicyDefaults (Safety-Critical)

| Field | Frozen Value | Rejects |
|-------|-------------|---------|
| `no_match` | `"require_human"` | `"auto_reply"` |
| `low_confidence` | `"require_human"` | `"auto_reply"` |

### Evaluation Semantics

- `policy_version` must be `"0"`.
- First-match-wins rule evaluation.
- `content_hash()` for policy identity.
- Extra fields forbidden (Pydantic `model_config`).

---

## Surface 4: Policy DSL v1

**Source:** `src/atlasbridge/core/policy/model_v1.py`
**Status:** Stable (except `extends` = experimental)

Additions over v0:
- `any_of` / `none_of` compound match conditions
- `session_tag` field on rules
- `max_confidence` match criterion
- `extends` policy inheritance (experimental — resolution semantics may change)

---

## Surface 5: DecisionTrace

**Source:** `src/atlasbridge/core/autopilot/trace.py`
**Guard:** `tests/safety/test_trace_integrity.py`, `tests/safety/test_safe_defaults_immutable.py`
**Status:** Stable

| Aspect | Detail |
|--------|--------|
| Format | Append-only JSONL, 14 fields per entry |
| Hash chain | `SHA-256(prev_hash + idempotency_key + action_type + canonical_json)` |
| Rotation | `MAX_BYTES_DEFAULT = 10 MB`, `MAX_ARCHIVES = 3` |
| Verification | `verify_integrity()` static method |

---

## Surface 6: Audit Log

**Source:** `src/atlasbridge/core/audit/writer.py`, `src/atlasbridge/core/store/database.py`
**Guard:** `tests/safety/test_audit_schema_stability.py`
**Status:** Stable

### SQLite Tables (4)

`sessions`, `prompts`, `replies`, `audit_events`

### audit_events Columns

`id`, `event_type`, `session_id`, `prompt_id`, `payload`, `timestamp`, `prev_hash`, `hash`

### Hash Chain Formula

```
SHA-256(prev_hash + event_id + event_type + payload_json)
```

Where `payload_json` uses `json.dumps(payload, separators=(",", ":"), sort_keys=True)`.

### AuditWriter Event Methods (12)

`session_started`, `session_ended`, `prompt_detected`, `prompt_routed`, `reply_received`, `response_injected`, `prompt_expired`, `duplicate_callback`, `late_reply_rejected`, `invalid_callback`, `telegram_polling_failed`, `daemon_restarted`

---

## Surface 7: Config

**Source:** `src/atlasbridge/core/config.py`
**Guard:** `tests/safety/test_config_schema_stability.py`
**Status:** Stable

### AtlasBridgeConfig Fields (7)

`config_version`, `telegram`, `slack`, `prompts`, `logging`, `database`, `adapters`

### Frozen Defaults

| Field | Value |
|-------|-------|
| `config_version` | `1` |
| `PromptsConfig.yes_no_safe_default` | `"n"` (rejects `"y"` and `"yes"`) |

### Environment Variable Overlay (8)

See [API Stability Policy](api-stability-policy.md#environment-variables) for the full list.

### Migration

`config_version` 0 → 1 migration handled by `src/atlasbridge/core/config_migrate.py`.

---

## Surface 8: CLI Surface

**Source:** `src/atlasbridge/cli/main.py` + 16 subcommand files
**Guard:** `tests/safety/test_cli_surface_stability.py`
**Status:** Stable (enterprise commands = experimental)

### Frozen Top-Level Commands (25)

`ui`, `setup`, `start`, `stop`, `status`, `run`, `sessions`, `logs`, `doctor`, `version`, `debug`, `channel`, `adapter`, `adapters`, `config`, `policy`, `autopilot`, `edition`, `features`, `cloud`, `trace`, `lab`, `db`, `pause`, `resume`

### Frozen Subcommands

| Group | Subcommands |
|-------|------------|
| `autopilot` | `enable`, `disable`, `status`, `mode`, `explain`, `history` |
| `policy` | `validate`, `test`, `migrate` |

### Experimental Commands

| Command | Label |
|---------|-------|
| `edition` | `[EXPERIMENTAL]` |
| `features` | `[EXPERIMENTAL]` |
| `cloud` | `[EXPERIMENTAL]` |
| `cloud status` | `[EXPERIMENTAL]` |

---

## Safety-Critical Default Values

**Guard:** `tests/safety/test_safe_defaults_immutable.py`

| Constant | Value | Source |
|----------|-------|--------|
| `DEFAULT_TIMEOUT_SECONDS` | `300` | `core/constants.py` |
| `MAX_BUFFER_BYTES` | `4096` | `core/constants.py` |
| `ECHO_SUPPRESS_MS` | `500` | `core/constants.py` |
| `PromptsConfig.yes_no_safe_default` | `"n"` | `core/config.py` |
| `PolicyDefaults().no_match` | `"require_human"` | `core/policy/model.py` |
| `PolicyDefaults().low_confidence` | `"require_human"` | `core/policy/model.py` |
| `DecisionTrace.MAX_BYTES_DEFAULT` | `10 MB` | `core/autopilot/trace.py` |
| `DecisionTrace.MAX_ARCHIVES` | `3` | `core/autopilot/trace.py` |
