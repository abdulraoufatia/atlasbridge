# Governance Evidence

AtlasBridge produces **verifiable governance evidence** from local decision logs, audit trails, and integrity data. This is distinct from compliance certification — AtlasBridge does not certify compliance with any framework.

---

## What It Is

Governance Evidence is an export of the artefacts AtlasBridge records during agent execution:

- Every prompt decision (auto, escalated, denied) with confidence and action taken
- Every escalation with risk level and action
- Integrity verification results (hash-chain status across audit log and decision trace)
- Policy snapshot (which rules were active and matched)
- Governance score (computed from decision and escalation data)
- File manifest with SHA-256 hashes for independent verification

These artefacts are generated deterministically from local SQLite and JSONL files — no network calls, no cloud dependency.

---

## What It Is Not

AtlasBridge does not:

- Certify SOC 2, ISO 27001, HIPAA, GDPR, or any other compliance framework
- Produce attestation reports
- Replace a compliance programme or auditor
- Guarantee regulatory compliance

The disclaimer appears on every export and in the dashboard UI.

---

## Accessing the Evidence Page

Open the dashboard and navigate to **Governance Evidence** in the top navigation.

```bash
atlasbridge dashboard start
# then open http://localhost:3737 → Governance Evidence
```

---

## Export Formats

| Format | Description |
|--------|-------------|
| JSON | Full evidence bundle — decisions, escalations, integrity report, replay references, policy snapshot, governance score |
| CSV | Tabular decisions and escalations — suitable for audit team review |
| Full Bundle | All of the above plus manifest.json (SHA-256 hashes of every file) and README.txt |

All exports redact known secret patterns (API keys, tokens, private keys, passwords) before writing.

---

## Bundle Contents

A full bundle includes:

```
evidence.json          — Full evidence data
decisions.csv          — Tabular decision log
integrity_report.json  — Hash-chain verification summary
manifest.json          — File list with SHA-256 hashes
README.txt             — Usage and disclaimer
```

### Verifying a bundle

Compute SHA-256 for each file and compare against `manifest.json`:

```bash
# macOS
shasum -a 256 evidence.json decisions.csv integrity_report.json README.txt

# Linux
sha256sum evidence.json decisions.csv integrity_report.json README.txt
```

Compare the output against the `files[].sha256` entries in `manifest.json`.

---

## Session Filtering

Exports can be scoped to a single session using the session filter on the Export tab. When a session is selected, only decisions, escalations, and traces from that session are included. The integrity report and governance score are also computed for that session only.

---

## Governance Score

The governance score (0–100) is computed from four weighted metrics:

| Metric | Weight | Description |
|--------|--------|-------------|
| Autonomous rate | 30% | Percentage of decisions handled automatically |
| Escalation rate (inverse) | 25% | Lower escalation rate → higher score |
| Policy coverage | 25% | Percentage of decisions matched by a named rule (not default) |
| Blocked high-risk | 20% | Count of blocked or escalated high-risk decisions (capped at 100) |

The score reflects how well the governance runtime performed — it is not a compliance indicator.

---

## Policy Pack Templates

The Policy Packs tab provides pre-configured policy bundles designed to support governance evidence collection aligned with common audit frameworks. Each pack:

- Is a policy preset, not a certification
- Includes an explicit disclaimer
- Lists the specific rule behaviours (enforce, require_human, advisory)

Available packs: SOC 2, ISO 27001, HIPAA, GDPR.

**These packs do not certify compliance.** Applying a pack produces governance evidence that _may support_ an audit narrative. Users are responsible for their compliance programmes.

---

## Integrity Verification

The Integrity Verification panel on the Overview tab shows:

- Overall hash-chain status (Verified / Warning / Failed)
- Per-component verification (audit log, decision trace, session registry)
- Total trace entries and trace hash summary

The hash-chain is append-only — any tampering with historical records will produce a verification failure.

---

## Redaction

All exports apply the following redaction rules before writing:

- API keys (`sk-*`, `ak-*`, `key-*`)
- Bearer tokens
- GitHub PATs (`ghp_*`, `ghu_*`, etc.)
- GitLab tokens (`glpat-*`)
- Slack tokens (`xoxb-*`, `xoxp-*`, etc.)
- AWS access keys (`AKIA*`)
- Private key blocks (`-----BEGIN PRIVATE KEY-----`)
- Long hex strings (≥64 chars)
- `password=`, `secret=`, `token=` patterns

Redacted values are replaced with `[REDACTED]`.
