# Memory Profile — AtlasBridge

## Purpose

Defines the project identity and technical profile. Used by Claude Code to maintain accurate context about what this project is, its current state, and key facts.

## Profile

- **Project:** AtlasBridge
- **Type:** Policy-driven autonomous runtime for AI CLI agents
- **Language:** Python 3.11+
- **Package:** `atlasbridge` (PyPI)
- **Framework:** Click (CLI), Textual (TUI), FastAPI (dashboard)
- **Database:** SQLite WAL mode
- **Channels:** Telegram, Slack
- **License:** Open source

## What AtlasBridge Is

A deterministic, policy-governed runtime that allows AI CLI agents to operate autonomously within defined boundaries. Humans define rules via YAML Policy DSL. AtlasBridge evaluates on every prompt and executes only what is explicitly permitted.

## What AtlasBridge Is NOT

- Not a wrapper around a CLI tool
- Not a security product (correctness invariants, not security features)
- Not a SaaS platform (local-first, single-user)
- Not an AI model or agent itself

## Formatting Rules

When updating this profile:
- Keep facts verifiable against the codebase
- Update version/test counts in MEMORY.md, not here
- Do not add aspirational features — only shipped capabilities
- Date any significant identity changes
