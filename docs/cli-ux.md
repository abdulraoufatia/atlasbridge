# AtlasBridge UX Specification

**Version:** 0.5.0
**Status:** Active
**Last updated:** 2026-02-21

---

## 1. Design Principles

AtlasBridge is a CLI-first tool. Every interaction must feel fast, clear, and recoverable. The following principles govern all command design decisions.

### Simple

The default invocation of every command does the right thing without flags. A new user who has just run `atlasbridge setup` should be able to run `atlasbridge start` and `atlasbridge run claude` without reading documentation.

Advanced control (dry runs, custom session names, JSON output) is available through flags, but flags are never required for normal use.

### Discoverable

`atlasbridge --help` shows every command. `atlasbridge <command> --help` shows every flag for that command. The help text is the spec — if the help text says something works, it works. If a command is experimental or platform-limited, the help text says so.

`atlasbridge doctor` is always the answer when something is wrong. The user should never have to guess what to check. Every error message ends with a suggested next step, usually `Run atlasbridge doctor to diagnose.`

### Self-healing (`doctor --fix`)

`atlasbridge doctor --fix` attempts to automatically repair common configuration problems: wrong file permissions, missing directories, stale lock files, expired tokens in the environment. It is safe to run at any time. It never makes destructive changes without confirmation.

### No hidden state

AtlasBridge does not have hidden global state beyond the files in `~/.atlasbridge/`. The location of every relevant file is shown by `atlasbridge status` and `atlasbridge doctor`. There are no undocumented environment variables. There are no magic fallback behaviors that only activate under specific conditions.

### Additional principles

- **Fail loudly**: errors produce clear messages to stderr with a suggested fix.
- **Recoverable**: every command can be re-run safely.
- **No surprises**: destructive or side-effecting actions require confirmation (unless `--yes` is passed).
- **Quiet mode**: scripts can suppress all non-error output with `--quiet`.
- **Debug mode**: `--debug` shows full stack traces and internal state.
- **JSON everywhere**: `--json` is available on every command that produces structured output.

---

## 2. Interactive TUI (v0.5.0+)

Running `atlasbridge` with no arguments in an interactive terminal launches the built-in TUI:

```bash
atlasbridge        # auto-detects TTY, launches TUI
atlasbridge ui     # explicit TUI launch
```

### Screens

| Screen | Key | Description |
|--------|-----|-------------|
| Welcome / Overview | (default) | Status summary; quick actions for setup, doctor, sessions, logs |
| Setup Wizard | `S` | 4-step guided configuration: channel → credentials → user IDs → confirm |
| Doctor | `D` | Environment and config health checks with ✓/⚠/✗ status |
| Sessions | `L` | DataTable of active and recent sessions |
| Logs | `G` | Tail of the hash-chained audit log (last 100 events) |

### Navigation

- `Escape` — go back / cancel
- `Q` — quit from any screen
- `R` — refresh current screen
- Arrow keys / Tab — navigate within screens
- Button labels show available keyboard shortcuts

### Welcome screen: unconfigured state

```
AtlasBridge
Autonomous runtime for AI developer agents with human oversight

You're not set up yet. Let's fix that.

AtlasBridge keeps your AI CLI sessions moving when they pause for input.
When your agent asks a question, AtlasBridge forwards it to your phone
(Telegram or Slack). You reply there — AtlasBridge resumes the CLI.

Setup takes ~2 minutes:
  1) Choose a channel (Telegram or Slack)
  2) Add your credentials (kept local)
  3) Allowlist your user ID(s)
  4) Run a quick health check

  [S] Setup AtlasBridge  (recommended)
  [D] Run Doctor         (check environment)
  [Q] Quit
```

### Welcome screen: configured state

```
AtlasBridge
Autonomous runtime for AI developer agents with human oversight

AtlasBridge is ready.

  Config:           Loaded
  Daemon:           Running
  Channel:          telegram
  Sessions:         2
  Pending prompts:  0

  [R] Run a tool      [S] Sessions
  [L] Logs (tail)     [D] Doctor
  [T] Start/Stop daemon
  [Q] Quit
```

### Setup wizard — steps

