# Memory Sessions — Rules

## Purpose

Defines the format and standards for logging engineering session summaries in the auto-memory `memory-sessions.md` file.

## When to Log a Session

Log a session when substantive engineering work is completed:
- Feature implementation (new code shipped)
- Bug fix with root cause analysis
- Refactoring that changes architecture
- CI/CD pipeline changes
- Release or deployment work
- Multi-step debugging that produced learnings

Do NOT log:
- Quick factual Q&A
- Trivial one-line fixes
- File reads without changes
- Temporary experiments that were reverted

## Session Entry Format

```markdown
### YYYY-MM-DD — Session Title

**Work completed:**
- Bullet points of what was done

**Key changes:**
- Files modified with brief description

**Metrics (if applicable):**
- Test count: before → after
- Coverage: before → after
- CI status: pass/fail

**Learnings (if any):**
- Engineering insights gained
```

## Rules

1. Every entry MUST have a date
2. Focus on outcomes, not process
3. Include metrics when available (test count, coverage)
4. Keep to 5-10 lines per session — concise summaries only
5. Newest entries at the top of the file
6. Group related work into one session entry (don't create one per commit)
7. Reference issue/PR numbers when available
