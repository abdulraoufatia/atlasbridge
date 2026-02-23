# GA Readiness Checklist

Assessment date: 2026-02-23

---

## Contract Freeze Status

| Surface | Frozen | Safety Test | Status |
|---------|--------|-------------|--------|
| Adapter API | Yes | `test_adapter_api_stability.py` | PASS |
| Channel API | Yes | `test_channel_api_stability.py` | PASS |
| Policy DSL | Yes | `test_policy_schema_stability.py` | PASS |
| CLI commands | Yes | `test_cli_surface_stability.py` | PASS |
| Dashboard routes | Yes | `test_dashboard_route_freeze.py` | PASS |
| Console surface | Yes | `test_console_surface_freeze.py` | PASS |
| Audit schema | Yes | `test_audit_schema_stability.py` | PASS |
| Config schema | Yes | `test_config_schema_stability.py` | PASS |

All 8 contract surfaces are frozen and enforced by CI.

---

## API Stability Commitment

- Stability levels defined in `docs/api-stability-policy.md`
- Deprecation policy: minimum 1 minor version cycle before removal
- Breaking change protocol: requires major version bump + safety test update
- Contract surfaces documented in `docs/contract-surfaces.md`

**Status:** PASS

---

## Coverage Metrics

| Metric | Value | Floor |
|--------|-------|-------|
| Global coverage | 85.80% | 80% |
| Core coverage | ~89% | 85% |
| Total tests | 2005 | — |
| Safety test files | 30 | 22 |

**Status:** PASS

---

## Threat Model Summary (Local-Only Attack Surface)

AtlasBridge v1.0 is local-only. The attack surface is:

| Boundary | Exposure | Mitigation |
|----------|----------|------------|
| Dashboard HTTP | Localhost only (127.0.0.1) | Loopback enforcement; `--i-understand-risk` for non-loopback |
| SQLite database | Local filesystem | Read-only dashboard access (`?mode=ro`) |
| Telegram/Slack tokens | Local config file | Token redaction in dashboard, logs, exports |
| PTY stdin injection | Local process | Nonce idempotency, TTL enforcement, session binding |
| Policy files | Local filesystem | Schema validation, `policy_version` field |

No network-facing services. No authentication required (network isolation is the boundary). No remote code execution path.

Full threat model: `docs/threat-model.md`

**Status:** PASS

---

## Backwards Compatibility

- Config migration from Aegis (`~/.aegis/`) is automatic
- Policy DSL v0 and v1 are both supported
- `AegisConfig` and `AegisError` aliases emit `DeprecationWarning`
- No breaking changes to frozen contract surfaces since v0.9.0

**Status:** PASS

---

## Release Reproducibility

- Build system: setuptools with `pyproject.toml`
- Publish: OIDC trusted publishing via GitHub Actions (tag-triggered)
- Version validation: tag must match `pyproject.toml` and `__init__.py`
- Pre-publish gates: lint, type check, test suite, twine check
- Artifacts: sdist + wheel, `.tcss` asset verification
- Publishing is idempotent: re-running for an already-published version exits cleanly

**Status:** PASS

---

## CI Matrix Coverage

| Job | Trigger | Platforms |
|-----|---------|-----------|
| CLI Smoke Tests | push/PR | ubuntu |
| Lint & Type Check | push/PR | ubuntu |
| Tests | push/PR | ubuntu 3.11, ubuntu 3.12, macOS 3.11, macOS 3.12, ubuntu 3.13, windows 3.12 (experimental) |
| Security Scan (bandit) | push/PR | ubuntu |
| Ethics & Safety Gate | push/PR | ubuntu |
| Build Distribution | push/PR | ubuntu |
| Packaging Smoke Test | push/PR | ubuntu (3.12) |
| Secret Scan | PR + weekly | ubuntu |
| Dependency Audit | PR + weekly | ubuntu |

**Status:** PASS

---

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| macOS | Stable | Full PTY support via ptyprocess |
| Linux | Stable | Full PTY support via ptyprocess, systemd integration |
| Windows | Experimental | ConPTY via pywinpty, requires `--experimental` flag |

**Status:** PASS

---

## Verdict

### PASS — ready for v1.0.0

All technical gates pass:

- 8/8 contract surfaces frozen and enforced by CI safety tests
- 2005 tests (1995 passed, 13 skipped), 85.80% global coverage
- 30 safety test files (floor: 22)
- Classifier updated to Production/Stable
- Version bumped to 1.0.0
- CI matrix covers macOS, Linux, Windows (experimental)
- Threat model well-defined for local-only scope
- Publishing pipeline is idempotent and tag-triggered
