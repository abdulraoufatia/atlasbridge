"""
Aegis fix engine — runs tests and attempts to fix failures.

The fix engine:
1. Runs the configured test command in the repo directory.
2. If tests fail, invokes the Anthropic Messages API to suggest fixes.
3. Applies the suggested changes (unified diff format).
4. Re-runs tests to verify.
5. Returns FixResult with outcome and any commit-ready changes.

Claude API integration
----------------------
The engine calls the Anthropic Messages API directly via httpx
(no additional dependency). Set ANTHROPIC_API_KEY in the environment
or configure it via aegis config. If no API key is available, the
engine falls back to logging the failure for human review.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
_CLAUDE_MODEL = "claude-sonnet-4-6"
_MAX_FIX_TOKENS = 4096
_MAX_OUTPUT_CHARS = 8000  # chars of test output to send to Claude


@dataclass
class FixResult:
    success: bool
    """True if tests pass after this fix cycle."""
    attempt: int = 0
    changed_files: list[str] = field(default_factory=list)
    test_output: str = ""
    error: str = ""


class FixEngine:
    """
    Run tests and attempt automated fixes using the Claude API.

    Parameters
    ----------
    repo_path:
        Absolute path to the local repository checkout.
    test_command:
        Shell command to run the test suite (e.g. ``"pytest tests/ -q"``).
    max_retries:
        Maximum fix attempts before giving up.
    api_key:
        Anthropic API key. If empty, fix attempts are skipped.
    dry_run:
        If True, never write files; only log what would change.
    """

    def __init__(
        self,
        repo_path: Path,
        test_command: str = "pytest tests/ -q",
        max_retries: int = 3,
        api_key: str = "",
        dry_run: bool = True,
    ) -> None:
        self._repo = repo_path
        self._test_cmd = test_command
        self._max_retries = max_retries
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._dry_run = dry_run

    async def run(self) -> FixResult:
        """
        Run the full fix loop:
        1. Run tests.
        2. If passing → return success immediately.
        3. If failing and we have an API key → attempt fix, repeat.
        4. Return final result.
        """
        test_result = await self._run_tests()
        if test_result.success:
            log.info("Tests pass without any changes.")
            return test_result

        if not self._api_key:
            log.warning(
                "Tests failing but no ANTHROPIC_API_KEY configured — "
                "skipping fix attempts. Set ANTHROPIC_API_KEY or configure "
                "auto_pr.anthropic_api_key to enable automated fixes."
            )
            return test_result

        for attempt in range(1, self._max_retries + 1):
            log.info("Fix attempt %d/%d", attempt, self._max_retries)

            fix = await self._attempt_fix(test_result.test_output, attempt)
            if fix is None:
                log.warning("Claude returned no actionable changes on attempt %d", attempt)
                break

            changed = await self._apply_changes(fix)
            if not changed:
                log.info("No file changes produced on attempt %d", attempt)
                break

            test_result = await self._run_tests()
            test_result.attempt = attempt
            test_result.changed_files = changed

            if test_result.success:
                log.info("Tests pass after fix attempt %d", attempt)
                return test_result

            log.info("Tests still failing after attempt %d — retrying", attempt)

        test_result.error = f"Fix failed after {self._max_retries} attempts"
        return test_result

    # ------------------------------------------------------------------
    # Test runner
    # ------------------------------------------------------------------

    async def _run_tests(self) -> FixResult:
        log.debug("Running: %s in %s", self._test_cmd, self._repo)
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    self._test_cmd,
                    shell=True,
                    cwd=str(self._repo),
                    capture_output=True,
                    text=True,
                    timeout=300,
                ),
            )
        except subprocess.TimeoutExpired:
            return FixResult(
                success=False,
                test_output="",
                error="Test suite timed out after 300s",
            )
        except Exception as exc:
            return FixResult(success=False, test_output="", error=str(exc))

        output = (result.stdout + result.stderr).strip()
        passed = result.returncode == 0
        log.debug("Test exit code: %d", result.returncode)
        return FixResult(success=passed, test_output=output)

    # ------------------------------------------------------------------
    # Claude fix
    # ------------------------------------------------------------------

    async def _attempt_fix(self, test_output: str, attempt: int) -> list[dict[str, str]] | None:
        """
        Ask Claude to analyse failures and return a list of file changes.
        Returns a list of {"path": ..., "content": ...} dicts, or None.
        """
        # Gather relevant source files
        file_context = _collect_relevant_files(self._repo, test_output)

        prompt = _build_fix_prompt(test_output, file_context, attempt)
        log.debug("Sending fix prompt to Claude (%d chars)", len(prompt))

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    _ANTHROPIC_API,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": _CLAUDE_MODEL,
                        "max_tokens": _MAX_FIX_TOKENS,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            log.error("Claude API call failed: %s", exc)
            return None

        text = data.get("content", [{}])[0].get("text", "")
        return _parse_file_changes(text)

    # ------------------------------------------------------------------
    # Apply changes
    # ------------------------------------------------------------------

    async def _apply_changes(self, changes: list[dict[str, str]]) -> list[str]:
        """Write changed files to disk. Returns list of modified paths."""
        changed: list[str] = []
        for change in changes:
            rel_path = change.get("path", "").lstrip("/")
            content = change.get("content", "")
            if not rel_path or not content:
                continue

            abs_path = self._repo / rel_path
            # Safety: only modify files inside the repo
            try:
                abs_path.resolve().relative_to(self._repo.resolve())
            except ValueError:
                log.warning("Skipping path outside repo: %s", rel_path)
                continue

            if self._dry_run:
                log.info("[dry_run] Would write %s (%d chars)", rel_path, len(content))
            else:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content, encoding="utf-8")
                log.info("Written: %s", rel_path)

            changed.append(rel_path)

        return changed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_relevant_files(repo: Path, test_output: str) -> dict[str, str]:
    """
    Heuristically collect source files mentioned in the test output
    for context. Caps total content at 12,000 chars.
    """
    files: dict[str, str] = {}
    total = 0
    limit = 12000

    # Look for file paths in test output
    for line in test_output.splitlines():
        for part in line.split():
            part = part.strip("\"',()[]")
            if part.endswith(".py") and "/" in part:
                candidate = repo / part.lstrip("/")
                if candidate.exists() and str(candidate) not in files:
                    try:
                        text = candidate.read_text(encoding="utf-8", errors="replace")
                        if total + len(text) > limit:
                            text = text[: limit - total]
                        files[part.lstrip("/")] = text
                        total += len(text)
                        if total >= limit:
                            break
                    except OSError:
                        pass
        if total >= limit:
            break

    return files


def _build_fix_prompt(test_output: str, file_context: dict[str, str], attempt: int) -> str:
    ctx_parts = []
    for path, content in file_context.items():
        ctx_parts.append(f'<file path="{path}">\n{content}\n</file>')

    file_ctx = "\n".join(ctx_parts) if ctx_parts else "(no source files identified)"
    truncated_output = test_output[-_MAX_OUTPUT_CHARS:]

    return f"""You are a senior Python engineer fixing a failing test suite.
