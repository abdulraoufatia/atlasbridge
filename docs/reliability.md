# AtlasBridge Reliability and PTY Strategy

**Version:** 0.2.0
**Status:** Design
**Last updated:** 2026-02-21

---

## 1. Reliability Philosophy

Phase 1 lives or dies by reliability of interactive interception: no deadlocks, no flaky prompt detection, no misrouted replies, no duplicate injections.

AtlasBridge occupies an unusual position in the software stack. It sits between a user and an AI agent's stdin/stdout, acting as a transparent relay that must make real-time decisions about whether the agent is blocked waiting for input. There is no retry mechanism once a prompt is missed. There is no "undo" once a reply is injected at the wrong moment. Every failure mode has a direct, visible impact on the user's session: either the AI agent hangs indefinitely, or AtlasBridge fires a false alarm and injects garbage into the process at the wrong time.

This document defines how AtlasBridge achieves the reliability targets required for Phase 1 to be useful in daily practice.

### Core reliability invariants

1. **No deadlock**: Every asyncio `await` has an explicit timeout. No task can block the event loop indefinitely.
2. **No flaky detection**: Prompt detection uses a three-signal strategy with a defined fallback path for ambiguity. A failed detection produces a recoverable ambiguity notice, not a silent hang.
3. **No misrouted replies**: Every reply is bound to a specific `prompt_id` and `nonce`. Stale, duplicate, or replayed replies are rejected at the SQL layer before any injection occurs.
4. **No duplicate injections**: The injection gate is an `asyncio.Lock`. Only one injection can be in flight per session at a time.
5. **Transparent passthrough**: Output bytes not involved in a prompt event are forwarded to the host terminal byte-for-byte and within 50ms of receipt.

### Failure modes and their handling

| Failure Mode | Detection | Response |
|---|---|---|
| Process exits during prompt wait | pty_reader EOF | Close session, expire pending prompt |
| Telegram unreachable | httpx timeout (10s) | Retry with exponential backoff; surface via `atlasbridge status` |
| No output for >stuck_timeout_seconds | stall_watchdog fires | Trigger LOW-confidence detection; start ambiguity protocol |
| Injected reply echoed back to detector | Echo suppression window (500ms) | Suppress detector re-triggering |
| Multiple concurrent prompt detections | Injection gate (asyncio.Lock) | Queue; process one at a time |
| PTY master fd goes away | pty_reader exception handler | Graceful session teardown |

---

## 2. PTY Supervisor Architecture (macOS/Linux)

### Overview

The PTY Supervisor is the core of AtlasBridge. It launches the target CLI tool inside a pseudoterminal, giving the tool a full TTY environment including ANSI escape sequences, terminal width/height, and interactive line-editing. This is what allows `atlasbridge run claude` to behave identically to running `claude` directly, from the tool's point of view.

`ptyprocess` is used to spawn the child process. It wraps `fork()`/`exec()` and connects the child to a PTY slave fd, while AtlasBridge holds the PTY master fd. All of the child's stdout and stderr go through the master fd. AtlasBridge writes to the master fd to deliver stdin to the child.

### The 4-task asyncio event loop

`atlasbridge run <tool>` creates a single asyncio event loop. The event loop runs four concurrent tasks for the lifetime of the session. Tasks communicate through shared state on the `PTYSupervisor` object and through an `asyncio.Queue`.

```
asyncio event loop
│
├── pty_reader          reads from PTY master fd; feeds detector; writes to host terminal
├── stdin_relay         reads host stdin; forwards to PTY master when not suppressed
├── stall_watchdog      monitors last-output timestamp; fires blocking heuristic
└── response_consumer   dequeues (prompt_id, reply_value); injects into PTY stdin
```

#### Task 1: pty_reader

The reader polls the PTY master fd using `asyncio.get_event_loop().run_in_executor` wrapping `select.select` with a 50ms timeout. On each available chunk:

