# Prompt Detection and Routing

**Version:** 0.2.0
**Status:** Implemented

> Note: Aegis is not a policy engine or security firewall. This document describes how Aegis detects that a process is waiting for input and decides how to handle it.

---

## Prompt detection

`aegis/policy/detector.py` — `PromptDetector`

Three-layer detection:

1. **Structured** (confidence 1.0) — tool emits explicit event; extension point for future use
2. **Regex patterns** (confidence 0.65–0.95) — matches output against pattern sets per prompt type
3. **Blocking heuristic** (confidence 0.60) — fires when no output for `stuck_timeout_seconds`

See `docs/claude-adapter-spec.md` §3 for full pattern lists.

### Threshold

Default: `0.65`. Configurable via `adapters.claude.detection_threshold` in config.

---

## Routing

`aegis/policy/engine.py` — `PolicyEngine`

Simple dispatch:

| Situation | Action |
|-----------|--------|
| Any detected prompt (except free-text when disabled) | Forward to Telegram |
| `TYPE_FREE_TEXT` when `free_text_enabled = false` | Auto-inject empty string |

That's the entire routing logic. There are no rules, allowlists, blocklists, or risk tiers.

---

## Safe defaults

Injected when the user doesn't reply within `timeout_seconds`:

| Type | Default |
|------|---------|
| YES_NO | `n` (cannot be overridden to `y`) |
| CONFIRM_ENTER | `\n` (Enter) |
| MULTIPLE_CHOICE | `1` |
| FREE_TEXT | `` (empty) |
| UNKNOWN | `n` |
