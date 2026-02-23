# AtlasBridge Policy DSL v1

Policy DSL v1 is a backward-compatible extension of v0. All v0 files continue to work
unchanged. v1 adds compound conditions, session scoping, confidence bounds, and policy
inheritance.

> **Migrate an existing v0 file:**
> ```bash
> atlasbridge policy migrate ~/.atlasbridge/policy.yaml
> ```

---

## Quick start

```yaml
policy_version: "1"
name: my-policy
autonomy_mode: full

rules:
  - id: ci-auto-yes
    description: Auto-reply y to yes/no prompts in CI sessions.
    match:
      prompt_type: [yes_no]
      min_confidence: high
      session_tag: "ci"
    action:
      type: auto_reply
      value: "y"

  - id: catch-all
    match: {}
    action:
      type: require_human

defaults:
  no_match: require_human
  low_confidence: require_human
```

---

## What's new in v1

| Feature | YAML field | Description |
|---------|-----------|-------------|
| OR logic | `any_of` | Rule matches if ANY sub-criteria block passes |
| NOT logic | `none_of` | Rule fails if ANY sub-criteria block matches |
| Session scope | `session_tag` | Rule only applies to sessions with this exact label |
| Confidence upper bound | `max_confidence` | Rule only applies at or below this confidence level |
| Policy inheritance | `extends` | Inherit rules from a base policy file |

All v0 fields (`tool_id`, `repo`, `prompt_type`, `contains`, `contains_is_regex`,
`min_confidence`) continue to work with the same semantics.

---

## Schema reference

### `match` block (v1)

```yaml
match:
  # ---- v0 fields (unchanged) ----
  tool_id: "claude_code"          # exact match or "*" wildcard
  repo: "/home/user/project"      # prefix match on session cwd
  prompt_type: [yes_no, confirm_enter]
  contains: "continue"            # substring or regex
  contains_is_regex: false
  min_confidence: medium          # low | medium | high

  # ---- v1 additions ----
  max_confidence: medium          # upper bound: low | medium | high
  session_tag: "ci"               # exact match on session label

  any_of:                         # OR: match if ANY sub-block passes
    - prompt_type: [yes_no]
    - prompt_type: [confirm_enter]

  none_of:                        # NOT: fail if ANY sub-block matches
    - contains: "destroy"
    - contains: "delete"
```

**Constraint:** `any_of` and flat criteria are mutually exclusive on the same block.
Put each alternative in a sub-block. `none_of` has no such restriction.

### `any_of` — OR logic

```yaml
match:
  any_of:
    - prompt_type: [yes_no]
      min_confidence: high
    - prompt_type: [confirm_enter]
```

The rule matches if **ANY** sub-block passes (all criteria within a sub-block must pass, AND logic).

### `none_of` — NOT logic

```yaml
match:
  prompt_type: [yes_no]
  none_of:
    - contains: "rm -rf"
    - contains: "destroy"
```

The rule matches only if **NONE** of the `none_of` sub-blocks match. Useful for excluding
dangerous patterns from otherwise broad rules.

### `session_tag` — session scoping

Set the session label when launching a tool:

```bash
atlasbridge run claude --session-label ci
```

Then scope rules to that session:

```yaml
match:
  session_tag: "ci"
```

The match is **exact** (case-sensitive). If `session_tag` is not set on the rule, it matches
any session regardless of label.

### `max_confidence` — confidence upper bound

```yaml
match:
  max_confidence: "low"   # only match LOW confidence signals
```

Useful for routing ambiguous (low-confidence) prompts differently from clear ones:

```yaml
rules:
  - id: low-confidence-notify
    match:
      max_confidence: "low"
    action:
      type: notify_only

  - id: high-confidence-auto
    match:
      prompt_type: [yes_no]
      min_confidence: high
    action:
      type: auto_reply
      value: "y"
```

---

## Policy inheritance (`extends`)

```yaml
policy_version: "1"
name: child-policy
extends: "base.yaml"     # relative or absolute path

rules:
  - id: override-rule
    # Child rules are evaluated first (shadow base rules)
    ...
```

Rules from the child policy are prepended to the base rules. If a rule ID appears in both,
the child's version wins. The base policy's `defaults` are inherited if the child doesn't
override them.

**Cycle detection:** circular `extends` chains (`A → B → A`) raise a `PolicyParseError`.

**Constraint:** the base policy must also be v1 (v0 base policies are not supported).

---

## CLI

