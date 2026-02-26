# DESIGN ONLY — NO IMPLEMENTATION IN THIS RELEASE

# Enterprise Dashboard — Threat Model

**Maturity:** Design Document — No Implementation
**Phase:** C (Enterprise Dashboard)
**Trust model:** Cloud OBSERVES, local EXECUTES.
**Methodology:** STRIDE per attack surface

---

## Trust Boundaries

The dashboard operates within a strict trust hierarchy:

```
┌─────────────────────────────────────────────────────────┐
│  LOCAL RUNTIME (Full Trust — sole execution authority)   │
│  PTY access, shell, filesystem, policy eval, injection  │
└──────────────────────┬──────────────────────────────────┘
                       │ metadata only (one-way)
                       │ no PTY output, no secrets
                       v
┌─────────────────────────────────────────────────────────┐
│  CLOUD API (Observation Only — no execution path)       │
│  Stores metadata, computes risk, distributes policies   │
└──────────────────────┬──────────────────────────────────┘
                       │ read-only data
                       v
┌─────────────────────────────────────────────────────────┐
│  WEB DASHBOARD (Read-Only Governance)                   │
│  Displays sessions, audit, risk. Edits policies.        │
│  Cannot reach runtime. Cannot inject commands.           │
└─────────────────────────────────────────────────────────┘
```

**Fundamental constraint:** Even if the dashboard and cloud API are fully
compromised, the attacker gains no execution path to any local runtime. The
runtime validates all inbound data (policy signatures) and ignores unsigned or
malformed inputs.

---

## STRIDE Analysis by Surface

### Surface 1: REST API

#### Spoofing

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Stolen JWT used to access API | Attacker reads audit/session data for one org | Short JWT TTL (1h). Refresh tokens bound to IP range (optional). Immediate revocation via token blacklist. |
| Forged JWT | Full API access under forged identity | JWT signed with RS256 (asymmetric). Signing key in HSM/vault. Signature verified on every request. |
| Stolen API key | Agent sync access for one org | Keys hashed at rest (SHA-256). Key rotation without downtime. Scope-limited keys (sync-only vs. management). |

#### Tampering

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Modified audit events in transit | Corrupted compliance record | TLS 1.3 in transit. Hash chain validation on ingestion — any modification breaks the chain. |
| Tampered policy YAML | Malicious policy distributed to agents | Ed25519 signature on every policy. Runtime rejects unsigned or invalid-signature policies. |
| Modified API request body | Unauthorized data changes | Input validation via strict JSON schema. RBAC enforcement on every write endpoint. |

#### Repudiation

| Threat | Impact | Mitigation |
|--------|--------|------------|
| User denies making a policy change | Compliance dispute | All write operations logged with user_id, timestamp, and request_id. Audit events are append-only and hash-chained. |
| Agent denies submitting bad data | Integrity dispute | All agent submissions are signed with the agent's Ed25519 private key. Provenance is cryptographically verifiable. |

#### Information Disclosure

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Cross-tenant data leakage | One org sees another org's data | RLS in PostgreSQL (defense-in-depth). org_id from JWT only (never from request params). No cross-org query path in application layer. |
| Prompt excerpt leakage | Sensitive prompt content exposed | Excerpts truncated to 200 chars before sync. PTY output never synced. Dashboard displays explicit "No PTY output" disclaimer. |
| API key exposure in logs | Key used for unauthorized access | Keys never logged. Only key_prefix (8 chars) appears in audit. Full key shown once at creation, then only hash stored. |

#### Denial of Service

| Threat | Impact | Mitigation |
|--------|--------|------------|
| API flood | Dashboard unavailable | Per-org rate limiting at API gateway. Tiered limits (free/team/enterprise). HTTP 429 with Retry-After. |
| WebSocket connection exhaustion | Live updates unavailable | Connection limits per org. Idle timeout (5 min). Server-side connection cap per org per plan. |
| Large batch sync | Database overload | Batch size limit (100 records). Request body size limit (1MB). Async processing for large imports. |

