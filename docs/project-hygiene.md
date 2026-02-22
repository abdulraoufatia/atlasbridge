# Project Hygiene — Operating Protocol

This document defines the operating protocol for keeping the
[AtlasBridge — Master Roadmap](https://github.com/users/abdulraoufatia/projects/17)
project board truthful and current.

---

## When work is merged / shipped

Immediately update the linked issue on the project board:

1. **Tick acceptance criteria** — only if the checkbox item is satisfied by
   the merged PR (point to the commit or test).
2. **Set Status → Done** — only after all acceptance criteria are met and
   CI is green on the merge commit.
3. **Set Sprint** — assign the sprint in which the work was completed
   (e.g. `S1`, `S2`).

Do **not** mark an issue Done if:
- The PR is merged but acceptance criteria are only partially satisfied.
- Tests referenced in the issue are missing or failing.
- Documentation deliverables referenced in the issue do not exist.

## When new work is discovered mid-sprint

1. Create a new issue describing the work.
2. Add it to the project board.
3. Set **Status = Backlog**, **Phase**, **Priority**, and **Category**.
4. If it should be picked up in the current sprint, move to
   **Status = In Progress** and set the current Sprint value.
5. If it can wait, leave it in Backlog for future sprint planning.

## Sprint convention

| Sprint | Meaning |
|--------|---------|
| `S1` | First completed sprint (historical) |
| `S2` | Second sprint (active or completed) |
| `S3` | Next planned sprint |
| `Backlog` | Not yet assigned to a sprint |

When a sprint completes (all items Done), increment: the next sprint
becomes active.

## Status definitions

| Status | Meaning |
|--------|---------|
| **Backlog** | Not started, not assigned to a sprint |
| **Planned** | Assigned to a sprint, not yet started |
| **In Progress** | Actively being worked on (PR open or in development) |
| **Blocked** | Cannot proceed — specify blocker in Blocked By field |
| **Done** | All acceptance criteria met, PR merged, CI green |

## Evidence rules for Done

An issue can be marked Done only if **at least one** of:

1. Linked to a merged PR whose contents satisfy the acceptance criteria,
   AND CI is green on the merge commit.
2. Explicitly shipped in a tagged release and the artifacts exist.
3. Acceptance criteria and test requirements are implemented and verified
   (tests exist and pass).

If none apply, the issue remains in its current status.
