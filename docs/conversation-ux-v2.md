# Conversation UX v2 — Interaction Pipeline

**Status:** Current
**Phase:** C.Y + C.Y2 + C.Z — Full Conversational Agent Mode
**Version:** v0.10.0

---

## Overview

Conversation UX v2 upgrades the human-operator experience from a raw terminal relay to a structured, conversational interface. The interaction pipeline classifies prompts, builds execution plans, handles injection with retry/verification, and provides structured feedback — while preserving all existing correctness invariants.

### Key capabilities

- **Structured prompt handling** — yes/no, confirm-enter, numbered-choice, free-text, and password prompts each get tailored button layouts and feedback
- **Chat Mode** — operators can type naturally between prompts; CLI output is forwarded as monospace messages
- **Retry and escalation** — if the CLI doesn't respond after injection, retry once then escalate
- **Password redaction** — credentials are never shown in feedback messages or logs
- **Operator feedback** — "Sent: y + Enter", "CLI advanced", "Sent: [REDACTED] + Enter"
- **Plan detection** — agent execution plans are detected and presented with Execute/Modify/Cancel buttons
- **Streaming state** — PTY output transitions session to STREAMING; user messages are queued until output settles
- **Secret redaction** — tokens and API keys are stripped from output before reaching channels

---

## Architecture

```
PromptDetector
  → PromptRouter._dispatch() → InteractionClassifier.classify()
    → InteractionPlan via build_plan()
      → Channel (structured buttons + feedback)
  → User responds
  → PromptRouter.handle_reply() → InteractionEngine.handle_prompt_reply()
    → InteractionExecutor.execute()
      → adapter.inject_reply() → verify advance → retry/escalate → feedback

Chat Mode (no active prompt):
  PTY output → OutputForwarder → Channel (code block messages)
  User message → PromptRouter._chat_mode_handler
    → InteractionEngine.handle_chat_input()
      → PTY stdin

Streaming + Plan Detection (v0.10.0):
  PTY output → OutputForwarder → StreamingManager.accumulate()
    → detect_plan() → DetectedPlan? → channel.send_plan() (buttons)
  State: RUNNING → STREAMING (output active) → RUNNING (idle)
  User message during STREAMING → queued → drained on RUNNING
```

---

## Components

### InteractionClassifier (`core/interaction/classifier.py`)

Refines `PromptType` into a finer-grained `InteractionClass`:

| InteractionClass | Maps from | Description |
|-----------------|-----------|-------------|
| `YES_NO` | TYPE_YES_NO | Binary confirmation |
| `CONFIRM_ENTER` | TYPE_CONFIRM_ENTER | Press Enter to continue |
| `NUMBERED_CHOICE` | TYPE_MULTIPLE_CHOICE | Numbered menu selection |
| `FREE_TEXT` | TYPE_FREE_TEXT | Generic text input |
| `PASSWORD_INPUT` | TYPE_FREE_TEXT (refined) | Sensitive credential input |
| `CHAT_INPUT` | N/A (no prompt) | Conversational mode |
| `FOLDER_TRUST` | ML-only | "Trust this folder?" special case |
| `RAW_TERMINAL` | ML-only | Unparsable interactive prompts (always escalates) |

Password detection uses regex patterns matching common credential prompts (password, token, API key, secret, etc.).

**Design:** `InteractionClass` does NOT replace `PromptType`. It is a refinement layer used only within the interaction engine. FOLDER_TRUST and RAW_TERMINAL are ML-only types that the deterministic classifier cannot produce; they are introduced by the ClassificationFuser when an ML classifier provides them.

### InteractionPlan (`core/interaction/plan.py`)

Frozen dataclass mapping each `InteractionClass` to an execution strategy:

| Field | Purpose |
|-------|---------|
| `append_cr` | Append `\r` after value (always True) |
| `suppress_value` | Redact value in logs/feedback (True for PASSWORD_INPUT) |
| `max_retries` | Retry count if CLI stalls (0–1) |
| `retry_delay_s` | Wait between retries (2s) |
| `verify_advance` | Check if CLI produced new output |
| `advance_timeout_s` | Timeout for advance check (5s) |
| `escalate_on_exhaustion` | Escalate when retries exhausted |
| `display_template` | Feedback template (e.g., "Sent: {value} + Enter") |
| `escalation_template` | Per-plan escalation message (no more generic "arrow keys" message) |
| `button_layout` | Channel button layout hint |

Plans are created via `build_plan(interaction_class)` — a pure function with no side effects.

### InteractionExecutor (`core/interaction/executor.py`)

Handles the actual injection and verification:

1. Inject value via `adapter.inject_reply()` (uses existing `_normalise()` with `\r`)
2. If `verify_advance`: poll `detector.last_output_time` at 200ms intervals
3. If stalled + retries remain: notify, wait, re-inject
4. If retries exhausted + escalation enabled: send escalation message

Returns `InjectionResult` with success/failure, advance status, retry count, and feedback.