1. Writes the raw bytes to the host terminal's stdout (transparent passthrough).
2. Appends the chunk to the rolling output buffer.
3. Updates `last_output_at` timestamp (used by stall_watchdog).
4. If the echo suppression window has not expired, skips detector invocation and returns.
5. Calls `PromptDetector.feed(buffer)` and checks the result.
6. If a `PromptEvent` is returned with sufficient confidence, enqueues it for the Telegram channel.

The reader never blocks for more than 50ms. If the PTY fd is closed (child exited), the reader performs a clean shutdown and signals the other tasks to stop.

#### Task 2: stdin_relay

The relay reads from the host's `sys.stdin` using `asyncio.StreamReader`. On each line (or raw character in raw mode):

1. Checks the `_stdin_suppressed` flag on the supervisor.
2. If suppressed, discards the input (or buffers it for delivery after suppression lifts).
3. If not suppressed, writes the bytes directly to the PTY master fd.

The relay is suppressed during injection to prevent the host user from accidentally interfering with a reply that is mid-inject.

#### Task 3: stall_watchdog

The watchdog runs in a loop, sleeping for `stuck_poll_interval_seconds` (default: 0.5s) between checks. On each wake:

1. Computes `idle_duration = now - last_output_at`.
2. If `idle_duration > stuck_timeout_seconds` (default: 2.0s) AND no HIGH-confidence detection is pending AND the child process is still running:
   - Fires the blocking heuristic with confidence 0.60.
   - Resets the watchdog timer to prevent repeat firing on the same stall.

The watchdog also cancels any task that has been `await`-ing for longer than `task_timeout_seconds` (default: 30s). This is the primary deadlock prevention mechanism.

#### Task 4: response_consumer

The consumer blocks on `asyncio.Queue.get()` with a timeout of 1.0s (to allow cancellation checks). When a `(prompt_id, normalized_value)` tuple arrives:

1. Acquires the injection gate `asyncio.Lock`. If another injection is in progress, this will block until it completes (but the lock is always released; see deadlock prevention).
2. Validates the `prompt_id` against the database. Rejects stale or already-responded prompts.
3. Sets `_stdin_suppressed = True` on the supervisor.
4. Writes the reply bytes to the PTY master fd.
5. Waits `inject_settle_ms` (default: 100ms) for the echo to appear in the pty_reader output.
6. Sets the echo suppression window start time (`_echo_suppression_until = now + 500ms`).
7. Sets `_stdin_suppressed = False`.
8. Releases the injection gate.
9. Writes the result to the database and audit log.

### Output buffer

The output buffer is a circular byte array with a maximum capacity of 64KB. It is ANSI-aware: when the buffer is full, it discards from the oldest ANSI-complete line boundary rather than from the middle of an escape sequence. This prevents the detector from seeing partial ANSI sequences that could confuse regex matching.

Buffer internals:
- `bytearray` backing store, 65536 bytes
- Write pointer wraps at capacity
- ANSI line assembly: the buffer maintains a "current line" that accumulates bytes until `\r`, `\n`, or a full ANSI cursor-movement sequence, then appends the assembled line to a `deque[str]` of recent lines (max 200 lines)
- The detector operates on the assembled line deque, not raw bytes, to avoid false positives from escape codes

### Injection gate

The injection gate is a per-session `asyncio.Lock`. It serializes all injections:

```python
async with self._injection_gate:
    # Write reply bytes to PTY master fd
    # Set echo suppression window
```

The lock is always released: the `async with` block guarantees release even if an exception occurs inside. If the lock cannot be acquired within `injection_timeout_seconds` (default: 5.0s), the injection is aborted and a warning is emitted. This prevents the response consumer from being stuck behind a deadlocked injection.

### Echo suppression window

After injecting a reply, the child process echoes the injected bytes back through the PTY master fd. Without suppression, the pty_reader would see this echo as new output and potentially re-trigger the detector on the same prompt text.

The echo suppression window works as follows:
1. At injection time, record `_echo_suppression_until = time.monotonic() + 0.500`.
2. In pty_reader, before calling the detector, check `time.monotonic() < _echo_suppression_until`.
3. If suppressed, forward bytes to the terminal but skip the detector.
4. After the window expires, resume normal detection.