1. **Channel** — choose Telegram (recommended) or Slack
2. **Credentials** — enter bot token (masked while typing); Slack adds app-level token field
3. **User IDs** — allowlist your numeric Telegram user IDs or Slack member IDs
4. **Confirm** — review summary, press Finish to write `~/.atlasbridge/config.toml`

Tokens are never shown in cleartext. The confirm screen shows `********<last 4>`.

---

## 3. Command Reference

### Global Flags

Available on every command:

| Flag | Short | Description |
|---|---|---|
| `--help` | `-h` | Show help and exit |
| `--version` | `-V` | Show version and exit |
| `--json` | | Output as JSON (machine-readable) |
| `--quiet` | `-q` | Suppress non-error output |
| `--debug` | | Show debug output and full stack traces |
| `--config PATH` | | Override config file path |
| `--no-color` | | Disable colored output |
| `--yes` | `-y` | Skip confirmation prompts; assume yes |

---

### `atlasbridge setup`

**Purpose:** Interactive first-run wizard. Configures AtlasBridge from scratch.

**Usage:**
```
atlasbridge setup [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--token TOKEN` | Telegram bot token (skips Step 1 prompt) |
| `--users IDS` | Comma-separated Telegram user IDs (skips Step 2 prompt) |
| `--channel TYPE` | Channel to configure: `telegram` (default), `slack` |
| `--non-interactive` | Skip all prompts; require `--token` and `--users` |
| `--force` | Re-run setup even if already configured |
| `--config-path PATH` | Custom config directory (default: `~/.atlasbridge/`) |
| `--json` | Output result as JSON |

**Interactive flow:**

```
Welcome to AtlasBridge Setup

AtlasBridge is a remote interactive prompt relay for AI developer agents.
When your AI agent pauses and waits for your input, AtlasBridge forwards
the prompt to your phone via Telegram and injects your reply.

Let's get you set up. This takes about 2 minutes.

Step 1/5: Telegram Bot Token
──────────────────────────────
You need a Telegram bot. If you don't have one:
  1. Open Telegram and search for @BotFather
  2. Send /newbot and follow the prompts
  3. Copy the token BotFather gives you

Enter your Telegram bot token: _

Step 2/5: Allowed Telegram Users
──────────────────────────────────
Only these Telegram user IDs can send replies to your agent.
To find your ID: open Telegram, search @userinfobot, send /start.

Enter your Telegram user ID(s) [comma-separated]: _

Step 3/5: Testing Telegram Connectivity
──────────────────────────────────────────
  Connecting to Telegram API...
  Bot token valid — bot name: @YourAtlasBridgeBot
  Sending test message to user 123456789...
  Test message delivered

Check Telegram — you should see a message from your bot.
Did you receive the test message? [Y/n]: _

Step 4/5: Channel
──────────────────
  1. Telegram (configured)
  2. Add Slack (optional)
  3. Skip

Select [1]: _

Step 5/5: Summary
──────────────────
  Config:   ~/.atlasbridge/config.toml    OK
  Database: ~/.atlasbridge/atlasbridge.db       OK
  Telegram: @YourAtlasBridgeBot           OK
  Users:    [123456789]             OK

AtlasBridge is ready. Start it with:
  atlasbridge start

Then wrap your AI tool:
  atlasbridge run claude

Setup complete.
```

**Non-interactive mode:**
```bash
atlasbridge setup \
  --non-interactive \
  --token "$ATLASBRIDGE_TELEGRAM_BOT_TOKEN" \
  --users "123456789"
```

**JSON output (`--json`):**
```json
{
  "status": "success",
  "config_path": "/Users/ara/.atlasbridge/config.toml",
  "db_path": "/Users/ara/.atlasbridge/atlasbridge.db",
  "telegram_bot": "@YourAtlasBridgeBot",
  "allowed_users": [123456789]
}
```

**Error cases:**
- Invalid token: exit 2. `Error: Invalid Telegram bot token. Verify the token from @BotFather.`
- Network failure: exit 4. `Error: Cannot reach Telegram API. Check your internet connection.`
- Already configured: prompt to confirm overwrite, or use `--force`.

---

### `atlasbridge start`

**Purpose:** Start the AtlasBridge background daemon.

