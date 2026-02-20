# Aegis CLI UX Design

**Version:** 0.1.0
**Status:** Design
**Last updated:** 2026-02-20

---

## Overview

Aegis is a CLI-first tool. Every interaction should feel fast, clear, and recoverable. This document defines the complete UX specification for all Aegis commands, flags, prompts, output formats, and error handling.

### Design Principles

1. **Fail safe, fail loudly** — errors produce clear messages with a suggested fix
2. **Progressive disclosure** — defaults work; advanced flags unlock more control
3. **Structured by default, human-readable always** — `--json` available everywhere
4. **Recoverable** — every command can be re-run safely
5. **No surprises** — destructive or side-effecting actions require confirmation
6. **Quiet mode** — scripts can suppress all non-error output with `--quiet`
7. **Debug mode** — `--debug` shows full stack traces and internal state

---

## Global Flags

Available on every command:

| Flag | Short | Description |
|------|-------|-------------|
| `--help` | `-h` | Show help and exit |
| `--version` | `-V` | Show version and exit |
| `--json` | | Output as JSON (machine-readable) |
| `--quiet` | `-q` | Suppress non-error output |
| `--debug` | | Show debug output and stack traces |
| `--config PATH` | | Override config file path |
| `--no-color` | | Disable colored output |

---

## Exit Codes

| Code | Name | Meaning |
|------|------|---------|
| `0` | `SUCCESS` | Command completed successfully |
| `1` | `ERROR` | General / unhandled error |
| `2` | `CONFIG_ERROR` | Configuration invalid or missing |
| `3` | `ENV_ERROR` | Environment problem (Python version, missing deps) |
| `4` | `NETWORK_ERROR` | Network failure (Telegram unreachable) |
| `5` | `PERMISSION_ERROR` | File permissions or access denied |
| `6` | `SECURITY_VIOLATION` | Policy block, unauthorized operation, unauthorized user |
| `7` | `DEPENDENCY_MISSING` | Required tool or library not found |
| `8` | `STATE_CORRUPTION` | Database, lock file, or audit log corrupted |

All error output goes to `stderr`. Exit codes are consistent and documented.

---

## Commands

### `aegis setup`

**Purpose:** Interactive first-run wizard. Configures Aegis from scratch.

**Usage:**
```
aegis setup [OPTIONS]
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--non-interactive` | Skip all prompts; require flags and env vars |
| `--telegram-token TOKEN` | Telegram bot token |
| `--allowed-users IDS` | Comma-separated Telegram user IDs |
| `--config-path PATH` | Custom config directory (default: `~/.aegis/`) |
| `--force` | Re-run setup even if already configured |
| `--json` | Output result as JSON |

**Interactive flow:**

```
╔══════════════════════════════════════════════╗
║           Welcome to Aegis Setup            ║
╚══════════════════════════════════════════════╝

Aegis protects your machine by intercepting AI agent
tool calls and routing dangerous operations to your
phone for approval.

Let's get you set up. This takes about 2 minutes.

Step 1/5: Telegram Bot Token
──────────────────────────────
You need a Telegram bot. If you don't have one:
  1. Open Telegram and search for @BotFather
  2. Send /newbot and follow the prompts
  3. Copy the token BotFather gives you

Enter your Telegram bot token: █

Step 2/5: Allowed Telegram Users
──────────────────────────────────
Only these Telegram user IDs can approve operations.

To find your ID:
  1. Open Telegram and search for @userinfobot
  2. Send /start — it will reply with your ID

Enter your Telegram user ID(s) [comma-separated]: █

Step 3/5: Testing Telegram Connectivity
──────────────────────────────────────────
  ⏳ Connecting to Telegram API...
  ✓  Bot token valid — bot name: @YourAegisBot
  ⏳ Sending test message to user 123456789...
  ✓  Test message delivered

Check Telegram — you should see a message from your bot.

Did you receive the test message? [Y/n]: █

Step 4/5: Default Policy
──────────────────────────
Choose your default policy:

  1. Strict (recommended)
     Require approval for all writes, deletes, and shell commands
  2. Balanced
     Allow safe reads; require approval for writes and deletes
  3. Custom
     I'll configure policy manually in ~/.aegis/policy.toml

Select policy [1]: █

Step 5/5: Summary
──────────────────
  Config:   ~/.aegis/config.toml       ✓
  Database: ~/.aegis/aegis.db          ✓
  Policy:   ~/.aegis/policy.toml       ✓
  Telegram: @YourAegisBot              ✓
  Users:    [123456789]                ✓

Aegis is ready. Start it with:

  aegis start

Then wrap your AI tool:

  aegis wrap claude

Setup complete. ✓
```

