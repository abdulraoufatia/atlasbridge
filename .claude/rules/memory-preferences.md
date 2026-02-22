# Memory Preferences — AtlasBridge

## Purpose

Captures the user's confirmed workflow preferences, communication style, and tooling choices. Only add entries that have been explicitly confirmed across multiple interactions or directly stated by the user.

## Confirmed Preferences

### Workflow
- **Sprint-driven development** — work in sprints, tier-ordered execution (P0 first)
- **Test-gated progression** — do not move to next issue unless all tests pass
- **Branch per feature** — `feature/*`, `fix/*` branches, squash-merge to main
- **Conventional commits** — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
- **Receipts required** — always show proof of work (test counts, coverage, CI status)

### Communication
- **No emojis** unless explicitly requested
- **Concise responses** — short and to the point
- **No time estimates** — focus on what, not how long
- **DV-safe language** — avoid "control plane", "enterprise governance", "SaaS" in public-facing content

### Tooling
- **Python 3.11+** as minimum
- **ruff** for linting and formatting
- **mypy** for type checking
- **pytest** for testing
- **GitHub Actions** for CI/CD
- **GitHub Projects v2** for project management

### Code Style
- **No over-engineering** — minimum complexity for current task
- **No speculative abstractions** — three similar lines > premature abstraction
- **No unnecessary comments/docstrings** — only where logic isn't self-evident
- **Keep open source** — no commercial/SaaS language in code or docs for now

## Formatting Rules

When updating preferences:
- Only add preferences confirmed by explicit user statement or repeated pattern (3+ times)
- Remove preferences the user explicitly revokes
- Date any significant preference changes
- Never store secrets, tokens, or personal data
