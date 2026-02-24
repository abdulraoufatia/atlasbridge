# AtlasBridge Policy Authoring Guide

**Version:** DSL v0 (AtlasBridge v0.6.0+)
**Status:** Implemented
**Last updated:** 2026-02-21

---

## Table of Contents

1. [Overview](#1-overview)
2. [Quick Start (5 Minutes)](#2-quick-start-5-minutes)
3. [Core Concepts](#3-core-concepts)
4. [Policy Syntax Reference](#4-policy-syntax-reference)
5. [Working With Policies (CLI)](#5-working-with-policies-cli)
6. [Writing Good Policies (Patterns)](#6-writing-good-policies-patterns)
7. [Profile-Aware Rules](#7-profile-aware-rules)
8. [Debugging Policies](#8-debugging-policies)
9. [FAQ](#9-faq)
10. [Safety Notes](#10-safety-notes)
11. [Next Steps](#11-next-steps)

---

## 1. Overview

The AtlasBridge Policy DSL lets you define rules that govern how the autopilot engine responds to prompts detected from your AI coding agent. Instead of forwarding every prompt to your phone, you can write a YAML file that says: "auto-approve this class of prompt, escalate that class to me, and deny these ones outright."

**What the policy controls:**

- Which prompts get auto-replied (and with what value)
- Which prompts always go to your phone
- Which prompts are blocked and held for manual intervention
- Which prompts generate a silent notification without blocking

**What the policy does NOT control:**

- Whether AtlasBridge is running (that is the daemon)
- Channel routing (Telegram vs. Slack — that is the config)
- Session TTLs (that is the config)
- Authentication (that is the channel's allowlist)

**Three autonomy modes:**

| Mode | Auto-reply | Human escalation | Deny |
|------|-----------|-----------------|------|
| `off` | Never | Every prompt | Never |
| `assist` | Never (routes suggestion to phone for confirmation) | Every prompt, plus suggestions | Never |
| `full` | When rules match | When no rule matches or rule says `require_human` | When rules say `deny` |

Start with `off` or `assist`. Graduate to `full` only after validating against real sessions.

---

## 2. Quick Start (5 Minutes)

### Step 1 — Create your first policy file

```yaml
# ~/.atlasbridge/policy.yaml
policy_version: "0"
name: "my-first-policy"
autonomy_mode: assist

rules:
  - id: "auto-enter"
    description: "Auto-press Enter on 'Press Enter to continue' prompts"
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

defaults:
  no_match: require_human
  low_confidence: require_human
```

### Step 2 — Validate it

```bash
atlasbridge policy validate ~/.atlasbridge/policy.yaml
# ✓ Policy 'my-first-policy' is valid (1 rule)
```

### Step 3 — Test it against a simulated prompt

```bash
atlasbridge policy test ~/.atlasbridge/policy.yaml \
  --prompt "Press Enter to continue..." \
  --type confirm_enter \
  --confidence high \
  --explain
```

Expected output:

```
Policy: my-first-policy (hash: a1b2c3d4e5f6a1b2)
Autonomy mode: assist  [auto_reply is BLOCKED in assist mode]
Input: type=confirm_enter, confidence=high

Evaluating 1 rule (first-match-wins):

  auto-enter  [MATCH]  auto_reply "\n"  -- OVERRIDDEN by autonomy_mode=assist
        prompt_type:    confirm_enter in [confirm_enter]  -- satisfied
        min_confidence: high >= medium                    -- satisfied
        contains:       not specified (always matches)

Decision: require_human  (autonomy_mode=assist blocked auto_reply; routed to phone for confirmation)
```

> Note: In `assist` mode, a suggestion is sent to your phone. You tap **CONFIRM** to allow the injection. Switch to `full` mode once you are satisfied the rule is correct.

### Step 4 — Enable autopilot

```bash
atlasbridge autopilot enable
atlasbridge autopilot mode assist
atlasbridge autopilot status
```

### Step 5 — Run your agent

```bash
atlasbridge run claude
```

Any `confirm_enter` prompt will now generate a suggestion in your Telegram/Slack. All other prompts route to you unchanged.

---

## 3. Core Concepts

### 3.1 Policy file

A policy file is a YAML document that contains:

- A version declaration (`policy_version: "0"`)
- An autonomy mode (`autonomy_mode: off | assist | full`)
- An ordered list of rules (`rules:`)
- Fallback defaults (`defaults:`)

The file lives anywhere on your filesystem. Point AtlasBridge at it with:

```bash
atlasbridge run claude --policy ~/.atlasbridge/policy.yaml
```

Or set the path in `~/.atlasbridge/config.toml`:

```toml
[autopilot]
policy_file = "~/.atlasbridge/policy.yaml"
```

### 3.2 PromptEvent

When the tri-signal detector fires, it produces a `PromptEvent` with these fields that your rules can match against:

| Field | Type | Example | Source |
|-------|------|---------|--------|
| `prompt_type` | enum | `yes_no` | Signal 1/2/3 classification |
| `confidence` | enum | `high` | Signal 1=high, 2=medium, 3=low |
| `excerpt` | string | `"Continue? [y/n]"` | Last 200 bytes, ANSI-stripped |
| `tool_id` | string | `"claude"` | Adapter name |
| `session.cwd` | string | `/home/user/project` | Working directory at session start |
| `prompt_id` | string | `"abc123..."` | Unique ID (24 hex chars) |
| `session_id` | UUID | `"e7f8..."` | Session UUID |

### 3.3 Prompt types

| Type | When it fires | Example excerpt |
|------|--------------|-----------------|
| `yes_no` | Binary yes/no or y/n prompt detected | `"Continue? [y/n]"`, `"Proceed? (Y/n)"` |
| `confirm_enter` | "Press Enter to continue" or pager prompt | `"-- More --"`, `"[Press Enter]"` |
| `multiple_choice` | Numbered option list | `"1) Accept  2) Reject  3) Skip"` |
| `free_text` | Open-ended input request | `"Enter branch name:"`, `"Password:"` |

### 3.4 Confidence levels

| Level | Source | Typical use |
|-------|--------|------------|
| `high` | Signal 1: pattern match on known prompt signatures | Safe to auto-reply |
| `medium` | Signal 2: TTY blocked-on-read inference | Suitable for confirm_enter |
| `low` | Signal 3: silence watchdog fired | Human escalation recommended |

A rule with `min_confidence: high` matches only high-confidence events. A rule with `min_confidence: low` matches all confidence levels (this is the default).

### 3.5 First-match-wins evaluation

Rules are evaluated in list order. The engine stops at the first rule whose **all** match criteria are satisfied. Rules below the matching rule are never evaluated.

```
rules:
  - id: "R-01"   ← evaluated first
  - id: "R-02"   ← evaluated only if R-01 did not match
  - id: "R-03"   ← evaluated only if R-01 and R-02 did not match
```

More specific rules must come BEFORE less specific rules. A catch-all rule (empty `match: {}`) must be last.

### 3.6 Autonomy mode as a gate

The top-level `autonomy_mode` overrides individual rule actions:

- `off` — all rules are skipped; every prompt goes to `require_human`
- `assist` — `auto_reply` and `deny` rules are blocked; they route to human with a suggestion
- `full` — all action types are permitted

This lets you change mode without rewriting rules. Your rule library stays intact; the mode controls whether the engine acts on it.

### 3.7 Defaults

If no rule matches, the engine falls back to the `defaults` block:

```yaml
defaults:
  no_match: require_human      # when no rule matches (safe default)
  low_confidence: require_human # when confidence=low and no explicit rule covers it
```

Both fields accept `require_human` or `deny`. **Never set `deny` as a default** — it silently blocks execution with no notification. See [Section 9 — Safety Notes](#9-safety-notes).

---

## 4. Policy Syntax Reference

### 4.1 Top-level structure

```yaml
policy_version: "0"          # required; must be the string "0"
name: "my-policy"            # optional; human label for logs and explain output
autonomy_mode: assist        # off | assist | full  (default: off)

rules:                       # ordered list; first-match-wins
  - ...

defaults:
  no_match: require_human    # require_human | deny
  low_confidence: require_human
```

### 4.2 Rule structure

```yaml
- id: "R-01"                     # required; unique identifier (A-Za-z0-9-_)
  description: "Why this rule exists"   # optional; shown in explain output
  match:
    tool_id: "claude"            # exact tool name or "*" wildcard (default: "*")
    repo: "/home/user/project"   # prefix match on session.cwd (optional)
    prompt_type:                 # list; omit to match any type
      - yes_no
      - confirm_enter
    contains: "Continue"         # substring or regex in excerpt (optional)
    contains_is_regex: false     # default: false; set true for regex
    min_confidence: high         # low | medium | high  (default: low)
  action:
    type: auto_reply             # auto_reply | require_human | deny | notify_only
    value: "y"                   # required for auto_reply; literal string
    message: "..."               # optional; for require_human (sent to channel)
    reason: "..."                # optional; for deny (logged)
    constraints:                 # optional; auto_reply only
      allowed_choices:
        - "y"
        - "n"
      numeric_only: false        # if true, value must be an integer string
      allow_free_text: true      # if false, rejects values not in allowed_choices
```

### 4.3 All `action.type` values

| Type | Effect | Required fields |
|------|--------|----------------|
| `auto_reply` | Injects `value` into PTY stdin | `value` |
| `require_human` | Routes prompt to your phone channel | none (optional: `message`) |
| `deny` | Blocks the prompt; process pauses, no notification | none (optional: `reason`) |
| `notify_only` | Sends notification; does not inject or block | none |

### 4.4 Match criteria (all optional; omit = always matches)

| Field | Type | Match logic |
|-------|------|------------|
| `tool_id` | string | Exact match or `"*"` wildcard |
| `repo` | string | Prefix match on `session.cwd` |
| `prompt_type` | list | `event.prompt_type` must be in this list |
| `contains` | string | Substring or regex in `event.excerpt` |
| `contains_is_regex` | boolean | If true, `contains` is a Python regex |
| `min_confidence` | string | `event.confidence >= rule.min_confidence` |

An empty `match: {}` matches every event (use as a catch-all last rule).

### 4.5 Constraints

Constraints apply to `auto_reply` actions only. They are validated at policy load time, not at runtime.

```yaml
action:
  type: auto_reply
  value: "1"
  constraints:
    allowed_choices: ["1", "2", "3"]   # value must be in this list
    numeric_only: true                  # value must be parseable as int
    allow_free_text: false              # reject values not in allowed_choices
    max_length: 200                     # max byte length of injected value
```

If `value` conflicts with `allowed_choices` at validation time, `atlasbridge policy validate` exits 1 with an error.

---

## 5. Working With Policies (CLI)

### 5.1 Validate

Check that a policy file parses correctly and passes all schema validations:

```bash
atlasbridge policy validate policy.yaml
```

Exits 0 if valid. Exits 1 with structured error output if any rule fails validation:

```
✗ Policy validation failed (2 errors):

  Rule R-03:
    action.value: "maybe" is not in allowed_choices ["y", "n"]

  Rule R-04:
    match.contains: regex 'a*' matches the empty string — use a non-empty pattern
```

### 5.2 Test against a simulated prompt

Run your policy against a manually specified prompt without starting a session:

```bash
# Basic test
atlasbridge policy test policy.yaml \
  --prompt "Continue? [y/n]" \
  --type yes_no \
  --confidence high

# With tool and repo scoping
atlasbridge policy test policy.yaml \
  --prompt "Run 42 tests? [y/n]" \
  --type yes_no \
  --confidence high \
  --tool claude \
  --repo /home/user/myproject

# With full explain output (shows every rule's evaluation)
atlasbridge policy test policy.yaml \
  --prompt "Delete 30 files permanently?" \
  --type yes_no \
  --confidence high \
  --explain
```

The `--explain` flag outputs the full evaluation trace — every rule, every criterion, which one matched, and why. This is your primary debugging tool.

### 5.3 Show active policy

```bash
atlasbridge policy show
```

Prints the active policy path (from config or flag), its content hash, autonomy mode, and rule count. Does not evaluate rules.

### 5.4 Autopilot control

```bash
atlasbridge autopilot enable          # load policy and start engine
atlasbridge autopilot disable         # stop engine; all prompts route to human

atlasbridge autopilot mode off        # switch to Off (relay-only)
atlasbridge autopilot mode assist     # switch to Assist
atlasbridge autopilot mode full       # switch to Full

atlasbridge autopilot status          # engine state, mode, policy hash
atlasbridge autopilot explain         # last 20 decisions with explanations
atlasbridge autopilot explain --last 50 --json   # machine-readable output
```

### 5.5 Kill switch (pause / resume)

Instantly pause autopilot from any terminal or from Telegram/Slack:

```bash
atlasbridge pause     # all prompts immediately route to human
atlasbridge resume    # autopilot resumes (full mode: auto-reply; assist mode: suggest)
```

From Telegram or Slack:

```
/pause
/resume
```

The pause state is persisted to disk (`autopilot_state.json`). A daemon restart will not lose a paused state.

---

## 6. Writing Good Policies (Patterns)

### Pattern 1 — Start safe, graduate to automation

The recommended sequence for rolling out a new policy:

**Phase 1 — Observe (autonomy_mode: off)**

```yaml
policy_version: "0"
name: "observe-mode"
autonomy_mode: off    # relay-only; no rules evaluated

rules: []

defaults:
  no_match: require_human
  low_confidence: require_human
```

Run your agent for several sessions. Check `atlasbridge autopilot explain` to see what prompt types and excerpts are appearing. Identify patterns that are safe to automate.

**Phase 2 — Suggest (autonomy_mode: assist)**

Add rules for the patterns you identified, but keep `autonomy_mode: assist`. The engine will suggest replies; you confirm from your phone. No auto-injection happens without your tap.

**Phase 3 — Automate (autonomy_mode: full)**

Once you have confirmed that all rules are behaving as expected over multiple sessions, switch to `full`. The engine injects approved replies immediately. Keep `/pause` accessible during the first full-mode session.

---

### Pattern 2 — Narrow before broad

Always place specific rules before general rules. Here is the wrong order:

```yaml
# WRONG order — the broad rule fires for everything
rules:
  - id: "catch-all"
    match: {}
    action:
      type: require_human

  - id: "auto-enter"           # never reached; catch-all wins first
    match:
      prompt_type: [confirm_enter]
    action:
      type: auto_reply
      value: "\n"
```

Correct order:

```yaml
# CORRECT order — specific before general
rules:
  - id: "auto-enter"           # checked first
    match:
      prompt_type: [confirm_enter]
    action:
      type: auto_reply
      value: "\n"

  - id: "catch-all"            # only reached if auto-enter didn't match
    match: {}
    action:
      type: require_human
```

---

### Pattern 3 — Add `contains` to narrow scope

A `prompt_type` rule without a `contains` filter fires for **every** prompt of that type. This is almost always too broad for `auto_reply`. Add a `contains` filter:

```yaml
# RISKY — fires for every yes_no, including "Delete all files? [y/n]"
- id: "all-yes"
  match:
    prompt_type: [yes_no]
  action:
    type: auto_reply
    value: "y"
```

```yaml
# SAFER — only fires for yes_no prompts containing "Continue"
- id: "continue-yes"
  match:
    prompt_type: [yes_no]
    contains: "Continue"
    min_confidence: high
  action:
    type: auto_reply
    value: "y"
    constraints:
      allowed_choices: ["y", "n"]
```

---

### Pattern 4 — Scope by tool and repo

Use `tool_id` and `repo` to limit rules to specific tools or projects:

```yaml
# Only auto-approve pytest yes_no in the backend repo
- id: "pytest-backend"
  match:
    tool_id: "claude"
    repo: "/home/alice/workspaces/backend"
    prompt_type: [yes_no]
    contains: "Run \\d+ tests"
    contains_is_regex: true
    min_confidence: high
  action:
    type: auto_reply
    value: "y"
    constraints:
      allowed_choices: ["y", "n"]
```

---

### Pattern 5 — Deny dangerous keywords

Block prompts that contain keywords associated with destructive operations:

```yaml
- id: "deny-destructive"
  description: "Block auto-reply for any destructive-looking prompt"
  match:
    contains: "delete|destroy|drop|purge|wipe|truncate|rm -rf"
    contains_is_regex: true
    min_confidence: low       # catch even low-confidence detections
  action:
    type: deny
    reason: >
      Destructive operation detected. Operator must manually review
      and respond via atlasbridge sessions or direct PTY input.
```

> **Warning:** `deny` pauses the supervised process with no notification. The operator must manually intervene. Prefer `require_human` for prompts you want to review — use `deny` only for prompts that should **never** receive an auto-reply.

---

### Pattern 6 — Free-text escalation with context

When escalating a free-text prompt, add a `message` so your phone shows useful context:

```yaml
- id: "branch-name"
  description: "Escalate branch name prompts with context"
  match:
    prompt_type: [free_text]
    contains: "branch"
    contains_is_regex: false
  action:
    type: require_human
    message: >
      The agent is asking for a Git branch name. Please enter a branch name
      (e.g. 'feature/my-feature' or 'fix/bug-123').
```

The `message` appears in your Telegram/Slack notification above the prompt excerpt, giving you context before you type a reply.

---

### Pattern 7 — Multiple-choice menus

Auto-select a numbered option in interactive menus:

```yaml
- id: "package-menu-select-1"
  description: "Auto-select first option in pip/npm install menus"
  match:
    prompt_type: [multiple_choice]
    contains: "npm|pip|yarn|pnpm"
    contains_is_regex: true
    min_confidence: high
  action:
    type: auto_reply
    value: "1"
    constraints:
      numeric_only: true
      allowed_choices: ["1", "2", "3"]
```

---

### Pattern 8 — Explicit catch-all

Always end your rules list with an explicit catch-all. This makes it clear in the decision trace that the catch-all was intentionally reached, rather than showing `matched_rule_id: null`:

```yaml
- id: "catch-all"
  description: "Any unmatched prompt goes to human"
  match: {}          # empty match = always matches
  action:
    type: require_human
    message: >
      No policy rule matched this prompt. Please review and respond.
      Consider adding a more specific rule if this pattern repeats.
```

---

## 7. Profile-Aware Rules

Agent profiles let you define reusable session presets (label, policy, adapter) and then scope policy rules to specific profiles using the `session_tag` match criterion in Policy DSL v1.

### 7.1 Setting up profiles

```bash
# Create profiles for different workflows
atlasbridge profile create ci --label ci --description "CI/CD pipeline sessions"
atlasbridge profile create code-review --label code-review --description "Code review sessions"

# Use a profile when running
atlasbridge run claude --profile ci
```

When you run with `--profile ci`, the profile's `session_label` ("ci") is passed through as `session_tag` in policy evaluation. This lets you write rules that only apply to specific profiles.

### 7.2 Writing profile-scoped rules

Use `session_tag` in your v1 policy rules to match specific profiles:

```yaml
policy_version: "1"
name: "profile-aware"
autonomy_mode: full

rules:
  # Only applies when running with --profile ci (session_label: ci)
  - id: "ci-auto-approve"
    description: "Auto-yes in CI sessions"
    match:
      session_tag: ci
      prompt_type: [yes_no, confirm_enter]
      min_confidence: high
    action:
      type: auto_reply
      value: "y"

  # Only applies when running with --profile code-review
  - id: "review-escalate"
    description: "Always escalate in code-review sessions"
    match:
      session_tag: code-review
    action:
      type: require_human
      message: "Code review session — all prompts require human review."

  # Default rules (no session_tag) apply to all sessions
  - id: "default-continue"
    match:
      prompt_type: [yes_no]
      contains: "Continue"
      min_confidence: high
    action:
      type: auto_reply
      value: "y"

defaults:
  no_match: require_human
```

### 7.3 How the flow works

```
Profile.session_label → Session.label → PromptEvent.session_label → session_tag in evaluate()
```

1. `atlasbridge run claude --profile ci` loads the "ci" profile
2. Profile's `session_label: ci` is set on the session's `label` field
3. When a prompt is detected, the router copies `session.label` to `event.session_label`
4. The policy evaluator uses `session_label` as `session_tag` for rule matching
5. Rules with `session_tag: ci` match; rules with other tags are skipped

### 7.4 Testing profile-aware rules

```bash
# Test with a specific session tag (simulates a profile)
atlasbridge policy test config/policies/profile-aware.example.yaml \
  --prompt "Continue? [y/n]" --type yes_no --confidence high \
  --session-tag ci --explain
```

See `config/policies/profile-aware.example.yaml` for a complete example.

---

## 8. Debugging Policies

### 7.1 The `--explain` flag

The most important debugging tool. Run any prompt through your policy and see the full evaluation trace:

```bash
atlasbridge policy test policy.yaml \
  --prompt "Run 23 tests? [y/n]" \
  --type yes_no \
  --confidence high \
  --explain
```

Example output:

```
Policy: my-policy (hash: d41d8cd98f00b204)
Autonomy mode: full
Input: type=yes_no, confidence=high, tool=*, excerpt="Run 23 tests? [y/n]"

Evaluating 4 rules (first-match-wins):

  R-01  [no match]
        tool_id:        * (wildcard, always matches)
        prompt_type:    yes_no in [confirm_enter]  -- FAILED

  R-02  [MATCH]  auto_reply "y"
        tool_id:        * (wildcard, always matches)
        prompt_type:    yes_no in [yes_no, confirm_enter]  -- satisfied
        min_confidence: high >= high                        -- satisfied
        contains:       "Run" found in excerpt              -- satisfied

  R-03  [skip — R-02 already matched]
  R-04  [skip — R-02 already matched]

Decision: auto_reply "y"
Idempotency key: a1b2c3d4e5f6a1b2
```

Read the trace from top to bottom:
- `[MATCH]` — this rule fired; action executed
- `[no match]` — this rule evaluated but at least one criterion failed; the failing criterion is shown as `-- FAILED`
- `[skip — Rxx already matched]` — rule not evaluated because an earlier rule matched

### 7.2 The decision trace log

Every decision is appended to `~/.atlasbridge/autopilot_decisions.jsonl`:

```bash
# View last 20 decisions
atlasbridge autopilot explain --last 20

# Raw JSONL
tail -n 50 ~/.atlasbridge/autopilot_decisions.jsonl | python3 -m json.tool
```

Each record includes: `timestamp`, `prompt_id`, `session_id`, `matched_rule_id`, `action_type`, `action_value`, `confidence`, `prompt_type`, `autonomy_mode`, `autonomy_override`, and `explanation`.

### 7.3 Common problems

**Rule never fires**

Check these in order:
1. Is the rule in the correct position? A more general rule earlier in the list may be matching first.
2. Run `atlasbridge policy test --explain` with a prompt that should match and read why each criterion fails.
3. Is `min_confidence` set higher than the events you're receiving? Use `atlasbridge autopilot explain` to check the confidence level of recent events.
4. Is `contains` matching what you expect? Test the regex with `python3 -c "import re; print(re.search('your-pattern', 'your-excerpt', re.I))"`.

**Rule fires too broadly**

Add a `contains` filter. Without one, any rule that only matches `prompt_type` will fire for every prompt of that type regardless of content.

**`auto_reply` fires in assist mode**

This is expected. In `assist` mode, `auto_reply` actions are blocked by the autonomy gate and routed to your phone as a suggestion. The decision trace will show `"autonomy_override": true`. Switch to `full` mode to enable actual injection.

**Validation fails on regex**

Run `atlasbridge policy validate policy.yaml` and read the error. Common causes:
- Pattern matches the empty string (`a*`, `b?`, `.*`) — use `a+` or `b{1}` instead
- Pattern is longer than 200 characters
- Pattern contains backreferences (`\1`)

**`deny` left session blocked**

The supervised process is waiting on stdin with no notification sent. Use:

```bash
atlasbridge sessions       # find the session ID
atlasbridge sessions unblock <session-id>   # unblock it
```

Or manually type a reply directly in the terminal where `atlasbridge run` is running.

### 7.4 Validate before every deploy

Make validating your policy before a `run` a habit:

```bash
atlasbridge policy validate policy.yaml && atlasbridge run claude
```

---

## 9. FAQ

**Q: Where does AtlasBridge look for my policy file?**

In order of precedence:
1. `--policy <path>` flag on `atlasbridge run`
2. `autopilot.policy_file` in `~/.atlasbridge/config.toml`
3. `~/.atlasbridge/policy.yaml` (default location)

If no policy file is found, the engine starts with a built-in safe-default policy: all prompts go to `require_human`.

---

**Q: Can I have multiple policy files for different projects?**

Yes. Use the `--policy` flag:

```bash
# Backend project
atlasbridge run claude --policy ~/policies/backend.yaml

# Frontend project
atlasbridge run claude --policy ~/policies/frontend.yaml
```

Or set the policy per-project in a `.atlasbridge.toml` file in your project root (planned for v0.7.0).

---

**Q: What happens if my policy file has a syntax error?**

The engine refuses to start. `atlasbridge run` will exit with an error describing the validation failure. Always run `atlasbridge policy validate` before deploying a new policy.

---

**Q: Can I hot-reload the policy without restarting?**

Yes. Send SIGHUP to the daemon process:

```bash
atlasbridge policy reload
```

The engine reloads the policy file from disk on the next prompt. Any in-flight prompt completes under the old policy.

---

**Q: What is the difference between `deny` and `require_human`?**

| | `require_human` | `deny` |
|--|-----------------|--------|
| Routes to phone | Yes | No |
| Notifies operator | Yes | No |
| Pauses execution | Yes (until reply or TTL) | Yes (indefinitely) |
| Unblock mechanism | Reply from phone | `atlasbridge sessions unblock` |
| Recommended for | "Route this to me" | "This must never auto-reply" |

Use `require_human` unless you specifically need to block without notification.

---

**Q: Does the policy see the full terminal output?**

No. The policy evaluates against `event.excerpt`, which is the last 200 bytes of ANSI-stripped terminal output at the time the prompt was detected. Long output is truncated. This is by design — the policy DSL is not a text analysis engine.

---

**Q: What happens to a prompt when autopilot is paused?**

When `/pause` is issued (or `atlasbridge pause`), all subsequent prompts bypass the policy and route directly to your phone. The paused state persists until `/resume`. In-flight prompts complete under the mode that was active when they entered the engine.

---

**Q: Can I use AtlasBridge with agents other than Claude Code?**

Yes. Use `tool_id` in rules to scope rules to specific adapters:

```yaml
match:
  tool_id: "openai"   # only matches atlasbridge run openai
  prompt_type: [yes_no]
  min_confidence: high
```

Supported adapters: `claude`, `openai`, `gemini`.

---

**Q: What does `policy_version` do?**

It future-proofs the schema. DSL v0 is the only version currently supported. Future DSL versions will introduce new fields under a new version number without breaking existing v0 files.

---

## 10. Safety Notes

### Never auto-reply to credential prompts

Write an explicit `deny` rule for any prompt that may be asking for passwords, tokens, or secrets:

```yaml
- id: "deny-credentials"
  description: "Never auto-reply to credential prompts"
  match:
    prompt_type: [free_text]
    contains: "password|token|api.?key|secret|passphrase"
    contains_is_regex: true
    min_confidence: low      # catch even low-confidence matches
  action:
    type: deny
    reason: >
      Credential prompts are never auto-replied. Supply the credential
      directly or use atlasbridge sessions to unblock.
```

Place this rule early in the list so it fires before any broader `free_text` rules.

---

### Never set `deny` as a default

`defaults.no_match: deny` will silently block every unrecognised prompt with no notification. The supervised process freezes indefinitely. This is the worst possible failure mode.

```yaml
# WRONG
defaults:
  no_match: deny

# CORRECT
defaults:
  no_match: require_human
```

---

### Use `min_confidence: high` for `auto_reply` rules

Low-confidence events come from the silence watchdog when no pattern matched. Their excerpt may be ambiguous or entirely wrong. Auto-replying to low-confidence events based on a `contains` match is unreliable.

```yaml
# RISKY
match:
  prompt_type: [yes_no]
  min_confidence: low     # includes watchdog-triggered events
  contains: "Continue"

# SAFER
match:
  prompt_type: [yes_no]
  min_confidence: high    # only fires when pattern matching is confident
  contains: "Continue"
```

---

### Keep `allowed_choices` on every `auto_reply` rule

The `allowed_choices` constraint validates at policy load time that your `value` is in the set you intended. It also documents the rule's intent to future editors.

```yaml
action:
  type: auto_reply
  value: "y"
  constraints:
    allowed_choices: ["y", "n"]   # documents intent + validated at load
```

---

### Test in `assist` mode before promoting to `full`

The recommended promotion workflow:

1. Write your rules.
2. Run `atlasbridge policy validate` — fix any errors.
3. Run `atlasbridge policy test --explain` for each prompt type you expect.
4. Deploy with `autonomy_mode: assist` — observe suggestions in Telegram/Slack for at least one full session.
5. If all suggestions are correct, switch to `full`: `atlasbridge autopilot mode full`.
6. Monitor `atlasbridge autopilot explain` during the first full-mode session.
7. Keep `/pause` available from your phone for the first several full-mode sessions.

---

### The kill switch is always available

No matter what mode you are in, `/pause` (from Telegram/Slack) or `atlasbridge pause` (from the terminal) immediately stops auto-injection. The next prompt is forwarded to your phone. The pause state survives daemon restarts.

---

## 11. Next Steps

- **Full DSL reference** — [docs/policy-dsl.md](policy-dsl.md) covers every field, evaluation algorithm, regex safety limits, idempotency, and decision trace format in complete detail.
- **Autonomy modes** — [docs/autonomy-modes.md](autonomy-modes.md) describes Off/Assist/Full in detail including the confirmation window, kill switch, and mode transition rules.
- **Example policies** — [config/policies/](../config/policies/) contains ready-to-use examples:
  - `minimal.yaml` — safe starting point; all prompts route to human except Enter confirmation
  - `assist-mode.yaml` — assist mode with common automation rules
  - `full-mode-safe.yaml` — full mode with deny rules for dangerous operations
  - `pr-remediation-dependabot.yaml` — auto-approve Dependabot PR prompts
  - `escalation-only.yaml` — catch-all escalation (all prompts → phone)
- **Prompt Lab** — run deterministic QA scenarios to test detection before writing rules: `atlasbridge lab run --all`