**Usage:**
```
atlasbridge start [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--foreground` | Run in foreground; do not daemonize. Useful for debugging. |
| `--port PORT` | Override daemon port (default: 39000) |
| `--log-level LEVEL` | Set log level: DEBUG, INFO, WARNING, ERROR (default: INFO) |
| `--json` | Output start result as JSON |

**Output:**
```
Starting AtlasBridge daemon...
  Config loaded
  Database initialized
  Telegram bot connected (@YourAtlasBridgeBot)
  Daemon started (PID 12345)

AtlasBridge is running. To stop it:
  atlasbridge stop
```

**Already running:**
```
AtlasBridge daemon is already running (PID 12345).
Use 'atlasbridge stop' to stop it first.
```

---

### `atlasbridge stop`

**Purpose:** Stop the AtlasBridge daemon.

**Usage:**
```
atlasbridge stop [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--force` | Send SIGKILL instead of SIGTERM |
| `--timeout SECONDS` | Wait this long for graceful shutdown (default: 10) |
| `--json` | Output result as JSON |

**Output:**
```
Stopping AtlasBridge daemon (PID 12345)...
  Daemon stopped
```

**If sessions are active:**
```
Warning: 1 active session will be terminated (claude, PID 9876).
Continue? [y/N]: _
```

**Not running:** Exit 0 (idempotent). Output: `AtlasBridge daemon is not running.`

---

### `atlasbridge status`

**Purpose:** Show daemon status and session overview.

**Usage:**
```
atlasbridge status [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--json` | Output as JSON |
| `--watch` | Refresh every 2 seconds |

**Output:**
```
AtlasBridge Status
────────────────────────────────────────────
Daemon:      Running (PID 12345)
Uptime:      2h 14m
Telegram:    Connected (@YourAtlasBridgeBot)

Sessions:
  Active:    1   (claude, PID 9876)
  Today:     3

Prompts today:
  Forwarded:  8
  Answered:   8
  Pending:    0

Database:    ~/.atlasbridge/atlasbridge.db (2.1 MB)
Version:     0.2.0
```

**JSON output:**
```json
{
  "daemon": { "running": true, "pid": 12345, "uptime_seconds": 8040 },
  "telegram": { "connected": true, "bot_name": "@YourAtlasBridgeBot" },
  "sessions": { "active": 1, "today": 3 },
  "prompts": { "forwarded_today": 8, "answered_today": 8, "pending": 0 },
  "version": "0.2.0"
}
```

---

### `atlasbridge run <tool> [args...]`

**Purpose:** Run an AI CLI tool under AtlasBridge supervision. This is the primary command users invoke on every session.

**Usage:**
```
atlasbridge run <tool> [tool-args...] [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--session-name NAME` | Label for this session in logs and Telegram messages |
| `--dry-run` | Show what would happen; do not start the process |
| `--no-inject` | Detect and forward prompts but do not inject replies (monitor-only mode) |
| `--timeout SECONDS` | Override prompt reply timeout for this session |
| `--policy PATH` | Override policy file for this session |

**Examples:**
```bash
atlasbridge run claude
atlasbridge run claude --model claude-opus-4-6
atlasbridge run python my_agent.py
atlasbridge run claude --session-name "auth-feature-sprint"
atlasbridge run claude --dry-run
```

**Behavior:**
- Requires the daemon to be running. If not running, suggests `atlasbridge start`.
- Launches the tool in a PTY (full interactive terminal, colors preserved).
- Forwards all output to the host terminal.
- On prompt detection, sends the prompt to Telegram and waits for the reply.
- Injects the reply into the tool's stdin. The tool resumes.

**Dry-run output:**
```
DRY RUN — process will not be started

Would run: claude
PTY: enabled
Session name: (auto)
Prompt detection: tri-signal (pattern + stall + time)
On detection: forward to Telegram user 123456789

No process started.
```

**Not-running warning:**
```
Error: AtlasBridge daemon is not running.

Start it with:
  atlasbridge start

Then retry:
  atlasbridge run claude

Exit code: 1
```

---

### `atlasbridge sessions`

**Purpose:** List active and recent sessions with their IDs, tool names, status, and prompt counts.

**Usage:**
```
atlasbridge sessions [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--all` | Show all sessions, not just today's |
| `--json` | Output as JSON |

