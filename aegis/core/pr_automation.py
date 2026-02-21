"""
Aegis PR automation engine.

Orchestrates the full automated PR remediation cycle:

1. Fetch open PRs from GitHub.
2. Filter by author, label, draft status, conflicts.
3. For each eligible PR:
   a. Evaluate CI status.
   b. If CI failing or unknown: checkout branch, run tests locally.
   c. If tests fail: invoke FixEngine (Claude-assisted).
   d. If fix produced changes: commit + push to PR branch.
   e. Wait for CI to re-run.
   f. If all required checks green: merge PR.
4. Log every decision with an explicit reason code.

Safety guarantees
-----------------
- Never merges if any required check is failing.
- Never bypasses branch protection rules.
- Never merges draft PRs.
- Never merges PRs with merge conflicts.
- Never force-pushes.
- Dry-run mode (default): logs everything, no push, no merge.
- Concurrency: processes one PR at a time by default.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from aegis.core.fix_engine import FixEngine
from aegis.core.github_client import GitHubClient

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class SkipReason(StrEnum):
    DRAFT = "draft_pr"
    CONFLICT = "merge_conflict"
    AUTHOR_FILTER = "author_not_in_allowlist"
    LABEL_FILTER = "label_not_in_allowlist"
    ALL_CHECKS_PASSING = "all_checks_already_passing"
    MISSING_REVIEWS = "insufficient_approving_reviews"
    REQUIRED_CHECK_FAILING = "required_check_still_failing"
    FIX_FAILED = "fix_attempts_exhausted"
    CI_TIMEOUT = "ci_polling_timeout"
    DRY_RUN = "dry_run_mode"
    PUSH_FAILED = "push_to_branch_failed"
    MERGE_FAILED = "merge_api_call_failed"


@dataclass
class PRResult:
    pr_number: int
    pr_title: str
    branch: str
    merged: bool = False
    skipped: bool = False
    skip_reason: SkipReason | None = None
    fix_attempts: int = 0
    commit_sha: str | None = None
    error: str | None = None
    protection_snapshot: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


@dataclass
class AutoPRConfig:
    """Flat config passed to the engine (decoupled from Pydantic model)."""

    github_token: str
    github_repo: str
    repo_path: Path
    authors: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    merge_method: str = "squash"
    delete_branch_on_merge: bool = True
    require_all_checks: bool = True
    max_retries: int = 3
    ci_timeout_seconds: int = 1200
    ci_poll_interval_seconds: int = 30
    test_command: str = "pytest tests/ -q"
    dry_run: bool = True
    anthropic_api_key: str = ""


# ---------------------------------------------------------------------------
# PR automation engine
# ---------------------------------------------------------------------------


class PRAutomationEngine:
    """
    Core engine for automated PR triage, fix, and merge.

    Usage::

        cfg = AutoPRConfig(...)
        engine = PRAutomationEngine(cfg)
        results = await engine.run_cycle()
    """

    def __init__(self, config: AutoPRConfig) -> None:
        self._cfg = config
        self._semaphore = asyncio.Semaphore(1)  # one PR at a time

    async def run_cycle(self) -> list[PRResult]:
        """Run one full triage cycle. Returns results for all PRs evaluated."""
        results: list[PRResult] = []
        async with GitHubClient(
            token=self._cfg.github_token,
            repo=self._cfg.github_repo,
        ) as gh:
            prs = await gh.list_open_prs()
            log.info("Found %d open PR(s) in %s", len(prs), self._cfg.github_repo)

            for pr in prs:
                result = await self._process_pr(gh, pr)
                results.append(result)
                _log_result(result)

        return results

    async def _process_pr(
        self, gh: GitHubClient, pr: dict[str, Any]
    ) -> PRResult:
        number = pr["number"]
        title = pr["title"]
        branch = pr["head"]["ref"]
        head_sha = pr["head"]["sha"]
        base_branch = pr["base"]["ref"]

        result = PRResult(pr_number=number, pr_title=title, branch=branch)

        # --- Draft check ---
        if pr.get("draft"):
            return _skip(result, SkipReason.DRAFT)

        # --- Author filter ---
        author = pr.get("user", {}).get("login", "")
        if self._cfg.authors and author not in self._cfg.authors:
            return _skip(result, SkipReason.AUTHOR_FILTER)

        # --- Label filter ---
        if self._cfg.labels:
            pr_labels = {lbl["name"] for lbl in pr.get("labels", [])}
            if not pr_labels.intersection(self._cfg.labels):
                return _skip(result, SkipReason.LABEL_FILTER)

        # --- Fetch full PR for mergeability ---
        # GitHub computes mergeability lazily; poll until it resolves
        full_pr = await _wait_for_mergeability(gh, number)

        if full_pr.get("mergeable") is False:
            return _skip(result, SkipReason.CONFLICT)

        # --- Branch protection snapshot ---
        await gh.get_branch_protection(base_branch)
        required_checks = await gh.get_required_checks(base_branch)
        required_reviews = await gh.get_required_reviews(base_branch)
        result.protection_snapshot = {
            "required_checks": required_checks,
            "required_approving_reviews": required_reviews,
        }
        log.debug(
            "PR #%d: required_checks=%s, required_reviews=%d",
            number, required_checks, required_reviews,
        )

        # --- Required reviews check ---
        if required_reviews > 0:
            reviews = await gh.get_pr_reviews(number)
            approved = sum(
                1 for r in reviews
                if r.get("state") == "APPROVED"
            )
            if approved < required_reviews:
                log.info(
                    "PR #%d: %d/%d required reviews — skipping",
                    number, approved, required_reviews,
                )
                return _skip(result, SkipReason.MISSING_REVIEWS)

        # --- CI status ---
        ci_ok, failing_checks = await _evaluate_ci(
            gh, head_sha, required_checks, self._cfg.require_all_checks
        )

        if ci_ok:
            # All CI green — try to merge directly
            return await self._try_merge(gh, result, full_pr, head_sha)

        log.info("PR #%d: CI failing checks=%s", number, failing_checks)

        # --- Local fix cycle ---
        async with self._semaphore:
            result = await self._fix_and_push(gh, result, number, branch)
            if result.skipped:
                return result

            # Wait for CI to re-run
            new_head_sha = result.commit_sha or head_sha
            ci_ok, failing = await _poll_ci_until_complete(
                gh,
                new_head_sha,
                required_checks,
                self._cfg.require_all_checks,
                timeout=self._cfg.ci_timeout_seconds,
                interval=self._cfg.ci_poll_interval_seconds,
            )

            if not ci_ok:
                log.warning(
                    "PR #%d: CI still failing after fix: %s", number, failing
                )
                return _skip(result, SkipReason.REQUIRED_CHECK_FAILING)

            # Re-fetch PR for updated mergeability / SHA
            full_pr = await _wait_for_mergeability(gh, number)
            merged_sha = full_pr["head"]["sha"]
            return await self._try_merge(gh, result, full_pr, merged_sha)

    # ------------------------------------------------------------------
    # Fix and push
    # ------------------------------------------------------------------

    async def _fix_and_push(
        self,
        gh: GitHubClient,
        result: PRResult,
        pr_number: int,
        branch: str,
    ) -> PRResult:
        repo = self._cfg.repo_path

        # Fetch and checkout the PR branch
        ok = await _git_checkout_pr_branch(repo, branch)
        if not ok:
            result.error = f"Failed to checkout branch {branch}"
            return _skip(result, SkipReason.PUSH_FAILED)

        # Install deps
        await _run_cmd(
            ["python", "-m", "pip", "install", "-e", ".[dev]", "-q"],
            cwd=repo,
        )

        # Run fix engine
        fix_engine = FixEngine(
            repo_path=repo,
            test_command=self._cfg.test_command,
            max_retries=self._cfg.max_retries,
            api_key=self._cfg.anthropic_api_key,
            dry_run=self._cfg.dry_run,
        )
        fix_result = await fix_engine.run()
        result.fix_attempts = fix_result.attempt

        if not fix_result.success:
            log.warning("PR #%d: tests still failing after %d fix attempts",
                        pr_number, fix_result.attempt)
            return _skip(result, SkipReason.FIX_FAILED)

        if not fix_result.changed_files:
            # Tests pass without changes — just push nothing; CI might re-run
            log.info("PR #%d: tests pass locally, no changes needed", pr_number)
            return result

        # Commit and push
        commit_sha = await _git_commit_and_push(
            repo,
            branch,
            fix_result.changed_files,
            f"fix(ci): resolve failing tests in PR #{pr_number}",
            dry_run=self._cfg.dry_run,
        )

        if commit_sha is None:
            return _skip(result, SkipReason.PUSH_FAILED)

        result.commit_sha = commit_sha
        return result

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    async def _try_merge(
        self,
        gh: GitHubClient,
        result: PRResult,
        pr: dict[str, Any],
        sha: str,
    ) -> PRResult:
        if self._cfg.dry_run:
            log.info(
                "[dry_run] Would merge PR #%d (%s) via %s",
                result.pr_number, result.branch, self._cfg.merge_method,
            )
            return _skip(result, SkipReason.DRY_RUN)

        try:
            merge_resp = await gh.merge_pr(
                pr_number=result.pr_number,
                merge_method=self._cfg.merge_method,
                commit_title=f"chore: merge PR #{result.pr_number} — {result.pr_title}",
                sha=sha,
            )
            result.merged = True
            log.info(
                "Merged PR #%d (%s) — sha=%s",
                result.pr_number,
                result.branch,
                merge_resp.get("sha", ""),
            )

            if self._cfg.delete_branch_on_merge:
                try:
                    await gh.delete_branch(result.branch)
                    log.info("Deleted branch %s", result.branch)
                except Exception as exc:
                    log.warning("Branch delete failed (ok): %s", exc)

        except Exception as exc:
            log.error("Merge failed for PR #%d: %s", result.pr_number, exc)
            result.error = str(exc)
            return _skip(result, SkipReason.MERGE_FAILED)

        return result


# ---------------------------------------------------------------------------
# Git helpers (subprocess)
# ---------------------------------------------------------------------------


async def _git_checkout_pr_branch(repo: Path, branch: str) -> bool:
    """Fetch and checkout a PR branch. Returns True on success."""
    cmds = [
        ["git", "fetch", "origin", branch],
        ["git", "checkout", branch],
        ["git", "reset", "--hard", f"origin/{branch}"],
    ]
    for cmd in cmds:
        ok = await _run_cmd(cmd, cwd=repo)
        if not ok:
            return False
    return True


async def _git_commit_and_push(
    repo: Path,
    branch: str,
    changed_files: list[str],
    message: str,
    dry_run: bool = True,
) -> str | None:
    """
    Stage changed files, commit, push. Returns the new HEAD SHA or None on failure.
    """
    # Stage specific files only — never git add -A
    add_cmd = ["git", "add", "--"] + changed_files
    if not await _run_cmd(add_cmd, cwd=repo):
        return None

    commit_cmd = [
        "git", "commit", "-m", message,
        "--author", "Aegis Bot <aegis-bot@noreply.local>",
    ]
    if not await _run_cmd(commit_cmd, cwd=repo):
        return None

    # Get the new HEAD SHA before pushing
    result = await _run_cmd_output(["git", "rev-parse", "HEAD"], cwd=repo)
    sha = result.strip() if result else None

    if dry_run:
        log.info("[dry_run] Would push %s to origin/%s", sha, branch)
        # Undo the commit we just made (safe — local only)
        await _run_cmd(["git", "reset", "--soft", "HEAD~1"], cwd=repo)
        return sha

    push_cmd = ["git", "push", "origin", f"HEAD:{branch}"]
    if not await _run_cmd(push_cmd, cwd=repo):
        return None

    return sha


async def _run_cmd(cmd: list[str], cwd: Path) -> bool:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True, timeout=120
            ),
        )
        if result.returncode != 0:
            log.debug("cmd %s failed: %s", cmd, result.stderr[:500])
            return False
        return True
    except Exception as exc:
        log.debug("cmd %s exception: %s", cmd, exc)
        return False


async def _run_cmd_output(cmd: list[str], cwd: Path) -> str:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True, timeout=30
            ),
        )
        return result.stdout
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CI helpers
# ---------------------------------------------------------------------------


async def _evaluate_ci(
    gh: GitHubClient,
    sha: str,
    required_checks: list[str],
    require_all: bool,
) -> tuple[bool, list[str]]:
    """
    Evaluate current CI status for a SHA.

    Returns (all_passing, list_of_failing_check_names).
    """
    check_runs = await gh.get_pr_checks(sha)
    combined = await gh.get_combined_status(sha)

    failing: list[str] = []

    # Check Runs API
    for run in check_runs:
        name = run.get("name", "")
        status = run.get("status", "")
        conclusion = run.get("conclusion", "")

        if status != "completed":
            # Still running
            if require_all or name in required_checks:
                failing.append(f"{name}(in_progress)")
            continue

        if conclusion not in ("success", "neutral", "skipped"):
            if not required_checks or name in required_checks or require_all:
                failing.append(f"{name}({conclusion})")

    # Legacy Status API contexts
    for status in combined.get("statuses", []):
        context = status.get("context", "")
        state = status.get("state", "")
        if state not in ("success",):
            if not required_checks or context in required_checks or require_all:
                failing.append(f"{context}({state})")

    return len(failing) == 0, failing


async def _poll_ci_until_complete(
    gh: GitHubClient,
    sha: str,
    required_checks: list[str],
    require_all: bool,
    timeout: int = 1200,
    interval: int = 30,
) -> tuple[bool, list[str]]:
    """
    Poll CI until all checks complete or timeout is reached.
    Returns (all_passing, failing_checks).
    """
    elapsed = 0
    while elapsed < timeout:
        ok, failing = await _evaluate_ci(gh, sha, required_checks, require_all)
        in_progress = any("in_progress" in f for f in failing)

        if not in_progress:
            return ok, failing

        log.debug(
            "CI in progress for %s — waiting %ds (elapsed=%d/%d)",
            sha[:8], interval, elapsed, timeout,
        )
        await asyncio.sleep(interval)
        elapsed += interval

    log.warning("CI polling timed out after %ds for %s", timeout, sha[:8])
    return False, ["timeout"]


async def _wait_for_mergeability(
    gh: GitHubClient, pr_number: int, retries: int = 5
) -> dict[str, Any]:
    """
    GitHub computes mergeability lazily. Poll until it resolves.
    """
    for _ in range(retries):
        pr = await gh.get_pr(pr_number)
        if pr.get("mergeable") is not None:
            return pr
        await asyncio.sleep(3)
    return await gh.get_pr(pr_number)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _skip(result: PRResult, reason: SkipReason) -> PRResult:
    result.skipped = True
    result.skip_reason = reason
    return result


def _log_result(result: PRResult) -> None:
    if result.merged:
        log.info(
            "PR #%d (%s): MERGED via branch=%s commit=%s",
            result.pr_number, result.pr_title, result.branch, result.commit_sha,
        )
    elif result.skipped:
        log.info(
            "PR #%d (%s): SKIPPED reason=%s",
            result.pr_number, result.pr_title, result.skip_reason,
        )
    else:
        log.error(
            "PR #%d (%s): ERROR %s",
            result.pr_number, result.pr_title, result.error,
        )
