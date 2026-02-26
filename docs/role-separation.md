# Role Separation

**Version:** 1.6.x
**Status:** Stable

AtlasBridge defines three minimal roles for deployment environments where separation of duties is required. Roles are coarse-grained and deterministic — they do not introduce RBAC middleware or access control lists.

---

## Roles

| Role | Identifier | Capabilities |
|------|-----------|--------------|
| Execution | `execution` | Run AI agent under AtlasBridge supervision; no policy changes |
| Policy Author | `policy_author` | Write and validate policy files; no runtime execution |
| Audit Viewer | `audit_viewer` | Read audit logs and governance evidence; no write access |

These roles are not enforced by AtlasBridge at runtime (enforcement is at the filesystem level). They are documented here as a reference for deployment configurations.

---

## Role definitions

### Execution role

The execution role is responsible for running the AI agent under AtlasBridge supervision.

**Permitted:**
- `atlasbridge run <agent>` — start a supervised session
- `atlasbridge start / stop / status` — manage the daemon
- `atlasbridge sessions / logs` — observe active sessions
- `atlasbridge doctor` — health checks
- `atlasbridge autopilot enable/disable` — toggle autopilot (kill switch)
- `atlasbridge autopilot mode <mode>` — change autonomy mode

**Not permitted by role convention:**
- Editing policy files
- Reading raw audit events

**Typical OS enforcement:**
- Policy files owned by `policy_author` user, mode 0640 (group read-only for execution user)
- Audit files owned by `atlasbridge` service user, readable by `audit_viewer` group

---

### Policy Author role

The policy author writes and validates policy files. They do not run the agent directly.

**Permitted:**
- `atlasbridge policy validate <file>` — validate a policy file
- `atlasbridge policy test <file> --prompt "..." --type ...` — simulate policy evaluation
- Read and write policy files
- `atlasbridge autopilot explain --last N` — review decision history

**Not permitted by role convention:**
- Starting the daemon or running agents
- Reading raw audit events

---

### Audit Viewer role

The audit viewer has read-only access to governance evidence. They cannot change any runtime state.

**Permitted:**
- `atlasbridge audit export` — export audit events
- `atlasbridge audit verify` — verify hash chain integrity
- `atlasbridge replay session <id>` — replay a session against a policy
- Dashboard read-only pages (sessions, audit, governance evidence)

**Not permitted by role convention:**
- Starting or stopping the daemon
- Changing policy files
- Using operator write actions (kill switch, mode change)

---

## Invariants preserved by all roles

Role separation does not weaken any correctness invariant:

- Hash chain is always appended, regardless of which role writes
- Idempotency guard (`decide_prompt()`) is enforced at the database level
- TTL and session binding are enforced at the database level
- No role can bypass the policy evaluation path

---

## Filesystem enforcement example

```bash
# Create role-specific system users
useradd -r atlasbridge-exec   # execution role
useradd -r atlasbridge-policy # policy author role
useradd -r atlasbridge-audit  # audit viewer role

# Policy files: policy author writes, execution reads
chown atlasbridge-policy:atlasbridge-exec /etc/atlasbridge/policy.yaml
chmod 0640 /etc/atlasbridge/policy.yaml

# Audit log: execution writes, audit viewer reads
chown atlasbridge-exec:atlasbridge-audit ~/.atlasbridge/atlasbridge.db
chmod 0640 ~/.atlasbridge/atlasbridge.db

# Config file: execution only
chown atlasbridge-exec:atlasbridge-exec ~/.atlasbridge/config.toml
chmod 0600 ~/.atlasbridge/config.toml
```

---

## Dashboard operator controls

The dashboard operator write actions (kill switch, mode change) are accessible to anyone who can reach the dashboard on localhost. For role-based access to operator controls in multi-user environments:

1. Run the dashboard on a port accessible only to the execution role user
2. Or restrict dashboard startup to the execution role in the systemd unit

The dashboard does not implement per-user authentication. It relies on OS-level isolation (loopback binding) as the trust boundary.

---

## High-assurance deployments

In high-assurance environments, combine role separation with the `high_assurance` deployment profile:

```bash
ATLASBRIDGE_PROFILE=high_assurance atlasbridge run claude
```

The `high_assurance` profile adds:
- Autonomy mode defaults to `off` — no auto-injection without explicit policy
- Policy file is required at startup
- Tighter escalation rate limits

See [deployment-profiles.md](deployment-profiles.md) for the full reference.
