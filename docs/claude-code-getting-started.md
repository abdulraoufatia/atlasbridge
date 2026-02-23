# Getting Started with Claude Code

This guide walks you through using AtlasBridge to govern **Claude Code** (the `claude` CLI by Anthropic).

---

## Prerequisites

- Python 3.11+
- AtlasBridge installed: `pip install atlasbridge`
- Claude Code installed: [claude.ai/download](https://claude.ai/download) (requires `claude` binary on PATH)
- A Telegram or Slack channel configured — see [Channel Token Setup](channel-token-setup.md)

Verify both tools are installed:

```bash
atlasbridge version
claude --version
```

---

## Step 1: Run the Setup Wizard

If this is your first time, run the interactive setup:

```bash
atlasbridge setup
```

The wizard will:
1. Detect your platform (macOS / Linux)
2. Ask for your Telegram bot token and chat ID (or Slack credentials)
3. Validate connectivity
4. Write the config file

You can skip the wizard and configure manually — see [Non-Interactive Setup](setup-noninteractive.md).

---

## Step 2: Launch Claude Code Under AtlasBridge

```bash
atlasbridge run claude
```

This spawns `claude` inside a PTY supervisor. You see the same terminal output as running `claude` directly — colors, cursor control, everything is preserved. The difference: every interactive prompt is intercepted, classified, and routed through your policy.

You can pass arguments to Claude Code after the tool name:

```bash
atlasbridge run claude -- --model opus
atlasbridge run claude -- --dangerously-skip-permissions
```

Add a session label for easier identification:

```bash
atlasbridge run claude --session-label "refactor-auth"
```

---

## Step 3: Apply a Policy

Without a policy, all prompts are forwarded to your phone. To enable autonomous operation, apply a policy file:

```bash
atlasbridge run claude --policy config/policies/minimal.yaml
```

### Recommended starter policy

Start with `minimal.yaml` — it auto-confirms "Press Enter" prompts and routes everything else to you:

```yaml
policy_version: "0"
name: "minimal"
autonomy_mode: assist

rules:
  - id: "auto-enter"
    description: "Auto-confirm Press-Enter prompts"
    match:
      prompt_type:
        - confirm_enter
      min_confidence: medium
    action:
      type: auto_reply
      value: "\n"
      constraints:
        allowed_choices:
          - "\n"

  - id: "catch-all"
    description: "All other prompts require human input"
    match: {}
    action:
      type: require_human
      message: "AtlasBridge detected a prompt. Please review and respond."

defaults:
  no_match: require_human
  low_confidence: require_human
```

Once you're comfortable, graduate to `full-mode-safe.yaml` for broader automation with safety guards.

---

## Claude Code Prompt Patterns

Claude Code emits these prompt types during normal operation:

| Prompt type | Example | Confidence |
|------------|---------|------------|
| `yes_no` | "Do you want to proceed? (Y/n)" | HIGH |
| `confirm_enter` | "Press Enter to continue..." | HIGH |
| `multiple_choice` | "Select an option: 1) Apply 2) Skip" | HIGH |
| `free_text` | "Enter a commit message:" | MED-HIGH |

### Claude Code-specific quirks

- **ANSI color codes** — Claude Code uses heavy ANSI styling. AtlasBridge strips ANSI before pattern matching, so your policy `contains` patterns match clean text.
- **Partial-line prompts** — Prompt lines often arrive without a trailing newline. The detector handles this via rolling buffer analysis.
- **Tool-use approval dialogs** — Claude Code asks for permission before running tools (file writes, shell commands). These appear as `yes_no` prompts with HIGH confidence.
- **File diff confirmation** — After showing a diff, Claude Code often shows "Press Enter to continue". These are `confirm_enter` with HIGH confidence.

### Policy example: auto-approve tool use

```yaml
rules:
  - id: "claude-tool-approve"
    description: "Auto-approve Claude Code tool-use prompts"
    match:
      tool_id: "claude"
      prompt_type:
        - yes_no
      min_confidence: high
    action:
      type: auto_reply
      value: "y"
      constraints:
        allowed_choices: ["y", "n"]

  - id: "deny-credentials"
    description: "Never auto-reply to credential prompts"
    match:
      contains: "password|token|api.?key|secret"
      contains_is_regex: true
      min_confidence: low
    action:
      type: deny
      reason: "Credential prompts require manual input."
```

---

## Step 4: Monitor and Debug

### Check session status

```bash
atlasbridge status
atlasbridge sessions list
```

### View recent decisions

```bash
atlasbridge autopilot explain --last 20
```

### Test your policy before deploying

```bash
atlasbridge policy validate policy.yaml
atlasbridge policy test policy.yaml \
  --prompt "Do you want to proceed? [Y/n]" \
  --type yes_no \
  --confidence high \
  --explain
```

### Run the environment doctor

```bash
atlasbridge doctor --fix
```

### Open the local dashboard

```bash
atlasbridge dashboard start
# Opens http://127.0.0.1:8111 in your browser
```

---

## Troubleshooting

### "Adapter not found: claude"

Ensure the `claude` binary is on your PATH:

```bash
which claude
```

If Claude Code is installed but not on PATH, specify the full path:

```bash
atlasbridge run claude -- /path/to/claude
```

### Prompts not being detected

Run `atlasbridge doctor --fix` to check PTY and adapter health. If prompts are still missed, the stall watchdog (silence-based detection) will catch them with LOW confidence after a timeout.

### High latency on prompt detection

Claude Code's ANSI output is stripped before pattern matching. If you see delays, check that your policy doesn't use overly complex regex patterns (there's a 100ms regex timeout safety net).

### Telegram bot not receiving prompts

See [Telegram Setup](telegram-setup.md) — the most common issue is forgetting to send `/start` to your bot.

---

## Next Steps

- [Policy Authoring Guide](policy-authoring.md) — write custom rules
- [Autonomy Modes](autonomy-modes.md) — understand Off / Assist / Full
- [Full-Mode Safe Policy](../config/policies/full-mode-safe.yaml) — graduated autopilot
- [Autopilot Engine](autopilot.md) — decision trace, kill switch, pause/resume
