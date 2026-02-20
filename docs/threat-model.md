# Aegis Implementation Notes: Relay Correctness

**Version:** 0.2.0
**Status:** Reference
**Last updated:** 2026-02-20

> **Important:** Aegis is not a security product. It is a remote interactive prompt relay. The notes below document correctness invariants and potential misuse scenarios for the relay mechanism — not a security posture claim.

---

## Overview

This document covers correctness concerns for the Aegis relay: how the system could behave incorrectly, and what implementation measures prevent that.

It does not claim Aegis is a security firewall or that it protects against any class of attack.

---

## STRIDE analysis (retained for reference)

The original STRIDE analysis below was written when Aegis was positioned as a "CLI firewall". It is retained as an implementation reference but should be read with the understanding that Aegis is a prompt relay, not a security enforcement layer.

STRIDE = **S**poofing · **T**ampering · **R**epudiation · **I**nformation Disclosure · **D**enial of Service · **E**levation of Privilege

---

## Assets

| Asset | Sensitivity | Description |
|-------|-------------|-------------|
| Telegram bot token | Critical | Full bot control; allows sending/receiving messages |
| Allowed user IDs | High | Defines who can approve operations |
| Config file | High | Contains bot token and policy paths |
| Policy rules | High | Defines what is allowed/denied/requires approval |
| Approval decisions | High | Records who approved what and when |
| Audit log | High | Evidence of all operations; must be tamper-evident |
| Active AI sessions | Medium | Tool calls in progress |
| SQLite database | Medium | Approval history, session state |
| Subprocess execution | Critical | Direct code execution on host machine |

---

## Trust Boundaries

```
┌─────────────────────────────────────────────────────────┐
│  Trusted: Local machine (user's process space)          │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │  AI Agent    │    │  Aegis Daemon│                  │
│  │  (claude)    │    │              │                  │
│  └──────────────┘    └──────────────┘                  │
│          │                   │                          │
│    [Tool call events]  [Policy decisions]               │
│                                                         │
└─────────────────────────────────────────────────────────┘
           │ HTTPS                    │ HTTPS
           │                          │
┌──────────┴──────────────────────────┴───────────────────┐
│  Semi-trusted: Telegram API (third-party HTTPS service) │
└─────────────────────────────────────────────────────────┘
           │
┌──────────┴──────────────────────────────────────────────┐
│  Trusted: User's phone (Telegram client)                │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Untrusted: AI agent prompts / tool arguments           │
│  (may contain adversarial content from external input)  │
└─────────────────────────────────────────────────────────┘
```

---

## STRIDE Analysis

### S — Spoofing

#### S-1: Telegram User Impersonation

**Scenario:** An attacker obtains the bot token and sends Telegram messages pretending to be the authorized user to approve malicious operations.

**Attack vector:** External (requires bot token)
**Likelihood:** Low (bot token must be stolen first)
**Impact:** Critical (can approve arbitrary operations)

**Mitigations:**
- Telegram user ID whitelist (`AEGIS_TELEGRAM_ALLOWED_USERS`) — only specific user IDs can interact with the bot
- Every incoming Telegram message is validated against the whitelist before processing
- Bot token is stored in `~/.aegis/config.toml` (mode 0600)

**Residual risk:** Low — whitelist enforcement makes spoofing non-trivial without also compromising the allowed user's Telegram account.

---

#### S-2: AI Agent Identity Spoofing

**Scenario:** A malicious process (not the actual Claude CLI) connects to the Aegis daemon socket and submits fake tool call events, potentially getting them approved.

**Attack vector:** Local (requires code execution on machine)
**Likelihood:** Medium (trivially done by any local process)
**Impact:** High (can inject arbitrary "tool calls" for approval)

**Mitigations:**
- Daemon socket uses process-owner authentication (same UID required)
- Session tokens generated per `aegis wrap` invocation, verified on each event
- Approval notifications include tool call hash; discrepancy would be visible

**Residual risk:** Medium — local code execution is a strong precondition. If attacker has local code exec, the machine is already compromised.

---

#### S-3: Config File Spoofing (Symlink Attack)

**Scenario:** Attacker replaces `~/.aegis/config.toml` with a symlink to a malicious config that changes the allowed user list or bot token.

**Attack vector:** Local
**Likelihood:** Low
**Impact:** High

