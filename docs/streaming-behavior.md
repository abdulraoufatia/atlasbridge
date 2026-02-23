# Streaming Behavior

AtlasBridge v0.10.0 adds enhanced streaming output with plan detection, secret redaction, and configurable message editing.

## Architecture

```
PTY Output ──► OutputForwarder ──► StreamingManager ──► Channel
                    │                    │
                    ├── ANSI strip       ├── Accumulate text
                    ├── Batch (2s)       ├── detect_plan()
                    ├── Rate limit       └── present_plan()
                    ├── Redact secrets
                    ├── OutputRouter classify
                    └── Message edit/send
```

## OutputForwarder

The `OutputForwarder` buffers raw PTY bytes and flushes them to the channel periodically:

1. **Feed**: Raw bytes are decoded, ANSI-stripped, and buffered
2. **Flush**: Every `batch_interval_s` seconds, the buffer is drained
3. **Redact**: Secret patterns are replaced with `[REDACTED]`
4. **Classify**: The `OutputRouter` categorizes text as agent prose, CLI output, plan output, or noise
5. **Send**: Text is sent to the channel, optionally editing the last message

## Secret Redaction

The following patterns are redacted before any output reaches the channel:

| Pattern | Example |
|---------|---------|
| Telegram bot token | `1234567890:ABCdef...` |
| Slack bot token | `xoxb-...` |
| Slack app token | `xapp-...` |
| OpenAI API key | `sk-...` |
| GitHub PAT | `ghp_...` |
| AWS access key | `AKIA...` |

Redaction can be disabled via `streaming.redact_secrets = false` in config.

## Plan Detection

The `PlanDetector` identifies structured plans in agent output using two strategies:

### Strategy 1: Header + Steps
A plan header ("Plan:", "## Plan", "Here's my plan:") followed by 2+ numbered steps.

### Strategy 2: Headerless Steps
3+ consecutive numbered steps where 60%+ begin with an action verb (create, add, update, fix, etc.).

### Plan Presentation

When a plan is detected, it's rendered with action buttons:

- **Execute** -- Notifies "Plan accepted. Agent continuing." (no PTY injection)
- **Modify** -- Notifies "Send your modifications as a message." (next free-text goes to chat mode)
- **Cancel** -- Injects cancellation text into the agent's PTY stdin

On Telegram, buttons are rendered as inline keyboard. On Slack, as Block Kit action buttons.

## Configuration

Add a `[streaming]` section to `config.toml`:

```toml
[streaming]
batch_interval_s = 2.0         # Seconds between flushes (0.5-30.0)
max_output_chars = 2000        # Truncate beyond this length
max_messages_per_minute = 15   # Rate limit (1-60)
min_meaningful_chars = 10      # Skip fragments shorter than this
edit_last_message = true       # Re-use last message for streaming updates
redact_secrets = true          # Strip token patterns before sending
```

All fields are optional; defaults are shown above.

## Message Editing

When `edit_last_message = true` (default), the forwarder tracks the last sent message ID and edits it with new output instead of sending a new message. This creates a live-updating effect in the chat.

If editing fails (e.g., message too old), the forwarder falls back to sending a new message.

## Output Classification

The `OutputRouter` classifies each output chunk:

| Kind | Description | Rendering |
|------|-------------|-----------|
| `AGENT_MESSAGE` | Agent prose (markdown, sentences) | Rich formatted text |
| `CLI_OUTPUT` | Command output, logs, stack traces | Monospace code block |
| `PLAN_OUTPUT` | Plan headers with numbered steps | Agent prose (or plan buttons if StreamingManager active) |
| `NOISE` | Too short or whitespace-only | Discarded |
