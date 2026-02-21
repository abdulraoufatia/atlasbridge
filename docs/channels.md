# AtlasBridge Channel Interface Specification

**Version:** 0.3.0
**Status:** Authoritative Design
**Last updated:** 2026-02-21

---

## 1. Purpose

The channel layer is the outbound half of AtlasBridge. Once the adapter layer has detected a prompt and the supervisor has created a `PromptEvent`, the channel is responsible for delivering that prompt to a human over whatever messaging platform they use, receiving their reply, and handing it back to the supervisor as a `Reply` object.

### The Channel Abstraction

Different messaging platforms have radically different APIs: Telegram uses long polling; Slack uses Socket Mode or webhooks; WhatsApp uses the Twilio Business API; a web UI uses WebSockets. Without an abstraction, adding a new platform would require modifying the supervisor, the database layer, and the routing logic.

`BaseChannel` removes this coupling entirely. The supervisor knows only that it holds a `BaseChannel` instance. It calls `send_prompt`, waits for `receive_replies`, and calls `notify`. The channel implementation handles everything platform-specific: API credentials, message formatting, rate limits, retry logic, inline keyboards, button callbacks, and connection lifecycle.

### Why This Matters for Extensibility

The current production channel is Telegram. The Slack channel is planned for Phase 4. WhatsApp and a web UI are on the future roadmap. Because all three must implement `BaseChannel`, the supervisor codebase requires zero changes when a new channel ships. The routing layer (`atlasbridge/core/routing/`) simply holds a list of active channel instances and forwards prompts to all of them (or to a configured primary).

The abstraction also enables multi-channel deployments: a user who wants both Telegram and Slack notifications can configure both channels; the first reply from either platform wins.

---

## 2. BaseChannel Interface

```python
# src/atlasbridge/channels/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from atlasbridge.adapters.base import PromptEvent, Reply


class BaseChannel(ABC):
    """
    Abstract base for all AtlasBridge notification and reply channels.

    A channel is responsible for:
      1. Establishing and maintaining a connection to the messaging platform.
      2. Formatting and sending a PromptEvent as a user-visible message.
      3. Sending plain informational notifications (session start/end, errors).
      4. Receiving and yielding Reply objects as the user responds.
      5. Gracefully closing the connection on session end.
      6. Reporting its own health (connected, authenticated, not rate-limited).

    Channels must NOT:
      - Validate or modify the Reply value. That is the supervisor's responsibility.
      - Write to the database or audit log. The supervisor owns persistence.
      - Block the event loop. All network I/O must be async.
      - Inject replies directly into the PTY. That is the adapter's responsibility.
    """

    @abstractmethod
    async def start(self) -> None:
        """
        Start the channel: establish connection, authenticate, begin polling or listening.

        For long-polling channels (Telegram), this starts a background asyncio task
        that polls the platform API and places replies onto an internal queue.

        For webhook/event-driven channels (Slack Socket Mode), this opens the WebSocket
        connection and registers event handlers.

        This method must return promptly. The actual connection work happens in the
        background task. The caller can await healthcheck() to confirm the channel
        is ready.

        Raises
        ------
        ChannelStartError
            If credentials are invalid or the platform API is unreachable.
        """

    @abstractmethod
    async def send_prompt(self, event: PromptEvent) -> str:
        """
        Send a prompt to the user. Returns a platform-specific message_id for tracking.

        The channel must:
          - Format the prompt according to the platform's message format (see platform
            sections for format specs).
          - Include: the prompt excerpt, the prompt type label, the session identifier,
            the TTL countdown, and one-tap reply options.
          - Store the mapping from prompt_id to message_id so that the message can
            be edited later (e.g., to show "expired" or "answered").

        Parameters
        ----------
        event:
            The PromptEvent produced by the adapter. The channel must use
            event.prompt_id and event.session_id to construct reply callback data.
            The channel must use event.choices for TYPE_MULTIPLE_CHOICE keyboards.
            The channel must use event.constraints["max_length"] for free-text guidance.

        Returns
        -------
        str
            A platform-specific message identifier (e.g., Telegram message_id as string,
            Slack message ts). Used by the supervisor to edit the message on expiry or
            receipt of a reply.

        Raises
        ------
        ChannelSendError
            If the platform API rejects the send (non-transient error).
        """

    @abstractmethod
    async def notify(self, session_id: str, message: str) -> None:
        """
        Send a plain informational notification. No reply is expected.

        Used for:
          - Session started / session ended announcements.
          - Timeout notices (prompt expired, safe default injected).
          - Error conditions (PTY crashed, config invalid).
          - Rate limit warnings.

        Parameters
        ----------
        session_id:
            The session this notification belongs to. Included in the message
            for multi-session disambiguation.
        message:
            Pre-formatted human-readable text. The channel may apply platform-specific
            escaping (e.g., Telegram MarkdownV2 escaping) before sending.
        """

    @abstractmethod
    async def receive_replies(self) -> AsyncIterator[Reply]:
        """
        Yield Reply objects as the user responds to prompts on this channel.

        For long-polling channels, this yields from an internal asyncio.Queue
        that is populated by the background polling task.

        For event-driven channels, this yields from a queue populated by
        incoming WebSocket events.

        Each yielded Reply must have already passed channel-level validation:
          - The user is in the allowed_users whitelist for this channel.
          - The callback data or message text is syntactically valid.
          - The nonce is present and correctly formatted (32 hex chars).

        The supervisor is responsible for semantic validation (checking nonce
        against the DB, expiry, session binding).

        Yields
        ------
        Reply
            A fully populated Reply object ready for the supervisor to process.
        """

    @abstractmethod
    async def close(self) -> None:
        """
        Gracefully close the channel connection.

        Must:
          - Cancel and await background polling/listening tasks.
          - Close HTTP clients or WebSocket connections.
          - Flush any pending outbound messages (best-effort, max 2s).
          - Not raise exceptions; log and swallow errors during shutdown.
        """

    @abstractmethod
    async def healthcheck(self) -> bool:
        """
        Return True if the channel is connected, authenticated, and healthy.

        Used by:
          - `atlasbridge doctor` — reports channel health in the diagnostic output.
          - The supervisor's startup sequence — waits for healthcheck() == True
            before beginning PTY supervision (with a 10s timeout).
          - The stall watchdog — if the channel is unhealthy during a pending prompt,
            the watchdog extends the TTL rather than injecting the safe default.

        Returns
        -------
        bool
            True if the channel can currently send and receive messages.
        """
```