### InteractionEngine (`core/interaction/engine.py`)

Per-session orchestrator:

- `handle_prompt_reply(event, reply)` — classify → plan → execute → return result
- `handle_chat_input(reply)` — direct PTY stdin injection for conversational mode

### OutputForwarder (`core/interaction/output_forwarder.py`)

Batches PTY output and forwards to channel as monospace messages:

| Setting | Value | Purpose |
|---------|-------|---------|
| `BATCH_INTERVAL_S` | 2.0 | Collect output for 2s before sending |
| `MAX_OUTPUT_CHARS` | 2000 | Truncate long output |
| `MAX_MESSAGES_PER_MINUTE` | 15 | Rate limit |
| `MIN_MEANINGFUL_CHARS` | 10 | Skip tiny fragments |

### MLClassifier Protocol (`core/interaction/ml_classifier.py`)

Defines the interface for optional ML-assisted classification:

- `MLClassifier` — runtime-checkable `Protocol` with `classify(text, prompt_type) -> MLClassification | None`
- `NullMLClassifier` — default no-op (always returns None); deterministic classifier wins
- `MLClassification` — StrEnum (9 values) including ML-only types FOLDER_TRUST, RAW_TERMINAL

**Design:** No actual ML model is shipped. The Protocol is a clean extension point for future ML classifiers without adding runtime dependencies.

### ClassificationFuser (`core/interaction/fuser.py`)

Fuses deterministic and ML classifications with safety-first rules:

| Rule | Condition | Result |
|------|-----------|--------|
| 1 | Deterministic HIGH | Deterministic wins, ignore ML |
| 2 | ML returns None/UNKNOWN | Deterministic wins |
| 3 | Deterministic MED + ML agrees | Boosted to "fused" HIGH |
| 4 | Deterministic MED + ML disagrees | Escalate (disagreement=True) |
| 5 | Deterministic LOW + ML has opinion | Use ML |
| 6 | ML returns FOLDER_TRUST/RAW_TERMINAL | Use ML (no deterministic equivalent) |

**Safety invariant:** ML output never triggers execution without deterministic confirmation at HIGH confidence.

### OutputRouter (`core/interaction/output_router.py`)

Classifies PTY output into three kinds:

- **AGENT_MESSAGE** — prose text (markdown, complete sentences) → `send_agent_message()`
- **CLI_OUTPUT** — commands, stack traces, build output → `send_output()`
- **NOISE** — too short, whitespace-only → discarded

When `show_raw_output=True`, classification is bypassed and everything becomes CLI_OUTPUT.

### ConversationRegistry (`core/conversation/session_binding.py`)

Thread-to-session binding with TTL and state tracking:

- `bind(channel, thread_id, session_id)` — create/update binding
- `resolve(channel, thread_id)` — deterministic session lookup
- `unbind(session_id)` — cleanup on session end
- `prune_expired()` — remove stale bindings (default TTL: 4 hours)

State machine: IDLE → RUNNING → AWAITING_INPUT → RUNNING → STOPPED

### BaseChannel.send_agent_message()

Non-abstract default method that delegates to `notify()`. Channels override for rich formatting:
- Telegram: HTML formatting (no `<pre>`)
- Slack: mrkdwn formatting (no code block)
- Multi: fan-out to all sub-channels

---

## Operator Feedback Messages

| Scenario | Message |
|----------|---------|
| Yes/No answered | `Sent: y + Enter` |
| Choice selected | `Sent: option 2 + Enter` |
| Enter pressed | `Sent: Enter` |
| Free text sent | `Sent: "deploy staging" + Enter` |
| Password sent | `Sent: [REDACTED] + Enter` |
| CLI advanced | `CLI advanced` |
| Stalled, retrying | `CLI did not respond to "y", retrying...` |
| Retry exhausted | Per-plan contextual message (e.g., `CLI did not respond to "y" after retries. Please respond locally.`) |
| Chat input | `Sent: "check the logs"` |

---

## Router Integration

The PromptRouter accepts two optional parameters:

- `interaction_engine` — when set, `handle_reply()` uses the interaction pipeline instead of direct `adapter.inject_reply()`
- `chat_mode_handler` — when set and a free-text reply has no active prompt, routes to chat mode instead of dropping

Both are backwards-compatible: without these params, the existing direct injection path is unchanged.

---

## Daemon Wiring

In `DaemonManager._run_adapter_session()`:

1. `ConversationRegistry` is created at daemon start and passed to `PromptRouter`
2. `ClassificationFuser(InteractionClassifier(), NullMLClassifier())` is created per session
3. `InteractionEngine` is created with the fuser injected
4. `OutputRouter` is created per session and injected into `OutputForwarder`
5. The engine is injected into `PromptRouter` via `_interaction_engine` and `_chat_mode_handler`
6. Session start/stop lifecycle notifications are sent via `channel.notify()`
7. On session end, conversation bindings are unbound via `registry.unbind(session_id)`

