# AtlasBridge QA: Top 20 Failure Scenarios

**Version:** 0.2.0
**Status:** Reference
**Last updated:** 2026-02-21

---

## Purpose

This document defines the 20 most critical failure scenarios for the AtlasBridge prompt relay system. Each scenario describes a real, reproducible failure mode in prompt detection, injection, session management, channel delivery, or process lifecycle. Every scenario includes a deterministic reproduction path via the Prompt Lab simulator, precise pass/fail criteria, and the instrumentation required to prove correctness in CI.

These scenarios are the canonical basis for AtlasBridge's CI gating matrix. A release cannot ship unless all scenarios gated to that version are green.

---

## How to Read This Document

Each scenario follows a fixed structure:

- **Title** — what the scenario is called (used as the `atlasbridge lab run` argument)
- **Risk / Impact** — what breaks in production if this scenario is not handled correctly
- **Setup** — how to reproduce the failure, using `atlasbridge lab run <scenario>` where possible
- **Expected Behavior** — the exact pass criterion AtlasBridge must satisfy
- **Test Type** — `unit`, `integration`, or `e2e`
- **Required Instrumentation** — the log fields and events that must appear in output for the test to be auto-verified
- **Test ID** — stable identifier for CI gating references

---

## Scenario Catalogue

---

### QA-001: Prompt Without Trailing Newline (Partial-Line Prompt)

**Test ID:** QA-001
**Test Type:** integration

**Risk / Impact**

Many interactive CLIs — including Claude Code in certain states — emit a prompt by writing characters directly to the PTY without a trailing newline, then block on `read()`. If the PTY supervisor's prompt detector only triggers on newline-terminated lines, it will never classify the prompt and the session will hang indefinitely. The user's phone receives nothing. The CLI appears stuck. The session times out rather than relaying the question.

**Setup**

```bash
atlasbridge lab run partial-line-prompt
```

The Prompt Lab scenario `partial-line-prompt` spawns a synthetic child process that:
1. Writes the bytes `Do you want to continue? (y/n)` to its PTY stdout without a trailing `\n` or `\r`
2. Immediately calls `read(0, buf, 1)` and blocks

The PTY supervisor must detect the prompt from incomplete output in the rolling buffer.

To reproduce manually without Prompt Lab:

```python
import pty, os, sys

master, slave = pty.openpty()
pid = os.fork()
if pid == 0:
    os.close(master)
    os.dup2(slave, sys.stdout.fileno())
    sys.stdout.write("Do you want to continue? (y/n)")
    sys.stdout.flush()
    os.read(0, 1)   # block
    os._exit(0)
```

**Expected Behavior**

1. `PromptDetector.detect()` must classify `TYPE_YES_NO` from the partial-line buffer within the `stuck_timeout_seconds` window (default 2.0 s) without waiting for a newline.
2. A single `prompt_detected` event is emitted to the audit log and the Telegram channel.
3. The Telegram message presents Yes / No / Use-default buttons.
4. After the user taps Yes, `y\r` is injected into the child's stdin and the process exits cleanly.

**Pass Criteria**

- Time from write to `prompt_detected` event: <= `stuck_timeout_seconds` + 0.5 s
- Exactly one Telegram message sent (no duplicates)
- Audit log contains event `prompt_detected` with field `confidence >= 0.60`
- Child process does not remain blocked after injection

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `prompt_detected` |
| `prompt_type` | `TYPE_YES_NO` or `TYPE_UNKNOWN` |
| `confidence` | `>= 0.60` |
| `trigger` | `regex` or `stall_watchdog` |
| `buffer_ends_with_newline` | `false` |
| `telegram_msg_id` | non-null |

---

### QA-002: ANSI Redraw / Carriage-Return Prompt

**Test ID:** QA-002
**Test Type:** integration

**Risk / Impact**

Some CLIs render dynamic status lines by emitting ANSI escape sequences and carriage returns (`\r`) to overwrite the same terminal line multiple times before finally arriving at a stable prompt state. If the detector is naive, it will fire on every intermediate redraw — potentially sending dozens of duplicate Telegram messages for a single user-facing question. This floods the notification channel and may cause multiple injections.

**Setup**

```bash
atlasbridge lab run ansi-redraw-prompt
```

The scenario replays the following byte sequence to the PTY master at 50 ms intervals, simulating a spinner that resolves to a prompt:

```
"Loading... \r"
"Loading... \r"
"Loading... \r"
"Loading. Done!\r\n"
"Proceed? (y/n) "   <- no newline; then blocks on read
```

**Expected Behavior**

1. The detector must suppress intermediate detections during the redraw phase.
2. Exactly one `prompt_detected` event is emitted, corresponding to the stable final line `Proceed? (y/n)`.
3. No Telegram message is sent until the output is stable (i.e., no new bytes arrive for at least `redraw_settle_ms`, default 150 ms).
4. ANSI sequences are stripped before pattern matching.

**Pass Criteria**

- Telegram message count: exactly 1
- `prompt_detected` event count in audit log: exactly 1
- `ansi_stripped_text` log field matches `"Proceed? (y/n)"` (or last 200 chars)
- No `duplicate_prompt_suppressed` error events

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `prompt_detected` |
| `ansi_stripped` | `true` |
| `redraw_settle_ms` | `>= 100` |
| `telegram_msg_count` | `1` |
| `suppressed_intermediate_count` | `>= 1` |

---

### QA-003: Prompt Text Overwritten Before Block

**Test ID:** QA-003
**Test Type:** integration

**Risk / Impact**

A CLI may emit a visible prompt string and then overwrite it with spaces or a blank redraw before blocking on read. This is common when a tool renders a status bar, then clears it while awaiting input. If the detector captures only the current state of the buffer it may see blank or low-signal content and either fail to detect any prompt or send a useless empty message to Telegram. The user cannot answer a blank prompt.

**Setup**

```bash
atlasbridge lab run overwrite-before-block
```