**Non-interactive mode:**
```bash
aegis setup \
  --non-interactive \
  --telegram-token "$(AEGIS_TELEGRAM_BOT_TOKEN)" \
  --allowed-users "123456789"
```

**JSON output (`--json`):**
```json
{
  "status": "success",
  "config_path": "/Users/ara/.aegis/config.toml",
  "db_path": "/Users/ara/.aegis/aegis.db",
  "policy_path": "/Users/ara/.aegis/policy.toml",
  "telegram_bot": "@YourAegisBot",
  "allowed_users": [123456789]
}
```

**Error handling:**
- Invalid token → exit 2, message: "Invalid Telegram bot token. Check the token from @BotFather."
- Network failure → exit 4, message: "Cannot reach Telegram API. Check your internet connection."
- Config already exists → prompt to confirm overwrite (unless `--force`)

---

### `aegis start`

**Purpose:** Start the Aegis background daemon.

**Usage:**
```
aegis start [OPTIONS]
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--foreground` | Run in foreground (don't daemonize); useful for debugging |
| `--port PORT` | Override daemon port (default: 39000) |
| `--log-level LEVEL` | Set log level: DEBUG, INFO, WARNING, ERROR |
| `--json` | Output status as JSON on start |

**Behavior:**
- Checks that setup has been completed (`~/.aegis/config.toml` exists)
- Runs `aegis doctor` lightweight check before starting
- Starts daemon process (background by default)
- Writes PID to `~/.aegis/aegis.pid`
- Polls Telegram for approval responses
- Exits 0 immediately (PID returned); daemon continues in background

**Output:**
```
Starting Aegis daemon...
  ✓  Config loaded
  ✓  Database initialized
  ✓  Telegram bot connected (@YourAegisBot)
  ✓  Daemon started (PID 12345)

Aegis is running. To stop it:
  aegis stop
```

**Already running:**
```
Aegis daemon is already running (PID 12345).
Use 'aegis stop' to stop it first, or 'aegis status' to check it.
```

**Foreground mode:**
```
aegis start --foreground
[2026-02-20 19:00:00] INFO  Aegis daemon starting
[2026-02-20 19:00:00] INFO  Telegram polling started
[2026-02-20 19:00:01] INFO  Listening for tool calls on port 39000
^C
[2026-02-20 19:05:00] INFO  Received SIGINT — shutting down
[2026-02-20 19:05:00] INFO  Daemon stopped
```

**Error handling:**
- Setup not complete → exit 2, suggest `aegis setup`
- Doctor check fails → exit 3, show failing checks
- Port in use → exit 1, suggest `--port`
- Already running → exit 1 (idempotent option via `--json` check)

---

### `aegis stop`

**Purpose:** Stop the Aegis daemon.

**Usage:**
```
aegis stop [OPTIONS]
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--force` | Send SIGKILL instead of SIGTERM |
| `--timeout SECONDS` | Wait this long for graceful shutdown (default: 10) |
| `--json` | Output result as JSON |

**Output:**
```
Stopping Aegis daemon (PID 12345)...
  ✓  Daemon stopped

Pending approvals: 0
```

**If pending approvals exist:**
```
Stopping Aegis daemon (PID 12345)...
  ⚠  Warning: 2 approvals are pending. They will expire on stop.
  Continue? [y/N]: █
```

**Not running:**
```
Aegis daemon is not running.
```
Exit 0 (idempotent).

---

### `aegis wrap <tool>`

**Purpose:** Wrap an AI CLI tool through the Aegis interception layer.

**Usage:**
```
aegis wrap <tool> [-- <tool-args>...]
```

**Examples:**
```bash
aegis wrap claude
aegis wrap claude -- --no-cache --model claude-opus-4-6
aegis wrap openai -- api chat.completions.create
aegis wrap python -- my_agent.py
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Show what interception would do; don't execute the tool |
| `--log-level LEVEL` | Override log level for this session |
| `--timeout SECONDS` | Override approval timeout for this session |
| `--policy PATH` | Override policy file for this session |
| `--passthrough` | Disable interception; run tool directly (emergency bypass) |

**Behavior:**
- Requires daemon to be running (auto-starts if `--auto-start` is configured)
- Launches tool with PTY (preserves interactive behavior, colors, etc.)
- Intercepts tool call events from the AI agent's tool use protocol
- Routes each tool call through the policy engine
- For `allow` — executes immediately, tool call proceeds
- For `deny` — blocks execution, returns error to agent
- For `require_approval` — suspends tool call, sends Telegram notification, waits

**Not-running warning:**
```
Aegis daemon is not running.

Start it with:
  aegis start

Or run this session with auto-start:
  aegis wrap claude --auto-start
```

**Dry run output:**
```
DRY RUN — tool calls will be shown but not executed

Intercepting: claude

Tool call intercepted:
  Tool:    write_file
  Path:    /Users/ara/project/src/main.py
  Action:  require_approval  (policy rule: require-approval-for-writes)
  Would:   suspend and notify Telegram user 123456789

Dry run complete. No tool calls were executed.
```

**Passthrough warning:**
```
⚠  WARNING: Passthrough mode disables all interception.
   Tool calls will NOT be policy-checked or approval-routed.
   This is an emergency bypass. Use with caution.

Continue with passthrough? [y/N]: █
```

---

### `aegis status`

**Purpose:** Show daemon status and system health.

**Usage:**
```
aegis status [OPTIONS]
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON |
| `--watch` | Refresh every 2 seconds (like `watch`) |

**Output:**
```
Aegis Status
────────────────────────────────────────
Daemon:      ● Running (PID 12345)
Uptime:      2h 14m
Port:        39000
Telegram:    ✓  Connected (@YourAegisBot)

Approvals:
  Pending:   2
  Today:     14 (12 approved, 2 denied)
  All time:  1,847

Database:    ~/.aegis/aegis.db (2.1 MB)
Log:         ~/.aegis/aegis.log
Version:     0.2.0
```

**JSON output:**
```json
{
  "daemon": {
    "running": true,
    "pid": 12345,
    "uptime_seconds": 8040,
    "port": 39000
  },
  "telegram": {
    "connected": true,
    "bot_name": "@YourAegisBot"
  },
  "approvals": {
    "pending": 2,
    "today_approved": 12,
    "today_denied": 2,
    "total": 1847
  },
  "database": {
    "path": "/Users/ara/.aegis/aegis.db",
    "size_bytes": 2202009
  },
  "version": "0.2.0"
}
```

---

### `aegis approvals`

**Purpose:** Manage pending and historical approvals.

**Subcommands:**

#### `aegis approvals list`

```
aegis approvals list [--all] [--limit N] [--json]
```

**Output:**
```
Pending Approvals (2)
────────────────────────────────────────────────────────────────────────
 ID      Tool         Path / Command                  Age     Status
────────────────────────────────────────────────────────────────────────
 a1b2c3  write_file   /src/main.py                    30s     ⏳ PENDING
 d4e5f6  bash         git push origin feature/auth    2m      ⏳ PENDING
────────────────────────────────────────────────────────────────────────

Approve:  aegis approvals approve <id>
Deny:     aegis approvals deny <id>
Detail:   aegis approvals show <id>
```

#### `aegis approvals show <id>`

```
Approval a1b2c3
────────────────────────────────────────────────────────────────────────
ID:            a1b2c3
Status:        PENDING
Created:       2026-02-20 19:14:32 (30 seconds ago)
Expires:       2026-02-20 19:19:32 (4m 30s remaining)

Tool:          write_file
Arguments:
  path:        /Users/ara/project/src/main.py
  content:     [1,247 bytes]

Policy rule:   require-approval-for-writes (priority 50)
Risk score:    MEDIUM

AI session:    claude (PID 9876, started 19:10:05)
Prompt hash:   sha256:a3f9...  (truncated for security)

Actions:
  aegis approvals approve a1b2c3
  aegis approvals deny a1b2c3 --reason "Wrong file"
```

#### `aegis approvals approve <id>`

```
aegis approvals approve <id> [--json]
```

```
Approved: a1b2c3 (write_file /src/main.py)
Tool call will now execute.
```

#### `aegis approvals deny <id>`

```
aegis approvals deny <id> [--reason TEXT] [--json]
```

```
Denied: a1b2c3 (write_file /src/main.py)
Reason: Wrong file
Tool call blocked. Agent will receive an error.
```

#### `aegis approvals history`

```
aegis approvals history [--limit N] [--since DATETIME] [--json]
```

---

### `aegis logs`

**Purpose:** View Aegis daemon and audit logs.

**Usage:**
```
aegis logs [OPTIONS]
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--follow` | Stream new log lines (like `tail -f`) |
| `--lines N` | Show last N lines (default: 50) |
| `--level LEVEL` | Filter by log level: DEBUG, INFO, WARNING, ERROR |
| `--json` | Output as JSON Lines |
| `--since DATETIME` | Show logs after this timestamp (ISO 8601) |
| `--audit` | Show audit log instead of daemon log |

**Text output:**
```
[2026-02-20 19:14:02] INFO  Daemon started (PID 12345)
[2026-02-20 19:14:03] INFO  Telegram polling started
[2026-02-20 19:14:32] INFO  Tool call intercepted: write_file (session claude/9876)
[2026-02-20 19:14:32] INFO  Approval required: a1b2c3 → notifying Telegram
[2026-02-20 19:14:55] INFO  Approval a1b2c3 APPROVED by user 123456789
[2026-02-20 19:14:55] INFO  Tool call a1b2c3 executed: write_file → SUCCESS
```

**JSON Lines output (`--json`):**
```json
{"ts": "2026-02-20T19:14:32Z", "level": "INFO", "event": "tool_call_intercepted", "tool": "write_file", "session": "claude/9876", "approval_id": "a1b2c3"}
{"ts": "2026-02-20T19:14:55Z", "level": "INFO", "event": "approval_decision", "approval_id": "a1b2c3", "decision": "approved", "user_id": 123456789}
```

---

### `aegis doctor`

**Purpose:** Run comprehensive system diagnostics.

**Usage:**
```
aegis doctor [OPTIONS]
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--fix` | Attempt safe automatic fixes |
| `--json` | Output as JSON |
| `--verbose` | Show details for PASS checks too |

**Output:**
```
Aegis Doctor — System Diagnostics
════════════════════════════════════════════════════════════════

Environment
───────────────────────────────────────────────────────────────
  ✓  Python 3.11.8 (required: 3.11+)
  ✓  Dependencies installed (aegis-cli 0.2.0)
  ✓  SQLite 3.45.1 accessible
  ✓  Config file exists: ~/.aegis/config.toml
  ✓  Config file valid (all required fields present)
  ✓  Telegram token format valid
  ✓  Telegram API reachable
  ✓  Bot responds: @YourAegisBot
  ✓  claude found on PATH: /usr/local/bin/claude
  ✗  openai not found on PATH
       → Install with: pip install openai

Security
───────────────────────────────────────────────────────────────
  ✓  .env file not in git index
  ✓  Config file permissions: 0600 (owner-only)
  ✓  No secrets found in environment visible to child processes
  ✓  Audit log integrity: OK (1,847 entries, no gaps)

Runtime
───────────────────────────────────────────────────────────────
  ✓  Daemon running (PID 12345)
  ✓  Lock file valid (~/.aegis/aegis.pid)
  ✓  No stuck approvals (oldest pending: 30s)
  ✓  Database schema: current (v3)
  ✓  Disk space: 12.4 GB available

════════════════════════════════════════════════════════════════
Summary: 16 PASS, 1 WARN, 0 FAIL

Issues:
  ⚠  openai not found on PATH
     To wrap the OpenAI CLI, install it first:
     pip install openai
```

**With `--fix`:**
```
  ✗  Config file permissions: 0644 (should be 0600)
       → Auto-fixing: chmod 0600 ~/.aegis/config.toml
       ✓  Fixed
```

**JSON output:**
```json
{
  "summary": {
    "pass": 16,
    "warn": 1,
    "fail": 0,
    "exit_code": 0
  },
  "checks": [
    {
      "category": "environment",
      "name": "python_version",
      "status": "pass",
      "detail": "Python 3.11.8"
    },
    {
      "category": "environment",
      "name": "openai_on_path",
      "status": "warn",
      "detail": "openai not found on PATH",
      "fix": "pip install openai"
    }
  ]
}
```

**Exit codes for doctor:**
- `0` — all pass (or only warnings)
- `3` — one or more environment checks fail
- `5` — permission check failed
- `8` — state corruption detected

---

### `aegis config`

**Purpose:** Read and write Aegis configuration.

**Usage:**
```
aegis config <subcommand> [OPTIONS]
```

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `get <key>` | Print value of config key |
| `set <key> <value>` | Set config key |
| `list` | List all config keys and values |
| `validate` | Validate config file |
| `path` | Print path to config file |
| `edit` | Open config in `$EDITOR` |

**Examples:**
```bash
aegis config get telegram.bot_token
aegis config set approvals.timeout_seconds 600
aegis config list
aegis config validate
aegis config path
aegis config edit
```

**Security:** `aegis config get telegram.bot_token` outputs `***REDACTED***` by default; use `--reveal` to show.

---

### `aegis version`

**Purpose:** Show version information.

**Usage:**
```
aegis version [--json]
```

**Output:**
```
aegis 0.2.0
Python 3.11.8
Platform: darwin arm64
```

**JSON:**
```json
{
  "aegis": "0.2.0",
  "python": "3.11.8",
  "platform": "darwin",
  "arch": "arm64"
}
```

---

### `aegis help`

**Usage:**
```
aegis help
aegis help <command>
aegis --help
aegis <command> --help
```

**Top-level help:**
```
Usage: aegis [OPTIONS] COMMAND [ARGS]...

  Aegis — CLI firewall and approval layer for AI coding agents.

  Intercepts AI tool calls and routes dangerous operations to your
  phone for approval via Telegram.

Options:
  -h, --help       Show this message and exit.
  -V, --version    Show version and exit.
  --json           Output as JSON.
  --quiet          Suppress non-error output.
  --debug          Show debug output.
  --config PATH    Override config file path.
  --no-color       Disable colored output.

Commands:
  setup      First-run wizard — configure Aegis
  start      Start the Aegis daemon
  stop       Stop the Aegis daemon
  wrap       Wrap an AI CLI tool with interception
  status     Show daemon status and health
  approvals  Manage pending and historical approvals
  logs       View daemon and audit logs
  doctor     Run system diagnostics
  config     Read and write configuration
  version    Show version information
  help       Show help for a command

Examples:
  aegis setup
  aegis start
  aegis wrap claude
  aegis status
  aegis approvals list
  aegis doctor

Documentation: https://github.com/abdulraoufatia/aegis-cli
```

---

## Error Message Format

All errors follow this format to stderr:

```
Error: <short description>

  <detail explaining what went wrong>

  <suggested fix or next step>

Exit code: <N>
```

Example:
```
Error: Telegram API unreachable

  Could not connect to https://api.telegram.org after 3 attempts.
  Last error: Connection timed out (10s)

  Check your internet connection and try again:
    aegis doctor --fix

  If behind a proxy, set HTTPS_PROXY in your environment.

Exit code: 4
```

---

## Cancellation UX

When a user presses `Ctrl+C` during an interactive command:

```
^C
Interrupted. Cleaning up...
  ✓  No pending approvals affected
  ✓  Daemon still running

Run 'aegis status' to check daemon state.
```

If an approval is in-flight:
```
^C
Interrupted. Cleaning up...
  ⚠  Approval a1b2c3 is pending — it will continue on Telegram
  ✓  Daemon still running
```

---

## First-Run Experience

On the very first invocation of any `aegis` command (before setup):

```
Welcome to Aegis!

It looks like Aegis hasn't been configured yet.
Run setup first:

  aegis setup

This takes about 2 minutes.
```

---

## Quiet Mode (`--quiet`)

In quiet mode:
- No progress spinners or status output
- No banners or welcome messages
- Errors still go to stderr
- Exit codes unchanged
- Only explicit output (e.g., `aegis config get` value) is printed

---

## Debug Mode (`--debug`)

In debug mode:
- Full Python stack traces on exceptions
- HTTP request/response bodies logged (with secrets masked)
- Policy evaluation steps shown
- Database queries logged
- PTY I/O shown

---

## JSON Output Mode (`--json`)

All commands support `--json`. JSON output:
- Always goes to `stdout`
- Always includes a `"status"` field: `"success"` or `"error"`
- On error, includes `"error"`, `"exit_code"`, and optionally `"detail"`
- Is valid JSON (not JSON Lines, except `aegis logs --json`)

Error JSON:
```json
{
  "status": "error",
  "error": "Telegram API unreachable",
  "exit_code": 4,
  "detail": "Connection timed out after 3 attempts"
}
```

---

## Structured Logging Mode

Set `AEGIS_LOG_FORMAT=json` or `--log-level` with structured output:

```json
{"ts": "2026-02-20T19:00:00Z", "level": "INFO", "logger": "aegis.daemon", "event": "started", "pid": 12345, "port": 39000}
{"ts": "2026-02-20T19:00:01Z", "level": "INFO", "logger": "aegis.telegram", "event": "polling_started"}
```

Uses `structlog` for consistent field naming.