The 500ms window is empirically derived. Most terminals echo injected bytes within 50ms; the 500ms window provides a 10x margin against slow pty implementations.

### Deadlock prevention

All potential blocking points have explicit timeouts:

| Operation | Timeout | On Timeout |
|---|---|---|
| `asyncio.Queue.get()` | 1.0s | Check cancellation, retry |
| `asyncio.Lock.acquire()` | 5.0s | Abort injection, log warning |
| Telegram HTTP request | 10.0s | Retry with backoff |
| `select.select` on PTY fd | 0.05s | Poll again |
| Child process alive check | 0.1s | Treat as exited |

The stall_watchdog also monitors the other tasks. If any task has been blocked for more than `task_timeout_seconds`, the watchdog logs an error and cancels the task. The task supervisor then restarts the cancelled task after a 1.0s delay (up to `max_task_restarts` times, default: 3). If a task fails `max_task_restarts` times, the session is terminated with a clear error message.

---

## 3. ConPTY (Windows)

### Status: Experimental — gated on v0.5.0

Windows does not have POSIX PTYs. The Windows equivalent is ConPTY (Console Pseudoconsole), available in Windows 10 build 1903 and later. ConPTY provides similar functionality: a pseudoterminal interface for child processes that preserves VT/ANSI sequences.

### Architecture differences from POSIX PTY

| Aspect | macOS/Linux | Windows (ConPTY) |
|---|---|---|
| Library | `ptyprocess` | `winpty` or direct Win32 API via `ctypes` |
| I/O primitives | POSIX fd, `select.select` | Windows HANDLE, `ReadFile`/`WriteFile` |
| Signal delivery | `os.kill(pid, SIGWINCH)` for resize | `ResizePseudoConsole` API call |
| EOF detection | `EIO` on read | HRESULT error or zero-byte read |
| Echo behavior | Standard TTY echo | ConPTY virtual terminal |
| ANSI support | Full | VT processing mode required |

### Implementation plan for v0.5.0

1. Introduce an `os_backend` abstraction layer: `PosixPTYBackend` (current) and `ConPTYBackend` (new).
2. `ConPTYBackend` wraps the Win32 `CreatePseudoConsole` / `CreateProcess` sequence.
3. Asyncio on Windows uses the `ProactorEventLoop` instead of `SelectorEventLoop`; I/O wrappers must use `loop.run_in_executor` for all synchronous Win32 calls.
4. The stall_watchdog, response_consumer, and injection gate are OS-agnostic and require no changes.
5. Echo suppression window behavior is identical; the 500ms default may need tuning for ConPTY.

### Gating criteria for v0.5.0

Windows support will not ship until QA scenario QA-020 (`ConPTYBaselineScenario`) passes reliably in CI on Windows Server 2022 and Windows 11. All existing QA-001 through QA-019 scenarios must also pass on Windows via the ConPTY backend before the release is tagged.

ConPTY support is an opt-in flag until it exits experimental status:

```bash
atlasbridge run claude --backend conpty   # explicit opt-in (v0.5.0)
```

---

## 4. Tri-Signal Detector Strategy

The prompt detector uses three independent signals. Each signal has an associated confidence level. The combination logic determines how to route the detection result.

### Signal 1 — Pattern Match

Pattern matching operates on the assembled line deque from the output buffer. For each prompt type, AtlasBridge maintains a list of compiled regex patterns:

| Prompt Type | Example Patterns | Confidence |
|---|---|---|
| `YES_NO` | `\(y/n\)`, `\[Y/N\]`, `\byes or no\b`, `Press y to` | HIGH (0.90) |
| `CONFIRM_ENTER` | `Press Enter to continue`, `\[Press Enter\]`, `Hit ENTER` | HIGH (0.90) |
| `MULTIPLE_CHOICE` | `^\s*\d+[.)]\s+\w`, `Enter choice \[1-\d\]`, `Select \[\d\]` | MED (0.75) |
| `FREE_TEXT` | `Enter your .+:`, `Password:`, `API key:`, `Username:` | MED (0.70) |