**Output:**
```
Sessions
────────────────────────────────────────────────────────────────
 ID        Tool     Status    Started    Prompts  Session Name
────────────────────────────────────────────────────────────────
 s-a1b2c3  claude   ACTIVE    19:10:05   8        auth-feature
 s-d4e5f6  claude   ENDED     17:30:11   3        (none)
────────────────────────────────────────────────────────────────

To attach logs for a session:
  atlasbridge logs --session s-a1b2c3
```

---

### `atlasbridge logs`

**Purpose:** View AtlasBridge daemon and session logs.

**Usage:**
```
atlasbridge logs [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--tail` | Stream new log lines continuously (like `tail -f`) |
| `-n N` | Show last N lines (default: 50) |
| `--session ID` | Filter to a specific session ID |
| `--level LEVEL` | Filter by log level: DEBUG, INFO, WARNING, ERROR |
| `--json` | Output as JSON Lines |
| `--since DATETIME` | Show logs after this timestamp (ISO 8601) |

**Output:**
```
[2026-02-21 19:10:05] INFO  Session started: claude (PID 9876, session s-a1b2c3)
[2026-02-21 19:14:32] INFO  Prompt detected: YES_NO (confidence 0.90, pattern match)
[2026-02-21 19:14:32] INFO  Prompt forwarded to Telegram: prompt-p1q2r3
[2026-02-21 19:14:55] INFO  Reply received from user 123456789: "y"
[2026-02-21 19:14:55] INFO  Reply injected into stdin (23ms)
```

**JSON Lines output (`--json`):**
```json
{"ts": "2026-02-21T19:14:32Z", "level": "INFO", "event": "prompt_detected", "type": "YES_NO", "confidence": 0.90}
{"ts": "2026-02-21T19:14:55Z", "level": "INFO", "event": "reply_injected", "latency_ms": 23, "user_id": 123456789}
```

---

### `atlasbridge doctor`

**Purpose:** Run comprehensive health diagnostics. Always the first thing to run when something is wrong.

**Usage:**
```
atlasbridge doctor [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--fix` | Attempt safe automatic repairs |
| `--json` | Output as JSON |
| `--verbose` | Show details for PASS checks too |

**Output:**
```
AtlasBridge Doctor — System Diagnostics
════════════════════════════════════════

Environment
──────────────────────────────────────
  PASS  Python 3.11.8 (required: 3.11+)
  PASS  Dependencies installed (atlasbridge 0.2.0)
  PASS  SQLite 3.45.1 accessible
  PASS  Config file exists: ~/.atlasbridge/config.toml
  PASS  Config file valid
  PASS  Telegram token format valid
  PASS  Telegram API reachable
  PASS  Bot responds: @YourAtlasBridgeBot
  PASS  claude found on PATH: /usr/local/bin/claude

Security
──────────────────────────────────────
  PASS  Config file permissions: 0600 (owner-only)
  PASS  Audit log integrity: OK

Runtime
──────────────────────────────────────
  PASS  Daemon running (PID 12345)
  PASS  No stuck sessions
  PASS  Database schema: current

════════════════════════════════════════
Summary: 13 PASS, 0 WARN, 0 FAIL
```

**With `--fix`:**
```
  FAIL  Config file permissions: 0644 (should be 0600)
        Auto-fixing: chmod 0600 ~/.atlasbridge/config.toml
        Fixed
```

**Exit codes for `doctor`:**
- `0`: all checks pass (warnings are OK)
- `3`: environment check failed
- `5`: permission check failed
- `8`: state corruption detected

---

### `atlasbridge doctor --fix`

The `--fix` flag enables automatic repair of the following issues:

| Issue | Auto-fix |
|---|---|
| Config file permissions not 0600 | `chmod 0600 ~/.atlasbridge/config.toml` |
| PID file orphaned (process not running) | Remove stale `~/.atlasbridge/atlasbridge.pid` |
| Database WAL file stuck | `PRAGMA wal_checkpoint(TRUNCATE)` |
| `~/.atlasbridge/` directory missing | `mkdir -p ~/.atlasbridge` with 0700 |

Fixes that would destroy data (e.g., a corrupted database) are never applied automatically. The doctor reports them and tells the user what to do manually.

---

