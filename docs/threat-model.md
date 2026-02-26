# AtlasBridge Correctness Notes: Relay and Runtime

**Version:** 1.6.x
**Status:** Reference
**Last updated:** 2026-02-26

> **Important:** AtlasBridge is not a security product. It is a policy-driven autonomous runtime with a human-in-the-loop relay. The notes below document correctness invariants and known misuse scenarios — not a security posture claim.

---

## Overview

This document covers correctness concerns for the AtlasBridge runtime: how the system could behave incorrectly, and what implementation measures prevent that.

It does not claim AtlasBridge is a security firewall or that it protects against any class of attack.

---

## STRIDE analysis (retained for reference)

The STRIDE analysis below documents misuse scenarios. It is retained as an implementation reference, not a security certification.

STRIDE = **S**poofing · **T**ampering · **R**epudiation · **I**nformation Disclosure · **D**enial of Service · **E**levation of Privilege

---

## Assets

| Asset | Sensitivity | Description |
|-------|-------------|-------------|
| Telegram bot token | Critical | Full bot control; allows sending/receiving messages |
| Slack bot token | Critical | Full Slack workspace access for the bot |
| Allowed user IDs | High | Defines who can approve operations |
| Config file | High | Contains bot tokens and policy paths |
| Policy rules | High | Defines what is allowed/denied/requires approval |
| Audit log | High | Evidence of all operations; must be tamper-evident |
| Autopilot state | High | Kill switch and autonomy mode; operator controls |
| Dashboard session | Medium | Localhost-only; controls runtime via operator write actions |
| SQLite database | Medium | Prompt history, session state, audit events |
| Active AI sessions | Medium | Tool calls in progress |
| Subprocess execution | Critical | Direct code execution on host machine |

---

## Trust Boundaries

```
┌──────────────────────────────────────────────────────────┐
│  Trusted: Local machine (user's process space)           │
│                                                          │
│  ┌──────────────────┐    ┌───────────────────────────┐  │
│  │  AI Agent (claude)│    │  AtlasBridge Daemon       │  │
│  └──────────────────┘    │  + Autopilot Engine        │  │
│          │               │  + Policy Evaluator        │  │
│    [PTY output]          │  + Audit Writer            │  │
│                          └───────────────────────────┘  │
│                                     │                    │
│                          ┌──────────┴───────────────┐   │
│                          │  Dashboard (127.0.0.1)   │   │
│                          │  + Operator Controls     │   │
│                          └──────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
           │ HTTPS                         │ HTTPS
           │                               │
┌──────────┴──────────┐       ┌────────────┴───────────────┐
│  Telegram API       │       │  Slack API                 │
│  (third-party HTTPS)│       │  (third-party HTTPS)       │
└──────────┬──────────┘       └────────────┬───────────────┘
           │                               │
┌──────────┴──────────────────────────────┴───────────────┐
│  Trusted: User's phone / Slack client                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Untrusted: AI agent prompts / tool arguments           │
│  (may contain adversarial content from external input)  │
└─────────────────────────────────────────────────────────┘
```

---

## STRIDE Analysis

### S — Spoofing

#### S-1: Channel User Impersonation

**Scenario:** An attacker obtains the bot token and sends messages pretending to be the authorised user, approving malicious operations.

**Attack vector:** External (requires bot token)
**Likelihood:** Low
**Impact:** Critical

**Mitigations:**
- Allowlisted user IDs (`ATLASBRIDGE_TELEGRAM_ALLOWED_USERS` / Slack user ID allowlist)
- Every incoming message validated against the allowlist before processing
- Bot token stored with 0600 permissions

**Residual risk:** Low — allowlist enforcement makes spoofing non-trivial.

---

#### S-2: Dashboard Operator Spoofing

**Scenario:** An attacker on the same machine sends crafted requests to the dashboard operator endpoints (`/api/operator/kill-switch`, `/api/operator/mode`) to change the autopilot state without authorisation.

**Attack vector:** Local (loopback only; requires local code execution)
**Likelihood:** Low
**Impact:** High

**Mitigations:**
- Dashboard binds to `127.0.0.1` only — no external network access
- CSRF protection: server sets `csrf-token` cookie; client must echo it in `x-csrf-token` header
- Rate limiting: 10 operator actions per minute per IP
- Bare `curl` without cookie/header returns 403

**Residual risk:** Low — local code execution is the prerequisite; loopback-only eliminates remote attack.

---

#### S-3: AI Agent Identity Spoofing

**Scenario:** A malicious local process submits fake prompt events to the daemon.

**Attack vector:** Local
**Likelihood:** Medium
**Impact:** High