Confidence is HIGH when the pattern is highly specific (exact string like `(y/n)`) and MED when the pattern is structural (numbered list heuristic). Multiple pattern matches on the same buffer window increase the effective confidence by 0.05 per additional match, up to a cap of 0.95.

### Signal 2 — TTY Blocked-on-Read

The OS-level blocked-on-read signal uses the stall_watchdog mechanism: if the child process produces no output for `stuck_timeout_seconds` (default: 2.0s) and the process is still running (as confirmed by `os.kill(pid, 0)` returning without error), the watchdog concludes the process is blocked waiting for stdin.

This signal has confidence MED (0.60) because many CLIs produce no output for extended periods while computing without waiting for input. The signal is only useful in combination with other signals or with the ambiguity protocol.

### Signal 3 — Time Fallback

The time fallback fires when Signal 2 fires AND there has been no pattern match (Signal 1 has not fired). It assigns confidence LOW (0.45). It is the last resort when neither pattern matching nor explicit OS signals provide a conclusive determination.

### Combination logic

```
if any signal has confidence >= HIGH_THRESHOLD (0.85):
    → route immediately to Telegram

elif two signals each have confidence >= MED_THRESHOLD (0.60):
    → route immediately to Telegram

elif one signal has confidence >= MED_THRESHOLD but not two:
    → if buffer ends with colon or question mark:
        → route as FREE_TEXT with MED confidence
    → else:
        → start ambiguity protocol

elif only LOW signal:
    → start ambiguity protocol
```

### Ambiguity protocol

When detection is ambiguous, AtlasBridge cannot determine with confidence whether the process is waiting for input. Rather than silently hanging or injecting blindly, AtlasBridge sends an explicit notice to Telegram:

```
AtlasBridge detected a possible input request.

Last output (last 200 chars):
  > Do you want to continue with the migration?

What should I do?
  [SEND ENTER]   [SHOW LAST OUTPUT]   [CANCEL]
```

- **SEND ENTER**: Inject `\n` into stdin. Appropriate for most "press enter to continue" scenarios.
- **SHOW LAST OUTPUT**: Return the last 2000 characters of the output buffer as a Telegram message so the user can assess the situation.
- **CANCEL**: Do nothing. The process remains blocked. The user can return to their terminal and handle it directly.

### Echo suppression after injection

After any injection (whether from a confident detection or from the ambiguity protocol), the echo suppression window activates. The 500ms window prevents the echo of the injected bytes from re-triggering the detector on the same prompt text. This is especially important for `CONFIRM_ENTER` prompts where the injected `\n` may cause the process to reprint the same prompt before proceeding.

---

## 5. Prompt Lab

The Prompt Lab is a mandatory test harness for prompt detection scenarios. It is the primary mechanism for verifying that the tri-signal detector works correctly across a wide range of real-world and adversarial PTY behaviors.

### CLI interface

```bash
atlasbridge lab run <scenario>     # run a single scenario by QA ID or name
atlasbridge lab run --all          # run all registered scenarios
atlasbridge lab list               # list all registered scenarios with descriptions
```

### pytest integration

```bash
pytest tests/prompt_lab/ -v         # run all scenarios via pytest
pytest tests/prompt_lab/ -k QA-001  # run a single scenario by ID
```

### Scenario structure

Each scenario is a Python class that extends `BasePromptLabScenario`:

```python
class BasePromptLabScenario:
    qa_id: str           # e.g. "QA-001"
    name: str            # e.g. "PartialLinePromptScenario"
    description: str
    platform: list[str]  # ["macos", "linux", "windows"]

    async def setup(self) -> None:
        """Prepare PTY master/slave pair and any fixtures."""

    async def run(self) -> None:
        """Write bytes to PTY master to simulate CLI output."""

    async def assert_behavior(self, result: DetectorResult) -> None:
        """Assert that the detector produced the expected output."""
```

The simulator writes to a PTY master fd and reads from the slave. The `PromptDetector` is instantiated against the slave's output. Deterministic timing is enforced using `asyncio.sleep` with fixed delays, not wall-clock waits, so scenarios run identically across fast and slow CI machines.

### Registered scenarios