**Mitigations:**
- Doctor checks file permissions (must be 0600)
- File is read with `O_NOFOLLOW` to prevent symlink following (implementation detail)
- Config loaded once at startup; reload via SIGHUP requires same permissions check

**Residual risk:** Low if file permissions are enforced.

---

### T — Tampering

#### T-1: Policy File Tampering

**Scenario:** An attacker (or malicious AI agent output) modifies `~/.aegis/policy.toml` to remove restrictive rules, allowing dangerous operations to proceed without approval.

**Attack vector:** Local (file write access)
**Likelihood:** Medium
**Impact:** Critical (bypasses entire approval layer)

**Mitigations:**
- Policy file should be 0600 (owner-only write)
- Policy reload via SIGHUP validates schema before applying
- Doctor checks policy file integrity
- Future: signed policy files with local key

**Residual risk:** Medium — any local process running as the same user can modify the file.

---

#### T-2: Audit Log Tampering

**Scenario:** Attacker modifies the audit log to remove evidence of approved operations or to alter decision records.

**Attack vector:** Local
**Likelihood:** Low
**Impact:** Medium (integrity / non-repudiation)

**Mitigations:**
- Audit log is append-only (file opened with O_APPEND)
- Each entry includes SHA-256 hash of the previous entry (hash chain)
- Doctor verifies hash chain integrity on `aegis doctor`
- Future: external log shipping to immutable store

**Residual risk:** Low for passive tampering; hash chain detects modifications.

---

#### T-3: Database Tampering

**Scenario:** Attacker modifies SQLite database to change approval decisions from `denied` to `approved`, or to delete audit records.

**Attack vector:** Local
**Likelihood:** Low
**Impact:** Medium

**Mitigations:**
- DB file should be 0600
- Audit log is separate from DB (audit.log file) and cannot be altered without detection
- Future: DB-level checksums

**Residual risk:** Medium — DB tampering is possible but does not bypass real-time approval flow (past decisions only).

---

#### T-4: Tool Call Argument Injection

**Scenario:** A malicious prompt causes the AI agent to issue tool calls with arguments crafted to bypass policy rules. Example: `write_file` with path `"../../.env"` intending to overwrite a secret file, relying on the policy using a non-normalized path comparison.

**Attack vector:** Via AI agent (prompt injection)
**Likelihood:** High (prompt injection is a known AI attack)
**Impact:** High

**Mitigations:**
- Policy engine normalizes all file paths before matching (`os.path.realpath`)
- Shell command policy rules use regex matching on the full, unexpanded command
- Critic agent flags unexpected argument patterns
- All tool arguments are validated against expected schemas before execution

**Residual risk:** Medium — sophisticated prompt injection may craft arguments that appear legitimate but aren't.

---

### R — Repudiation

#### R-1: Denial of Approval Action

**Scenario:** A user claims they did not approve a destructive operation, but Aegis has a record. The user challenges the audit log.

**Attack vector:** Social
**Likelihood:** Low
**Impact:** Medium

**Mitigations:**
- Audit log records Telegram user ID, timestamp, and approval message ID
- Hash chain prevents after-the-fact record insertion
- Telegram delivers messages with its own timestamps (separate evidence)

**Residual risk:** Low — multiple evidence sources make repudiation implausible.

---

#### R-2: Denial of Tool Call

**Scenario:** AI agent denies issuing a tool call. Aegis must prove the call was made.

**Attack vector:** Social
**Likelihood:** Low
**Impact:** Low

**Mitigations:**
- All tool calls logged with full arguments at interception point
- Session ID links tool call to specific `aegis wrap` invocation

**Residual risk:** Low.

---

### I — Information Disclosure

#### I-1: Secret Exfiltration via Tool Call Arguments

**Scenario:** AI agent issues a `read_file` call on `.env` or a private key file. Even if denied, the file content may appear in logs.

**Attack vector:** Via AI agent
**Likelihood:** High
**Impact:** Critical

**Mitigations:**
- Policy contains default deny rules for `*.env`, `*.pem`, `*.key`, `*credentials*`, `*secret*`
- Tool call arguments are logged at DEBUG level only (not INFO)
- File contents are NEVER logged (only path and size)
- Doctor checks for common secret files in unexpected locations