---

## 3. Telegram Channel

### 3.1 Status

**Implementation status:** Production. Fully implemented in `atlasbridge/channels/telegram/`.

Source files:
- `atlasbridge/channels/telegram/bot.py` — `TelegramBot(BaseChannel)`, long-poll loop, callback dispatch
- `atlasbridge/channels/telegram/templates.py` — message formatters, keyboard builders, callback parser

### 3.2 Long Polling Architecture

Telegram does not push events to bots; bots must poll `getUpdates`. AtlasBridge uses long polling: each `getUpdates` call includes a `timeout=30` parameter, causing the Telegram API server to hold the connection open for up to 30 seconds and return as soon as an update arrives.

```
TelegramBot.start()
    └─► asyncio.create_task(_poll_loop())

_poll_loop():
    while running:
        updates = await _get_updates(offset=N, timeout=30)   # blocks up to 30s
        for update in updates:
            offset = max(offset, update["update_id"] + 1)
            await _dispatch(update)   # routes to _handle_callback or _handle_message
        # loop immediately: next long-poll begins
```

The `offset` parameter tells Telegram to discard all updates with `update_id < offset`, preventing re-delivery. This is Telegram's built-in deduplication for the polling protocol.

**Error handling in the poll loop:**
- `httpx.TimeoutException`: This is the normal end-of-long-poll cycle when no updates arrived. The loop simply continues with the next poll.
- Network errors (DNS failure, connection refused, TLS error): Log a warning, wait 5 seconds with `asyncio.sleep(5)`, then retry. This prevents a fast-crash loop during connectivity loss.
- Telegram API error (`ok: false`): Log an error, wait 5 seconds, retry. This handles temporary Telegram outages.
- `asyncio.CancelledError`: Break the loop cleanly. This is the normal shutdown path.

### 3.3 Inline Keyboard Format

Telegram's inline keyboards are arrays of button rows. Each button has a `text` label and a `callback_data` string. When the user taps a button, Telegram sends a `callback_query` update containing the `callback_data`.

Format per prompt type:

**TYPE_YES_NO:**
```
Row 1: [✅  Yes]  [❌  No]
Row 2: [⏩  Use default (n)]
```

**TYPE_CONFIRM_ENTER:**
```
Row 1: [↩️  Press Enter]
Row 2: [⏩  Use default (↩)]
```

**TYPE_MULTIPLE_CHOICE** (example with 3 options):
```
Row 1: [1. Install]
Row 2: [2. Skip]
Row 3: [3. Abort]
Row 4: [⏩  Use default (1)]
```

Each choice is on its own row to prevent accidental taps. Choice labels are truncated to 30 characters with `…` if needed.

**TYPE_FREE_TEXT:**
```
Row 1: [⏩  Use default (empty)]
```

Free text is provided by the user replying to the Telegram message (not via a button), so the keyboard only offers the default option. The message text instructs: "Reply to this message with your text response."

**TYPE_UNKNOWN:**
```
Row 1: [✅  Yes / Enter]  [❌  No / Skip]
Row 2: [⏩  Use default]
```

### 3.4 Callback Data Encoding

Telegram's `callback_data` field has a hard limit of 64 bytes (64 ASCII characters). The AtlasBridge callback format must fit within this limit.

**Format:**

```
ans:{prompt_id}:{session_id}:{nonce}:{value}
```

**Field sizes:**
- Prefix `ans:` — 4 bytes
- `prompt_id` (UUID v4 without hyphens) — 32 bytes
- `:` — 1 byte
- `session_id` (UUID v4 without hyphens) — 32 bytes
- `:` — 1 byte
- `nonce` (`secrets.token_hex(16)`) — 32 bytes
- `:` — 1 byte
- `value` — variable

Total fixed overhead: 4 + 32 + 1 + 32 + 1 + 32 + 1 = 103 bytes. This exceeds Telegram's 64-byte limit.

**Truncation strategy:**

To stay within the 64-byte limit while preserving security, AtlasBridge uses abbreviated identifiers in the callback data and resolves them via the database:

```
ans:{short_prompt_id}:{nonce_prefix}:{value}
```

Where:
- `short_prompt_id` = first 8 hex characters of the UUID (`prompt_id[:8]`) — 8 bytes
- `nonce_prefix` = first 16 hex characters of the nonce — 16 bytes

This yields: `ans:` (4) + 8 + `:` (1) + 16 + `:` (1) + value (up to 34) = 64 bytes maximum.

The database lookup uses `short_prompt_id` to find the full prompt record and validates the `nonce_prefix` against the stored nonce's first 16 characters. Because the nonce is a 128-bit random value, a 64-bit prefix (16 hex chars) provides sufficient uniqueness (collision probability: 1 in 2^64 per session).

For the current implementation, `session_id` is omitted from callback data and is retrieved from the database via the `prompt_id` lookup.

**Parsing:**

```python
def parse_callback_data(data: str) -> tuple[str, str, str] | None:
    """
    Parse ``ans:<prompt_id>:<nonce>:<value>`` callback data.
    Returns ``(prompt_id, nonce, value)`` or ``None`` if malformed.
    """
    parts = data.split(":", 3)
    if len(parts) != 4 or parts[0] != "ans":
        return None
    _, prompt_id, nonce, value = parts
    if not prompt_id or not nonce or not value:
        return None
    return prompt_id, nonce, value
```

### 3.5 Rate Limiting

Telegram enforces a rate limit of approximately 30 messages per second per bot globally, and 1 message per second per chat. Exceeding this limit causes `429 Too Many Requests` responses with a `retry_after` field.

**AtlasBridge rate limit strategy:**

1. **Per-chat bucket:** The bot tracks the last send time per chat ID. If a send would exceed 1 message/second for that chat, it waits `max(0, 1.0 - elapsed)` seconds before sending. This is enforced in `_send_message_to`.

2. **Global bucket:** A semaphore limits global concurrent Telegram API calls to 10. This is a conservative limit that keeps the bot well within Telegram's 30/s global cap even if multiple sessions are running simultaneously.

3. **Retry on 429:** If Telegram returns `429 Too Many Requests`, the bot reads the `retry_after` field and sleeps for that duration before retrying. The send is then retried up to `DEFAULT_TELEGRAM_MAX_RETRIES` (5) times.

### 3.6 Retry and Backoff Strategy

All Telegram API calls use the following retry policy:

