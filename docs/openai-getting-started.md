# Getting Started with OpenAI Codex CLI

This guide walks you through using AtlasBridge to govern the **OpenAI Codex CLI** (`codex` binary).

---

## Prerequisites

- Python 3.11+
- AtlasBridge installed: `pip install atlasbridge`
- OpenAI Codex CLI installed and on PATH (`codex` binary)
- A Telegram or Slack channel configured — see [Channel Token Setup](channel-token-setup.md)

Verify both tools are installed:

```bash
atlasbridge version
codex --version
```

---

## Step 1: Run the Setup Wizard

If this is your first time, run the interactive setup:

```bash
atlasbridge setup
```

See [Non-Interactive Setup](setup-noninteractive.md) for headless deployment.

---

## Step 2: Launch Codex Under AtlasBridge

```bash
atlasbridge run openai
```

The adapter name is `openai` (not `codex`). This spawns the `codex` binary inside a PTY supervisor with full terminal fidelity.

Pass arguments after the tool name:

```bash
atlasbridge run openai -- --model gpt-4o
```

Add a session label:

```bash
atlasbridge run openai --session-label "fix-api-routes"
```

---

## Step 3: Apply a Policy

Start with the minimal policy and customize for Codex patterns:

```bash
atlasbridge run openai --policy config/policies/minimal.yaml
```

### Codex-specific policy example

```yaml
policy_version: "0"
name: "codex-safe"
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

  # Auto-approve "Apply changes?" prompts from Codex
  - id: "codex-apply-changes"
    description: "Auto-approve Codex apply-changes prompts"
    match:
      tool_id: "openai"
      prompt_type:
        - yes_no
      contains: "Apply.*changes"
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

  # Catch-all: route to human
  - id: "catch-all"
    description: "All other prompts require human input"
    match: {}
    action:
      type: require_human
      message: "Codex prompt detected. Please review and respond."

defaults:
  no_match: require_human
  low_confidence: require_human
```

---

## Codex CLI Prompt Patterns

The OpenAI adapter extends the base detector with Codex-specific patterns:

| Prompt type | Example | Confidence |
|------------|---------|------------|
| `yes_no` | "Apply changes? [y/n]" | HIGH |
| `yes_no` | "Run command? [y/n]" | HIGH |
| `yes_no` | "Approve this action? (yes/no)" | HIGH |
| `yes_no` | "Allow Codex to ...? [y/n]" | HIGH |
| `multiple_choice` | "Select action: 1. Apply 2. Skip 3. Abort" | HIGH |
| `multiple_choice` | "Choose model: [1] gpt-4o [2] gpt-4-turbo" | HIGH |
| `free_text` | "Enter a description:" | MED-HIGH |
| `free_text` | "What do you want Codex to do?" | MED |
| `confirm_enter` | "Press Enter to continue" | HIGH |

### Codex-specific quirks

- **Approval gates** — Codex asks "Approve this action? (yes/no)" before executing file modifications or shell commands. These are `yes_no` HIGH confidence.
- **Model selection menus** — When multiple models are available, Codex presents a numbered menu. These are `multiple_choice` HIGH confidence.
- **Run command prompts** — Before executing shell commands, Codex asks "Run command? [y/n]". Use `tool_id: "openai"` to scope rules to Codex sessions only.

---

## Step 4: Monitor and Debug

```bash
# Check session status
atlasbridge status

# View recent autopilot decisions
atlasbridge autopilot explain --last 20

# Test policy rules
atlasbridge policy test policy.yaml \
  --prompt "Apply changes? [y/n]" \
  --type yes_no \
  --confidence high \
  --explain

# Run doctor
atlasbridge doctor --fix
```

---

## Troubleshooting

### "Adapter not found: openai"

The adapter registers under the name `openai`. Verify it is available:

```bash
atlasbridge adapters
```

Ensure the `codex` binary is on your PATH:

```bash
which codex
```

### Codex prompts not detected

The Codex adapter adds patterns on top of the base detector. If a prompt is not matching, check whether it matches the patterns listed above. You can also rely on the stall watchdog (silence-based detection) as a fallback.

### Policy not matching Codex-specific prompts

Use `tool_id: "openai"` in your policy rules to scope them to Codex sessions. Without `tool_id`, rules match all adapters.

---

## Next Steps

- [Policy Authoring Guide](policy-authoring.md) — write custom rules
- [Autonomy Modes](autonomy-modes.md) — understand Off / Assist / Full
- [Adapter Interface Spec](adapters.md) — how adapters work under the hood
- [Troubleshooting](troubleshooting.md) — common issues and solutions