**Residual risk:** Medium — policy must be configured correctly; defaults help but don't cover all cases.

---

#### I-2: Bot Token Exposure in Logs/Environment

**Scenario:** The Telegram bot token appears in process environment, logs, or shell history.

**Attack vector:** Local log inspection
**Likelihood:** Medium (common misconfiguration)
**Impact:** Critical

**Mitigations:**
- Bot token stored in `~/.aegis/config.toml` (0600), not environment by default
- structlog masks values matching token patterns (regex: `\d+:[A-Za-z0-9_-]{35}`)
- `.env` in `.gitignore`
- `aegis config get telegram.bot_token` outputs `***REDACTED***` by default
- Doctor checks that `.env` is not in the git index

**Residual risk:** Low with correct configuration.

---

#### I-3: Approval Content Visible to Telegram

**Scenario:** Tool call arguments (potentially containing sensitive data) are included in Telegram approval messages sent to Telegram's servers.

**Attack vector:** Third-party service
**Likelihood:** Medium (by design — needs data for approval decision)
**Impact:** Medium

**Mitigations:**
- Approval messages include tool name, path, and operation type — not file contents
- File contents, secret values, and credential arguments are truncated/redacted before sending
- Telegram uses end-to-end encryption for secret chats (standard chats are encrypted in transit)

**Residual risk:** Medium — Telegram receives metadata about operations. This is an accepted trade-off for the MVP.

---

#### I-4: Audit Log Disclosure

**Scenario:** The audit log, stored on disk, is readable by other processes running as the same user.

**Attack vector:** Local
**Likelihood:** Low
**Impact:** Medium

**Mitigations:**
- Audit log file permissions should be 0600
- Doctor checks and warns if permissions are wrong

**Residual risk:** Low with correct permissions.

---

### D — Denial of Service

#### D-1: Approval Flood Attack

**Scenario:** A malicious AI agent (or runaway prompt) issues thousands of tool calls rapidly, flooding the Telegram channel with approval requests and making the system unusable.

**Attack vector:** Via AI agent
**Likelihood:** Medium (can happen accidentally with agentic loops)
**Impact:** Medium

**Mitigations:**
- Rate limiting: max N approvals per minute per session (configurable, default: 10/min)
- Session-level circuit breaker: after M consecutive denies, session is paused
- Telegram rate limit: Telegram's own API limits bot messages (30/sec globally, 1/sec per chat)
- Alert sent to Telegram when rate limit is approaching

**Residual risk:** Low with rate limiting in place.

---

#### D-2: Telegram Long-Poll Disruption

**Scenario:** Telegram API is unavailable, causing the daemon to fail and block all operations.

**Attack vector:** External (network/Telegram outage)
**Likelihood:** Low
**Impact:** High (all approvals would fail)

**Mitigations:**
- Configurable timeout action on Telegram unavailability: `deny` (default) or `allow` (dangerous)
- Exponential backoff on polling failures
- Local fallback: `aegis approvals approve <id>` via CLI works even without Telegram
- Daemon continues running; pending approvals are queued for when connectivity returns

**Residual risk:** Medium — Telegram outage blocks mobile approvals but CLI override remains.

---

#### D-3: Database Lock Corruption

**Scenario:** Aegis daemon crashes mid-write, leaving the SQLite database in an inconsistent state.

**Attack vector:** Internal failure
**Likelihood:** Low
**Impact:** Medium

**Mitigations:**
- SQLite WAL (Write-Ahead Logging) mode for crash-safe writes
- Doctor detects DB corruption and suggests repair
- DB is backed up before migrations
- Audit log is separate file — DB corruption doesn't affect audit integrity

**Residual risk:** Low.

---

### E — Elevation of Privilege

#### E-1: Arbitrary Shell Execution from Telegram

**Scenario:** An attacker sends a Telegram message containing a shell command and tricks Aegis into executing it.

**Attack vector:** External via Telegram
**Likelihood:** Low (requires bot token or whitelisted account)
**Impact:** Critical

**Mitigations:**
- Aegis NEVER executes arbitrary commands from Telegram messages
- Only structured responses are accepted: `approve`, `deny` with approval ID
- All Telegram input is parsed against a strict schema; anything else is rejected
- No `/exec`, `/run`, or similar commands in the bot

