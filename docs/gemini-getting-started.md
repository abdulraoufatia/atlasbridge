# Getting Started with Gemini CLI

This guide walks you through using AtlasBridge to govern the **Google Gemini CLI** (`gemini` binary).

---

## Prerequisites

- Python 3.11+
- AtlasBridge installed: `pip install atlasbridge`
- Gemini CLI installed and on PATH (`gemini` binary)
- A Telegram or Slack channel configured — see [Channel Token Setup](channel-token-setup.md)

Verify both tools are installed:

```bash
atlasbridge version
gemini --version
```

---

## Step 1: Run the Setup Wizard

If this is your first time, run the interactive setup:

```bash
atlasbridge setup
```

See [Non-Interactive Setup](setup-noninteractive.md) for headless deployment.

---

## Step 2: Launch Gemini Under AtlasBridge

```bash
atlasbridge run gemini
```

This spawns the `gemini` binary inside a PTY supervisor with full terminal fidelity — colors, cursor control, and readline are preserved.

Pass arguments after the tool name:

```bash
atlasbridge run gemini -- --model gemini-2.5-pro
```

Add a session label:

```bash
atlasbridge run gemini --session-label "migrate-database"
```

---

## Step 3: Apply a Policy

Start with the minimal policy and customize for Gemini patterns:

```bash
atlasbridge run gemini --policy config/policies/minimal.yaml
```

### Gemini-specific policy example

```yaml
policy_version: "0"
name: "gemini-safe"
autonomy_mode: assist

rules:
  # Auto-confirm Press-Enter prompts
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
        allowed_choices: ["\n"]

  # Auto-approve Gemini execution prompts
  - id: "gemini-execute"
    description: "Auto-approve Gemini execute/apply prompts"
    match:
      tool_id: "gemini"
      prompt_type:
        - yes_no
      contains: "(?i)execute|apply|continue|proceed"
      contains_is_regex: true
      min_confidence: high
    action:
      type: auto_reply
      value: "y"
      constraints:
        allowed_choices: ["y", "n"]

  # Block credential prompts
  - id: "deny-credentials"
    description: "Never auto-reply to credential prompts"
    match:
      contains: "password|token|api.?key|secret"
      contains_is_regex: true
      min_confidence: low
    action:
      type: deny
      reason: "Credential prompts require manual input."

  # Escalate destructive operations
  - id: "destructive-human"
    description: "Escalate destructive operations to human"
    match:
      contains: "delete|destroy|drop|purge|rm -rf"
      contains_is_regex: true
      min_confidence: low
    action:
      type: require_human
      message: "Destructive operation detected. Please review."

  # Catch-all: route to human
  - id: "catch-all"
    description: "All other prompts require human input"
    match: {}
    action:
      type: require_human
      message: "Gemini prompt detected. Please review and respond."

defaults:
  no_match: require_human
  low_confidence: require_human
```

---

## Gemini CLI Prompt Patterns

The Gemini adapter extends the base detector with Gemini-specific patterns:

| Prompt type | Example | Confidence |
|------------|---------|------------|
| `yes_no` | "Do you want to continue? (y/n)" | HIGH |
| `yes_no` | "Allow Gemini to execute this? [Yes/No]" | HIGH |
| `yes_no` | "Execute this code? (yes/no)" | HIGH |
| `yes_no` | "Save the file? [y/n]" | HIGH |
| `multiple_choice` | "Select an option: 1) Generate code 2) Explain code" | HIGH |
| `multiple_choice` | "Choose a model: [1] gemini-2.5-pro [2] gemini-2.5-flash" | HIGH |
| `free_text` | "Enter your prompt:" | MED-HIGH |
| `free_text` | "What would you like Gemini to do?" | MED |
| `confirm_enter` | "Press Enter to continue" | HIGH |

### Gemini-specific quirks

- **Execution approval** — Gemini asks "Allow Gemini to execute this? [Yes/No]" before running code or commands. These are `yes_no` HIGH confidence.
- **Model selection** — When multiple models are available, Gemini presents a numbered menu. These are `multiple_choice` HIGH confidence.
- **Save prompts** — After generating output, Gemini may ask "Save the file? [y/n]". Use `tool_id: "gemini"` to scope auto-approve rules.
- **Parenthetical vs bracket format** — Gemini uses both `(y/n)` and `[Yes/No]` formats. The adapter handles both.

---

## Step 4: Monitor and Debug

```bash
# Check session status
atlasbridge status

# View recent autopilot decisions
atlasbridge autopilot explain --last 20

# Test policy rules
atlasbridge policy test policy.yaml \
  --prompt "Do you want to continue? (y/n)" \
  --type yes_no \
  --confidence high \
  --explain

# Run doctor
atlasbridge doctor --fix
```

---

## Troubleshooting

### "Adapter not found: gemini"

The adapter registers under the name `gemini`. Verify it is available:

```bash
atlasbridge adapters
```

Ensure the `gemini` binary is on your PATH:

```bash
which gemini
```

### Gemini prompts not detected

The Gemini adapter adds patterns on top of the base detector. If a prompt is not matching, the stall watchdog (silence-based detection) will catch it as a LOW confidence event after a timeout.

### Policy not matching Gemini-specific prompts

Use `tool_id: "gemini"` in your policy rules to scope them to Gemini sessions. Without `tool_id`, rules match all adapters.

---

## Next Steps

- [Policy Authoring Guide](policy-authoring.md) — write custom rules
- [Autonomy Modes](autonomy-modes.md) — understand Off / Assist / Full
- [Adapter Interface Spec](adapters.md) — how adapters work under the hood
- [Troubleshooting](troubleshooting.md) — common issues and solutions