```bash
# Validate (v0 and v1)
atlasbridge policy validate policy_v1.yaml

# Test with session_tag
atlasbridge policy test policy_v1.yaml \
  --prompt "Deploy to prod? [y/n]" \
  --type yes_no --confidence high \
  --session-tag ci --explain

# Migrate v0 → v1 (in place)
atlasbridge policy migrate policy.yaml

# Migrate to a new file (preserve original)
atlasbridge policy migrate policy.yaml --output policy_v1.yaml

# Preview migration without writing
atlasbridge policy migrate policy.yaml --dry-run
```

---

## Evaluation semantics

1. Rules are evaluated in order — **first match wins**
2. For each rule, the `match` block is evaluated:
   - If `any_of` is set: OR logic (match if any sub-block passes)
   - Otherwise: flat AND logic (all criteria must pass)
3. If `none_of` is set: NOT filter applied after the primary match
4. `session_tag` is checked as exact case-sensitive match
5. `max_confidence` is an upper bound (`<=`); `min_confidence` is a lower bound (`>=`)
6. If no rule matches: `defaults.no_match` or `defaults.low_confidence` applies
7. All v0 evaluation semantics are preserved (regex timeout, idempotency, decision trace)

---

## Field reference (v1 additions)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `policy_version` | `"1"` | required | Must be `"1"` for v1 policies |
| `extends` | `str` | `null` | Path to base policy (relative or absolute) |
| `match.max_confidence` | `"low"` \| `"medium"` \| `"high"` | `null` | Upper bound on confidence level |
| `match.session_tag` | `str` | `null` | Exact match on session label |
| `match.any_of` | `list[match]` | `null` | OR: match if any sub-block passes |
| `match.none_of` | `list[match]` | `null` | NOT: fail if any sub-block matches |

**Inherited from v0** (unchanged): `tool_id`, `repo`, `prompt_type`, `contains`,
`contains_is_regex`, `min_confidence`, `action`, `defaults`, `autonomy_mode`, `name`.

See [Policy DSL v0 reference](policy-dsl.md) for full v0 field documentation.

---

## Validation rules

- Unknown fields in `match`, `action`, `defaults`, or root cause a parse error (`extra: "forbid"`)
- `any_of` and flat criteria (e.g. `prompt_type`) are mutually exclusive on the same block
- `none_of` can coexist with flat criteria or `any_of`
- `contains_is_regex: true` enforces a 100ms regex compilation timeout
- Circular `extends` chains raise `PolicyParseError`
- The base policy referenced by `extends` must also be v1
- Rule IDs must be unique within a policy (including inherited rules)
- `max_confidence` must be `>=` `min_confidence` if both are set (logical constraint)

---

## Edge cases

| Scenario | Behaviour |
|----------|-----------|
| Empty `match: {}` | Matches all prompts (catch-all) |
| Empty `any_of: []` | Never matches (no sub-blocks pass) |
| Empty `none_of: []` | Always passes (nothing excluded) |
| `any_of` with one sub-block | Equivalent to flat criteria |
| `min_confidence: high` + `max_confidence: high` | Only matches HIGH confidence exactly |
| `session_tag` not set on rule | Matches any session regardless of label |
| `session_tag` set but session has no label | Rule does not match |
| Overlapping rules | First-match-wins; order matters |
| `extends` with conflicting rule IDs | Child rule shadows base rule |
| `extends` with conflicting `defaults` | Child defaults override base defaults |

---

## Anti-patterns

**Overly broad `any_of`:**
```yaml
# BAD: matches everything — equivalent to an empty match
match:
  any_of:
    - {}
    - prompt_type: [yes_no]
```

**`none_of` without positive criteria:**
```yaml
# BAD: matches everything EXCEPT "sudo" — too broad
match:
  none_of:
    - contains: "sudo"
  action:
    type: auto_reply
    value: "y"
```

**Auto-reply to `free_text` with empty value:**
```yaml
# DANGEROUS: silently presses Enter on all free-text prompts
match:
  prompt_type: [free_text]
action:
  type: auto_reply
  value: ""
```

**Mismatched confidence bounds:**
```yaml
# USELESS: min > max means the rule can never match
match:
  min_confidence: high
  max_confidence: low
```

---

## Migration guide (v0 → v1)

The only required change is `policy_version: "0"` → `"1"`. All v0 syntax is valid v1.

```bash
atlasbridge policy migrate policy.yaml
```

To take advantage of v1 features:

1. Replace chains of similar rules with `any_of` OR blocks
2. Add `session_tag` to scope CI-specific rules
3. Use `max_confidence: low` to handle ambiguous prompts
4. Use `none_of` to exclude dangerous patterns from broad rules
5. Use `extends` to share a base policy across environments

---

## See also

- [Policy DSL v0 reference](policy-dsl.md)
- [Policy authoring guide](policy-authoring.md)
- [Example v1 policy](../config/policy.example_v1.yaml)
