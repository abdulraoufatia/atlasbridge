# API Stability Policy

This document defines what "frozen" means for AtlasBridge contract surfaces, and the rules for deprecation and breaking changes.

## Stability Levels

| Level | Meaning |
|-------|---------|
| **Stable** | Frozen. Will not change without a major version bump. Covered by safety tests. |
| **Experimental** | May change between minor versions. Marked `[EXPERIMENTAL]` in CLI help text. Not covered by contract stability tests. |
| **Internal** | No stability guarantee. Private APIs (prefixed with `_`) may change at any time. |

## What "Frozen" Means

A frozen contract surface guarantees:

1. **No removals** — Existing methods, fields, enum members, and CLI commands will not be removed.
2. **No signature changes** — Method parameter names, types, and return types will not change.
3. **No semantic changes** — Behavior for existing inputs will not change (e.g., `PolicyDefaults().no_match` will always be `"require_human"`).
4. **Additive only** — New methods, fields, or enum members may be added, but existing ones are immutable.

## Safety Test Enforcement

Every frozen surface has a corresponding test file in `tests/safety/`:

| Surface | Test File |
|---------|-----------|
| Adapter API | `test_adapter_api_stability.py` |
| Channel API | `test_channel_api_stability.py` |
| Policy DSL | `test_policy_schema_stability.py` |
| Audit Log | `test_audit_schema_stability.py` |
| Config | `test_config_schema_stability.py` |
| CLI Surface | `test_cli_surface_stability.py` |
| Safe Defaults | `test_safe_defaults_immutable.py` |
| Injection Path | `test_no_injection_without_policy.py` |
| Release Artifacts | `test_release_artifacts.py` |
| Version Sync | `test_version_sync.py` |

These tests run in the `ethics-safety-gate` CI job. A failing safety test blocks the build.

## Deprecation Rules

1. **Announce** — Add a `DeprecationWarning` with a message naming the replacement and removal version.
2. **Grace period** — Deprecated APIs remain functional for at least one minor version.
3. **Remove** — Remove in the next major version (or the version stated in the warning).

Current deprecations:

| Deprecated | Replacement | Removal |
|------------|-------------|---------|
| `AegisConfig` | `AtlasBridgeConfig` | v1.0 |
| `AegisError` | `AtlasBridgeError` | v1.0 |
| `AEGIS_*` env vars | `ATLASBRIDGE_*` env vars | v1.0 |

## Breaking Change Policy

A breaking change is any change that would cause existing code or configuration to stop working:

- Removing a CLI command or subcommand
- Removing a method from `BaseAdapter` or `BaseChannel`
- Changing the SQLite schema in a non-additive way
- Changing a safety-critical default value
- Removing a Policy DSL field or enum member
- Changing hash chain algorithms (audit or decision trace)

Breaking changes require:

1. A major version bump (e.g., v1.0 → v2.0)
2. A migration path documented in `docs/upgrade.md`
3. Updating the corresponding safety test

## Environment Variables

The following environment variables are frozen and will not be removed:

- `ATLASBRIDGE_TELEGRAM_BOT_TOKEN`
- `ATLASBRIDGE_TELEGRAM_ALLOWED_USERS`
- `ATLASBRIDGE_SLACK_BOT_TOKEN`
- `ATLASBRIDGE_SLACK_APP_TOKEN`
- `ATLASBRIDGE_SLACK_ALLOWED_USERS`
- `ATLASBRIDGE_LOG_LEVEL`
- `ATLASBRIDGE_DB_PATH`
- `ATLASBRIDGE_APPROVAL_TIMEOUT_SECONDS`

Legacy `AEGIS_*` equivalents are honoured as fallbacks until v1.0.