This is fix attempt {attempt}.

## Failing test output

```
{truncated_output}
```

## Relevant source files

{file_ctx}

## Task

Analyze the failing tests and provide minimal code fixes.
Return ONLY a JSON array of file changes in this exact format:

```json
[
  {{
    "path": "relative/path/to/file.py",
    "content": "complete file content here"
  }}
]
```

Rules:
- Only modify files that directly cause the failures.
- Return complete file contents (not diffs).
- Do not change tests unless the test itself is clearly wrong.
- Do not add new dependencies.
- Keep changes minimal.
- If you cannot fix the issue, return an empty array: []
"""


def _parse_file_changes(text: str) -> list[dict[str, str]] | None:
    """
    Extract a JSON array of {"path": ..., "content": ...} from Claude's response.
    """
    # Find JSON block
    import re

    # Try code fence first
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m:
        json_str = m.group(1)
    else:
        # Try to find bare array
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return None
        json_str = m.group(0)

    try:
        changes = json.loads(json_str)
        if not isinstance(changes, list):
            return None
        # Validate each entry
        valid = []
        for item in changes:
            if isinstance(item, dict) and "path" in item and "content" in item:
                valid.append({"path": str(item["path"]), "content": str(item["content"])})
        return valid or None
    except json.JSONDecodeError:
        return None
