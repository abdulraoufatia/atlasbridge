# Changelog

All notable changes to Aegis will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.1.0] — 2026-02-20

### Added

- Repository scaffold and project structure
- MIT License
- SECURITY.md with responsible disclosure process
- CONTRIBUTING.md with branching and commit conventions
- CODE_OF_CONDUCT.md (Contributor Covenant v2.1)
- .env.example with all configurable parameters
- .gitignore for Python projects
- GitHub Actions CI workflow
- Dependabot configuration
- GitHub Issue templates (bug report, feature request, security)
- Pull request template
- CLI UX design (`docs/cli-ux.md`)
- Architecture design (`docs/architecture.md`)
- STRIDE threat model (`docs/threat-model.md`)
- Red team analysis report (`docs/red-team-report.md`)
- Tool interception design with Mermaid diagrams (`docs/tool-interception-design.md`)
- Policy engine design (`docs/policy-engine.md`)
- Data model design (`docs/data-model.md`)
- Approval lifecycle design (`docs/approval-lifecycle.md`)
- Setup flow design (`docs/setup-flow.md`)
- Tool adapter abstraction design (`docs/tool-adapter.md`)
- Python project scaffolding (`pyproject.toml`)
- Package stubs for all modules

### Security

- Established security-first design principles
- Defined exit codes for all failure categories
- Documented allowlist, RBAC, and audit log requirements

---

[Unreleased]: https://github.com/abdulraoufatia/aegis-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/abdulraoufatia/aegis-cli/releases/tag/v0.1.0
