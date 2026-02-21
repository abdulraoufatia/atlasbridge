"""Unit tests for aegis.core.pr_automation — PR filter logic, CI evaluation, merge gating."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aegis.core.fix_engine import _parse_file_changes
from aegis.core.pr_automation import (
    AutoPRConfig,
    PRAutomationEngine,
    PRResult,
    SkipReason,
    _evaluate_ci,
    _skip,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _cfg(**overrides: Any) -> AutoPRConfig:
    defaults: dict[str, Any] = {
        "github_token": "tok",
        "github_repo": "owner/repo",
        "repo_path": Path("/tmp/repo"),
        "authors": ["dependabot[bot]"],
        "labels": [],
        "merge_method": "squash",
        "delete_branch_on_merge": True,
        "require_all_checks": True,
        "max_retries": 2,
        "ci_timeout_seconds": 60,
        "ci_poll_interval_seconds": 5,
        "test_command": "pytest tests/ -q",
        "dry_run": True,
        "anthropic_api_key": "",
    }
    defaults.update(overrides)
    return AutoPRConfig(**defaults)


def _pr(
    number: int = 1,
    author: str = "dependabot[bot]",
    draft: bool = False,
    labels: list[str] | None = None,
    title: str = "Bump foo from 1.0 to 2.0",
    branch: str = "dependabot/pip/foo-2.0",
    base: str = "main",
    sha: str = "abc123",
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "draft": draft,
        "user": {"login": author},
        "labels": [{"name": lbl} for lbl in (labels or [])],
        "head": {"ref": branch, "sha": sha},
        "base": {"ref": base},
        "mergeable": True,
        "mergeable_state": "clean",
    }


# ---------------------------------------------------------------------------
# PR filter logic
# ---------------------------------------------------------------------------


class TestPRFilters:
    def test_draft_pr_skipped(self) -> None:
        result = PRResult(pr_number=1, pr_title="t", branch="b")
        out = _skip(result, SkipReason.DRAFT)
        assert out.skipped is True
        assert out.skip_reason == SkipReason.DRAFT

    def test_author_filter_skipped(self) -> None:
        result = PRResult(pr_number=1, pr_title="t", branch="b")
        out = _skip(result, SkipReason.AUTHOR_FILTER)
        assert out.skip_reason == SkipReason.AUTHOR_FILTER

    def test_label_filter_skipped(self) -> None:
        result = PRResult(pr_number=1, pr_title="t", branch="b")
        out = _skip(result, SkipReason.LABEL_FILTER)
        assert out.skip_reason == SkipReason.LABEL_FILTER

    def test_conflict_skipped(self) -> None:
        result = PRResult(pr_number=1, pr_title="t", branch="b")
        out = _skip(result, SkipReason.CONFLICT)
        assert out.skip_reason == SkipReason.CONFLICT

    def test_dry_run_not_merged(self) -> None:
        result = PRResult(pr_number=1, pr_title="t", branch="b")
        out = _skip(result, SkipReason.DRY_RUN)
        assert not out.merged
        assert out.skip_reason == SkipReason.DRY_RUN


# ---------------------------------------------------------------------------
# CI state evaluation
# ---------------------------------------------------------------------------


class TestCIEvaluation:
    @pytest.mark.asyncio
    async def test_all_checks_passing(self) -> None:
        check_runs = [
            {"name": "ci/test", "status": "completed", "conclusion": "success"},
            {"name": "ci/lint", "status": "completed", "conclusion": "success"},
        ]
        combined = {"statuses": []}

        gh = AsyncMock()
        gh.get_pr_checks.return_value = check_runs
        gh.get_combined_status.return_value = combined

        ok, failing = await _evaluate_ci(gh, "sha", ["ci/test", "ci/lint"], True)
        assert ok is True
        assert failing == []

    @pytest.mark.asyncio
    async def test_one_check_failing(self) -> None:
        check_runs = [
            {"name": "ci/test", "status": "completed", "conclusion": "failure"},
            {"name": "ci/lint", "status": "completed", "conclusion": "success"},
        ]
        combined = {"statuses": []}
        gh = AsyncMock()
        gh.get_pr_checks.return_value = check_runs
        gh.get_combined_status.return_value = combined

        ok, failing = await _evaluate_ci(gh, "sha", ["ci/test", "ci/lint"], True)
        assert ok is False
        assert any("ci/test" in f for f in failing)

    @pytest.mark.asyncio
    async def test_in_progress_check_treated_as_failing(self) -> None:
        check_runs = [
            {"name": "ci/test", "status": "in_progress", "conclusion": None},
        ]
        combined = {"statuses": []}
        gh = AsyncMock()
        gh.get_pr_checks.return_value = check_runs
        gh.get_combined_status.return_value = combined

        ok, failing = await _evaluate_ci(gh, "sha", ["ci/test"], True)
        assert ok is False
        assert any("in_progress" in f for f in failing)

    @pytest.mark.asyncio
    async def test_skipped_conclusion_passes(self) -> None:
        check_runs = [
            {"name": "ci/test", "status": "completed", "conclusion": "skipped"},
        ]
        combined = {"statuses": []}
        gh = AsyncMock()
        gh.get_pr_checks.return_value = check_runs
        gh.get_combined_status.return_value = combined

        ok, failing = await _evaluate_ci(gh, "sha", [], True)
        assert ok is True

    @pytest.mark.asyncio
    async def test_legacy_status_api_failing(self) -> None:
        check_runs: list = []
        combined = {
            "statuses": [
                {"context": "ci/legacy", "state": "failure"},
            ]
        }
        gh = AsyncMock()
        gh.get_pr_checks.return_value = check_runs
        gh.get_combined_status.return_value = combined

        ok, failing = await _evaluate_ci(gh, "sha", ["ci/legacy"], True)
        assert ok is False
        assert any("ci/legacy" in f for f in failing)

    @pytest.mark.asyncio
    async def test_require_all_checks_false_ignores_non_required(self) -> None:
        check_runs = [
            {"name": "optional-check", "status": "completed", "conclusion": "failure"},
        ]
        combined = {"statuses": []}
        gh = AsyncMock()
        gh.get_pr_checks.return_value = check_runs
        gh.get_combined_status.return_value = combined

        # require_all=False and "optional-check" not in required list
        ok, failing = await _evaluate_ci(gh, "sha", ["ci/required"], False)
        # optional-check should not block
        assert ok is True


# ---------------------------------------------------------------------------
# Branch protection gating
# ---------------------------------------------------------------------------


class TestBranchProtectionGating:
    @pytest.mark.asyncio
    async def test_missing_reviews_blocks_merge(self) -> None:
        """PR should be skipped when required reviews > current approvals."""
        cfg = _cfg(dry_run=True)
        engine = PRAutomationEngine(cfg)

        pr = _pr(author="dependabot[bot]")

        gh = AsyncMock()
        gh.list_open_prs.return_value = [pr]
        gh.get_pr.return_value = {**pr, "mergeable": True}
        gh.get_pr_checks.return_value = [
            {"name": "ci/test", "status": "completed", "conclusion": "success"}
        ]
        gh.get_combined_status.return_value = {"statuses": []}
        gh.get_branch_protection.return_value = {
            "required_pull_request_reviews": {
                "required_approving_review_count": 2
            },
            "required_status_checks": {"contexts": [], "checks": []},
        }
        gh.get_required_checks.return_value = []
        gh.get_required_reviews.return_value = 2
        gh.get_pr_reviews.return_value = [
            {"state": "APPROVED"},  # only 1 approval
        ]

        result = await engine._process_pr(gh, pr)
        assert result.skipped
        assert result.skip_reason == SkipReason.MISSING_REVIEWS

    @pytest.mark.asyncio
    async def test_draft_pr_always_skipped(self) -> None:
        cfg = _cfg()
        engine = PRAutomationEngine(cfg)
        pr = _pr(draft=True)
        gh = AsyncMock()
        result = await engine._process_pr(gh, pr)
        assert result.skipped
        assert result.skip_reason == SkipReason.DRAFT

    @pytest.mark.asyncio
    async def test_conflict_pr_skipped(self) -> None:
        cfg = _cfg()
        engine = PRAutomationEngine(cfg)
        pr = _pr()

        gh = AsyncMock()
        gh.get_pr.return_value = {**pr, "mergeable": False}
        gh.get_pr_checks.return_value = []
        gh.get_combined_status.return_value = {"statuses": []}
        gh.get_branch_protection.return_value = None
        gh.get_required_checks.return_value = []
        gh.get_required_reviews.return_value = 0
        gh.get_pr_reviews.return_value = []

        result = await engine._process_pr(gh, pr)
        assert result.skipped
        assert result.skip_reason == SkipReason.CONFLICT

    @pytest.mark.asyncio
    async def test_wrong_author_skipped(self) -> None:
        cfg = _cfg(authors=["dependabot[bot]"])
        engine = PRAutomationEngine(cfg)
        pr = _pr(author="random-human")
        gh = AsyncMock()
        result = await engine._process_pr(gh, pr)
        assert result.skipped
        assert result.skip_reason == SkipReason.AUTHOR_FILTER


# ---------------------------------------------------------------------------
# Merge gating — dry_run blocks actual merge
# ---------------------------------------------------------------------------


class TestMergeGating:
    @pytest.mark.asyncio
    async def test_dry_run_prevents_merge(self) -> None:
        cfg = _cfg(dry_run=True)
        engine = PRAutomationEngine(cfg)

        pr = _pr()
        result = PRResult(pr_number=1, pr_title="t", branch="b")
        gh = AsyncMock()

        out = await engine._try_merge(gh, result, pr, "abc123")
        assert not out.merged
        assert out.skip_reason == SkipReason.DRY_RUN
        gh.merge_pr.assert_not_called()

    @pytest.mark.asyncio
    async def test_merge_api_failure_records_error(self) -> None:
        cfg = _cfg(dry_run=False)
        engine = PRAutomationEngine(cfg)

        pr = _pr()
        result = PRResult(pr_number=1, pr_title="t", branch="b")
        gh = AsyncMock()
        gh.merge_pr.side_effect = Exception("Merge not allowed")

        out = await engine._try_merge(gh, result, pr, "abc123")
        assert not out.merged
        assert out.skip_reason == SkipReason.MERGE_FAILED
        assert "Merge not allowed" in (out.error or "")


# ---------------------------------------------------------------------------
# Retry / backoff logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_fix_engine_respects_max_retries(self, tmp_path: Path) -> None:
        """FixEngine should stop after max_retries attempts."""
        from aegis.core.fix_engine import FixEngine

        engine = FixEngine(
            repo_path=tmp_path,
            test_command="exit 1",  # always fails
            max_retries=2,
            api_key="",  # no key → skip fix attempts
            dry_run=True,
        )
        result = await engine.run()
        assert result.success is False
        # No fix attempts without API key
        assert result.attempt == 0

    @pytest.mark.asyncio
    async def test_fix_engine_succeeds_immediately(self, tmp_path: Path) -> None:
        from aegis.core.fix_engine import FixEngine

        engine = FixEngine(
            repo_path=tmp_path,
            test_command="exit 0",
            max_retries=3,
            api_key="",
            dry_run=True,
        )
        result = await engine.run()
        assert result.success is True


# ---------------------------------------------------------------------------
# File change parsing
# ---------------------------------------------------------------------------


class TestParseFileChanges:
    def test_valid_json_array_in_code_fence(self) -> None:
        text = """
Here are the fixes:

```json
[{"path": "aegis/foo.py", "content": "print('fixed')"}]
```
"""
        changes = _parse_file_changes(text)
        assert changes is not None
        assert len(changes) == 1
        assert changes[0]["path"] == "aegis/foo.py"

    def test_empty_array_returns_none(self) -> None:
        text = "```json\n[]\n```"
        result = _parse_file_changes(text)
        assert result is None

    def test_invalid_json_returns_none(self) -> None:
        assert _parse_file_changes("not json at all") is None

    def test_bare_array_without_fence(self) -> None:
        text = '[{"path": "x.py", "content": "hello"}]'
        changes = _parse_file_changes(text)
        assert changes is not None
        assert changes[0]["content"] == "hello"

    def test_ignores_entries_missing_path_or_content(self) -> None:
        text = """```json
[{"path": "ok.py", "content": "x"}, {"only_path": "bad.py"}]
```"""
        changes = _parse_file_changes(text)
        assert changes is not None
        assert len(changes) == 1
        assert changes[0]["path"] == "ok.py"
