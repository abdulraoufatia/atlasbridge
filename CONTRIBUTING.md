# Contributing to Aegis

Thank you for your interest in contributing to Aegis! This document describes
how to contribute code, documentation, bug reports, and feature requests.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Branching Strategy](#branching-strategy)
- [Commit Convention](#commit-convention)
- [Pull Request Process](#pull-request-process)
- [Testing](#testing)
- [Documentation](#documentation)
- [Security Issues](#security-issues)

---

## Code of Conduct

By participating, you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/<you>/aegis-cli.git`
3. Add upstream: `git remote add upstream https://github.com/abdulraoufatia/aegis-cli.git`
4. Create a feature branch (see [Branching Strategy](#branching-strategy))

---

## Development Setup

**Requirements:**
- Python 3.11+
- `pip` or `uv`

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Copy env example
cp .env.example .env
# Fill in your values in .env

# Run tests
pytest

# Run linter
ruff check .

# Run type checker
mypy aegis/
```

---

## Branching Strategy

| Type          | Pattern                     | Example                         |
|---------------|-----------------------------|---------------------------------|
| Feature       | `feature/<short-desc>`      | `feature/telegram-approval`     |
| Bug fix       | `fix/<short-desc>`          | `fix/timeout-race-condition`    |
| Documentation | `docs/<short-desc>`         | `docs/threat-model-update`      |
| Chore         | `chore/<short-desc>`        | `chore/update-dependencies`     |
| Release       | `release/v<semver>`         | `release/v0.2.0`                |

Rules:
- **One feature/fix per branch**. Never mix concerns.
- Branch from `main` always.
- Delete branch after merge.

---

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

**Types:**

| Type       | When to use                                    |
|------------|------------------------------------------------|
| `feat`     | New feature                                    |
| `fix`      | Bug fix                                        |
| `docs`     | Documentation only                             |
| `style`    | Formatting, no logic change                    |
| `refactor` | Code restructure, no feature/fix               |
| `test`     | Add/fix tests                                  |
| `chore`    | Build, deps, CI                                |
| `security` | Security fix or hardening                      |
| `perf`     | Performance improvement                        |

**Examples:**

```
feat(telegram): add approval timeout with auto-deny
fix(policy): correct allowlist regex matching
docs(threat-model): add replay attack section
security(daemon): enforce local-only socket binding
```

Breaking changes: append `!` after type and add `BREAKING CHANGE:` footer.

---

## Pull Request Process

1. Ensure CI passes (`pytest`, `ruff`, `mypy`)
2. Add/update tests for your change
3. Update documentation if behavior changes
4. Update `CHANGELOG.md` under `[Unreleased]`
5. Request review from a maintainer
6. Squash commits if asked
7. PRs require **1 approving review** before merge
8. Maintainer merges (no self-merge)

### PR Title Format

Same as commit format:
```
feat(cli): add `aegis doctor --fix` auto-remediation
```

---

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=aegis --cov-report=html

# Run specific test file
pytest tests/test_policy.py

# Run with verbose output
pytest -v
```

All PRs must maintain or improve test coverage.

---

## Documentation

- Design docs live in `docs/`
- Keep `docs/` in sync with code changes
- Use Mermaid for diagrams where applicable
- No docs-only commits to `main` without CI green

---

## Security Issues

**Do not open public issues for security vulnerabilities.**

See [SECURITY.md](SECURITY.md) for the full responsible disclosure process.