**Mitigations:**
- PTY adapter observes output on its own PTY file descriptor — not a shared socket
- Session tokens generated per `atlasbridge run` invocation
- Audit log records every event; detectable in replay

**Residual risk:** Medium — local code execution is the prerequisite.

---

### T — Tampering

#### T-1: Policy File Tampering

**Scenario:** A malicious process modifies the policy file to remove restrictive rules.

**Attack vector:** Local (file write access)
**Likelihood:** Medium
**Impact:** Critical

**Mitigations:**
- Policy file should be 0600
- Policy reload validates schema before applying
- Invalid policy falls back to safe default (`require_human`)

**Residual risk:** Medium — local write access is sufficient.

---

#### T-2: Audit Log Tampering

**Scenario:** Attacker modifies stored audit events to remove evidence.

**Attack vector:** Local
**Likelihood:** Low
**Impact:** Medium

**Mitigations:**
- SHA-256 hash chain: each event includes `prev_hash` and its own `hash`
- `atlasbridge audit verify` re-computes and validates the entire chain
- Deletion, reordering, payload modification, and phantom insertion are all detectable

**Residual risk:** Low — hash chain detects all in-place modifications.

---

#### T-3: Autopilot State Tampering via Dashboard DB

**Scenario:** Attacker directly modifies `dashboard.db` to flip the autopilot state without using operator controls.

**Attack vector:** Local
**Likelihood:** Low
**Impact:** High

**Mitigations:**
- Operator write actions call `atlasbridge autopilot` CLI → state change audited in `atlasbridge.db`
- Operator audit log in `dashboard.db` records every write action
- Runtime reads autopilot state from `atlasbridge.db`, not `dashboard.db`

**Residual risk:** Low — DB-level tampering bypasses the audit trail but not runtime invariants.

---

#### T-4: Tool Call Argument Injection

**Scenario:** A malicious prompt causes the AI agent to issue tool calls with crafted arguments designed to bypass policy rules.

**Attack vector:** Via AI agent (prompt injection)
**Likelihood:** High
**Impact:** High

**Mitigations:**
- Policy engine normalises file paths before matching
- Shell command rules use regex on full unexpanded command
- Prompt injection does not change the deterministic policy evaluation result

**Residual risk:** Medium — sophisticated injection may craft arguments that appear legitimate.

---

### R — Repudiation

#### R-1: Denial of Operator Action

**Scenario:** An operator claims they did not change the autonomy mode.

**Mitigations:**
- Operator audit log in `dashboard.db`: every POST to `/api/operator/*` recorded with timestamp, body, and result
- Autopilot state changes recorded in `atlasbridge.db` (hash-chained)
- `atlasbridge autopilot explain --last N` shows full history

**Residual risk:** Low — two independent audit trails.

---

#### R-2: Denial of Approval Action

**Scenario:** User claims they did not approve a destructive operation.

**Mitigations:**
- Audit log records channel identity, timestamp, nonce, and value
- Hash chain prevents after-the-fact record insertion
- Telegram/Slack deliver messages with their own timestamps (independent evidence)

**Residual risk:** Low.

---

### I — Information Disclosure

#### I-1: Secret Exfiltration via Tool Call Arguments

**Scenario:** AI agent reads `.env` or a private key; content appears in logs or channel messages.

**Mitigations:**
- Default policy contains deny rules for `*.env`, `*.pem`, `*.key`, `*credentials*`, `*secret*`
- `SecretRedactor` strips tokens matching known patterns before audit logging
- File contents are never logged (only path and size)
- Audit writer uses `safe_excerpt()` — first 20 chars, token-redacted

**Residual risk:** Medium — policy must be configured correctly.

---

#### I-2: Stack Trace Disclosure in Dashboard

**Scenario:** An unhandled error in the dashboard API leaks internal details to clients.

**Mitigations:**
- Production error handler returns generic `"Internal Server Error"` for all 5xx responses
- Stack traces and internal error messages not included in responses
- `err.message` preserved only for 4xx (client errors) where user-facing

**Residual risk:** Very low.

---

#### I-3: Bot Token Exposure in Logs

**Scenario:** Telegram or Slack bot token appears in process environment, logs, or shell history.

**Mitigations:**
- Tokens stored in config file (0600), not environment by default
- structlog masks values matching token patterns
- `atlasbridge config get telegram.bot_token` outputs `***REDACTED***`

**Residual risk:** Low with correct configuration.

---

### D — Denial of Service

#### D-1: Operator Endpoint Abuse

**Scenario:** Automated script hammers `/api/operator/kill-switch` repeatedly.

**Mitigations:**
- Rate limiter: 10 requests per minute per IP per path
- CSRF token required — automated scripts without cookie jar blocked at 403
- 429 response with `Retry-After` header

