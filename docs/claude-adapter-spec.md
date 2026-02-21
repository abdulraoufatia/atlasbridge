# Claude Adapter Specification

**Version:** 0.2.0
**Status:** Implemented
**Last updated:** 2026-02-20

This document specifies how AtlasBridge detects, forwards, and responds to interactive prompts from Claude Code (and compatible AI CLIs).

---

## 1. Overview

Claude Code (and most interactive CLI tools) occasionally pauses execution and waits for human input. AtlasBridge wraps Claude in a PTY, monitors its output, and when it detects a waiting prompt, forwards it to the user's phone. The user replies. AtlasBridge injects the reply into Claude's stdin. Claude resumes.

The adapter does **not** classify operations as risky or dangerous. It only asks: *"Is the process waiting for input right now, and if so, what kind?"*

---

## 2. Launch model

```
atlasbridge run claude [args...]
```

Spawns `claude` inside a `ptyprocess.PtyProcess` with:
- Terminal dimensions matching the current host terminal (`os.get_terminal_size()`)
- Host terminal set to raw mode (`tty.setraw`) so all control sequences (arrows, Ctrl-C, etc.) pass through correctly
- Full colour, readline, and cursor-control fidelity preserved

On exit, the host terminal is restored (`termios.tcsetattr`).

---

## 3. Prompt detection

### 3.1 Three-layer detection

**Layer 1 — Structured events (confidence 1.0)**

If a tool emits structured JSON events indicating it is awaiting input, `PromptDetector.detect_structured()` can be called directly with the type and excerpt. This is an extension point; no current tool emits these.

**Layer 2 — Regex pattern matching (confidence 0.65–0.95)**

`PromptDetector.detect(text)` runs a rolling 4096-byte output buffer through pattern sets for each prompt type. Confidence is `base + 0.05 * (extra_matches)`, capped at 0.99.

Default threshold: 0.65 (configurable via `detection_threshold` in config).

**Layer 3 — Blocking heuristic (confidence 0.60)**

`stall_watchdog` fires after `stuck_timeout_seconds` (default 2.0s) of no output. This catches prompts that don't match any text patterns (e.g. a bare `> ` cursor).

### 3.2 Prompt type patterns

#### TYPE_YES_NO

Patterns matched (case-insensitive on ANSI-stripped output):

```
(y/n), [y/N], [Y/n], (yes/no)
? [y/n], ? (y/n)
Proceed/Continue/Delete/... ? (y/n)
Press 'y' to continue
Enter y or n
```

Safe default: `n`

#### TYPE_CONFIRM_ENTER

```
Press Enter to continue
Press Return to start
Hit enter to proceed
[Press Enter]
-- More --
```

Safe default: `\n` (Enter)

#### TYPE_MULTIPLE_CHOICE

```
1) Option A\n2) Option B\n
Enter your choice [1-4]:
Select option (1-3):
Which ... do you want?
[1/2/3]
```

Safe default: `1`

Choices are extracted with `re.findall(r"^\s*(\d+)[)\.]\s+(.+)$", ...)` (up to 9 options).

#### TYPE_FREE_TEXT

```
Enter your name:
Password:
API key:
Email:
Enter commit message:
> (bare prompt character)
```

Safe default: `` (empty string — injects Enter with no text)

Free-text forwarding is off by default (`free_text_enabled = false`). When disabled, the safe default is injected immediately without sending to Telegram.

#### TYPE_UNKNOWN

Triggered by the blocking heuristic when no pattern matches. Forwards the last 200 chars of the output buffer to Telegram with Yes / No / Enter options. Safe default: `n`.

---

## 4. Telegram message format

### 4.1 Prompt messages

Each prompt type gets a dedicated message template:

```
🤖 Claude Code is waiting for your input
_Yes / No question_

```
Continue? (y/n)
```

⏳ Expires in 9m 58s — default: n
```

Followed by inline keyboard buttons:

| Type | Buttons |
|------|---------|
| YES_NO | ✅ Yes · ❌ No · ⏩ Use default (n) |
| CONFIRM_ENTER | ↩️ Press Enter · ⏩ Use default (↩) |
| MULTIPLE_CHOICE | 1. Option A · 2. Option B · … · ⏩ Use default (1) |
| FREE_TEXT | ⏩ Use default (empty) |
| UNKNOWN | ✅ Yes/Enter · ❌ No/Skip · ⏩ Use default |

### 4.2 Callback data format

```
ans:<prompt_id>:<nonce>:<value>
```

- `prompt_id` — UUID of the pending prompt
- `nonce` — `secrets.token_hex(16)`, single-use
- `value` — `y`, `n`, `enter`, `1`–`9`, `default`, or free text

### 4.3 Value normalisation

| Raw value | Injected bytes |
|-----------|---------------|
| `y` | `y\r` |
| `n` | `n\r` |
| `enter` | `\r` |
| `1`–`9` | `N\r` |
| `default` | prompt's `safe_default` → corresponding bytes |
| free text | `text.encode() + b"\r"` |

---

## 5. Injection

Once a response is received (from Telegram or timeout), `PTYSupervisor._inject_response()`:

1. Sets `self._injecting = True` (pauses stdin relay)
2. Writes the inject bytes to the PTY master fd with `os.write(self._proc.fd, inject_bytes)`
3. Updates DB prompt record to `injected` / `auto_injected`
4. Writes audit event `response_injected`
5. Clears the output buffer (prevents re-detection of the same prompt text)
6. Resets `self._injecting = False` and `self._state = RUNNING`

---

## 6. Timeout behaviour

Each prompt has an `expires_at` field (now + `timeout_seconds`). A dedicated asyncio task `_prompt_timeout()` sleeps until TTL + 0.5s, then checks if the prompt was answered. If not, it:

1. Updates DB status to `expired`
2. Sends a timeout notice to Telegram (edits the original message if possible)
3. Calls `_inject_response()` with `timed_out=True` and `prompt.safe_default`

The safe default for YES/NO cannot be overridden to `y` — the config validator rejects it.

---

## 7. Session lifecycle

```
atlasbridge run claude
    │
    ▼ PTY spawned, session saved to DB
    │ Telegram: "▶️ Session started"
    │
    ├── [prompt detected] → Telegram message sent
    │       ├── [reply received] → injected, Claude resumes
    │       └── [timeout] → safe default injected, Telegram notice
    │
    ▼ Claude exits
    │ Session updated in DB (status, exit_code)
    │ Telegram: "⏹ Session ended"
    ▼
```

---

## 8. Failure modes

| Failure | Behaviour |
|---------|-----------|
| Telegram API unreachable | Log error; keep polling; prompt stays pending |
| Prompt timeout (no reply) | Inject safe default; log; notify via Telegram |
| Duplicate callback tap | `decide_prompt` returns 0 rows; silent ignore |
| Expired prompt tapped | "Prompt expired" edit sent to Telegram |
| PTY child crashes | `pty_reader` exits; event loop tasks cancelled; session marked crashed |
| Config invalid | `load_config` raises `ConfigError`; `atlasbridge run` exits before spawning |

---

## 9. Test coverage

| Area | Test file |
|------|-----------|
| Detector patterns | `tests/unit/test_detector.py` (27 cases) |
| DB decide_prompt guard | `tests/unit/test_database.py` |
| Audit chain | `tests/unit/test_audit.py` |
| Telegram templates | `tests/unit/test_telegram_templates.py` |
| Config validation | `tests/unit/test_config.py` |
| CLI commands | `tests/integration/test_cli.py` |
