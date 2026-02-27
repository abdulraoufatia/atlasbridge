# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.x.x   | Yes       |

Once v1.0.0 is released, only the latest minor release will receive security patches.

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Please report security issues via one of these channels:

1. **GitHub Private Vulnerability Reporting** (preferred):
   Go to the [Security tab](../../security/advisories/new) of this repository
   and click "Report a vulnerability".

2. **Email**: security@atlasbridge.dev *(placeholder — update before public release)*

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigations

### What to Expect

- Acknowledgement within **48 hours**
- Status update within **7 days**
- Fix timeline communicated as soon as assessed
- Credit in the security advisory (if desired)

## Security Design Principles

AtlasBridge is designed around correctness invariants. Key principles:

- **Local-first**: No data leaves your machine unless you configure a channel (e.g., Telegram).
- **Allowlist by default**: Operations are denied unless explicitly permitted by policy.
- **Append-only audit log**: All decisions are permanently recorded and tamper-evident.
- **No secret exposure**: Secrets are never logged, displayed, or transmitted.
- **Telegram whitelist**: Only pre-approved Telegram user IDs can approve operations.
- **No shell from mobile**: The Telegram channel cannot execute arbitrary shell commands.
- **Rate limiting**: Approval channels are rate-limited to prevent abuse.

## Threat Model

See [docs/threat-model.md](docs/threat-model.md) for the full STRIDE analysis.

## Red Team Report

See [docs/red-team-report.md](docs/red-team-report.md) for known attack vectors and mitigations.
