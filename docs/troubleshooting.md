# Troubleshooting Guide

Common issues and their solutions when running AtlasBridge.

---

## Adapter Issues

### "Unknown adapter: 'claude'. Available: (none)"

**Cause:** The adapter modules failed to import, usually due to a missing dependency.

**Fix:**
```bash
# Reinstall AtlasBridge
pip install -U atlasbridge

# Verify adapters load
atlasbridge adapter list
```

If `adapter list` shows adapters but `run` doesn't, check for import errors:
```bash
python -c "import atlasbridge.adapters.claude_code"
```

### "Unknown adapter: 'claude'"

**Cause:** The adapter name doesn't match a registered adapter.

**Fix:** Use one of the registered names:
```bash
atlasbridge adapter list          # see available adapters
atlasbridge run claude            # or: atlasbridge run claude-code
```

Both `claude` and `claude-code` are valid names for the Claude Code adapter.

---

## Telegram Issues

### "chat not found" (400 Bad Request)

**Cause:** The Telegram user hasn't started a conversation with the bot.

**Fix:**
1. Open Telegram
2. Search for your bot by username
3. Send `/start` to the bot
4. Retry `atlasbridge run claude`

See [Telegram Setup Guide](telegram-setup.md) for details.

### "409 Conflict: terminated by other getUpdates request"

**Cause:** Two processes are polling the same Telegram bot token simultaneously.

**Fix:**
```bash
atlasbridge stop                  # stop any running daemon
atlasbridge doctor                # check for stale lock files
atlasbridge run claude            # restart cleanly
```

AtlasBridge enforces singleton polling via an OS-level file lock. If a process crashes, the lock may be stale. `atlasbridge doctor` detects and cleans up stale locks automatically.

### Prompts not arriving in Telegram

1. Verify you sent `/start` to the bot
2. Check your user ID is in the allowlist: `atlasbridge doctor`
3. View logs: `atlasbridge logs --tail`
4. Check the bot token is valid: re-run `atlasbridge setup --channel telegram`

### Responding to workspace trust prompts from your phone

When Claude Code (or another tool) asks to **trust this workspace**, AtlasBridge forwards the prompt to Telegram. You can respond in several ways:

- **Reply with text:** `yes`, `y`, `1` (trust) or `no`, `n`, `2` (don’t trust / exit).
- **Tap the inline buttons** (e.g. **1** or **2**) if the message shows them.

The relay presents this as a **workspace trust confirmation** and strips terminal-only hints (e.g. “Enter to confirm”) so the message is phone-friendly. If you see “No active session” after replying, ensure you’re replying in the same chat where the prompt appeared and that the session is still running (`atlasbridge status`).

---

## Doctor Issues

### "'str' object has no attribute 'exists'"

**Cause:** An older version had a bug where config paths were strings instead of Path objects.

**Fix:** Upgrade to the latest version:
```bash
pip install -U atlasbridge
atlasbridge doctor
```

### doctor --fix doesn't fix

If `atlasbridge doctor --fix` doesn't resolve all issues:
1. Run `atlasbridge setup` to reconfigure from scratch
2. Check that environment variables are set correctly (if using `--from-env`)
3. Verify file permissions on the config directory

---

## Upgrade Issues

### Tokens/config lost after upgrade

AtlasBridge preserves your config file across upgrades. The config file lives at a platform-specific location:

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/atlasbridge/config.toml` |
| Linux | `~/.config/atlasbridge/config.toml` |

`pip install -U atlasbridge` only replaces the Python package, not your config files.

If you previously used the `aegis` name, AtlasBridge auto-migrates from `~/.aegis/` on first run.

### Setup asks to reconfigure after upgrade

`atlasbridge setup` now detects existing configuration and asks:
```
Existing config found: /path/to/config.toml
Keep existing configuration? [Y/n]
```

Choose **Y** to keep your existing tokens and settings.

---

## Channel Message Issues

### "Agent is working. Message not sent."

**Cause:** The agent is streaming output. Messages are blocked during streaming.

**Fix:** Wait for the agent to finish. When it needs input, a prompt will appear.

### "Policy does not allow this action."

**Cause:** Your policy doesn't permit this message type in the current session state.

**Fix:** To allow chat turns when idle, add `allow_chat_turns: true` to your policy. To allow interrupts during execution, add `allow_interrupts: true`. See [Channel Message Gating](channel-message-gating.md).

### "This prompt requires local input."

**Cause:** The agent is asking for a password or token. These must be entered in the terminal.

**Fix:** Switch to the terminal where the session is running and enter the value directly.

### "You are not authorized for this session."

**Cause:** Your channel user ID is not on the session's allowlist.

**Fix:** Contact the session operator to add your user ID.

---

## Windows Support

### Windows ConPTY is experimental

Windows support uses the ConPTY API via `pywinpty` and is gated behind the `--experimental` flag:

```bash
atlasbridge run claude --experimental
```

**Requirements:**
- Windows 10 1809+ (build 17763) or Windows 11
- `pywinpty` package: `pip install atlasbridge[windows]`

**Recommended path:** Use WSL2 for the most reliable experience. AtlasBridge runs natively on Linux inside WSL2 with full PTY support.

**Known limitations:**
- ConPTY has behavioural differences across Windows builds
- CRLF line ending normalisation may affect some prompts
- The `atlasbridge doctor` command shows "experimental" status on Windows
- CI runs Windows tests as non-blocking (`continue-on-error: true`)

### "pywinpty is required for Windows ConPTY support"

**Cause:** The `pywinpty` package is not installed.

**Fix:**
```bash
pip install atlasbridge[windows]
```

### "Windows ConPTY requires build 17763+"

**Cause:** Your Windows version is too old for the ConPTY API.

**Fix:** Update to Windows 10 version 1809 or later, or use WSL2.

### "Windows ConPTY support is experimental"

**Cause:** You ran `atlasbridge run` without the `--experimental` flag on Windows.

**Fix:**
```bash
atlasbridge run claude --experimental
```

---

## General Debugging

### View logs
```bash
atlasbridge logs --tail            # recent audit events
atlasbridge logs --session <id>    # specific session
```

### Check system health
```bash
atlasbridge doctor                 # run all health checks
atlasbridge doctor --fix           # auto-repair what's possible
atlasbridge doctor --json          # machine-readable output
```

### Check active sessions
```bash
atlasbridge sessions               # list sessions
atlasbridge status                 # daemon status
```

### Debug bundle
```bash
atlasbridge debug bundle           # create redacted diagnostic archive
```

This creates a zip with config (secrets redacted), recent audit log entries, and doctor output.
