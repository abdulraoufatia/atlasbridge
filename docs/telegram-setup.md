# Telegram Setup Guide

This guide walks you through configuring Telegram as your AtlasBridge notification channel.

---

## Prerequisites

- A Telegram account
- Python 3.11+ with AtlasBridge installed (`pip install atlasbridge`)

---

## Step 1: Create a Bot with BotFather

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a display name (e.g., "AtlasBridge")
4. Choose a username (e.g., "my_atlasbridge_bot")
5. BotFather will give you a **bot token** like:
   ```
   7123456789:AAHfiqksKZ8WmR2zMnQJGQxKBqD8E1234xx
   ```
6. Save this token — you'll need it in Step 3.

---

## Step 2: Get Your Telegram User ID

You need your numeric Telegram user ID (not your username).

1. Search for **@userinfobot** on Telegram
2. Send it any message
3. It will reply with your user ID (a number like `123456789`)

---

## Step 3: Send /start to Your Bot

**This step is critical.** Telegram bots cannot message you until you initiate a conversation.

1. Search for your bot by its username in Telegram
2. Open the chat and tap **Start** (or send `/start`)
3. The bot should acknowledge — if it doesn't, that's fine, AtlasBridge will handle responses

Without this step, AtlasBridge will get "chat not found" errors when trying to send you prompts.

---

## Step 4: Run AtlasBridge Setup

```bash
atlasbridge setup --channel telegram
```

The wizard will ask for:
- **Bot token** — paste the token from Step 1
- **Allowed user ID(s)** — enter your user ID from Step 2

For non-interactive setup (CI/scripts):
```bash
export ATLASBRIDGE_TELEGRAM_BOT_TOKEN="7123456789:AAHfiqksKZ..."
export ATLASBRIDGE_TELEGRAM_ALLOWED_USERS="123456789"
atlasbridge setup --from-env
```

---

## Step 5: Verify

```bash
atlasbridge doctor
```

You should see:
```
  PASS  Config file: /path/to/config.toml
  PASS  Bot token: 7123456...1234
  PASS  Telegram poller lock: no lock file — poller is free
```

---

## Step 6: Start Supervising

```bash
atlasbridge run claude
```

When the CLI asks a question, it will appear in your Telegram chat with inline buttons.

---

## Troubleshooting

### "chat not found" (400 error)

**Cause:** You haven't sent `/start` to the bot yet.

**Fix:** Open Telegram, find your bot, send `/start`, then retry.

### "409 Conflict: terminated by other getUpdates request"

**Cause:** Two AtlasBridge processes are polling the same bot token.

**Fix:**
```bash
atlasbridge stop          # stop any running daemon
atlasbridge doctor        # check for stale locks
atlasbridge run claude    # restart
```

AtlasBridge uses a singleton poller lock to prevent this. If you see this error, another instance is already running.

### Prompts not arriving

1. Check that you sent `/start` to the bot
2. Check that your user ID is in the allowlist: `atlasbridge doctor`
3. Check logs: `atlasbridge logs --tail`

---

## Multiple Users

You can allow multiple users to receive and respond to prompts:

```bash
atlasbridge setup --channel telegram --users "123456789,987654321"
```

All listed user IDs will receive prompts. Any of them can respond.
