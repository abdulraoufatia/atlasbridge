# Channel Token Setup Guide

This guide walks you through obtaining the tokens required for AtlasBridge's notification channels.

You can also view a summary of these instructions inside the TUI setup wizard by pressing **H**.

---

## Telegram Bot Token

### Step-by-step

1. Open Telegram on your phone or desktop.
2. Search for **@BotFather** and start a chat.
3. Send the command: `/newbot`
4. Choose a **display name** for your bot (e.g. "AtlasBridge Relay").
5. Choose a **username** ending in `bot` (e.g. `atlasbridge_relay_bot`).
6. BotFather replies with your bot token.
   - Format: `123456789:ABCDefghIJKLMNopQRSTuvwxyz12345678901`
7. Copy the token and paste it into the AtlasBridge setup wizard or config file.

### Finding your Telegram user ID

1. Search for **@userinfobot** on Telegram and start a chat.
2. It replies with your numeric user ID (e.g. `123456789`).
3. Enter this ID in the "Allowlisted user IDs" step of the setup wizard.

### Security notes

- Your bot token grants full control of the bot. **Keep it secret.**
- AtlasBridge stores the token in your local config file only (`~/.config/atlasbridge/config.toml` on Linux, `~/Library/Application Support/atlasbridge/config.toml` on macOS).
- The token is never uploaded or transmitted to any service other than the Telegram Bot API.
- If you suspect your token has been compromised, revoke it via `/revoke` in BotFather and run `atlasbridge setup` again.

---

## Slack Bot Token

### Step-by-step

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps).
2. Click **Create New App** → **From scratch**.
3. Enter an app name (e.g. "AtlasBridge") and select your workspace.
4. Navigate to **OAuth & Permissions** in the sidebar.
5. Under **Bot Token Scopes**, add the following scopes:
   - `chat:write` — send messages
   - `users:read` — resolve user identities
6. Click **Install to Workspace** and authorize the app.
7. Copy the **Bot User OAuth Token** (starts with `xoxb-`).

### App-level token (for Socket Mode)

1. Go to **Basic Information** in your app settings.
2. Scroll to **App-Level Tokens** and click **Generate Token and Scopes**.
3. Name the token (e.g. "atlasbridge-socket") and add the scope: `connections:write`.
4. Click **Generate** and copy the token (starts with `xapp-`).

### Enable Socket Mode

1. Go to **Socket Mode** in the sidebar.
2. Toggle **Enable Socket Mode** to on.

### Finding your Slack member ID

1. Open Slack and click on your profile picture.
2. Click **Profile**.
3. Click the **···** (more) button.
4. Select **Copy member ID** (format: `U1234567890`).

### Security notes

- Your bot token and app-level token grant access to your Slack workspace. **Keep them secret.**
- AtlasBridge stores tokens locally only — they are never uploaded.
- The bot only needs the scopes listed above. Do not grant additional scopes.
- If you suspect a token has been compromised, regenerate it in the Slack App settings and run `atlasbridge setup` again.

---

## Using tokens with AtlasBridge

### Interactive setup (recommended)

```bash
atlasbridge          # launches TUI → press S for setup wizard
atlasbridge ui       # same as above
```

### CLI setup

```bash
atlasbridge setup --channel telegram
atlasbridge setup --channel slack
```

### Manual configuration

Edit your config file directly:

**Telegram:**
```toml
[telegram]
bot_token = "123456789:ABCDefgh..."
allowed_users = [123456789]
```

**Slack:**
```toml
[slack]
bot_token = "xoxb-..."
app_token = "xapp-..."
allowed_users = ["U1234567890"]
```

Config file location:
- macOS: `~/Library/Application Support/atlasbridge/config.toml`
- Linux: `~/.config/atlasbridge/config.toml`
- Override: set `ATLASBRIDGE_CONFIG` environment variable
