# Channel Message Gating

**Status:** Current
**Phase:** S4 — Channel Gating Features
**Version:** v0.10.x

---

## Overview

Every message from a Telegram or Slack channel is evaluated immediately by the **ChannelMessageGate** — a pure, deterministic function that returns ACCEPT or REJECT. No messages are ever queued or held for later delivery.

This page documents:
- How the gate evaluates messages
- What each session state means for message handling
- All rejection reasons and what to do about them
- Policy configuration for chat turns and interrupts

---

## How Channel Messages Are Handled

```
User sends message (Telegram/Slack)
    │
    ▼
ChannelMessageGate.evaluate_gate(context)
    │
    ├── ACCEPT → inject into session, send "✓ Sent to session."
    │
    └── REJECT → send rejection message + next action hint
```

1. A message arrives from any channel
2. The gate builds a frozen `GateContext` snapshot (session state, identity, prompt binding, etc.)
3. `evaluate_gate()` runs a deterministic 6-step evaluation
4. The result is an immutable `GateDecision` — either ACCEPT or REJECT
5. The channel sends a user-facing confirmation or rejection message

**No queueing.** Messages are never stored, buffered, or replayed. Every message gets an immediate verdict.

---

## Evaluation Order

The gate evaluates in strict order. The first failing check produces a rejection:

| Step | Check | Rejection |
|------|-------|-----------|
| 1 | Identity — is the user on the allowlist? | `REJECT_IDENTITY_NOT_ALLOWLISTED` |
| 2 | Session — does an active session exist? | `REJECT_NO_ACTIVE_SESSION` |
| 3a | State: STREAMING — is the agent producing output? | `REJECT_BUSY_STREAMING` |
| 3b | State: RUNNING — is the agent executing? (unless interrupt policy allows) | `REJECT_BUSY_RUNNING` |
| 3c | State: STOPPED — has the session ended? | `REJECT_NO_ACTIVE_SESSION` |
| 4a | Prompt binding — is the agent waiting for input? | `REJECT_NOT_AWAITING_INPUT` |
| 4b | TTL — has the prompt expired? | `REJECT_TTL_EXPIRED` |
| 4c | Input type — is this a password/credential prompt? | `REJECT_UNSAFE_INPUT_TYPE` |
| 4d | Choice validation — is the selection valid? | `REJECT_INVALID_CHOICE` |
| 5 | IDLE: chat turns — does policy allow free text? | `REJECT_POLICY_DENY` |
| 6 | Default deny — unrecognized state | `REJECT_POLICY_DENY` |

---

## Session States and Message Handling

| State | Accepts messages? | Behavior |
|-------|-------------------|----------|
| **AWAITING_INPUT** | Yes, if valid | Prompt reply — checks binding, TTL, input type, choice validity |
| **IDLE** | Only with policy | Free text — requires `allow_chat_turns: true` in policy |
| **STREAMING** | Never | Agent is producing output; all messages rejected |
| **RUNNING** | Only with policy | Agent is executing; requires `allow_interrupts: true` |
| **STOPPED** | Never | Session has ended; start a new one |

---

## Rejection Reasons Reference

### Agent is working (STREAMING)

> **Message:** "Agent is working. Message not sent."
> **Next action:** Wait for the current operation to finish, then try again.

The agent is actively producing output (streaming text to the terminal). Wait for it to finish — when the agent needs your input, you'll see a prompt with options.

### Agent is busy (RUNNING)

> **Message:** "Agent is busy. Message not sent."
> **Next action:** Wait for the agent to finish or request input.

The agent is executing a command. Unless the operator's policy allows interrupts (`allow_interrupts: true`), messages are blocked until the agent finishes.

### No active session

> **Message:** "No active session. Message not sent."
> **Next action:** Start a session first: `atlasbridge run claude`

No session is running, or the session has stopped. Start a new session from the terminal.

### Prompt expired (TTL)

> **Message:** "This prompt has expired. Message not sent."
> **Next action:** A new prompt will appear if the agent needs input.

The prompt you were responding to has expired. The agent may have moved on. Check `atlasbridge status` or wait for the next prompt.

### Not authorized