```
Attempt 1: immediate
Attempt 2: wait 1s
Attempt 3: wait 2s
Attempt 4: wait 4s
Attempt 5: wait 8s
After attempt 5: log error, mark send as failed, continue
```

Exponential backoff with a base of 2 and a cap of 30 seconds. For `send_prompt`, a failed send after all retries causes the prompt to remain in `telegram_sent` status but with `telegram_msg_id = None`. The prompt will still time out and inject the safe default; the user just won't receive the message.

For `notify` (informational messages), failure is logged but not retried (notifications are best-effort).

### 3.7 Bot Commands

The Telegram bot responds to the following slash commands from allowed users:

| Command | Description |
|---|---|
| `/sessions` | List all active AtlasBridge sessions with their status and uptime |
| `/switch <session_id>` | Set the primary session for subsequent replies (multi-session disambiguation) |
| `/status` | Show the current session's supervisor state, pending prompt count, and last activity time |
| `/cancel <prompt_id>` | Cancel a pending prompt by injecting the safe default immediately |
| `/help` | Display the list of available commands |

**Multi-session handling:**

When multiple `atlasbridge run` instances are active simultaneously (e.g., Claude and another CLI tool), prompts from all sessions arrive in the same Telegram chat. Each prompt message includes a session identifier in its header so the user can distinguish them:

```
🤖 Claude Code is waiting for your input
Session: abc12345 · Yes / No question

```Do you want to overwrite /src/main.py?```
```

The `/switch` command sets a session preference; subsequent free-text replies (for `TYPE_FREE_TEXT`) are routed to the switched session rather than requiring the user to reply-to a specific message.

### 3.8 Message Formatting (MarkdownV2 Templates)

All Telegram messages use Markdown parse mode. The header template for each prompt type:

```
🤖 *{tool}* is waiting for your input
_{type_label}_

```
{excerpt}
```

⏳ Expires in *{ttl}* — default: *{safe_default}*
```

Where `ttl` is formatted as `Xm Ys` (e.g., `9m 58s`) or `Xs` if under a minute.

Session started notification:
```
▶️ *AtlasBridge session started*

Tool: `{tool}`
CWD: `{cwd}`
Session: `{session_id[:8]}`
```

Session ended notification:
```
⏹ *AtlasBridge session ended*

Tool: `{tool}`
Session: `{session_id[:8]}`
Status: ✅ exited 0
```

Timeout notice (replaces or follows the original prompt message):
```
⏰ *{tool}* prompt timed out

```
{excerpt}
```

Auto-injected: *{injected!r}*
```

### 3.9 Sequence Diagram: User Sends Reply

The following is the complete flow from a user tapping a button in Telegram to the reply being queued for injection.

```
User (Telegram)       Telegram API       TelegramBot (AtlasBridge)         Database          Supervisor
      │                    │                    │                       │                  │
      │── tap button ──────►│                   │                       │                  │
      │                    │── callback_query ──►│                       │                  │
      │                    │                    │                       │                  │
      │                    │                    ├── parse_callback_data()                  │
      │                    │                    │   (prompt_id, nonce, value)              │
      │                    │                    │                       │                  │
      │                    │                    ├── is_allowed(user_id)?│                  │
      │                    │                    │   YES                 │                  │
      │                    │                    │                       │                  │
      │                    │                    ├── get_prompt(prompt_id) ──────────────────
      │                    │                    │   ◄── PromptRecord ───│                  │
      │                    │                    │                       │                  │
      │                    │                    ├── is_expired? NO      │                  │
      │                    │                    │                       │                  │
      │                    │                    ├── normalize_value(raw_value, prompt)      │
      │                    │                    │                       │                  │
      │                    │                    ├─────── decide_prompt(prompt_id, nonce, normalized) ──►
      │                    │                    │                       │   atomic UPDATE   │
      │                    │                    │   ◄── rows_affected=1 │                  │
      │                    │                    │                       │                  │
      │                    │                    ├── answerCallbackQuery("✅ Recorded")      │
      │                    │◄── answer ─────────│                       │                  │
      │◄── notification ───│                    │                       │                  │
      │                    │                    │                       │                  │
      │                    │                    ├── editMessageText (show "Response recorded")
      │                    │◄── edit ───────────│                       │                  │
      │◄── message updated─│                    │                       │                  │
      │                    │                    │                       │                  │
      │                    │                    ├── response_queue.put((prompt_id, normalized))
      │                    │                    │                       │                  │
      │                    │                    │                       │── response_consumer reads
      │                    │                    │                       │   ► inject_reply(...)
      │                    │                    │                       │                  │
```