#### Elevation of Privilege

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Viewer escalates to admin | Unauthorized policy changes | RBAC enforced in middleware, not just UI. Role stored in JWT, validated server-side. No client-side role switching. |
| Compromised cloud sends execution commands | Runtime executes attacker's commands | **Impossible by design.** Cloud has no execution path. No API, message, or protocol can instruct a runtime to execute a command. The runtime only accepts signed policies (which it evaluates locally) and advisory messages (which it may ignore). |

---

### Surface 2: Web UI

#### Cross-Site Scripting (XSS)

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Stored XSS via policy YAML display | Session hijacking | YAML rendered in read-only code editor (no HTML interpretation). All user content escaped before rendering. |
| Stored XSS via audit event payload | Cookie theft | Audit payloads rendered as JSON in monospace, not interpreted as HTML. React auto-escapes by default. |
| Reflected XSS via URL parameters | Phishing, session theft | Strict CSP with `script-src 'self'`. No inline scripts. No `eval()`. URL parameters validated and sanitized server-side. |

#### Content Security Policy

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data:;
  connect-src 'self' wss://api.atlasbridge.io;
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self';
```

- No inline scripts allowed.
- WebSocket connections only to the API origin.
- No framing (prevents clickjacking).

#### CORS

```
Access-Control-Allow-Origin: https://dashboard.atlasbridge.io
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Max-Age: 86400
```

- Strict origin allowlist (dashboard domain only).
- Credentials mode requires exact origin match.
- No wildcard origins.

---

### Surface 3: Authentication

#### Threats

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Session hijacking | Attacker acts as victim user | JWT stored in httpOnly, Secure, SameSite=Strict cookie. No localStorage for tokens. |
| Token replay | Reused token after logout | Token blacklist checked on every request. Short TTL (1h). Refresh rotation (each refresh invalidates the previous). |
| Brute force on email/password | Account takeover | Rate limiting on login endpoint (5 attempts/min per IP). Account lockout after 10 failures. MFA available. |
| OIDC provider compromise | Mass account takeover | OIDC token validation includes audience, issuer, and expiry checks. PKCE required for authorization code flow. Nonce verified to prevent replay. |
| RBAC bypass via direct API call | Unauthorized actions | RBAC enforced in server middleware, not client-side. Every endpoint handler checks role before processing. |

---

### Surface 4: Data Storage

#### Threats

| Threat | Impact | Mitigation |
|--------|--------|------------|
| SQL injection | Data exfiltration or corruption | Parameterized queries only (ORM-level enforcement). No raw SQL with user input. |
| Cross-tenant query via application bug | One org reads another's data | PostgreSQL RLS as defense-in-depth. `org_id` set from JWT in session variable, not from request. RLS policy on every tenant-scoped table. |
| Database backup exposure | Full data breach | Backups encrypted at rest (AES-256). Backup access restricted to infrastructure team. Audit log on backup access. |
| Audit event deletion | Compliance violation | Audit events are append-only. No DELETE endpoint exists. Database user for the application has no DELETE grant on audit tables. |

---

### Surface 5: Audit Ingestion

#### Threats

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Forged audit events | False compliance record | Events signed by agent's Ed25519 private key. Server verifies signature. Unsigned events rejected. |
| Hash chain manipulation | Undetected event insertion/deletion | Hash chain validated on ingestion. Breaks flagged immediately. Chain verification endpoint (`GET /audit/integrity`) for manual review. |
| Log injection (malicious payload content) | XSS via audit display, log forging | Payload stored as JSONB (structured). Rendered as escaped JSON in dashboard. No HTML interpretation. Payload size limit (64KB per event). |
| Replay attack (re-submit old events) | Duplicate events | Deduplication by event `id`. Repeated submissions are no-ops. |
| Event flooding from compromised agent | Storage exhaustion, cost | Per-org audit event rate limits (daily cap per plan). Agent-level rate limiting. Alerts on unusual volume. |

---

## Global Non-Negotiable Invariants

These invariants hold even under full cloud/dashboard compromise:

1. **Execution is local only.** No cloud component can execute commands, access
   PTYs, or inject replies. There is no API, protocol message, or code path
   that enables remote execution.

2. **Policy evaluation is local.** The cloud distributes policies, but the
   local runtime evaluates them. The cloud cannot override a policy decision.

3. **Unsigned policies are rejected.** The runtime verifies Ed25519 signatures
   against a pinned cloud public key. Invalid signatures cause immediate
   rejection with local audit logging.

4. **PTY output never leaves the runtime.** No sync endpoint, audit event, or
   protocol message carries PTY output. The dashboard explicitly disclaims this
   with a visible notice on every session detail screen.

5. **Secrets never appear in cloud data.** Private keys stay in the local
   keyring. API tokens are hashed at rest. No audit event or decision trace
   contains secret material.

6. **Audit events are append-only everywhere.** No mutation or deletion API
   exists. The database user has no DELETE grant. Hash chains provide tamper
   detection.

7. **Offline operation is unaffected.** Cloud unavailability does not block,
   pause, or degrade the local runtime. All cloud communication is
   asynchronous and timeout-protected.

8. **Tenant isolation is enforced at two layers.** Application-level org_id
   scoping from JWT plus PostgreSQL RLS. Neither layer alone is sufficient;
   both are required.

9. **The channel relay is independent of the cloud.** Telegram and Slack
   prompt delivery operates directly between the runtime and the messaging
   service. Cloud downtime does not affect human escalation.

10. **Runtime continues with the last known good state.** If the cloud sends a
    bad policy, bad config, or no data at all, the runtime continues with its
    current local state indefinitely.

---

## Incident Response Runbook Outline (Design)

### Scenario 1: Suspected Cross-Tenant Data Leak

1. Quarantine: Disable affected org's API access.
2. Investigate: Review API access logs filtered by org_id. Check RLS policy
   status. Verify `app.current_org_id` was set correctly in all code paths.
3. Scope: Determine which data was exposed and to which tenant.
4. Notify: Affected tenants within 24 hours per breach notification policy.
5. Remediate: Fix code path, add regression test, redeploy.
6. Post-mortem: Document root cause, add monitoring for the specific failure mode.

### Scenario 2: Audit Chain Integrity Break

1. Alert: `GET /audit/integrity` returns `break_count > 0`.
2. Investigate: Identify the agent and time window. Check if the agent was
   compromised or if it's a sync bug.
3. Quarantine: Flag affected events as `integrity_disputed`.
4. Recover: Request the agent to re-sync from its local SQLite (authoritative
   source). Re-validate chain.
5. If agent is compromised: Revoke agent credentials, issue new keypair.

### Scenario 3: Dashboard Session Hijacking

1. Detect: Unusual login location, concurrent sessions, or API calls after
   logout.
2. Invalidate: Revoke all tokens for the affected user. Force re-authentication.
3. Investigate: Review API access logs for unauthorized actions.
4. Scope: Determine if any policy changes were made. If so, verify signatures
   on distributed policies.
5. Remediate: Reset credentials, enable MFA if not already active.

### Scenario 4: Compromised Cloud Signing Key

1. **Critical severity.** Attacker can sign policies that runtimes will accept.
2. Rotate: Generate new Ed25519 keypair in HSM.
3. Distribute: Push new public key to all runtimes (requires manual config
   update or signed key-rotation message using the old key before revocation).
4. Revoke: Mark all policies signed with the old key as `signature_revoked`.
5. Re-sign: Re-sign all active policies with the new key and redistribute.
6. Audit: Review all policies distributed during the compromise window.

---

> **Reminder:** This is a design document. No security infrastructure exists.
> Cloud OBSERVES, local EXECUTES. The local runtime is the sole execution
> environment and continues operating safely even under full cloud compromise.