> **Message:** "You are not authorized for this session."
> **Next action:** Contact the session operator.

Your Telegram/Slack user ID is not on the session's identity allowlist. Only the operator who started the session (and any explicitly allowlisted users) can send messages.

### Invalid response

> **Message:** "Invalid response. Message not sent."
> **Next action:** Reply with one of the valid options shown in the prompt.

You sent a response that doesn't match any of the valid choices for a numbered-choice prompt. Send the correct option number.

### Rate limited

> **Message:** "Too many messages. Please wait a moment."
> **Next action:** Try again in a few seconds.

You've sent too many messages in a short period. The default limit is 10 messages per minute with a burst of 3. Wait a moment and try again.

### Use the terminal (password/credential prompt)

> **Message:** "This prompt requires local input (not via channel)."
> **Next action:** Enter this value directly in the terminal.

The agent is asking for sensitive input (a password, token, or API key). For security, this must be entered directly in the terminal where the agent is running — never via a messaging channel.

### Policy deny

> **Message:** "Policy does not allow this action. Message not sent."
> **Next action:** Check your policy configuration or contact the operator.

Your policy does not permit this type of message in the current session state. You may need to enable chat turns or interrupt policy.

---

## Rate Limiting

Incoming channel messages are rate-limited per user, per channel:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_per_minute` | 10 | Sustained message rate |
| `burst` | 3 | Rapid messages allowed before throttling |
| Floor | 1/min | Minimum rate — cannot be disabled |

Rate limiting uses a token-bucket algorithm. Buckets are per-user per-channel (not per-session) and reset on daemon restart.

---

## Binary Menu Normalization

When the agent presents a numbered menu with exactly two options that have yes/no semantics (e.g., "1. Allow / 2. Deny"), you can reply with natural language:

| Your reply | Maps to |
|------------|---------|
| `yes`, `y`, `ok`, `allow`, `approve`, `trust`, `continue`, `accept`, `confirm` | The "yes" option |
| `no`, `n`, `exit`, `deny`, `cancel`, `abort`, `reject`, `quit`, `stop` | The "no" option |
| `1`, `2` (digit) | Direct option selection |

Ambiguous replies (anything not in the lists above or a valid option number) will prompt you to send the option number directly.

This normalization only applies to **binary** menus with semantic labels. Multi-option menus (3+ choices) or non-semantic menus (e.g., "Option A / Option B") require the exact option number.

---

## Troubleshooting

### "Agent is working. Message not sent."

The agent is currently streaming output. This is normal — wait for it to finish. When the agent needs your input, a prompt will appear with buttons (Yes/No, choices, etc.).

### "Policy does not allow this action."

Your policy file does not permit this type of message in the current session state. Common fixes:

- To allow free-text messages when the agent is idle, your policy needs a rule with `allow_chat_turns: true`
- To allow interrupts when the agent is running, your policy needs `allow_interrupts: true`
- Check your policy with `atlasbridge policy validate config/policy.yaml`

### "This prompt requires local input."

The agent is asking for sensitive input (password, token, API key). **This is by design** — sensitive values should never be sent over a messaging channel. Switch to the terminal where the agent is running and enter the value directly.

### "You are not authorized for this session."

Your channel user ID is not on the allowlist. The session operator must add your Telegram/Slack user ID to the session configuration.

### Messages seem delayed or lost

AtlasBridge does not queue messages. If your message was rejected, you received a rejection notice. If you didn't receive any response, check:

1. Is the Telegram/Slack bot running? Check `atlasbridge status`
2. Is the daemon running? Check `atlasbridge daemon status`
3. Is the session active? Check `atlasbridge session list`

---

## Design Principles

1. **Immediate evaluation** — every message gets a verdict within milliseconds
2. **No queueing** — messages are never stored for later delivery
3. **Default-safe** — unrecognized states default to REJECT
4. **No secrets in messages** — rejection messages never contain session IDs, prompt IDs, or config paths
5. **Phone-friendly** — all messages are short and readable on a phone screen
6. **Channel-agnostic** — same messages for Telegram and Slack
7. **Pure function** — the gate has no side effects, no state mutation, no network calls