The scenario emits:

```
"Delete file? (y/n) "
"\r                  \r"   <- overwrite with spaces
```

Then blocks on `read()`. The prompt text has been erased by the time the stall watchdog fires.

**Expected Behavior**

1. AtlasBridge must retain a snapshot of the most recent non-blank buffer state in the rolling buffer.
2. If the current buffer is blank or below a signal threshold, the system falls back to the LOW-confidence `TYPE_UNKNOWN` flow: it forwards the last 200 chars of the most recent stable content to Telegram and offers SEND_ENTER, Cancel, and Show-Last-Output options.
3. The Telegram message must include the field `"[low confidence — last captured output shown]"` or equivalent disclaimer.
4. The prompt is not silently dropped.

**Pass Criteria**

- A Telegram message is sent even when the final buffer state is blank
- `prompt_type` is `TYPE_UNKNOWN` or `TYPE_FREE_TEXT`
- `confidence` is `<= 0.65`
- Audit log event `prompt_detected` contains `low_confidence: true`
- User can still respond and inject via Telegram

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `prompt_detected` |
| `confidence` | `<= 0.65` |
| `low_confidence` | `true` |
| `fallback_used` | `true` |
| `buffer_at_detection` | last stable snapshot (non-empty) |

---

### QA-004: CLI Blocks on Input With No Visible Prompt

**Test ID:** QA-004
**Test Type:** integration

**Risk / Impact**

The most invisible failure mode: the wrapped process calls `read(0, ...)` and blocks but emits zero output before doing so. No text, no prompt, no indicator. The stall watchdog fires, but there is nothing to show the user. If AtlasBridge is silent in this case, the user's session is frozen with no notification. If AtlasBridge sends a blank message it is confusing. The system must make a sensible choice under zero-information conditions.

**Setup**

```bash
atlasbridge lab run silent-block
```

The scenario spawns a child that immediately calls `read(0, 1)` without writing any output first. The PTY supervisor's stall watchdog fires after `stuck_timeout_seconds`.

**Expected Behavior**

1. After `stuck_timeout_seconds` of silence, the stall watchdog fires with confidence 0.60.
2. Because there is no buffer content to show, the Telegram message reads: `"Process is waiting for input (no prompt text detected)"`.
3. The message offers three actions as inline keyboard buttons: **Send Enter**, **Cancel session**, **Show last output** (which shows the last 200 chars of any prior output, or `"[no output]"` if the buffer is empty).
4. The prompt type is `TYPE_UNKNOWN`.
5. If the user taps **Send Enter**, `\r` is injected. If they tap **Cancel session**, the child is sent SIGTERM and the session is marked `terminated`.

**Pass Criteria**

- One Telegram message sent after `stuck_timeout_seconds` elapses
- `prompt_type = TYPE_UNKNOWN`
- `trigger = stall_watchdog`
- `confidence = 0.60`
- All three action buttons present in message keyboard

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `stall_watchdog_fired` |
| `output_bytes_in_buffer` | `0` |
| `prompt_type` | `TYPE_UNKNOWN` |
| `trigger` | `stall_watchdog` |
| `confidence` | `0.60` |
| `telegram_buttons` | `["send_enter", "cancel", "show_last_output"]` |

---

### QA-005: Nested Prompts (Sequential Questions)

**Test ID:** QA-005
**Test Type:** integration

**Risk / Impact**

Interactive CLI workflows often ask multiple questions in sequence: confirm a choice, provide a name, confirm deletion. If AtlasBridge handles these sequentially but incorrectly correlates a reply to the wrong prompt — or loses track of the second prompt while the first is being answered — it will inject the wrong text at the wrong time. In the worst case, the user's "yes" to question 1 gets injected as the answer to question 2.

**Setup**

```bash
atlasbridge lab run sequential-prompts
```

The scenario runs a script that asks:
1. `"Overwrite existing file? (y/n) "` — blocks, awaits `y\r` or `n\r`
2. Immediately after receiving input, prints: `"Enter new filename: "` — blocks again

Both prompts fire in sequence with no idle time between them.

**Expected Behavior**

1. Each prompt is detected and assigned its own `prompt_id` and `nonce`.
2. Prompts are queued internally; the second is not sent to Telegram until the first is resolved (or unless the config allows concurrent prompts, in which case they are both sent with distinct message IDs).
3. The correlation between reply and injection is correct: the reply to prompt 1 is injected at the point where prompt 1 blocked, not at the current read position.
4. The audit log records two separate `prompt_detected` and `response_injected` event pairs.
5. Session state is consistent after both are resolved.

**Pass Criteria**

- Two distinct `prompt_id` values in audit log
- Two distinct Telegram messages (or one if queued until resolved)
- Correct injection order (answer 1 precedes answer 2 in PTY stdin)
- No cross-contamination of nonces between prompts

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `prompt_detected` (twice, with distinct `prompt_id`) |
| `event` | `response_injected` (twice, with matching `prompt_id`) |
| `injection_sequence` | `[1, 2]` (ordered) |
| `cross_injection_error` | absent (must not appear) |

---

### QA-006: Multiple-Choice Prompt Parsing (A/B/C and 1/2/3 Variants)

**Test ID:** QA-006
**Test Type:** unit + integration

**Risk / Impact**

Multiple-choice prompts come in two dominant formats: numeric (`1) Option A`, `2) Option B`) and alphabetic (`a) Option A`, `b) Option B`). The `PromptDetector` must correctly classify both forms as `TYPE_MULTIPLE_CHOICE` and extract the options. If extraction fails, the Telegram message will show broken or missing buttons, and the user cannot make a valid selection. Injecting an out-of-range value will corrupt the child's input stream.

**Setup**

Unit test path:

```python
# tests/unit/test_detector.py
def test_numeric_choice():
    text = "Select an option:\n1) Deploy to staging\n2) Deploy to production\n3) Cancel\nEnter choice [1-3]: "
    result = detector.detect(text)
    assert result.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE
    assert len(result.choices) == 3

def test_alpha_choice():
    text = "Choose action:\na) Approve\nb) Reject\nc) Skip\n> "
    result = detector.detect(text)
    assert result.prompt_type == PromptType.TYPE_MULTIPLE_CHOICE
    assert result.choices[0].key == "a"
```

Integration path:

```bash
atlasbridge lab run multiple-choice-numeric
atlasbridge lab run multiple-choice-alpha
```

**Expected Behavior**

1. Both numeric and alphabetic forms are classified as `TYPE_MULTIPLE_CHOICE` with `confidence >= 0.75`.
2. Up to 9 choices are extracted and presented as inline keyboard buttons in Telegram.
3. Tapping button N causes the value `N\r` (or the alphabetic equivalent `a\r`) to be injected.
4. Out-of-range selections are rejected; the user is prompted to choose again.
5. The safe default is `1` (or `a` for alphabetic), not `n`.

**Pass Criteria**

- `choices` array is non-empty and length matches options in text
- Each button's `callback_data` encodes the correct answer value
- Injection value matches the tapped button exactly
- Safe default is the first available choice

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `prompt_type` | `TYPE_MULTIPLE_CHOICE` |
| `confidence` | `>= 0.75` |
| `choices_extracted` | `>= 2` |
| `safe_default` | `"1"` or first alphabetic key |
| `injected_value` | matches user selection |

---

### QA-007: Yes/No Prompt Variants

**Test ID:** QA-007
**Test Type:** unit

**Risk / Impact**

The most common interactive prompt in the wild has dozens of textual variants: `(y/n)`, `[Y/N]`, `[y]`, `[n]`, `yes/no`, `Press y to confirm`. If any of these are misclassified as `TYPE_FREE_TEXT` or `TYPE_UNKNOWN`, the user is presented with a text-input interface instead of simple Allow/Deny buttons, adding friction to every common prompt. If the safe default is incorrectly mapped to `y` on a destructive operation, data loss can result.

**Setup**

Unit tests covering all known variants:

```python
YES_NO_VARIANTS = [
    "Delete this file? (y/n)",
    "Continue? [Y/n]",
    "Are you sure? [y/N]",
    "Overwrite? (yes/no)",
    "Press y to continue, n to cancel",
    "Confirm [y] [n]:",
    "Proceed? y/N",
]

@pytest.mark.parametrize("text", YES_NO_VARIANTS)
def test_yes_no_classification(text):
    result = detector.detect(text)
    assert result.prompt_type == PromptType.TYPE_YES_NO
    assert result.safe_default == "n"
```

```bash
atlasbridge lab run yes-no-variants
```

**Expected Behavior**

1. All listed variants are classified as `TYPE_YES_NO` with `confidence >= 0.65`.
2. The safe default is always `n` and cannot be changed to `y` via config (the validator rejects it).
3. Telegram buttons are **Allow** (injects `y\r`) and **Deny** (injects `n\r`).
4. The mapping is: Allow → `y`, Deny → `n`, regardless of the case shown in the prompt text (`[Y/n]` does not make Y the safe default).

**Pass Criteria**

- All 7+ variants classified correctly
- Zero variants classified as `TYPE_FREE_TEXT` or `TYPE_UNKNOWN`
- `safe_default` is always `"n"` for all variants
- Config validation raises `ConfigError` if `safe_default_yes_no = "y"` is set

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `prompt_type` | `TYPE_YES_NO` for all variants |
| `safe_default` | `"n"` |
| `inject_allow` | `"y\r"` |
| `inject_deny` | `"n\r"` |

---

### QA-008: Press-Enter Prompt Classification

**Test ID:** QA-008
**Test Type:** unit + integration

**Risk / Impact**

A common CLI pattern is the "press enter to continue" gate — used by installers, pagers (`-- More --`), and confirmation flows. If this is misclassified as `TYPE_YES_NO`, the user is shown incorrect buttons (Yes/No instead of a single Enter button), and a tap on "Yes" injects `y\r` instead of `\r`, which may cause the CLI to receive an unexpected character and misbehave.

**Setup**

```python
PRESS_ENTER_VARIANTS = [
    "Press Enter to continue",
    "Press Return to start",
    "Hit enter to proceed",
    "[Press Enter]",
    "-- More --",
    "(press enter)",
]

@pytest.mark.parametrize("text", PRESS_ENTER_VARIANTS)
def test_confirm_enter_classification(text):
    result = detector.detect(text)
    assert result.prompt_type == PromptType.TYPE_CONFIRM_ENTER
    assert result.safe_default == "\n"
```

```bash
atlasbridge lab run press-enter
```

**Expected Behavior**

1. All listed variants are classified as `TYPE_CONFIRM_ENTER` with `confidence >= 0.65`.
2. The Telegram message shows a single **Press Enter** button (plus Use Default).
3. Tapping the button injects `\r` (carriage return, the correct PTY newline representation).
4. No `y` or `n` is injected under any circumstances.
5. The safe default is `\n` (injects as `\r`).

**Pass Criteria**

- All variants classified as `TYPE_CONFIRM_ENTER`
- Injected bytes are exactly `b"\r"` (not `b"\n"`, not `b"y\r"`)
- Telegram keyboard has button labelled "Press Enter" or similar, not "Yes"

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `prompt_type` | `TYPE_CONFIRM_ENTER` |
| `inject_bytes_hex` | `"0d"` (CR only) |
| `safe_default` | `"\n"` |
| `telegram_button_label` | contains `"Enter"` |

---

### QA-009: Free-Text Prompt With Length Constraints

**Test ID:** QA-009
**Test Type:** unit + integration

**Risk / Impact**

Free-text prompts (commit messages, file names, API keys) may have implicit or explicit maximum lengths. If AtlasBridge relays a reply that exceeds the length the child process expects, the excess bytes spill into the next read or corrupt the PTY stream. This is especially dangerous for password fields where the overrun could be misinterpreted as a command.