### `atlasbridge debug bundle`

**Purpose:** Package logs and configuration into a redacted archive for support.

**Usage:**
```
atlasbridge debug bundle [OPTIONS]
```

**Flags:**

| Flag | Description |
|---|---|
| `--output PATH` | Output path for the bundle (default: `./atlasbridge-debug-<timestamp>.zip`) |
| `--include-logs N` | Include last N lines of logs (default: 500) |
| `--no-redact` | Include secrets unredacted (use with care) |

**What is included (redacted by default):**
- `~/.atlasbridge/config.toml` with `bot_token` replaced by `***REDACTED***`
- Last 500 lines of `~/.atlasbridge/atlasbridge.log`
- `atlasbridge doctor --json` output
- `atlasbridge version --json` output
- Python version and platform info
- OS version

**Output:**
```
Creating debug bundle...
  Collecting config (redacted)...       done
  Collecting logs (last 500 lines)...   done
  Running doctor...                     done
  Collecting version info...            done

Bundle saved to: ./atlasbridge-debug-20260221-191055.zip (12 KB)

Share this file with the AtlasBridge team. It does not contain your bot token or user IDs.
```

---

### `atlasbridge channel add telegram|slack`

**Purpose:** Add or reconfigure a notification channel.

**Usage:**
```
atlasbridge channel add <type> [OPTIONS]
```

Supported types: `telegram`, `slack`

**Flags (telegram):**

| Flag | Description |
|---|---|
| `--token TOKEN` | Bot token |
| `--users IDS` | Comma-separated user IDs |

**Flags (slack):**

| Flag | Description |
|---|---|
| `--token TOKEN` | Slack bot OAuth token |
| `--channel CHANNEL` | Slack channel to post to (e.g., `#atlasbridge-approvals`) |
| `--users IDS` | Comma-separated Slack user IDs allowed to reply |

**Output:**
```
Adding Slack channel...

Step 1/3: Slack Bot Token
──────────────────────────
Install the AtlasBridge Slack app at your workspace, then enter the bot token:
Enter Slack bot token: _

Step 2/3: Slack Channel
────────────────────────
Enter the Slack channel (e.g. #atlasbridge-approvals): _

Step 3/3: Testing
──────────────────
  Connecting to Slack API...    OK
  Sending test message...       OK

Slack channel configured.
```

---

### `atlasbridge adapter list`

**Purpose:** Show available tool adapters and their compatibility status.

**Usage:**
```
atlasbridge adapter list [--json]
```

**Output:**
```
Available Adapters

 Adapter    Status        Tested With
 claude     Supported     claude 0.2.x (Claude Code)
 openai     Supported     openai-cli 1.x
 gemini     Experimental  gemini-cli 0.1.x
 custom     Any           Any interactive CLI

Use: atlasbridge run <tool>
```

---

### `atlasbridge version`

**Purpose:** Show version information and active feature flags.

**Usage:**
```
atlasbridge version [--json]
```

**Output:**
```
atlasbridge 0.2.0
Python 3.11.8
Platform: darwin arm64

Feature flags:
  conpty_backend    disabled  (v0.5.0)
  slack_channel     disabled  (v0.4.0)
  whatsapp_channel  disabled  (future)
```

**JSON:**
```json
{
  "atlasbridge": "0.2.0",
  "python": "3.11.8",
  "platform": "darwin",
  "arch": "arm64",
  "feature_flags": {
    "conpty_backend": false,
    "slack_channel": false,
    "whatsapp_channel": false
  }
}
```

---

### `atlasbridge lab run <scenario>` / `atlasbridge lab list`

**Purpose:** Prompt Lab — developer and QA tool for running PTY/detection scenarios. Not intended for end users.

**Usage:**
```
atlasbridge lab run <scenario>     Run a single scenario by QA ID or name
atlasbridge lab run --all          Run all registered scenarios
atlasbridge lab list               List all registered scenarios
```

**`atlasbridge lab list` output:**
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