**Residual risk:** Low.

---

#### D-2: Approval Flood Attack

**Scenario:** Runaway AI agent issues thousands of tool calls, flooding the escalation channel.

**Mitigations:**
- Rate limiting: max N escalations per minute per session (default 10)
- Circuit breaker: pause autopilot after M consecutive escalations (default 20)
- Kill switch: operator can disable autopilot from dashboard or CLI

**Residual risk:** Low with rate limiting and kill switch.

---

#### D-3: Oversized Payload Attack

**Scenario:** Attacker sends a large JSON payload to the dashboard API.

**Mitigations:**
- `express.json({ limit: "32kb" })` — payloads larger than 32 KB rejected with 413
- `urlencoded({ limit: "32kb" })` on URL-encoded endpoints

**Residual risk:** Very low.

---

#### D-4: Channel Outage

**Scenario:** Telegram or Slack API unavailable; daemon blocks, all escalations stall.

**Mitigations:**
- Configurable timeout action: `deny` (default) or `require_human`
- Exponential backoff on polling failures
- Local fallback: `atlasbridge autopilot disable` works without channel

**Residual risk:** Medium — channel outage blocks mobile approvals; CLI override remains.

---

### E — Elevation of Privilege

#### E-1: Arbitrary Shell Execution from Channel

**Scenario:** Attacker sends a channel message containing a shell command.

**Mitigations:**
- AtlasBridge never executes arbitrary commands from channel messages
- Operator write actions use `execFile` (not `exec`) — no shell interpolation
- Only structured responses accepted (approve/deny with prompt ID)

**Residual risk:** Very low — by design.

---

#### E-2: Content-Type Bypass on Operator Endpoints

**Scenario:** Attacker bypasses content-type validation and injects a non-JSON body.

**Mitigations:**
- Content-type middleware enforces `application/json` on all POST/PUT/PATCH to `/api`
- Non-JSON content type rejected with 415 before request body is parsed

**Residual risk:** Very low.

---

## Risk Summary Matrix

| Threat | Likelihood | Impact | Risk | Status |
|--------|------------|--------|------|--------|
| S-1 Channel user impersonation | Low | Critical | Medium | Mitigated |
| S-2 Dashboard operator spoofing | Low | High | Low | Mitigated |
| S-3 AI agent identity spoofing | Medium | High | Medium | Partially mitigated |
| T-1 Policy file tampering | Medium | Critical | High | Partially mitigated |
| T-2 Audit log tampering | Low | Medium | Low | Mitigated |
| T-3 Autopilot state DB tampering | Low | High | Low | Mitigated |
| T-4 Tool call argument injection | High | High | **Critical** | Mitigated |
| R-1 Denial of operator action | Low | Medium | Low | Mitigated |
| R-2 Denial of approval | Low | Medium | Low | Mitigated |
| I-1 Secret exfiltration | High | Critical | **Critical** | Mitigated |
| I-2 Stack trace disclosure | Low | Low | Very Low | Mitigated |
| I-3 Bot token in logs | Medium | Critical | High | Mitigated |
| D-1 Operator endpoint abuse | Low | Medium | Low | Mitigated |
| D-2 Approval flood | Medium | Medium | Medium | Mitigated |
| D-3 Oversized payload | Low | Medium | Very Low | Mitigated |
| D-4 Channel outage | Low | High | Medium | Partially mitigated |
| E-1 Arbitrary shell from channel | Low | Critical | Medium | Mitigated |
| E-2 Content-type bypass | Low | Low | Very Low | Mitigated |

---

## Correctness Invariants (not security features)

These invariants exist to keep the relay working correctly:

| # | Invariant | Implementation |
|---|-----------|----------------|
| 1 | No duplicate injection | `decide_prompt()` atomic SQL guard (`nonce_used = 0`) |
| 2 | No expired injection | `expires_at > datetime('now')` in WHERE clause |
| 3 | No cross-session injection | `prompt_id + session_id` binding verified |
| 4 | No unauthorised injection | Allowlisted channel identities only |
| 5 | No echo loops | 500ms suppression window after every injection |
| 6 | No lost prompts | Daemon restart reloads pending from SQLite |
| 7 | Bounded memory | Rolling 4096-byte output buffer |

---

## Accepted Risks

1. **Local privilege (same user):** AtlasBridge does not protect against a fully compromised user account.
2. **Channel metadata visible to Telegram/Slack:** Accepted trade-off; never send file contents.
3. **Config injection via env:** Documented, intentional behavior for CI/CD scripting.

---

## Review Schedule

This document should be reviewed before each major version release, when a new channel is added, when operator controls change, or when a security incident occurs.

Next review: v2.0.0
