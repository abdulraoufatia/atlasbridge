"""
Aegis GitHub REST API client.

Thin httpx-based wrapper around the GitHub REST API v3.
Handles authentication (PAT), rate limiting, and the specific
calls needed by the PR automation engine.

All methods are async. Authentication is via Bearer token
(Personal Access Token or GitHub App installation token).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

_API = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_VERSION = "2022-11-28"


class GitHubClient:
    """
    Async GitHub REST API client.

    Parameters
    ----------
    token:
        GitHub Personal Access Token (or installation token).
    repo:
        Repository in ``owner/repo`` format.
    """

    def __init__(self, token: str, repo: str) -> None:
        self._repo = repo
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _VERSION,
        }
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GitHubClient:
        self._client = httpx.AsyncClient(
            base_url=_API,
            headers=self._headers,
            timeout=30,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Pull Requests
    # ------------------------------------------------------------------

    async def list_open_prs(self) -> list[dict[str, Any]]:
        """Return all open, non-draft PRs for the repo."""
        prs: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._get(
                f"/repos/{self._repo}/pulls",
                params={"state": "open", "per_page": 100, "page": page},
            )
            if not data:
                break
            prs.extend(data)
            if len(data) < 100:
                break
            page += 1
        return prs

    async def get_pr(self, pr_number: int) -> dict[str, Any]:
        """Fetch a single PR with full detail (including mergeability)."""
        return await self._get(f"/repos/{self._repo}/pulls/{pr_number}")

    async def get_pr_checks(self, ref: str) -> list[dict[str, Any]]:
        """
        Return all check runs for a commit SHA or branch ref.
        Uses the Check Runs API (more complete than Status API).
        """
        data = await self._get(
            f"/repos/{self._repo}/commits/{ref}/check-runs",
            params={"per_page": 100},
        )
        return data.get("check_runs", [])

    async def get_combined_status(self, ref: str) -> dict[str, Any]:
        """Return the combined commit status (legacy Status API)."""
        return await self._get(f"/repos/{self._repo}/commits/{ref}/status")

    async def get_branch_protection(self, branch: str) -> dict[str, Any] | None:
        """
        Fetch branch protection rules for a branch.
        Returns None if no protection rules are configured.
        """
        try:
            return await self._get(f"/repos/{self._repo}/branches/{branch}/protection")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def merge_pr(
        self,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: str | None = None,
        commit_message: str | None = None,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """
        Merge a pull request.

        Parameters
        ----------
        pr_number:
            PR number to merge.
        merge_method:
            One of "squash", "merge", "rebase".
        commit_title:
            Optional commit title (for squash/merge).
        commit_message:
            Optional commit message.
        sha:
            Head SHA to merge (guards against race conditions).
        """
        payload: dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message
        if sha:
            payload["sha"] = sha
        return await self._put(f"/repos/{self._repo}/pulls/{pr_number}/merge", json=payload)

    async def delete_branch(self, branch: str) -> None:
        """Delete a remote branch."""
        await self._delete(f"/repos/{self._repo}/git/refs/heads/{branch}")

    async def create_pr_comment(self, pr_number: int, body: str) -> dict[str, Any]:
        """Post a comment on a PR."""
        return await self._post(
            f"/repos/{self._repo}/issues/{pr_number}/comments",
            json={"body": body},
        )

    async def get_repo(self) -> dict[str, Any]:
        """Fetch repository metadata."""
        return await self._get(f"/repos/{self._repo}")

    async def get_required_checks(self, branch: str) -> list[str]:
        """
        Return the list of required status check context names for a branch.
        Returns an empty list if no branch protection or no required checks.
        """
        protection = await self.get_branch_protection(branch)
        if not protection:
            return []
        rsc = protection.get("required_status_checks") or {}
        contexts = rsc.get("contexts") or []
        # Also include check suite names from strict checks
        checks = rsc.get("checks") or []
        names = list(contexts)
        for c in checks:
            name = c.get("context") or c.get("name")
            if name and name not in names:
                names.append(name)
        return names

    async def get_required_reviews(self, branch: str) -> int:
        """
        Return the minimum number of required approving reviews for a branch.
        Returns 0 if none required.
        """
        protection = await self.get_branch_protection(branch)
        if not protection:
            return 0
        rpr = protection.get("required_pull_request_reviews") or {}
        return rpr.get("required_approving_review_count", 0)

    async def get_pr_reviews(self, pr_number: int) -> list[dict[str, Any]]:
        """Return all reviews for a PR."""
        return await self._get(
            f"/repos/{self._repo}/pulls/{pr_number}/reviews",
            params={"per_page": 100},
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        assert self._client is not None
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        assert self._client is not None
        resp = await self._client.post(path, json=json)
        resp.raise_for_status()
        return resp.json()

    async def _put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        assert self._client is not None
        resp = await self._client.put(path, json=json)
        resp.raise_for_status()
        return resp.json()

    async def _delete(self, path: str) -> None:
        assert self._client is not None
        resp = await self._client.delete(path)
        if resp.status_code not in (200, 204):
            resp.raise_for_status()