**Setup**

```python
def test_free_text_max_length_enforced():
    config = AtlasBridgeConfig(free_text_max_length=80)
    reply = "a" * 100
    result = injector.prepare_injection(reply, max_length=80)
    assert len(result.text) <= 80
    assert result.truncated is True

def test_free_text_overlong_rejected():
    reply = "x" * 300
    with pytest.raises(ReplyTooLongError):
        channel.validate_reply(reply, max_length=80)
```

```bash
atlasbridge lab run free-text-length
```

**Expected Behavior**

1. `free_text_max_length` (default: 500 chars) is applied at the channel layer before injection.
2. Replies longer than `free_text_max_length` are rejected at the Telegram handler with a user-visible error: `"Reply too long (N chars, max M). Please shorten and try again."`.
3. The reply is not injected. The prompt remains active.
4. The audit log records a `reply_rejected` event with `reason: too_long`.
5. An overlong free-text reply never reaches the PTY stdin write call.

**Pass Criteria**

- Replies > `free_text_max_length` are rejected before injection
- User receives Telegram error message
- Audit log records `reply_rejected` event
- Child process stdin is not written

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `reply_rejected` |
| `reason` | `"too_long"` |
| `reply_length` | `> max_length` |
| `injected` | `false` |
| `telegram_error_sent` | `true` |

---

### QA-010: Telegram Duplicate Callback Delivery

**Test ID:** QA-010
**Test Type:** integration

**Risk / Impact**

Telegram's `getUpdates` long-poll API guarantees at-least-once delivery, not exactly-once. The same `callback_query` update may be delivered twice if the bot acknowledges it but the network connection drops before Telegram registers the acknowledgement. If `decide_prompt()` is not idempotent, the second delivery will inject the same text twice into the child's stdin — causing a double-enter, a repeated choice selection, or data duplication in a free-text field.

**Setup**

```bash
atlasbridge lab run duplicate-callback
```

The scenario uses the Prompt Lab's Telegram stub to deliver the same `callback_query` update ID twice in sequence within 500 ms, simulating a redelivery. The bot token and nonce in both callbacks are identical.

```python
# Manual reproduction using the Telegram stub
stub.deliver_callback(update_id=12345, callback_data="ans:prompt-abc:nonce-xyz:y")
stub.deliver_callback(update_id=12345, callback_data="ans:prompt-abc:nonce-xyz:y")  # duplicate
```

**Expected Behavior**

1. The first callback updates the prompt record: `nonce_used → 1`, `status → injected`, and triggers injection.
2. The second callback finds `nonce_used = 1` in the database. `decide_prompt()` returns 0 rows affected. The callback is silently acknowledged and ignored.
3. Exactly one injection occurs in the child's PTY stdin.
4. A `duplicate_callback_ignored` event is written to the audit log for observability.

**Pass Criteria**

- PTY stdin receives exactly one write for the prompt reply
- `decide_prompt()` returns `rows_affected = 0` on the second call
- Audit log contains `duplicate_callback_ignored` event with matching `nonce`
- No error is raised; the Telegram callback is answered 200 OK

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `duplicate_callback_ignored` |
| `nonce` | matches the duplicate callback |
| `rows_affected` | `0` |
| `injection_count` | `1` (exactly once) |
| `decide_prompt_result` | `"nonce_already_used"` |

---

### QA-011: Late Reply After Prompt TTL Expiry

**Test ID:** QA-011
**Test Type:** integration

**Risk / Impact**

A user may leave their phone unattended and tap an approval long after the prompt TTL has expired and the safe default has already been injected. If the expired callback still triggers an injection, the child receives two stdin writes — the auto-injected default and the late reply — in sequence. Depending on the child's input handling, this can cause command duplication, cursor corruption, or unintended command execution.

**Setup**

```bash
atlasbridge lab run late-reply-after-ttl
```

The scenario sets `timeout_seconds = 2` for the test session, then:
1. Detects a prompt and records it with a 2-second TTL.
2. Waits 3 seconds (TTL + 1 s margin) — the timeout fires and injects the safe default.
3. Delivers a valid callback for the expired prompt to the Telegram handler.

**Expected Behavior**

1. After TTL expires: status → `expired`, safe default injected, Telegram message edited to show expiry.
2. When the late callback arrives: `decide_prompt()` finds `expires_at < now` and returns 0 rows affected.
3. No injection occurs for the late reply.
4. Telegram sends a reply to the callback: `"This prompt has expired. The safe default was used."`.
5. Audit log records `late_reply_rejected` with `expired_at` and `reply_arrived_at` fields.

**Pass Criteria**

- Late callback produces zero PTY stdin writes
- Telegram callback is acknowledged with an expiry message (not silently dropped)
- Audit log records `late_reply_rejected` event
- Child process has only one stdin write (the auto-default)

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `late_reply_rejected` |
| `prompt_status_at_reply` | `"expired"` |
| `expired_at` | ISO 8601 timestamp before `reply_arrived_at` |
| `injection_count` | `1` (auto-default only) |
| `telegram_expiry_notice_sent` | `true` |

---

### QA-012: Reply for Wrong Session or Prompt ID

**Test ID:** QA-012
**Test Type:** integration

**Risk / Impact**

AtlasBridge maintains multiple prompt records across sessions. A callback that encodes a `prompt_id` that does not exist, belongs to a different session, or was generated by a different AtlasBridge installation must be rejected without injecting anything. This prevents misdirected approvals from controlling unintended sessions, particularly when a user has multiple sessions open simultaneously.

**Setup**

```bash
atlasbridge lab run wrong-session-reply
```

The scenario:
1. Creates session A with prompt A1 (active, awaiting reply).
2. Generates a crafted callback referencing a nonexistent `prompt_id` (`"ans:deadbeef-0000:bad-nonce:y"`).
3. Delivers the crafted callback to the Telegram handler.

Also tests with a real but mismatched session:

