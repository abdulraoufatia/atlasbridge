# Ethics & Safety Guarantees

AtlasBridge enforces safety properties through deterministic, testable invariants.
These are not aspirational principles — they are properties verified by CI on every commit.

## Guarantee 1: Network Isolation (Cloud Module)

The cloud module (`src/atlasbridge/cloud/`) contains interface definitions only.
No network-capable libraries may be imported.

**What is tested:** An AST-based scanner walks every `.py` file in the cloud module
and fails if any banned import is found. Banned modules include `requests`, `httpx`,
`aiohttp`, `urllib3`, `socket`, `websockets`, `grpc`, and `subprocess`.

**Test file:** `tests/safety/test_cloud_network_isolation.py`

## Guarantee 2: Injection Idempotency

The `decide_prompt()` atomic SQL guard ensures:
- No duplicate injection (nonce replay rejected)
- No expired injection (TTL enforced)
- No cross-session injection (wrong nonce rejected)
- No unauthorised injection (unknown prompt_id rejected)

**What is tested:** Each invariant is verified by calling `decide_prompt()` with
invalid inputs and confirming it returns 0 (rejected).

**Test file:** `tests/safety/test_injection_safety.py`

## Guarantee 3: Secret Redaction

Secrets (Telegram bot tokens, Slack tokens, API keys) are redacted in debug output,
support bundles, and audit logs. The audit writer stores `value_length` and
`excerpt_length` instead of raw values.

**What is tested:** Known token patterns are redacted by `_redact_text()` and
`_redact_dict()`. Sensitive dictionary keys are recursively redacted.

**Test file:** `tests/safety/test_secret_redaction.py`

## Guarantee 4: Trace Integrity (Hash-Chained Decision Trace)

Every autopilot decision is recorded in an append-only JSONL trace file with
SHA-256 hash chaining. Each entry includes `prev_hash` (linking to the previous
entry) and its own `hash`. Tampering with any entry breaks the chain.

**What is tested:** Hash chain contiguity, tamper detection, chain restart after
rotation, and chain resumption after process restart.

**Verification command:**
```bash
atlasbridge trace integrity-check
```

**Test file:** `tests/safety/test_trace_integrity.py`

## Guarantee 5: Risk Determinism

The enterprise risk classifier (`EnterpriseRiskClassifier.classify()`) is a pure
function: identical inputs always produce identical outputs. No randomness, no
side effects, no environment drift.

**What is tested:** 1000 identical calls produce the same result. All four risk
levels (LOW, MEDIUM, HIGH, CRITICAL) are reachable via known inputs. Output
dataclasses are frozen (immutable).

**Test file:** `tests/safety/test_risk_determinism.py`

## Guarantee 6: Default-Safe Escalation

When no policy rule matches or confidence is LOW, the system defaults to
`require_human` (escalate to a human). The fallback action is never `auto_reply`.

**What is tested:** `PolicyDefaults` fields accept only `require_human` or `deny`.
Empty policies always escalate. Low confidence with no matching rule triggers
escalation across all prompt types.

**Test file:** `tests/safety/test_low_confidence_default_safe.py`

## Guarantee 7: State Machine Safety

The prompt state machine enforces valid transitions. Terminal states
(RESOLVED, EXPIRED, CANCELED, FAILED) have no outgoing transitions.
Invalid transitions raise `ValueError`. History is append-only.

**What is tested:** Terminal state transition sets are empty. Full lifecycle
path succeeds. Invalid transitions raise. All `PromptStatus` values have
entries in `VALID_TRANSITIONS`.

**Test file:** `tests/safety/test_prompt_state_machine.py`

## CI Enforcement

The `ethics-safety-gate` CI job runs all safety tests on every push and pull
request. It is a required dependency of the `build` job — builds cannot
proceed unless all safety tests pass.

**What is tested:** The CI YAML is parsed and verified to contain the
`ethics-safety-gate` job, and that `build.needs` includes it.

**Test file:** `tests/safety/test_ci_gate_enforcement.py`

## Running Safety Tests Locally

```bash
# Run all safety tests
pytest tests/safety/ -v

# Run a specific guarantee
pytest tests/safety/test_injection_safety.py -v

# Verify trace integrity
atlasbridge trace integrity-check

# Full CI equivalent
ruff check . && ruff format --check . && mypy src/atlasbridge/ && pytest tests/ --cov=atlasbridge
```
