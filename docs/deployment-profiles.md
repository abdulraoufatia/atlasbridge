# Deployment Profiles

**Version:** 1.6.x
**Status:** Stable

AtlasBridge ships two built-in deployment profiles. A profile is a configuration overlay — same binary, same architecture, same invariants. Profiles only adjust defaults.

---

## Profiles

| Profile | Autonomy default | Escalation | Rate limit | Use case |
|---------|-----------------|------------|-----------|----------|
| `core` | `assist` | require_human on no-match | 10/min | Standard development |
| `high_assurance` | `off` | require_human always | 5/min | CI/CD, regulated workflows |

---

## How to use

```bash
# Environment variable (recommended for CI)
ATLASBRIDGE_PROFILE=high_assurance atlasbridge run claude

# CLI flag
atlasbridge run claude --profile high_assurance

# Config file (config.toml)
[runtime]
profile = "high_assurance"
```

Priority order (highest first): CLI flag > env var > config file > default (`core`).

---

## Profile files

Profile YAML files live in `config/profiles/`:

| File | Description |
|------|-------------|
| `config/profiles/core.yaml` | Default profile — full capabilities, sensible defaults |
| `config/profiles/high_assurance.yaml` | Stricter defaults for regulated environments |

---

## core profile

The default profile. Suitable for standard development workflows.

Key defaults:
- Autonomy mode: `assist` (policy handles allowed prompts; others escalate)
- No-match action: `require_human`
- Max escalations/min: 10
- Audit rotation: 10 MB
- Replay hash validation: `strict`
- Telemetry: disabled

---

## high_assurance profile

Stricter defaults for environments where every action requires explicit oversight.

Key differences from `core`:
- Autonomy mode: `off` (all prompts escalated; no auto-injection without policy override)
- Max auto-replies per rule: 3 (vs 10 in core)
- Max escalations/min: 5 (vs 10)
- Escalation timeout: 120s (vs 300s)
- Policy file: required (runtime fails to start without one)
- Unknown policy versions: rejected

---

## Invariants unchanged by profiles

Profiles adjust defaults only. The following are **never** affected by profile selection:

- Nonce idempotency guard (`decide_prompt()` atomic SQL)
- TTL enforcement in database WHERE clause
- Cross-session injection prevention (prompt_id + session_id binding)
- Allowlisted channel identity enforcement
- Echo loop suppression (500ms window)
- Append-only audit log with hash chain
- Session persistence across daemon restarts

---

## Custom profiles

Profiles are standard YAML files. To create a custom profile:

```bash
cp config/profiles/core.yaml config/profiles/my-profile.yaml
# edit my-profile.yaml
ATLASBRIDGE_PROFILE=my-profile atlasbridge run claude
```

Custom profiles inherit all unspecified values from `core`.

---

## Profile validation

```bash
atlasbridge config validate --profile high_assurance
```

Validation checks:
- Required fields present
- Autonomy mode is a valid enum value
- No unknown keys
- Invariant-breaking combinations rejected (e.g., `hash_chain_enabled: false` is an error)