```python
stub.deliver_callback(callback_data=f"ans:{prompt_in_session_B}:nonce:y")
# while session A is the active one in the current PTY supervisor
```

**Expected Behavior**

1. The Telegram handler looks up `prompt_id` in the database. If not found, the callback is rejected.
2. No injection occurs for any session.
3. Telegram sends the user a reply: `"Unknown prompt ID. This may be an old or invalid request."`.
4. Audit log records `invalid_callback` event with `reason: prompt_not_found` or `reason: session_mismatch`.
5. The active prompt A1 remains in `awaiting_response` status unchanged.

**Pass Criteria**

- Zero PTY stdin writes to any session
- Telegram callback receives an explanatory reply
- Active prompt A1 is unaffected (still awaiting)
- Audit log records `invalid_callback` event

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `invalid_callback` |
| `reason` | `"prompt_not_found"` or `"session_mismatch"` |
| `attempted_prompt_id` | the bogus ID from the callback |
| `active_prompt_affected` | `false` |
| `injected` | `false` |

---

### QA-013: Two Sessions Prompting Concurrently

**Test ID:** QA-013
**Test Type:** integration

**Risk / Impact**

A user may legitimately run two `atlasbridge run` invocations simultaneously — for example, one running `claude` in a frontend project and another in a backend project. Both sessions may trigger prompts at the same time. If the Telegram bot routes a reply intended for session A into session B's PTY stdin, the wrong process receives the input. This is a critical correctness failure.

**Setup**

```bash
atlasbridge lab run concurrent-sessions
```

The scenario starts two independent PTY supervisors (session A and session B), each with their own synthetic child. Both children emit a `(y/n)` prompt simultaneously. The bot receives two distinct Telegram messages with distinct `prompt_id` values.

**Expected Behavior**

1. Each session has a unique `session_id` and each prompt has a unique `prompt_id` and `nonce`.
2. Telegram sends two separate messages, each with callback buttons encoding their respective `prompt_id`.
3. Tapping the Yes button on session A's message causes `y\r` to be written to session A's PTY stdin only.
4. Session B remains blocked awaiting its own reply.
5. Tapping session B's button injects into session B only.
6. No cross-injection occurs at any point.

**Pass Criteria**

- Each PTY supervisor receives exactly one injection corresponding to its own prompt
- `session_id` in each `response_injected` audit event matches the session that owns the prompt
- No `cross_injection_error` events in audit log

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `response_injected` (twice, distinct `session_id` per event) |
| `prompt_id` | distinct for each session's event |
| `cross_injection_error` | absent |
| `session_isolation_verified` | `true` |

---

### QA-014: Text Reply Ambiguity With Multiple Active Sessions

**Test ID:** QA-014
**Test Type:** integration

**Risk / Impact**

For `TYPE_FREE_TEXT` prompts, the user replies by sending a text message (not a button tap) in reply to the Telegram bot message. If two sessions both have active `TYPE_FREE_TEXT` prompts simultaneously, and the user sends a plain text message without replying to a specific bot message, AtlasBridge cannot determine which session the reply targets. Injecting into the wrong session would corrupt a free-text input field.

**Setup**

```bash
atlasbridge lab run ambiguous-text-reply
```

The scenario:
1. Opens two sessions, each blocking on a `TYPE_FREE_TEXT` prompt.
2. Simulates the user sending the text `"my-commit-message"` to the bot without `reply_to_message` context.

**Expected Behavior**

1. AtlasBridge detects that there are two or more active `TYPE_FREE_TEXT` prompts with no reply context to disambiguate.
2. Rather than injecting, AtlasBridge sends the user a disambiguation message listing the active sessions with request to reply to the specific bot message for each.
3. Neither session receives an injection.
4. If the user then replies to a specific bot message, the injection proceeds correctly for that session only.

**Pass Criteria**

- Zero injections on ambiguous text delivery
- Disambiguation message sent to user with list of active prompts
- After targeted reply, correct session receives injection
- Audit log records `ambiguous_reply_held` event

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `ambiguous_reply_held` |
| `active_free_text_prompts` | `>= 2` |
| `disambiguation_sent` | `true` |
| `injected` | `false` (for the ambiguous delivery) |
| `injected` | `true` (after targeted reply) |

---

### QA-015: Telegram Outage During Active Prompt

**Test ID:** QA-015
**Test Type:** integration

**Risk / Impact**

Telegram's API may be temporarily unreachable due to outages or network interruption. If this happens while a prompt is awaiting a reply, the session must not crash, the prompt must not be auto-failed, and AtlasBridge must recover automatically when connectivity returns. Without retry logic and exponential backoff, an outage would require the user to restart the daemon and re-initiate the session.

**Setup**

```bash
atlasbridge lab run telegram-outage
```

The scenario:
1. Detects a prompt and begins waiting for a reply.
2. The Prompt Lab's Telegram stub returns `503 Service Unavailable` for all requests for 10 seconds.
3. After 10 seconds, the stub resumes normal operation.

The stub simulates Telegram long-poll failures and `sendMessage` failures separately.

**Expected Behavior**

1. During the outage, polling failures are logged with exponential backoff starting at 1 s, doubling up to `max_backoff_seconds` (default: 60 s).
2. The session remains in `awaiting_response` — not failed, not crashed.
3. No injection occurs during the outage.
4. When connectivity returns, polling resumes, and the user can respond normally.
5. A `telegram_outage_recovered` event is logged when the first successful poll occurs after failure.

**Pass Criteria**

- Session status never changes to `crashed` or `failed` during outage
- Backoff intervals are >= 1 s and increase geometrically
- After recovery, user reply is accepted and injected correctly
- Audit log records `telegram_polling_failed` events during outage and `telegram_outage_recovered` on recovery

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `telegram_polling_failed` (one or more) |
| `backoff_seconds` | increasing sequence |
| `event` | `telegram_outage_recovered` |
| `session_status_during_outage` | `"awaiting_response"` |
| `recovery_injection_succeeded` | `true` |

