# AtlasBridge Policy DSL v0

**Version:** DSL v0 (AtlasBridge v0.6.0+)
**Status:** Implemented — superseded by [Policy DSL v1](policy-dsl-v1.md) (AtlasBridge v0.8.0+)
**Last updated:** 2026-02-21

> **v0 is still fully supported.** v1 is a backward-compatible extension — v0 files work
> unchanged. To migrate: `atlasbridge policy migrate <file>`.
> See the [Policy DSL v1 reference](policy-dsl-v1.md) for new features.

---

## Table of Contents

1. [Overview and Design Goals](#1-overview-and-design-goals)
2. [Evaluation Semantics](#2-evaluation-semantics)
3. [Top-Level Schema](#3-top-level-schema)
4. [PolicyRule Schema](#4-policyrule-schema)
5. [Match Field Semantics](#5-match-field-semantics)
6. [Action Types](#6-action-types)
7. [Regex Safety Limits](#7-regex-safety-limits)
8. [Validation Rules](#8-validation-rules)
9. [Idempotency](#9-idempotency)
10. [Decision Trace Format](#10-decision-trace-format)
11. [CLI Usage](#11-cli-usage)
12. [Explain Output](#12-explain-output)
13. [Anti-Patterns and Warnings](#13-anti-patterns-and-warnings)

---

## 1. Overview and Design Goals

The AtlasBridge Policy DSL v0 is a YAML-based language for specifying how the AtlasBridge autopilot engine responds to detected prompts. When AtlasBridge detects that a supervised AI CLI tool is waiting for input, it evaluates the active policy file to determine whether to route the prompt to a human, inject an automatic reply, block execution, or send a silent notification.

### Design principles

**YAML-based, DSL-quality semantics.** Policy files are plain YAML. However, they are not treated as generic configuration: every field has a precise semantic definition, evaluation order is guaranteed, and the engine rejects unknown fields rather than silently ignoring them.

**Strictly typed via Pydantic validation.** The engine parses the policy file through a Pydantic v2 model before any evaluation occurs. Invalid enum values, unknown fields, malformed regexes, and constraint violations all produce structured error messages that identify the exact rule and field that failed. No evaluation happens on an invalid policy.

**Versioned.** Every policy file must carry a `policy_version` field. Only version `"0"` is currently supported. This allows future DSL evolution without breaking existing files: v0 files remain valid against the v0 engine, and a v1 engine can reject them or upgrade them explicitly.

**Deterministic evaluation semantics.** The evaluation algorithm is first-match-wins and is specified exactly. Given the same policy file and the same `PromptEvent`, the engine always produces the same decision. There is no scoring, ranking, weighting, or non-deterministic tie-breaking.

**Safe: no code execution, no templated shell.** Action values are literal strings. The DSL has no expression language, no variable interpolation, no subprocess references, and no conditionals that could execute code. An `auto_reply` value of `"y"` injects the literal byte sequence `y\r` into the PTY; nothing more.

**Explainable.** Every decision produced by the engine includes a human-readable explanation of exactly which rule matched and why each match criterion was satisfied or skipped. This explanation is available via `--explain` in the CLI, in structured JSONL decision traces, and in the audit log.

---

## 2. Evaluation Semantics

### 2.1 First-match-wins

Rules are evaluated in the order they appear in the `rules` list. The engine inspects each rule's `match` block against the incoming `PromptEvent`. The first rule whose **all** match criteria are satisfied wins: its `action` is executed immediately, and no further rules are evaluated.

```
for rule in policy.rules:
    if all match criteria satisfied:
        return rule.action   # evaluation stops here
# No rule matched:
return policy.defaults.no_match
```

There is no implicit priority scoring. A rule appearing later in the list will never override a rule appearing earlier, regardless of how specific or general each rule is. Rule ordering is the operator's explicit tool for expressing priority.

### 2.2 Default fallbacks

If no rule matches, the engine applies one of two defaults from the `defaults` block:

- **`defaults.no_match`** — Applied when no rule's match criteria are satisfied and confidence is medium or high. Default value: `require_human`.
- **`defaults.low_confidence`** — Applied when the detected `PromptEvent` carries `Confidence.LOW` and no rule explicitly includes `min_confidence: low` in its match criteria. Default value: `require_human`.

The `defaults` block only affects fallback behaviour. If a rule explicitly matches a low-confidence event (by setting `min_confidence: low`), that rule wins; `defaults.low_confidence` is never consulted.

### 2.3 Autonomy mode

The top-level `autonomy_mode` field is a global gate that constrains what actions the engine may perform:

| Mode | Permitted actions |
|------|------------------|
| `off` | No automatic action; all prompts go to `require_human` regardless of rules |
| `assist` | `require_human` and `notify_only` are permitted; `auto_reply` and `deny` are blocked |
| `full` | All action types are permitted |

When `autonomy_mode` blocks an action, the engine substitutes `require_human` and records the override in the decision trace.

### 2.4 Idempotency guarantee

The engine assigns every decision an `idempotency_key` (see Section 9). Duplicate evaluations for the same `(policy_hash, prompt_id, session_id)` triple are recognised and short-circuited without re-routing or re-injecting.

---

## 3. Top-Level Schema

```yaml
policy_version: "0"          # required; must be the string "0"
name: "my-policy"            # optional; human-readable label (no uniqueness constraint)
autonomy_mode: assist        # off | assist | full  (default: off)

rules:                       # ordered list of PolicyRule objects (may be empty)
  - ...

defaults:
  no_match: require_human    # require_human | deny  (default: require_human)
  low_confidence: require_human  # require_human | deny  (default: require_human)
```

### Field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `policy_version` | string | yes | Must be `"0"`. Rejected if absent or any other value. |
| `name` | string | no | Human label shown in explain output and decision traces. |
| `autonomy_mode` | enum | no | Global action gate. Defaults to `off` (maximally conservative). |
| `rules` | list | no | Ordered list of `PolicyRule` objects. Empty list is valid (all prompts fall through to defaults). |
| `defaults` | object | no | Fallback actions when no rule matches. Both sub-fields default to `require_human`. |
| `defaults.no_match` | enum | no | Action when no rule matches a medium/high confidence prompt. |
| `defaults.low_confidence` | enum | no | Action when the prompt is low confidence and no rule explicitly matches it. |

---

## 4. PolicyRule Schema

Each entry in the `rules` list is a `PolicyRule` object:

```yaml
- id: "R-01"                     # required; unique string identifier
  description: "..."             # optional; human-readable label
  match:
    tool_id: "*"                 # exact tool name OR "*" wildcard (default: "*")
    repo: "/home/user/project"   # prefix match on session.cwd (optional)
    prompt_type:                 # list of prompt_type values (optional; omit = match any)
      - yes_no
      - confirm_enter
    contains: "Continue?"        # substring or regex in prompt excerpt (optional)
    contains_is_regex: false     # if true, treat contains as Python regex (default: false)
    min_confidence: low          # low | medium | high  (default: low)
  action:
    type: auto_reply             # auto_reply | require_human | deny | notify_only
    value: "y"                   # required for auto_reply; literal string
    message: "..."               # optional; for require_human (sent to channel as context)
    reason: "..."                # optional; for deny (logged and shown to operator)
    constraints:                 # optional; only evaluated for auto_reply
      max_length: 200
      numeric_only: false
      allowed_choices:
        - "y"
        - "n"
      allow_free_text: true
```

### Rule field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique identifier for this rule. Pattern: `[A-Za-z0-9][A-Za-z0-9\-_]{0,63}`. Duplicate IDs are a validation error. |
| `description` | string | no | Human-readable label. Included in explain output. |
| `match` | object | yes | Match criteria. All specified criteria must be satisfied. |
| `action` | object | yes | Action to execute when this rule matches. |
| `max_auto_replies` | integer | no | Maximum number of times this rule may auto-reply per session. When the limit is reached, the prompt is escalated to a human instead. `null` (default) means unlimited. Minimum value: 1. Only meaningful for `auto_reply` actions; ignored for other action types. |

### Match field reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `tool_id` | string | no | `"*"` | Exact tool name or `"*"` wildcard. |
| `repo` | string | no | (absent) | Prefix match on `session.cwd`. |
| `prompt_type` | list[string] | no | (absent) | List of prompt types to match. Omit to match any type. |
| `contains` | string | no | (absent) | Substring or regex to search in `event.excerpt`. |
| `contains_is_regex` | boolean | no | `false` | If true, `contains` is a Python regex. |
| `min_confidence` | enum | no | `low` | Minimum confidence level. Event confidence must be >= this value. |

### Action field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | enum | yes | One of: `auto_reply`, `require_human`, `deny`, `notify_only`. |
| `value` | string | conditionally | Required when `type` is `auto_reply`. Literal string to inject. |
| `message` | string | no | Context message for `require_human`. Forwarded to the channel alongside the prompt. |
| `reason` | string | no | Human-readable reason for `deny`. Logged and shown to operator. |
| `constraints` | object | no | Reply constraints for `auto_reply` actions only. |

### Constraints field reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_length` | integer | (absent) | Maximum byte length of the injected value. |
| `numeric_only` | boolean | `false` | If true, value must be a string representation of an integer. |
| `allowed_choices` | list[string] | (absent) | If set, `value` must be one of these strings. |
| `allow_free_text` | boolean | `true` | If false, rejects values that are not in `allowed_choices`. |

---

## 5. Match Field Semantics

Each field in the `match` block is evaluated independently. All specified fields must match for the rule to fire. Fields that are not specified always match (they are not a constraint).

### `tool_id`

Performs exact string comparison between the rule's `tool_id` and `session.tool` (the adapter name registered in the `AdapterRegistry`, e.g. `"claude"`, `"openai"`, `"gemini"`).

The special value `"*"` always matches regardless of the session tool. This is the default when `tool_id` is not specified.

```yaml
match:
  tool_id: "claude"    # matches sessions started with `atlasbridge run claude`
```

```yaml
match:
  tool_id: "*"         # matches any tool (this is the default)
```

### `repo`

Performs a string prefix match against `session.cwd` (the working directory of the session at the time it was started). A `repo` value of `"/home/user/project"` will match sessions started in `/home/user/project`, `/home/user/project/src`, or `/home/user/project/docs/api`, but not `/home/user/project2`.

The comparison is exact-prefix, not filesystem-glob. No path normalisation or symlink resolution is applied.

```yaml
match:
  repo: "/home/alice/workspaces/backend"
  # matches: /home/alice/workspaces/backend
  # matches: /home/alice/workspaces/backend/src/api
  # no match: /home/alice/workspaces/backend-v2
```

### `prompt_type`

A list of `PromptType` string values. The rule matches if `event.prompt_type` is found in this list. Omitting `prompt_type` is equivalent to accepting all types.

Valid values: `yes_no`, `confirm_enter`, `multiple_choice`, `free_text`.

```yaml
match:
  prompt_type:
    - yes_no
    - confirm_enter    # matches either yes_no OR confirm_enter
```

### `contains`

Searches `event.excerpt` (the ANSI-stripped, 200-character-truncated terminal output fragment) for the specified string.

**When `contains_is_regex` is `false` (default):** A case-insensitive substring search. The rule matches if the string appears anywhere in the excerpt.

**When `contains_is_regex` is `true`:** The value is compiled as a Python regex and matched against the excerpt using `re.search()` (case-insensitive). Subject to the regex safety limits described in Section 7.

```yaml
match:
  contains: "are you sure"             # substring match (case-insensitive)

match:
  contains: "delete|destroy|remove"    # regex alternation
  contains_is_regex: true
```

### `min_confidence`

Specifies the minimum confidence level required for the rule to fire. Confidence levels have the ordering: `low < medium < high`.

A rule with `min_confidence: low` matches events at any confidence level. A rule with `min_confidence: high` matches only high-confidence events and ignores medium and low.

```yaml
match:
  min_confidence: high    # only matches HIGH confidence events
```

```yaml
match:
  min_confidence: low     # matches LOW, MEDIUM, and HIGH (this is the default)
```

---

## 6. Action Types

### `auto_reply`

Injects the literal `value` string into the PTY's standard input, followed by a carriage return (`\r`). The value must be a string literal; no interpolation, shell expansion, or variable substitution occurs.

```yaml
action:
  type: auto_reply
  value: "y"
```

```yaml
action:
  type: auto_reply
  value: "\n"           # injects newline (confirm_enter prompts)
  constraints:
    allowed_choices:
      - "\n"
```

If `constraints.allowed_choices` is set, the engine validates that `value` is one of the listed strings before accepting the rule during policy load. A value that conflicts with its own constraints is a validation error.

### `require_human`

Routes the prompt to the configured notification channel (Telegram, Slack) and waits for a human reply. Execution is paused until a reply is received or the prompt TTL expires. The optional `message` field is forwarded to the channel as additional context above the prompt excerpt.

```yaml
action:
  type: require_human
  message: "This prompt is asking for a branch name. Please provide one."
```

### `deny`

Blocks the prompt and pauses execution without routing to any channel. The supervised process remains waiting on stdin. The optional `reason` is written to the audit log and shown in `atlasbridge sessions`. The operator must manually intervene via `atlasbridge sessions` to unblock the session.

`deny` should be used sparingly and never as a default. Prefer `require_human` when in doubt.

```yaml
action:
  type: deny
  reason: "Auto-reply to credential prompts is prohibited."
```

### `notify_only`

Sends a notification to the configured channel but does not wait for a reply and does not inject anything. After the notification is sent, the prompt continues as if no rule matched — the engine falls through to `defaults.no_match`. Use this to create audit trail entries or operator awareness without blocking.

```yaml
action:
  type: notify_only
```

---

## 7. Regex Safety Limits

When `contains_is_regex: true`, the engine enforces the following safety constraints to prevent catastrophic backtracking and ReDoS:

| Limit | Value |
|-------|-------|
| Maximum regex length | 200 characters |
| Evaluation timeout | 100 ms per rule evaluation |
| Forbidden: backreferences | `\1`, `\2`, etc. are rejected at validation time |
| Forbidden: quantified lookahead/lookbehind | e.g. `(?=.*){3}` are rejected at validation time |
| Forbidden: matches empty string | Patterns like `.*` or `a*` that match the empty string are rejected at validation time |

**Timeout behaviour:** If a regex evaluation exceeds 100 ms (implemented via `signal.alarm` or a thread timeout), the rule evaluation is aborted, a warning is logged, and the engine falls through to the next rule. The rule is not treated as a match. This means a timing-sensitive rule may silently stop matching if the regex becomes expensive for a particular input.

**Validation-time rejection:** Patterns that contain forbidden constructs or match the empty string are rejected when `atlasbridge policy validate` is run. They are not evaluated at runtime.

---

## 8. Validation Rules

`atlasbridge policy validate policy.yaml` must fail with a structured error for any of the following:

| Error | Description |
|-------|-------------|
| Unknown fields | Any field not in the defined schema at any nesting level. `additionalProperties: false` is enforced everywhere. |
| Invalid action type | `action.type` is not one of `auto_reply`, `require_human`, `deny`, `notify_only`. |
| Invalid prompt_type value | Any value in `match.prompt_type` is not one of `yes_no`, `confirm_enter`, `multiple_choice`, `free_text`. |
| Invalid regex | `contains_is_regex: true` and `contains` is not a valid Python regex. |
| Empty-matching regex | `contains_is_regex: true` and the pattern matches the empty string (e.g. `.*`, `a*`, `b?`). |
| Forbidden regex construct | `contains_is_regex: true` and the pattern contains backreferences or quantified lookahead/lookbehind. |
| Duplicate rule IDs | Two or more rules share the same `id` value. |
| Value conflicts with constraints | `action.type` is `auto_reply`, `constraints.allowed_choices` is set, and `action.value` is not in `allowed_choices`. |
| Missing `value` for `auto_reply` | `action.type` is `auto_reply` but `action.value` is absent or empty. |
| Invalid `policy_version` | `policy_version` is absent, or is not the string `"0"`. |
| Invalid `autonomy_mode` | `autonomy_mode` is not one of `off`, `assist`, `full`. |
| Invalid `defaults` action | `defaults.no_match` or `defaults.low_confidence` is not `require_human` or `deny`. |

Validation errors are reported as a structured list: each entry identifies the rule ID (if applicable), the field path, and a plain-English description of the violation.

---

## 9. Idempotency

Every decision record carries a 16-hex-character `idempotency_key` computed as:

```
idempotency_key = SHA-256(policy_hash + ":" + prompt_id + ":" + session_id)[:16]
```

Where:

- **`policy_hash`** — SHA-256 of the canonical serialised policy content (JSON-normalised, keys sorted). Stable across process restarts for the same policy file. Changes whenever the policy file content changes.
- **`prompt_id`** — The unique prompt identifier from `PromptEvent.prompt_id` (24 hex characters, `secrets.token_hex(12)`).
- **`session_id`** — The session UUID from `Session.session_id`.

The idempotency key is stored in the `prompts` table alongside the policy hash. If the engine receives a duplicate routing request for the same `(prompt_id, session_id)` pair under the same policy, it returns the already-recorded decision without re-evaluating rules, re-routing to the channel, or re-injecting.

This guarantee holds across daemon restarts: the idempotency key is persisted to SQLite before any action is taken.

---

## 10. Decision Trace Format

Every decision is written to the audit log as a JSONL record immediately before the action is executed:

```json
{
  "timestamp": "2026-02-21T10:00:00.000Z",
  "idempotency_key": "a1b2c3d4e5f6a1b2",
  "prompt_id": "abc123def456abc123def456",
  "session_id": "e7f8a9b0-c1d2-3e4f-5a6b-7c8d9e0f1a2b",
  "policy_hash": "d41d8cd98f00b204e9800998ecf8427e",
  "matched_rule_id": "R-01",
  "action_type": "auto_reply",
  "action_value": "y",
  "confidence": "high",
  "prompt_type": "yes_no",
  "autonomy_mode": "full",
  "autonomy_override": false,
  "explanation": "Rule R-01 matched: tool_id=* (wildcard), prompt_type=yes_no in [yes_no, confirm_enter], confidence=high >= low, contains not specified (always matches)"
}
```

When no rule matches:

```json
{
  "timestamp": "2026-02-21T10:05:00.000Z",
  "idempotency_key": "b2c3d4e5f6a1b2c3",
  "prompt_id": "def456abc123def456abc123",
  "session_id": "e7f8a9b0-c1d2-3e4f-5a6b-7c8d9e0f1a2b",
  "policy_hash": "d41d8cd98f00b204e9800998ecf8427e",
  "matched_rule_id": null,
  "action_type": "require_human",
  "action_value": null,
  "confidence": "medium",
  "prompt_type": "free_text",
  "autonomy_mode": "full",
  "autonomy_override": false,
  "explanation": "No rule matched. Applied defaults.no_match=require_human."
}
```

When `autonomy_mode` overrides the matched action:

```json
{
  "matched_rule_id": "R-01",
  "action_type": "require_human",
  "autonomy_override": true,
  "explanation": "Rule R-01 matched action=auto_reply, but autonomy_mode=assist blocks auto_reply. Substituted require_human."
}
```

---

## 11. CLI Usage

### Validate a policy file

```bash
atlasbridge policy validate policy.yaml
```

Exits 0 if the policy is valid. Exits 1 with structured error output if any validation rule fails.

```bash
atlasbridge policy validate policy.yaml --json
```

Outputs validation results as JSON for machine consumption.

### Test a policy against a simulated prompt

```bash
atlasbridge policy test \
  --policy policy.yaml \
  --prompt "Continue? [y/n]" \
  --type yes_no \
  --confidence high \
  --explain
```

```bash
atlasbridge policy test \
  --policy policy.yaml \
  --prompt "Enter branch name:" \
  --type free_text \
  --confidence medium \
  --explain
```

```bash
atlasbridge policy test \
  --policy policy.yaml \
  --prompt "Deleting 47 files. Are you sure?" \
  --type yes_no \
  --confidence high \
  --tool claude \
  --repo /home/user/project \
  --explain
```

The `--explain` flag prints the full evaluation trace (see Section 12). Without `--explain`, only the resulting action is printed.

### Show the active policy

```bash
atlasbridge policy show
```

Prints the active policy (path from config or `~/.atlasbridge/policy.yaml`), its hash, and its autonomy mode.

---

## 12. Explain Output

The `--explain` flag produces a structured evaluation trace showing exactly how each rule was evaluated. Rules that were never reached because an earlier rule matched are shown as skipped.

### Example: match on first rule

```
Policy: my-policy (hash: d41d8cd98f00b204)
Autonomy mode: full
Input: type=yes_no, confidence=high, tool=claude, excerpt="Continue? [y/n]"

Evaluating 3 rules (first-match-wins):

  R-01  [MATCH]  auto_reply "y"
        tool_id:        * (wildcard, always matches)
        prompt_type:    yes_no in [yes_no, confirm_enter]  -- satisfied
        min_confidence: high >= low                         -- satisfied
        contains:       not specified (always matches)

  R-02  [skip -- R-01 already matched]
  R-03  [skip -- R-01 already matched]

Decision: auto_reply "y"
Idempotency key: a1b2c3d4e5f6a1b2
```

### Example: no rule matches

```
Policy: my-policy (hash: d41d8cd98f00b204)
Autonomy mode: full
Input: type=free_text, confidence=medium, tool=claude, excerpt="Enter branch name:"

Evaluating 3 rules (first-match-wins):

  R-01  [no match]
        tool_id:        * (wildcard, always matches)
        prompt_type:    free_text NOT IN [yes_no, confirm_enter]  -- FAILED

  R-02  [no match]
        tool_id:        * (wildcard, always matches)
        prompt_type:    free_text in [free_text]  -- satisfied
        min_confidence: medium >= high             -- FAILED

  R-03  [no match]
        tool_id:        * (wildcard, always matches)
        prompt_type:    not specified (always matches)
        min_confidence: medium >= low              -- satisfied
        contains:       "branch" NOT found in excerpt  -- FAILED

Decision: require_human  (defaults.no_match -- no rule matched)
Idempotency key: b2c3d4e5f6a7b8c9
```

### Example: autonomy_mode override

```
Policy: my-policy (hash: d41d8cd98f00b204)
Autonomy mode: assist  [auto_reply is BLOCKED in this mode]
Input: type=yes_no, confidence=high, excerpt="Continue? [y/n]"

Evaluating 3 rules (first-match-wins):

  R-01  [MATCH]  auto_reply "y"  -- OVERRIDDEN by autonomy_mode=assist
        ...

Decision: require_human  (autonomy_mode=assist blocked auto_reply; substituted require_human)
Idempotency key: c3d4e5f6a7b8c9d0
```

---

## 13. Anti-Patterns and Warnings

### Do not use `auto_reply` for `free_text` without `allowed_choices`

A `free_text` prompt accepts arbitrary user input. Auto-replying with a fixed literal string is almost always wrong for this prompt type unless the set of expected inputs is constrained. If you must auto-reply to a `free_text` prompt, set `constraints.allowed_choices` to the exact set of valid responses, and document why the fixed response is safe.

```yaml
# WRONG: auto-replying to an unconstrained free_text prompt
- id: "R-bad"
  match:
    prompt_type: [free_text]
  action:
    type: auto_reply
    value: "yes"    # this will be injected for ANY free_text prompt in the session
```

```yaml
# BETTER: constrain to a specific prompt pattern
- id: "R-better"
  match:
    prompt_type: [free_text]
    contains: "Use default branch?"
    contains_is_regex: false
  action:
    type: auto_reply
    value: "main"
    constraints:
      allowed_choices: ["main", "master"]
```

### Do not use `".*"` as a `contains` regex

A regex of `.*` matches the empty string and every possible excerpt. Beyond being rejected by the validator, it communicates no information about what the rule is matching. Use `contains: ""` (empty string match, always true) only when you explicitly want "any excerpt", and document it.

### Do not put `deny` as a default

Setting `defaults.no_match: deny` means any unrecognised prompt will silently block execution with no operator notification. This is the worst failure mode: the supervised process freezes with no indication of what happened. Always use `require_human` as your default.

```yaml
defaults:
  no_match: deny      # WRONG: silent block on unknown prompts
```

```yaml
defaults:
  no_match: require_human   # CORRECT: humans handle the unknown
```

### Do not start with `auto_reply` rules

Start with all rules set to `require_human`. Run your workload, observe the prompts that appear in the decision trace, and promote individual rules to `auto_reply` once you have verified that the match criteria are narrow enough. Broad `auto_reply` rules on early iterations will auto-inject into prompts you did not intend.

Recommended promotion workflow:

1. Deploy with `autonomy_mode: off` — all prompts go to human regardless of rules.
2. Collect decision traces for a representative workload.
3. Identify repeating, high-confidence prompts that are safe to auto-reply.
4. Write specific rules for those prompts with `require_human`.
5. Switch to `autonomy_mode: assist` — test that routing is correct.
6. Promote selected rules to `auto_reply`.
7. Switch to `autonomy_mode: full` only when confident in coverage.

### Never set `yes_no_safe_default: "y"` in AtlasBridge config

This is a separate concern from the Policy DSL, but related: the AtlasBridge system config (`~/.atlasbridge/config.toml`) has a `prompts.yes_no_safe_default` field. Setting it to `"y"` is rejected by the Pydantic validator. The safe default for timed-out yes/no prompts is always `"n"`. Policy `auto_reply` rules are the correct mechanism for approved auto-yes responses.

### Prefer narrow `contains` matches over broad `prompt_type` matches

A rule that matches `prompt_type: [yes_no]` with no `contains` constraint will fire for every yes/no prompt across the entire session, regardless of what the prompt is about. This is rarely what you want. Always pair `prompt_type` rules with a `contains` constraint to limit scope:

```yaml
# RISKY: fires for ALL yes_no prompts
- id: "R-all-yesno"
  match:
    prompt_type: [yes_no]
  action:
    type: auto_reply
    value: "y"
```

```yaml
# SAFER: fires only for yes_no prompts containing "Continue"
- id: "R-continue"
  match:
    prompt_type: [yes_no]
    contains: "Continue"
  action:
    type: auto_reply
    value: "y"
```