---

## Streaming and Plan Detection (v0.10.0)

### STREAMING State

The `ConversationState` enum includes a `STREAMING` state. When the OutputForwarder detects active PTY output, it transitions the conversation to STREAMING. During STREAMING:

- User messages are **queued** in `ConversationBinding.queued_messages`, not injected
- The channel notifies the user: "Queued for next turn."
- After 2 idle flush cycles (no new output), state transitions back to RUNNING
- Queued messages are drained and injected as chat input

State diagram: `IDLE → RUNNING → STREAMING → RUNNING → AWAITING_INPUT → RUNNING → STOPPED`

### Plan Detection

The `StreamingManager` accumulates output and runs `detect_plan()` on each batch. When a plan is detected:

1. The plan is rendered via `channel.send_plan()` with Execute/Modify/Cancel buttons
2. **Execute** — notifies "Plan accepted. Agent continuing." (no PTY injection)
3. **Modify** — notifies "Send your modifications as a message." (next free-text → chat mode)
4. **Cancel** — injects cancellation text via chat handler (uses `\r`)

Plan responses use the `__plan__` sentinel prompt_id and are routed by `PromptRouter.handle_plan_response()`.

### Secret Redaction

The `OutputForwarder._redact()` method strips tokens matching known patterns before any output reaches a channel:

- Telegram bot tokens (`\d+:[A-Za-z0-9_-]{35}`)
- Slack tokens (`xoxb-`, `xoxp-`, `xapp-`)
- OpenAI keys (`sk-`)
- GitHub PATs (`ghp_`, `gho_`, `ghs_`, `ghp_`)
- AWS access keys (`AKIA`)

---

## Invariant Preservation

All existing correctness invariants remain enforced:

| Invariant | How preserved |
|-----------|--------------|
| No duplicate injection | Nonce guard in `decide_prompt()` — executor uses existing adapter path |
| No expired injection | TTL checked in router before reaching executor |
| No cross-session injection | Session binding checked in router before reaching executor |
| No unauthorized injection | Allowlist checked in router before reaching executor |
| No echo loops | `detector.mark_injected()` called after every injection |
| No lost prompts | Pending prompt reload unchanged |
| Bounded memory | Rolling 4096-byte buffer unchanged |
| CR semantics | All PTY injection uses `\r` (never `\n`) |
| Password safety | `suppress_value=True` prevents credentials in feedback/logs |
| ML never executes | Fuser outputs classification only; execution goes through deterministic plan→executor |
| Thread isolation | ConversationRegistry prevents cross-thread session leakage |
| No secret leakage | `_redact()` strips tokens before any channel send |
| Plan never injects on Execute | Execute decision notifies only; no PTY injection |
| Bounded accumulator | StreamingManager capped at 8192 chars |
| State-driven routing | STREAMING queues messages; STOPPED drops; RUNNING→chat; AWAITING_INPUT→prompt |

---

## Test Coverage

| Test file | Count | What it tests |
|-----------|-------|---------------|
| `test_interaction_classifier.py` | 19 | Classification for all prompt types, password detection, chat input |
| `test_interaction_plan.py` | 27 | Plan building, frozen immutability, button layouts, display templates |
| `test_interaction_executor.py` | 14 | Injection, advance verification, retry, escalation, password redaction |
| `test_interaction_engine.py` | 7 | Orchestration flow, chat input, feedback routing |
| `test_output_forwarder.py` | 17 | ANSI stripping, batching, truncation, rate limiting, flush loop |
| `test_router.py` | 15 | Forward/return path + interaction engine + chat mode integration |
| `test_interaction_flow.py` | 6 | End-to-end pipeline: yes/no, confirm-enter, password, chat mode |
| `test_interaction_safety.py` | 29 | CR semantics, password redaction, echo suppression, determinism |
| `test_ml_classifier.py` | 5 | NullMLClassifier, Protocol compliance, enum values |
| `test_fuser.py` | 12 | All 6 fusion rules, NullML equivalence, determinism |
| `test_output_router.py` | 16 | Agent prose, CLI output, noise, bypass mode, determinism |
| `test_session_binding.py` | 20 | Bind/resolve/unbind, TTL, state transitions, multi-channel |
| `test_conversation_flow.py` | 8 | End-to-end conversation binding lifecycle |
| `test_ml_safety.py` | 7 | ML cannot override HIGH, disagreement flags, escalation |
| `test_plan_detector.py` | 15 | Plan header detection, headerless plans, step extraction, edge cases |
| `test_streaming.py` | 10 | Accumulation, plan detection, presentation, resolution, reset |
| `test_streaming_safety.py` | 15 | Secret redaction, plan safety, streaming state, accumulator bounds |
| `test_state_routing_safety.py` | 5 | State-driven routing invariants for all conversation states |

**Total:** 245+ tests covering the interaction pipeline, conversation subsystem, and streaming.