If `decide_prompt` returns `rows_affected = 0` (nonce mismatch, already answered, or expired), the bot answers the callback with "Already answered or expired" and edits the message to reflect the current state. No reply is placed on the queue.

---

## 4. Slack Channel

### 4.1 Status

**Implementation status:** Planned, Phase 4. The `src/atlasbridge/channels/slack/` package contains only an `__init__.py` placeholder.

### 4.2 Architecture Choices

**Socket Mode vs. Event API:**

AtlasBridge will use Slack's **Socket Mode** rather than the Event API. The rationale:
- Socket Mode does not require a publicly accessible inbound URL. AtlasBridge runs on a developer's local machine; exposing an inbound webhook endpoint would require a tunnel (ngrok) or a server.
- Socket Mode uses an outbound WebSocket connection, consistent with AtlasBridge's design principle of not requiring inbound ports.
- The latency is comparable to long polling.

**Slash commands vs. Interactive Components:**

Both will be supported:
- `/atlasbridge sessions` — list active sessions (slash command)
- `/atlasbridge cancel <id>` — cancel a pending prompt (slash command)
- Inline `Approve` / `Deny` buttons for each prompt message (interactive components, handled via Socket Mode)

### 4.3 Block Kit Layout

Each prompt message uses Slack's Block Kit. The layout for a `TYPE_YES_NO` prompt:

```json
{
  "blocks": [
    {
      "type": "header",
      "text": { "type": "plain_text", "text": "Claude Code is waiting" }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Yes / No* · Session `abc12345` · Expires in *9m 58s*\n```Do you want to overwrite /src/main.py? (y/n)```"
      }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": { "type": "plain_text", "text": "Yes" },
          "style": "primary",
          "action_id": "atlasbridge_reply",
          "value": "ans:{prompt_id}:{nonce}:y"
        },
        {
          "type": "button",
          "text": { "type": "plain_text", "text": "No" },
          "style": "danger",
          "action_id": "atlasbridge_reply",
          "value": "ans:{prompt_id}:{nonce}:n"
        },
        {
          "type": "button",
          "text": { "type": "plain_text", "text": "Use default (n)" },
          "action_id": "atlasbridge_reply",
          "value": "ans:{prompt_id}:{nonce}:default"
        }
      ]
    }
  ]
}
```

Slack's `value` field on buttons has a limit of 2000 characters, which is far more generous than Telegram's 64-byte limit. The full `prompt_id` (UUID v4) and `nonce` (32 hex chars) can be included without truncation.

### 4.4 Required OAuth Scopes

The Slack app requires the following OAuth scopes:

| Scope | Purpose |
|---|---|
| `chat:write` | Post messages to channels |
| `chat:write.public` | Post to channels the bot is not a member of |
| `commands` | Register slash commands |
| `connections:write` | Use Socket Mode WebSocket connections |
| `im:write` | Send direct messages to users |
| `users:read` | Resolve user IDs to verify allowed_users |

The bot token (`xoxb-...`) is stored in `~/.atlasbridge/config.toml` under `[slack]` alongside the app-level token (`xapp-...`) required for Socket Mode.

### 4.5 Implementation Status

Planned for Phase 4. The `SlackChannel` class will implement `BaseChannel` identically to `TelegramBot`. The supervisor, routing layer, and persistence layer require no changes. The Phase 4 milestone includes:

- `SlackChannel` implementation with Socket Mode
- Block Kit templates for all five prompt types
- Slash command handler for `/atlasbridge`
- Integration tests against Slack's Bolt test client
- Documentation update in this file

---

## 5. WhatsApp and Web UI

### 5.1 WhatsApp

**Status:** Future (no phase assigned).