---

### QA-016: AtlasBridge Daemon Restart Mid-Prompt

**Test ID:** QA-016
**Test Type:** e2e

**Risk / Impact**

The AtlasBridge daemon may be killed and restarted by launchd, systemd, or the user while a session is mid-prompt. The PTY child is still running (it's a separate process), still blocked on `read()`. If the daemon does not reload prompt state from the SQLite store on restart, the pending prompt will be permanently orphaned — the child blocks forever and the user receives no notification.

**Setup**

```bash
atlasbridge lab run daemon-restart-mid-prompt
```

The scenario:
1. Starts a session and detects a prompt (status: `awaiting_response`, stored in DB).
2. Sends SIGTERM to the daemon process.
3. Immediately restarts the daemon.

**Expected Behavior**

1. On restart, the daemon queries the `prompts` table for records with `status = 'awaiting_response'` and `expires_at > now`.
2. For each surviving prompt: the daemon sends a new Telegram message (or edits the existing one if `telegram_msg_id` is stored) informing the user that the daemon restarted and the prompt is still pending.
3. The prompt remains actionable — the user can still reply, and the reply will be injected into the still-running child process.
4. If `expires_at < now` at restart time, the prompt is marked `expired` and the safe default is injected.

**Pass Criteria**

- Pending prompt is not lost on restart
- Telegram re-notification is sent within 5 s of daemon restart
- User reply after restart is injected correctly into the child
- Expired prompts at restart time receive safe-default injection

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `daemon_restarted` |
| `prompts_reloaded` | count of recovered prompts |
| `event` | `prompt_renotified` (for non-expired) |
| `event` | `prompt_expired_on_restart` (for expired) |
| `child_still_alive` | `true` |

---

### QA-017: CLI Child Crash While Awaiting Reply

**Test ID:** QA-017
**Test Type:** integration

**Risk / Impact**

The wrapped CLI may crash (SIGSEGV, unhandled exception, OOM) while AtlasBridge is waiting for a Telegram reply to an active prompt. The pending prompt becomes meaningless — there is no process to inject into. If AtlasBridge is not notified of the child's death, it will continue waiting indefinitely and the user's Telegram message will remain showing "awaiting response" with an active button. Tapping that button after the child has died must not crash the Telegram handler.

**Setup**

```bash
atlasbridge lab run child-crash-mid-prompt
```

The scenario detects a prompt, then sends SIGKILL to the child process, simulating a crash.

**Expected Behavior**

1. `pty_reader` detects EOF on the PTY master fd, indicating the child has died.
2. The PTY supervisor cancels all pending asyncio tasks and marks the session `crashed`.
3. All active prompts for this session are immediately marked `failed` in the database.
4. The Telegram bot edits each pending prompt message to read: `"Session ended unexpectedly. This prompt is no longer active."`.
5. If a user taps a button on the stale message after the crash, `decide_prompt()` finds `status = 'failed'` and returns 0 rows affected. A reply is sent: `"This session has ended."`.

**Pass Criteria**

- Session status transitions to `crashed`
- All prompts for that session transition to `failed`
- Telegram messages are edited to reflect the crash
- Late button taps after crash are rejected gracefully with a user message
- No exception is raised in the Telegram handler for the stale callback

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `child_process_died` |
| `session_status` | `"crashed"` |
| `prompts_marked_failed` | count |
| `telegram_crash_notice_sent` | `true` |
| `stale_callback_rejected` | `true` (if tested) |

---

### QA-018: Output Flood / High-Volume Log Stream

**Test ID:** QA-018
**Test Type:** integration

**Risk / Impact**

Some AI CLI tools produce extremely high-volume output streams — thousands of lines of log output, progress bars, or tool call results. The PTY supervisor maintains a rolling 4096-byte buffer. If the buffer implementation uses unbounded growth (or copies too frequently), a high-throughput output stream will cause memory exhaustion (OOM) or CPU spin. Furthermore, prompts embedded in a flood of output must still be detected reliably.

**Setup**

```bash
atlasbridge lab run output-flood
```

The scenario spawns a child that produces 100,000 lines of output at maximum speed, then emits a `(y/n)` prompt and blocks.

Memory and CPU profiling is performed during the flood phase:

```python
# Measured in prompt_lab/scenarios/output_flood.py
assert max_rss_delta_mb < 10   # AtlasBridge memory growth <= 10 MB
assert cpu_time_s < 5          # AtlasBridge CPU time for 100k lines <= 5 s
```

**Expected Behavior**

1. The rolling buffer never grows beyond `max_buffer_bytes` (default: 4096 bytes). Older bytes are evicted as new bytes arrive.
2. AtlasBridge memory usage (RSS) does not grow unboundedly during the flood — growth is bounded at `O(buffer_size)`, not `O(output_size)`.
3. The `(y/n)` prompt at the end of the flood is correctly detected despite being preceded by a large volume of output.
4. The prompt is relayed to Telegram and injected correctly after user reply.
5. No out-of-memory condition, no dropped prompt.

**Pass Criteria**

- Memory growth during flood <= 10 MB
- Prompt detected after flood within `stuck_timeout_seconds + 1 s`
- Buffer size never exceeds `max_buffer_bytes`
- Prompt correctly classified and relayed to Telegram

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `max_rss_delta_mb` | `< 10` |
| `buffer_evictions` | `> 0` (confirms bounded buffer) |
| `prompt_detected_after_flood` | `true` |
| `prompt_type` | `TYPE_YES_NO` |
| `oom_event` | absent |

---

### QA-019: Injection Echo Loop

**Test ID:** QA-019
**Test Type:** integration

**Risk / Impact**

PTYs echo input back to the master side by default. When AtlasBridge injects a reply (e.g., `y\r`) into the PTY slave's stdin, the PTY layer may echo those bytes back through the output stream. If the `PromptDetector` is still active on the output stream and the echo contains characters that match a prompt pattern, the detector will fire again — creating a second (spurious) prompt detection for the echoed input. This results in a second Telegram message being sent for text the user already answered.

**Setup**

```bash
atlasbridge lab run injection-echo-loop
```

The scenario:
1. Detects a `(y/n)` prompt.
2. Simulates user tapping Yes — AtlasBridge injects `y\r`.
3. The PTY echoes `y` back to the master output stream.
4. Measures whether the detector fires again on the echo.

**Expected Behavior**

1. At the moment of injection, AtlasBridge sets an internal `_injecting` flag or clears the rolling output buffer.
2. The detector is suppressed for a brief window (`post_inject_suppress_ms`, default: 500 ms) after injection completes.
3. The echoed `y` does not trigger a second `prompt_detected` event.
4. If the suppression window is implemented via buffer clearing, the cleared buffer must not prevent detection of a genuine subsequent prompt that arrives after the suppression window ends.

**Pass Criteria**

- Exactly one `prompt_detected` event per user-facing prompt
- No `prompt_detected` event fires within `post_inject_suppress_ms` after injection
- A genuine subsequent prompt (if any) is still detected after the suppression window
- Audit log contains no `echo_loop_detected` error events

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `event` | `injection_completed` |
| `post_inject_suppress_active` | `true` for `post_inject_suppress_ms` |
| `echo_suppressed` | `true` |
| `spurious_prompt_count` | `0` |
| `prompt_detected_count_per_user_question` | `1` |

---

### QA-020: Windows-Specific Newline / Encoding (ConPTY Readiness Test)

**Test ID:** QA-020
**Test Type:** e2e (Windows experimental)

**Risk / Impact**

Windows uses the ConPTY (Console Pseudo-Terminal) API instead of POSIX PTYs. Output from a ConPTY session uses CRLF (`\r\n`) line endings rather than LF (`\n`). Unicode output (emoji, box-drawing characters, multi-byte sequences) may behave differently in a ConPTY stream than in a POSIX PTY. If AtlasBridge's pattern matching is not CRLF-aware, prompts on Windows will go undetected. If ANSI stripping does not account for ConPTY-specific sequences, pattern matching will produce false negatives on Windows.

**Setup**

```bash
atlasbridge lab run conpty-readiness --platform windows
```

The test is only executed on Windows CI runners (or via WSL2 with ConPTY emulation). The scenario:
1. Spawns a synthetic child via the ConPTY API.
2. Emits the following over ConPTY: `"Continue? (y/n)\r\n"` followed by CRLF-terminated multi-line output containing Unicode characters (e.g., `"\u2714 Done\r\n"`).
3. Verifies that pattern matching correctly handles CRLF line endings.

```python
CRLF_VARIANTS = [
    "Delete? (y/n)\r\n",
    "Proceed? [Y/N]\r\n",
    "Press Enter to continue\r\n",
    "1) Option A\r\n2) Option B\r\n",
]

@pytest.mark.parametrize("text", CRLF_VARIANTS)
def test_crlf_prompt_detection(text):
    result = detector.detect(text)
    assert result.prompt_type is not None
    assert result.confidence >= 0.65
```

**Expected Behavior**

1. `PromptDetector` normalizes CRLF to LF before pattern matching (or patterns accept both).
2. All prompt types (YES_NO, CONFIRM_ENTER, MULTIPLE_CHOICE, FREE_TEXT) are correctly classified on CRLF input.
3. Unicode output in the buffer does not cause encoding errors — the buffer handles arbitrary bytes and decodes with `errors='replace'`.
4. Injection of `y\r\n` (CRLF) is used on Windows instead of `y\r` (CR only) — configurable via `windows_crlf_inject` setting.
5. The `atlasbridge version --experimental` flag reports `windows_conpty: true` when the ConPTY adapter is active.

**Pass Criteria**

- All 4 CRLF prompt variants classified correctly
- No `UnicodeDecodeError` on Unicode output
- `inject_bytes` is CRLF-terminated on Windows
- `atlasbridge version --experimental` includes `windows_conpty` capability flag

**Required Instrumentation**

| Field | Required Value |
|-------|---------------|
| `platform` | `"windows"` |
| `conpty_active` | `true` |
| `crlf_normalized` | `true` |
| `unicode_decode_errors` | `0` |
| `inject_line_ending` | `"\r\n"` |
| `prompt_type` | correctly classified for all CRLF variants |

---

## CI Gating Matrix

The following matrix defines which scenarios must pass for each release to ship. A release is blocked from tagging if any mandatory scenario is failing on its required platform.

| Test ID | Scenario | v0.2.0 (macOS) | v0.3.0 (Linux) | v0.4.0 (Slack) | v0.5.0 (Windows) |
|---------|----------|:--------------:|:--------------:|:--------------:|:----------------:|
| QA-001 | Partial-line prompt | Mandatory | Mandatory | — | — |
| QA-002 | ANSI redraw prompt | Mandatory | Mandatory | — | — |
| QA-003 | Overwrite before block | Mandatory | Mandatory | — | — |
| QA-004 | Silent block | Mandatory | Mandatory | — | — |
| QA-005 | Sequential prompts | Mandatory | Mandatory | — | — |
| QA-006 | Multiple-choice parsing | Mandatory | Mandatory | — | — |
| QA-007 | Yes/No variants | Mandatory | Mandatory | — | — |
| QA-008 | Press-Enter prompt | Mandatory | Mandatory | — | — |
| QA-009 | Free-text length | Mandatory | Mandatory | — | — |
| QA-010 | Telegram duplicate callback | Mandatory | Mandatory | Slack variant | — |
| QA-011 | Late reply after TTL | Mandatory | Mandatory | Slack variant | — |
| QA-012 | Wrong session reply | Mandatory | Mandatory | Slack variant | — |
| QA-013 | Concurrent sessions | Mandatory | Mandatory | Slack variant | — |
| QA-014 | Ambiguous text reply | Mandatory | Mandatory | Slack variant | — |
| QA-015 | Telegram outage | Mandatory | Mandatory | Slack variant | — |
| QA-016 | Daemon restart mid-prompt | Mandatory | Mandatory | — | — |
| QA-017 | Child crash mid-prompt | Mandatory | Mandatory | — | — |
| QA-018 | Output flood | Mandatory | Mandatory | — | — |
| QA-019 | Injection echo loop | Mandatory | Mandatory | — | — |
| QA-020 | Windows ConPTY | — | — | — | Mandatory |

### Release Definitions

**v0.2.0 (macOS MVP)**
All of QA-001 through QA-019 must pass on macOS (darwin, arm64 and x86_64). This is the gate for the initial public release. 85% unit test coverage is required in addition to these scenario tests. All CI lint and type checks must be green.

**v0.3.0 (Linux)**
All of QA-001 through QA-019 must pass on Linux (ubuntu-latest) in addition to macOS. The CI matrix must include `python-version: ["3.11", "3.12"]` on both platforms. The Linux PTY adapter (`LinuxTTY`) must be proven equivalent to the macOS `ptyprocess` adapter for all 19 scenarios.

**v0.4.0 (Slack channel)**
QA-010, QA-011, QA-012, QA-013, and QA-014 must pass a Slack-variant version where the "Telegram stub" is replaced by a Slack API stub. The Slack channel implementation must exhibit identical idempotency, expiry enforcement, session isolation, and disambiguation behaviour. All v0.3.0 gates must remain green.

**v0.5.0 (Windows experimental)**
QA-020 must pass on a Windows CI runner. This gate is labelled "experimental" — Windows ConPTY support ships behind the `--experimental` flag. All prior QA gates remain applicable on macOS and Linux.

---

## Prompt Lab Usage

### Overview

The Prompt Lab is a deterministic simulator that reproduces failure scenarios without requiring a live AI CLI, a real Telegram account, or network access. It ships as `tests/prompt_lab/` and is invocable via the `atlasbridge lab` CLI command.

### Quick Start

```bash
# Install AtlasBridge with dev dependencies
uv pip install -e ".[dev]"

# List all available scenarios
atlasbridge lab list

# Run a single scenario
atlasbridge lab run partial-line-prompt

# Run all scenarios and report
atlasbridge lab run --all

# Run scenarios matching a filter
atlasbridge lab run --filter "QA-01*"

# Run with verbose output
atlasbridge lab run --all --verbose

# Run with JSON output for CI parsing
atlasbridge lab run --all --json > qa-results.json
```

### Scenario Architecture

Each scenario is a Python module in `tests/prompt_lab/scenarios/`. A scenario implements the `LabScenario` interface:

```python
class PartialLinePromptScenario(LabScenario):
    scenario_id = "QA-001"
    name = "partial-line-prompt"

    def setup(self) -> ScenarioConfig:
        return ScenarioConfig(
            child_script=self.emit_partial_line_then_block,
            telegram_stub=TelegramStub(auto_reply="y"),
            timeout_seconds=5,
        )

    async def emit_partial_line_then_block(self, pty_slave):
        pty_slave.write(b"Do you want to continue? (y/n)")
        pty_slave.flush()
        await asyncio.sleep(60)   # block without newline
```

### Telegram Stub

The Prompt Lab includes a `TelegramStub` that intercepts all `sendMessage` and `getUpdates` calls made by the AtlasBridge bot. The stub records all outbound messages and allows scenarios to inject replies:

```python
stub = TelegramStub()
stub.auto_reply("y")          # automatically tap Yes on the next prompt
stub.deliver_callback(...)    # inject a specific callback_query
stub.get_messages()           # inspect all messages sent to Telegram
stub.simulate_outage(seconds=10)  # simulate Telegram unavailability
```

### Assertions

Each scenario defines expected assertions that the `atlasbridge lab run` runner verifies automatically:

```python
def assert_results(self, results: ScenarioResults) -> None:
    assert results.telegram_message_count == 1
    assert results.injection_count == 1
    assert results.audit_events_contain("prompt_detected")
    assert results.prompt_type == "TYPE_YES_NO"
```

### CI Integration

In CI, `atlasbridge lab run --all --json` produces a machine-readable report used to gate pull requests:

```yaml
# .github/workflows/qa.yml
- name: Run QA scenarios
  run: atlasbridge lab run --all --json --output qa-results.json

- name: Check mandatory scenarios
  run: python scripts/check_qa_gate.py --results qa-results.json --release v0.2.0
```

The gate script parses the JSON results and fails the CI job if any mandatory scenario for the target release is not in `"status": "pass"`.

### Writing New Scenarios

New scenarios are added by creating a file in `tests/prompt_lab/scenarios/` following the naming convention `QA-NNN-<slug>.py`. The file must define a class inheriting from `LabScenario` with `scenario_id`, `name`, `setup()`, and `assert_results()` methods. The scenario is automatically discovered by `atlasbridge lab list`.

### Debugging Failures

When a scenario fails, use `--verbose` to see the full PTY output, all audit log events, and the Telegram stub's message log:

```bash
atlasbridge lab run partial-line-prompt --verbose --debug

# Output:
# [PTY OUTPUT] "Do you want to continue? (y/n)"
# [DETECTOR] buffer=b"Do you want to continue? (y/n)", newline=False
# [STALL WATCHDOG] fired after 2.001s
# [DETECTOR] result=TYPE_YES_NO confidence=0.75 trigger=stall_watchdog
# [TELEGRAM STUB] sendMessage -> msg_id=1
# [TELEGRAM STUB] auto_reply injecting callback ans:prompt-abc:nonce-xyz:y
# [INJECTOR] writing b"y\r" to PTY fd 5
# [AUDIT] prompt_detected | TYPE_YES_NO | confidence=0.75
# [AUDIT] response_injected | value=y | prompt_id=prompt-abc
# PASS
```