11 scenarios registered.
```

**`atlasbridge lab run --all` output:**
```
Running all Prompt Lab scenarios...

  QA-001   PartialLinePromptScenario     PASS  (42ms)
  QA-002   ANSIRedrawScenario            PASS  (38ms)
  QA-003   OverwrittenPromptScenario     PASS  (61ms)
  QA-004   SilentBlockScenario           PASS  (2104ms)
  QA-005   NestedPromptsScenario         PASS  (88ms)
  QA-006   MultipleChoiceScenario        PASS  (45ms)
  QA-007   YesNoVariantsScenario         PASS  (39ms)
  QA-008   PressEnterScenario            PASS  (41ms)
  QA-009   FreeTextConstraintScenario    PASS  (44ms)
  QA-018   OutputFloodScenario           PASS  (5231ms)
  QA-019   EchoLoopScenario              PASS  (97ms)

11/11 passed. All scenarios green.
```

---

## 3. Output Formatting

### When to use Rich tables

Use Rich tables for multi-row structured output: `atlasbridge sessions`, `atlasbridge adapter list`, `atlasbridge lab list`. Rich tables are rendered only when stdout is a TTY. When stdout is piped or redirected, fall back to plain tab-separated values.

### When to use plain text

Use plain text for single-value output (`atlasbridge config get <key>`), status lines that scripts may parse, and all output in `--quiet` mode. Plain text is the default for error messages to stderr.

### When to use JSON (`--json`)

All commands that produce structured output support `--json`. JSON output:
- Always goes to stdout.
- Always includes a `"status"` field: `"success"` or `"error"`.
- Is valid JSON (not JSON Lines), except `atlasbridge logs --json` which uses JSON Lines (one object per line).
- Is produced even when stdout is not a TTY.

JSON is the recommended format for use in scripts, CI pipelines, and any context where the output will be parsed.

### Spinners and progress

Spinners (via Rich) are shown during operations that take more than 500ms: Telegram connectivity test, daemon startup, debug bundle creation. Spinners are suppressed in `--quiet` mode and when stdout is not a TTY.

---

## 4. Error Messages

### Tone and format

Error messages are direct, non-blaming, and always end with a suggested next step. The user is never left wondering what to do.

Format:
```
Error: <short description of what went wrong>

  <one or two sentences of detail>

  <suggested next step>

Exit code: <N>
```

Example:
```
Error: Telegram API unreachable

  Could not connect to api.telegram.org after 3 attempts.
  Last error: Connection timed out (10s)

  Check your internet connection, then run:
    atlasbridge doctor --fix

Exit code: 4
```

### Actionable by default

Every error message includes at least one concrete action the user can take. Acceptable actions:
- A specific `atlasbridge` command to run
- A file to check
- A URL to visit

Unacceptable:
- "An unknown error occurred."
- "Please try again."
- "Contact support." (without a link or command)

### Common error templates

| Situation | Message |
|---|---|
| Setup not complete | `Run 'atlasbridge setup' to configure AtlasBridge first.` |
| Daemon not running | `Run 'atlasbridge start' to start the daemon.` |
| Config invalid | `Run 'atlasbridge doctor' to diagnose configuration issues.` |
| Permission denied | `Run 'atlasbridge doctor --fix' to auto-repair file permissions.` |
| Network failure | `Check your internet connection. Run 'atlasbridge doctor' for details.` |
| Unknown error | `Run 'atlasbridge debug bundle' and share the output with the AtlasBridge team.` |

---

## 5. Exit Codes

| Code | Name | Meaning |
|---|---|---|
| `0` | `SUCCESS` | Command completed successfully |
| `1` | `ERROR` | General or unhandled error |
| `2` | `CONFIG_ERROR` | Configuration invalid, missing, or incomplete |
| `3` | `ENV_ERROR` | Python version wrong, dependency missing, OS not supported |
| `4` | `NETWORK_ERROR` | Network failure (Telegram or Slack unreachable) |
| `5` | `PERMISSION_ERROR` | File permissions or access denied |
| `8` | `STATE_CORRUPTION` | Database, lock file, or audit log corrupted |
| `130` | `INTERRUPTED` | Interrupted by Ctrl+C (SIGINT) |

All error output goes to stderr. Exit codes are consistent and documented. Scripts can rely on them.

### Ctrl+C (SIGINT) handling

When the user presses Ctrl+C during an interactive command:

```
^C
Interrupted. Cleaning up...
  No active sessions affected
  Daemon still running

