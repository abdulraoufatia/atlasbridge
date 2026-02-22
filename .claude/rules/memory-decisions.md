# Memory Decisions — Rules

## Purpose

Defines the format and standards for logging architecture and design decisions in the auto-memory `memory-decisions.md` file.

## When to Log a Decision

Log a decision when:
- An architecture or design choice is made that affects multiple files or subsystems
- A technology, pattern, or approach is chosen over alternatives
- A policy or convention is established for the project
- A previous decision is reversed or amended

Do NOT log:
- Implementation details that are obvious from the code
- Decisions that only affect a single function or variable
- Temporary debugging choices

## Decision Entry Format

```markdown
### YYYY-MM-DD — Decision Title

**Context:** Why this decision was needed
**Decision:** What was decided
**Alternatives considered:** What else was evaluated (if any)
**Tradeoffs:** What was gained and what was sacrificed
**Affected files/subsystems:** Where the impact is felt
```

## Rules

1. Every entry MUST have a date
2. Capture WHY, not just WHAT
3. Include tradeoffs — every decision has costs
4. Link to related issues/PRs when available
5. Mark reversed decisions with `[REVERSED YYYY-MM-DD]` prefix
6. Keep entries concise — 3-5 lines per section maximum
7. Newest entries at the top of the file