| QA ID | Scenario Class | Description |
|---|---|---|
| QA-001 | `PartialLinePromptScenario` | Prompt arrives as two separate chunks; detector must not fire on first chunk alone |
| QA-002 | `ANSIRedrawScenario` | Prompt is preceded by a full-screen ANSI redraw; ANSI must be stripped before matching |
| QA-003 | `OverwrittenPromptScenario` | Prompt text is overwritten via carriage return before the final prompt appears |
| QA-004 | `SilentBlockScenario` | Process writes nothing; only the stall_watchdog can detect the block |
| QA-005 | `NestedPromptsScenario` | Two prompts arrive in rapid succession before the first is answered |
| QA-006 | `MultipleChoiceScenario` | Numbered list `1) ... 2) ... 3) ...` with `Enter choice [1-3]:` |
| QA-007 | `YesNoVariantsScenario` | Multiple phrasings: `(y/n)`, `[Y/n]`, `yes/no`, `y or n` |
| QA-008 | `PressEnterScenario` | Exact phrase `Press Enter to continue` and variants |
| QA-009 | `FreeTextConstraintScenario` | Free text prompt with character limit hint: `Enter name (max 20 chars):` |
| QA-018 | `OutputFloodScenario` | High-volume output (>1MB/s) followed by a prompt; detector must not degrade |
| QA-019 | `EchoLoopScenario` | Injected reply is echoed back; detector must not re-fire on the echo |

Additional scenarios (QA-010 through QA-017) cover channel-specific behaviors (Slack formatting, multi-user approval, etc.) and are defined in the channel integration test suite, not the Prompt Lab.

### `atlasbridge lab list` output

```
AtlasBridge Prompt Lab — Registered Scenarios

QA ID    Name                         Platform           Status
QA-001   PartialLinePromptScenario    macos, linux       registered
QA-002   ANSIRedrawScenario           macos, linux       registered
QA-003   OverwrittenPromptScenario    macos, linux       registered
QA-004   SilentBlockScenario          macos, linux       registered
QA-005   NestedPromptsScenario        macos, linux       registered
QA-006   MultipleChoiceScenario       macos, linux       registered
QA-007   YesNoVariantsScenario        macos, linux       registered
QA-008   PressEnterScenario           macos, linux       registered
QA-009   FreeTextConstraintScenario   macos, linux       registered
QA-018   OutputFloodScenario          macos, linux       registered
QA-019   EchoLoopScenario             macos, linux       registered

11 scenarios registered. Run with: atlasbridge lab run --all
```

### Usage in CI

The Prompt Lab runs as part of the integration test suite in GitHub Actions. It is a blocking gate: if any scenario fails, the CI pipeline fails and the PR cannot be merged.

```yaml
# .github/workflows/ci.yml
- name: Prompt Lab
  run: pytest tests/prompt_lab/ -v --tb=short
```

---

## 6. CI Gating Matrix

The following matrix shows which Prompt Lab scenarios gate each release milestone. A checkmark means the scenario must pass in CI on that platform before the release is tagged.

| Scenario | v0.2.0 macOS | v0.3.0 Linux | v0.4.0 Slack | v0.5.0 Windows |
|---|---|---|---|---|
| QA-001 PartialLinePrompt | Yes | Yes | - | Yes |
| QA-002 ANSIRedraw | Yes | Yes | - | Yes |
| QA-003 OverwrittenPrompt | Yes | Yes | - | Yes |
| QA-004 SilentBlock | Yes | Yes | - | Yes |
| QA-005 NestedPrompts | Yes | Yes | - | Yes |
| QA-006 MultipleChoice | Yes | Yes | - | Yes |
| QA-007 YesNoVariants | Yes | Yes | - | Yes |
| QA-008 PressEnter | Yes | Yes | - | Yes |
| QA-009 FreeTextConstraint | Yes | Yes | - | Yes |
| QA-010 SlackMessageFormat | - | - | Yes | - |
| QA-013 SlackThreadReply | - | - | Yes | - |
| QA-014 SlackMultiUser | - | - | Yes | - |
| QA-015 SlackRateLimit | - | - | Yes | - |
| QA-018 OutputFlood | Yes | Yes | - | Yes |
| QA-019 EchoLoop | Yes | Yes | - | Yes |
| QA-020 ConPTYBaseline | - | - | - | Yes |

