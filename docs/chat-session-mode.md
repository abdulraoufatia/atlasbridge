# Chat Session Mode

AtlasBridge v0.10.0 introduces a full conversational agent mode where users can interact with AI CLI agents naturally through Telegram or Slack.

## Session States

Each conversation binding tracks its state via the `ConversationState` enum:

```
IDLE ──► RUNNING ──► STREAMING ──► RUNNING (cycle)
              │           │              │
              ▼           ▼              ▼
         AWAITING_INPUT   │         AWAITING_INPUT
              │           │              │
              ▼           ▼              ▼
           STOPPED     STOPPED        STOPPED
```

| State | Description | User messages |
|-------|-------------|---------------|
| `IDLE` | Bound but session not yet started | Dropped |
| `RUNNING` | Agent active, accepting input | Routed to chat mode (injected into PTY) |
| `STREAMING` | Agent producing output | Queued for next turn |
| `AWAITING_INPUT` | Prompt detected, waiting on user | Resolved to active prompt |
| `STOPPED` | Session ended | Dropped |

## State-Driven Routing

When a user sends a message (not a button response), the router checks the conversation state:

1. **STREAMING** -- The message is queued in the binding's `queued_messages` list. The user sees "Queued for next turn." When the agent finishes streaming (2 idle flush cycles), the forwarder transitions to RUNNING and drains queued messages.

2. **RUNNING / IDLE** -- The message goes to the chat mode handler, which injects it into the agent's PTY stdin via `execute_chat_input()`.

3. **AWAITING_INPUT** -- If there's an active prompt, the message resolves to that prompt. Otherwise, falls through to chat mode.

## Message Queuing

During the STREAMING state, user messages are accumulated in `ConversationBinding.queued_messages`. When the `OutputForwarder` detects 2 consecutive idle flush cycles (no output from the agent), it:

1. Transitions the binding from STREAMING to RUNNING
2. Drains all queued messages
3. Delivers them to the channel as "(queued) {message}"

This prevents user messages from being lost when the agent is actively producing output.

## Conversation Registry

The `ConversationRegistry` maps `(channel_name, thread_id)` to `session_id`, enabling:

- **Deterministic routing**: Messages in a thread always reach the correct session
- **State tracking**: Each binding has its own `ConversationState`
- **TTL expiry**: Bindings expire after 4 hours of inactivity
- **Multi-channel**: A session can have bindings across Telegram and Slack simultaneously

## Validated Transitions

State transitions are validated against `VALID_CONVERSATION_TRANSITIONS`. Invalid transitions are rejected and logged. This prevents impossible state combinations (e.g., a STOPPED session transitioning to RUNNING).