WhatsApp Business API (via Twilio or Meta's Cloud API) supports template messages and interactive reply buttons. The interactive button limit is 3 buttons per message, which accommodates `TYPE_YES_NO` (Yes / No / Default) but requires adaptation for `TYPE_MULTIPLE_CHOICE` with more than 2 options (would fall back to numbered text replies).

Free-text input via WhatsApp works natively (user types a message; the webhook receives it). The `TYPE_FREE_TEXT` flow maps cleanly.

Key implementation challenges:
- WhatsApp requires pre-approved message templates for outbound business-initiated messages. The prompt template would need to be submitted to Meta for approval.
- Phone number binding: the `channel_identity` format would be `whatsapp:+15551234567`.
- Webhook endpoint required: unlike Telegram or Slack Socket Mode, WhatsApp requires an inbound HTTPS webhook. A hosted deployment model or a proxy service would be needed.

### 5.2 Web UI

**Status:** Future (no phase assigned).

A browser-based UI would allow users to respond to prompts from a desktop browser, with no third-party messaging platform dependency. The architecture:

- AtlasBridge starts a local HTTP server (e.g., on `localhost:7777`) when `web_ui_enabled = true` in config.
- The UI is a single-page application that polls `/api/pending` or connects via WebSocket.
- Prompts appear as cards with one-tap response buttons.
- Authentication is token-based (a secret URL segment, not a login form).
- The `BaseChannel` implementation sends prompts to the local HTTP server's in-memory queue; the browser polls this queue via the WebSocket.
- `channel_identity` format: `web:localhost`.

The web UI is particularly useful in environments where Telegram is blocked (corporate networks) or where the user wants to see a rich diff view of the prompt alongside other context.

---

## 6. Channel UX Requirements

All channels must satisfy the following cross-channel consistency requirements to ensure a coherent user experience regardless of which messaging platform the user chooses.

### 6.1 Required Information in Every Prompt Message

Every prompt message sent by any channel must include:

1. **Prompt excerpt** — the ANSI-stripped, truncated text of the prompt as it appeared in the terminal. Maximum 200 characters. If truncated, the truncation must be visually indicated (`…`).

2. **Session identifier** — the first 8 characters of the `session_id` UUID (the "short session ID"). For users with multiple active sessions, this disambiguates which session the prompt belongs to.

3. **TTL countdown** — the time remaining until the prompt expires and the safe default is injected. Must be expressed in human-readable form (`9m 58s`, not a raw epoch timestamp). Must be accurate to within 5 seconds at the time of message delivery.

4. **Safe default indication** — the value that will be injected if no reply is received before expiry. Must be clearly labelled: "default: n", "default: ↩", "default: 1", "default: (empty)". The user must be able to see the consequence of ignoring the message.

### 6.2 Required Reply Mechanism

Every channel must support one-tap (or one-click) replies for the following prompt types:

| Prompt type | Required reply options |
|---|---|
| `TYPE_YES_NO` | Yes · No · Use default |
| `TYPE_CONFIRM_ENTER` | Press Enter · Use default |
| `TYPE_MULTIPLE_CHOICE` | One button per choice (up to 9) · Use default |
| `TYPE_FREE_TEXT` | Use default (empty); typing a reply to the message sends free text |
| `TYPE_UNKNOWN` | Yes/Enter · No/Skip · Use default |

"One-tap" means the user can respond without typing. For `TYPE_FREE_TEXT`, a "Use default" button must always be present so the user can respond without typing if they want to proceed with the empty default.

### 6.3 Expired Prompt Handling

When a prompt expires (TTL reaches zero) and the safe default is injected, the channel must:

1. **Edit the original message** (if the platform supports message editing: Telegram, Slack) to replace the inline keyboard with an expiry notice: "Prompt expired — injected: n".
2. **Send a separate notification** if the platform does not support editing, or if the original `message_id` was not recorded (e.g., due to a send failure).
3. **Never accept a reply** to an expired prompt. The `decide_prompt` database guard handles this at the server side, but the channel should also visually indicate expiry to prevent user confusion.

The expiry state must be distinguishable from the "already answered" state. If a user taps a button on an already-answered prompt, the message should show "Already answered" (with the recorded value), not "Expired".

### 6.4 Multiple Active Sessions

When multiple sessions are active simultaneously, the channel must display them without confusion:

- Each prompt message includes the session short ID, the tool name, and the working directory.
- `/sessions` (or equivalent) lists all active sessions with their short IDs.
- Free-text replies (for `TYPE_FREE_TEXT`) must be associated with a specific session. The channel must use the `reply_to_message` mechanism (Telegram) or the session-aware message routing (Slack) to determine which session a free-text reply belongs to. A free-text message that cannot be attributed to a specific pending prompt must be silently ignored.
- If prompts from multiple sessions arrive nearly simultaneously, each must be sent as a separate message; they must not be batched into a single message.

### 6.5 Security Requirements

- Every inbound reply must be validated against an `allowed_users` list before being processed. Replies from unauthorized users must be silently rejected with a logged warning.
- Callback data must include a nonce that is validated before any database write or queue enqueue.
- Free-text input must be length-capped to `constraints["max_length"]` (default 200 characters) before being placed on the reply queue.
- The channel must not log the full `raw_bytes` of a `PromptEvent` (may contain secrets). Only the sanitised `excerpt` is included in channel-level logs.

---

## 7. Adding a New Channel

### Step 1: Create the channel package

```
src/atlasbridge/channels/<channel_name>/
    __init__.py
    channel.py       # BaseChannel subclass
    templates.py     # message formatters (optional, recommended)
```

### Step 2: Subclass BaseChannel

```python
# src/atlasbridge/channels/mychanne/channel.py
from atlasbridge.channels.base import BaseChannel
from atlasbridge.adapters.base import PromptEvent, Reply
from typing import AsyncIterator


class MyChannelChannel(BaseChannel):
    """
    <MyChannel> channel for AtlasBridge.

    Uses <protocol> for outbound messages and <mechanism> for receiving replies.
    """

    def __init__(
        self,
        api_token: str,
        allowed_users: list[str],
        # ... channel-specific config
    ) -> None:
        self._token = api_token
        self._allowed_users = set(allowed_users)
        self._reply_queue: asyncio.Queue[Reply] = asyncio.Queue()
        self._running = False
```

### Step 3: Implement all abstract methods

Refer to Section 2 for the full docstrings. Pay particular attention to:

- `receive_replies`: must be an async generator that yields from an internal `asyncio.Queue`. The queue is populated by the background connection task. Do not poll the platform API inside `receive_replies`; that belongs in the background task.
- `send_prompt`: must store the `prompt_id → message_id` mapping so that messages can be edited later. Use a `dict[str, str]` keyed on `prompt_id`.
- `healthcheck`: must return `False` if the background connection task is not running, even if authentication credentials are valid.

### Step 4: Add configuration support

Add a `[<channel_name>]` section to the `AtlasBridgeConfig` Pydantic model in `atlasbridge/core/config.py`:

```python
class MyChannelConfig(BaseModel):
    enabled: bool = False
    api_token: str = ""
    allowed_users: list[str] = []
```

Add the config section to the TOML template generated by `atlasbridge setup`.

### Step 5: Register the channel

Add the channel to the channel factory in `atlasbridge/core/routing/`:

```python
def build_channels(config: AtlasBridgeConfig) -> list[BaseChannel]:
    channels = []
    if config.telegram.bot_token:
        channels.append(TelegramBot(...))
    if config.mychannel.enabled and config.mychannel.api_token:
        channels.append(MyChannelChannel(...))
    return channels
```

### Step 6: Write tests

Create `tests/unit/channels/test_<channel_name>_channel.py`. Required test coverage:

- `test_send_prompt_<type>` — one test per `PromptType`. Assert the platform API is called with correctly formatted message content.
- `test_receive_reply_button` — simulate an inbound callback/event; assert a `Reply` is yielded.
- `test_receive_reply_rejected_unauthorized` — simulate a reply from a non-allowed user; assert nothing is yielded and a warning is logged.
- `test_expired_prompt_edit` — simulate an expiry notification; assert the original message is edited.
- `test_healthcheck_not_started` — assert `healthcheck()` returns `False` before `start()` is called.
- `test_healthcheck_connected` — assert `healthcheck()` returns `True` after `start()` succeeds.
- `test_close_cancels_background_task` — assert `close()` cancels the polling/listening task without raising.

### Step 7: Update this document

Add a section (following the pattern of Section 3 and Section 4) that describes:
- The platform's message format and limitations.
- The inline keyboard or equivalent reply mechanism.
- The reply callback format (equivalent of Telegram's `ans:{prompt_id}:{nonce}:{value}`).
- Rate limits and backoff strategy.
- Any bot commands supported.
- OAuth scopes or API permissions required.
- Implementation status.

Submit the documentation update in the same pull request as the implementation.