**Residual risk:** Very low — this is a design principle, not just a mitigation.

---

#### E-2: PTY Escape from Wrapped Process

**Scenario:** The wrapped AI CLI process escapes the PTY sandbox and gains control of the interceptor process.

**Attack vector:** Via AI agent / subprocess
**Likelihood:** Low (requires PTY vulnerability)
**Impact:** Critical

**Mitigations:**
- PTY adapter runs subprocess with restricted environment (no `AEGIS_*` vars passed through)
- Subprocess runs as same user (no privilege escalation possible)
- Signal handling: SIGTERM/SIGINT from subprocess doesn't kill daemon
- Future: namespaced execution (Phase 4)

**Residual risk:** Low.

---

#### E-3: Config Injection via Environment Variables

**Scenario:** An attacker sets `AEGIS_TELEGRAM_ALLOWED_USERS` in the environment to add themselves as an allowed user.

**Attack vector:** Local (requires ability to set env vars in daemon's environment)
**Likelihood:** Low
**Impact:** Critical

**Mitigations:**
- Environment vars documented as intentional override mechanism (expected behavior)
- Daemon logs the source of each config value at DEBUG level
- Running as separate user/service account in hardened deployments

**Residual risk:** Low — local code execution is the prerequisite.

---

## Risk Summary Matrix

| Threat | Likelihood | Impact | Risk Level | Status |
|--------|------------|--------|------------|--------|
| S-1 Telegram user impersonation | Low | Critical | Medium | Mitigated |
| S-2 AI agent identity spoofing | Medium | High | High | Partially mitigated |
| S-3 Config symlink attack | Low | High | Low | Mitigated |
| T-1 Policy file tampering | Medium | Critical | High | Partially mitigated |
| T-2 Audit log tampering | Low | Medium | Low | Mitigated |
| T-3 Database tampering | Low | Medium | Low | Mitigated |
| T-4 Tool call argument injection | High | High | **Critical** | Mitigated |
| R-1 Denial of approval action | Low | Medium | Low | Mitigated |
| R-2 Denial of tool call | Low | Low | Low | Mitigated |
| I-1 Secret exfiltration via args | High | Critical | **Critical** | Mitigated |
| I-2 Bot token in logs/env | Medium | Critical | High | Mitigated |
| I-3 Data visible to Telegram | Medium | Medium | Medium | Accepted |
| I-4 Audit log disclosure | Low | Medium | Low | Mitigated |
| D-1 Approval flood | Medium | Medium | Medium | Mitigated |
| D-2 Telegram outage | Low | High | Medium | Mitigated |
| D-3 DB lock corruption | Low | Medium | Low | Mitigated |
| E-1 Arbitrary shell from Telegram | Low | Critical | Medium | Mitigated |
| E-2 PTY escape | Low | Critical | Medium | Mitigated |
| E-3 Config injection via env | Low | Critical | Medium | Accepted |

---

## Supply Chain Risks

| Risk | Mitigation |
|------|------------|
| Malicious PyPI package in deps | Pin exact versions in production; use `pip-audit` |
| Compromised GitHub Actions runner | Use pinned action SHAs (`actions/checkout@v4` → SHA) |
| Dependabot PR introducing vulnerability | CI runs `bandit` and `pip-audit` on every PR |
| Typosquatting of `aegis-cli` | Publish to PyPI early to claim namespace |

---

## Concurrency Risks

| Risk | Mitigation |
|------|------------|
| Two Telegram responses for same approval | Approvals are processed with database row locking; first response wins |
| Race between approval and timeout | Atomic status transition in DB; timeout worker checks status before acting |
| Concurrent writes to audit log | Audit log writer serializes via `asyncio.Lock` |

---

## Accepted Risks

1. **I-3 (Telegram receives operation metadata)**: An accepted trade-off for usability. Mitigation: never send file contents.
2. **E-3 (Config injection via env)**: Documented, intentional behavior for CI/CD and scripting use cases.
3. **Local privilege (same user)**: Aegis does not protect against a fully compromised user account. The threat model assumes the user's machine and account are not already fully compromised.

---

## Threat Model Review Schedule

This threat model should be reviewed:
- Before each major version release
- When a new channel (WhatsApp) is added
- When the tool interception mechanism changes
- When a security incident occurs

Next review: v0.2.0 (MVP release)