Run 'atlasbridge status' to check daemon state.
Exit code: 130
```

If a session is active:
```
^C
Interrupted.
  Session s-a1b2c3 (claude) is still running in the background.
  A pending prompt will continue waiting for your Telegram reply.
  Daemon still running.

To monitor the session:
  atlasbridge logs --session s-a1b2c3 --tail
Exit code: 130
```

---

## 6. Shell Completion

AtlasBridge generates shell completion scripts for bash, zsh, and fish via Click's built-in completion system.

### Bash

Add to `~/.bashrc`:
```bash
eval "$(_ATLASBRIDGE_COMPLETE=bash_source atlasbridge)"
```

Or generate and source a file:
```bash
_ATLASBRIDGE_COMPLETE=bash_source atlasbridge > ~/.atlasbridge-complete.bash
echo "source ~/.atlasbridge-complete.bash" >> ~/.bashrc
```

### Zsh

Add to `~/.zshrc`:
```zsh
eval "$(_ATLASBRIDGE_COMPLETE=zsh_source atlasbridge)"
```

### Fish

```fish
_ATLASBRIDGE_COMPLETE=fish_source atlasbridge > ~/.config/fish/completions/atlasbridge.fish
```

### What is completed

- All commands and subcommands
- All flags and their arguments
- `atlasbridge run <TAB>`: completes tool names found on PATH
- `atlasbridge lab run <TAB>`: completes registered QA scenario IDs
- `atlasbridge logs --session <TAB>`: completes active session IDs
- `atlasbridge channel add <TAB>`: completes `telegram slack`

---

## 7. Telegram Bot Commands

The AtlasBridge Telegram bot supports the following slash commands. These commands are sent directly to the bot in Telegram and control the active session.

### `/start`

Sent automatically when a user opens a conversation with the bot. Responds with a welcome message and the current connection status.

```
AtlasBridge bot connected.
Daemon status: Running
Active sessions: 1 (claude, started 19:10)

When your AI agent asks a question, I'll send it here.
Use /help to see available commands.
```

### `/sessions`

Lists all active and recent sessions.

```
Active Sessions

  s-a1b2c3  claude  started 19:10  8 prompts  auth-feature
  s-d4e5f6  claude  ended 17:30    3 prompts   (none)

Tap a session name to see its last output.
```

### `/switch <session-id>`

Switches the active session context. When multiple sessions are running, replies go to the session set by `/switch`. If only one session is active, `/switch` is not needed.

```
/switch s-a1b2c3

Now routing replies to: claude (s-a1b2c3, auth-feature)
```

### `/status`

Shows daemon and session status inline in Telegram.

```
AtlasBridge Status

  Daemon: Running (PID 12345)
  Telegram: Connected
  Active sessions: 1
  Pending prompts: 0

Last prompt: "Do you want to apply this change? (y/n)" — answered 2m ago
```

### `/cancel`

Cancels the most recent pending prompt without sending a reply. The agent will receive a timeout or a neutral response depending on the prompt type.

```
/cancel

Cancelled prompt: "Do you want to apply this change?" (s-a1b2c3)
The agent will receive a timeout response.
```

### `/help`

Shows all available bot commands with brief descriptions.

```
AtlasBridge Bot Commands

  /start    Show connection status
  /sessions List active sessions
  /switch   Switch active session: /switch <session-id>
  /status   Show daemon status
  /cancel   Cancel the pending prompt
  /help     Show this message

To answer a prompt, tap an inline button or reply to the message directly.
```

### Inline prompt messages

When a prompt is detected, the bot sends a message with an inline keyboard. The message format:

```
claude (auth-feature) is waiting for your input:

  "Do you want to continue with the database migration?
   This will modify 3 tables. (y/n)"

Prompt type: YES_NO
Detected: pattern match (confidence 0.90)
```

Keyboard buttons for `YES_NO`: `Yes`  `No`

Keyboard buttons for `CONFIRM_ENTER`: `Send Enter`  `Cancel`

Keyboard buttons for `MULTIPLE_CHOICE`: one button per option, labeled `1`, `2`, `3`, etc.

For `FREE_TEXT` prompts, there are no inline buttons. The message instructs the user to reply directly to the message, and the bot routes the reply text to the session.