Notes:
- v0.2.0: All QA-001 through QA-019 (excluding QA-010/013/014/015) must pass on macOS in CI before the tag is created.
- v0.3.0: All QA-001 through QA-019 (excluding QA-010/013/014/015) must pass on Linux (ubuntu-latest) in CI.
- v0.4.0: QA-010, QA-013, QA-014, QA-015 must pass with a live Slack test workspace. The Slack bot token is stored as a CI secret.
- v0.5.0: QA-020 must pass on Windows Server 2022 via the ConPTY backend. All other scenarios must also pass on Windows.

---

## 7. Regression Protocol

When a bug is found in prompt detection or injection, the following protocol is mandatory before the bug is closed:

### Step 1: Reproduce as a Prompt Lab scenario

Before writing any fix, write a failing Prompt Lab scenario that reproduces the exact bug. The scenario class must:
- Have a new QA ID (assigned sequentially)
- Have a `description` that includes the bug report reference (e.g., `"Regression for #42: detector fires on ANSI progress bar"`)
- Fail with the current code

Commit the failing test first:

```bash
git commit -m "test(prompt_lab): add QA-021 regression for #42"
```

### Step 2: Fix the bug

Make the minimum code change required to make the new scenario pass. Do not refactor unrelated code in the same commit.

```bash
git commit -m "fix(detector): ignore ANSI SGR sequences in pattern matching (#42)"
```

### Step 3: Verify no regressions

Run the full Prompt Lab:

```bash
pytest tests/prompt_lab/ -v
```

All previously passing scenarios must still pass.

### Step 4: Update the CI gating matrix

If the new scenario should gate a future release, add it to the CI gating matrix in this document and to the CI configuration.

### Step 5: Add to the release notes

The bug fix and the new QA scenario are both called out in `CHANGELOG.md` under the next release.

---

## 8. Performance Targets

The following performance targets are required for Phase 1. They are measured in the CI Prompt Lab with the `OutputFloodScenario` (QA-018) and by the performance benchmark suite in `tests/benchmarks/`.

| Metric | Target | How Measured |
|---|---|---|
| Prompt detection latency | < 200ms from block to PromptEvent | `QA-004 SilentBlockScenario`: time from last byte written to first `PromptEvent` |
| Reply injection latency | < 100ms from reply received to stdin inject | `response_consumer`: time from `asyncio.Queue.get()` to PTY master write |
| Memory (RSS) | < 50MB per session | `psutil.Process().memory_info().rss` sampled every 5s during `QA-018` |
| Output throughput | > 1MB/s without detector degradation | `QA-018 OutputFloodScenario`: write 5MB at 2MB/s; assert detection still fires correctly |

### Throughput target rationale

1MB/s is the minimum required to handle `claude --verbose` or similar tools that produce large amounts of streamed output. At this rate, the 64KB output buffer turns over approximately every 64ms. The ANSI-aware line assembly must keep up with this rate without introducing latency into the passthrough path.

If the output flood benchmark degrades detection latency beyond 200ms, the most likely cause is the ANSI line assembly becoming a bottleneck. The fix is to move line assembly to a separate task or to optimize the regex compilation (use `re.compile` with `re.MULTILINE` on pre-stripped text).

### Memory target rationale

50MB RSS per session is achievable with the 64KB circular buffer and a 200-line assembled line deque. The primary memory consumers per session are:
- SQLite WAL file: ~1MB typical
- The asyncio event loop and task stack frames: ~2MB
- `httpx` async client and connection pool: ~5MB
- Output buffer and line deque: ~2MB

The remaining headroom is for Python interpreter overhead and imported modules. Sessions should never approach 50MB under normal use. If they do, the most likely cause is an unbounded accumulation of `PromptRecord` objects in memory; the fix is to ensure the store layer evicts records older than `session_max_age_hours` from the in-memory cache.
