"""
Integration tests for aegis pr-auto CLI commands.

Uses Click test runner with mocked GitHub API and daemon service.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from aegis.cli.main import cli

VALID_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    import tomli_w

    data = {
        "telegram": {
            "bot_token": VALID_TOKEN,
            "allowed_users": [12345678],
        },
        "auto_pr": {
            "enabled": True,
            "github_token": "ghp_test_token_abc123",
            "github_repo": "owner/repo",
            "dry_run": True,
        },
    }
    p = tmp_path / "config.toml"
    with open(p, "wb") as f:
        tomli_w.dump(data, f)
    return p


# ---------------------------------------------------------------------------
# pr-auto run-once
# ---------------------------------------------------------------------------


class TestPRAutoRunOnce:
    def test_run_once_no_prs(self, runner: CliRunner, config_path: Path) -> None:
        """Should exit 0 and print 'No open PRs found' when GitHub returns empty."""

        async def _fake_run_once(cfg):
            return []

        # Patch at the module level where it's imported at call time
        with patch(
            "aegis.core.daemon_services.pr_automation_service.run_once",
            side_effect=_fake_run_once,
        ):
            result = runner.invoke(
                cli,
                ["pr-auto", "run-once"],
                env={"AEGIS_CONFIG": str(config_path)},
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "No open PRs" in result.output

    def test_run_once_missing_token_exits_nonzero(self, runner: CliRunner, tmp_path: Path) -> None:
        import tomli_w

        data = {
            "telegram": {"bot_token": VALID_TOKEN, "allowed_users": [1]},
            "auto_pr": {"github_token": "", "github_repo": "", "dry_run": True},
        }
        p = tmp_path / "config.toml"
        with open(p, "wb") as f:
            tomli_w.dump(data, f)

        result = runner.invoke(
            cli,
            ["pr-auto", "run-once"],
            env={"AEGIS_CONFIG": str(p)},
        )
        assert result.exit_code != 0

    def test_run_once_json_output(self, runner: CliRunner, config_path: Path) -> None:
        from aegis.core.pr_automation import PRResult, SkipReason

        async def _fake(cfg):
            r = PRResult(pr_number=42, pr_title="Bump foo", branch="dep/foo")
            r.skipped = True
            r.skip_reason = SkipReason.ALL_CHECKS_PASSING
            return [r]

        with patch(
            "aegis.core.daemon_services.pr_automation_service.run_once",
            side_effect=_fake,
        ):
            result = runner.invoke(
                cli,
                ["pr-auto", "run-once", "--json"],
                env={"AEGIS_CONFIG": str(config_path)},
                catch_exceptions=True,  # capture errors for diagnosis
            )

        # If an error occurred, print it for debugging
        if result.exception:
            import traceback

            traceback.print_exception(
                type(result.exception), result.exception, result.exception.__traceback__
            )

        assert result.exit_code == 0, result.output
        import json

        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["pr_number"] == 42


# ---------------------------------------------------------------------------
# pr-auto status
# ---------------------------------------------------------------------------


class TestPRAutoStatus:
    def test_status_when_stopped(self, runner: CliRunner, config_path: Path) -> None:
        with (
            patch(
                "aegis.core.daemon_services.pr_automation_service.is_running",
                return_value=False,
            ),
            patch(
                "aegis.core.daemon_services.pr_automation_service._STATUS_FILE",
                Path("/nonexistent/status.json"),
            ),
        ):
            result = runner.invoke(
                cli,
                ["pr-auto", "status"],
                env={"AEGIS_CONFIG": str(config_path)},
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "stopped" in result.output.lower()

    def test_status_json_output(self, runner: CliRunner, config_path: Path) -> None:
        fake_status = {
            "running": False,
            "last_cycle": "2026-01-01T00:00:00Z",
            "results": [],
        }
        with patch(
            "aegis.core.daemon_services.pr_automation_service.get_status",
            return_value=fake_status,
        ):
            result = runner.invoke(
                cli,
                ["pr-auto", "status", "--json"],
                env={"AEGIS_CONFIG": str(config_path)},
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data["running"] is False


# ---------------------------------------------------------------------------
# pr-auto stop
# ---------------------------------------------------------------------------


class TestPRAutoStop:
    def test_stop_when_not_running(self, runner: CliRunner, config_path: Path) -> None:
        with patch(
            "aegis.core.daemon_services.pr_automation_service.stop",
            return_value=False,
        ):
            result = runner.invoke(
                cli,
                ["pr-auto", "stop"],
                env={"AEGIS_CONFIG": str(config_path)},
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "not running" in result.output.lower()

    def test_stop_when_running(self, runner: CliRunner, config_path: Path) -> None:
        with patch(
            "aegis.core.daemon_services.pr_automation_service.stop",
            return_value=True,
        ):
            result = runner.invoke(
                cli,
                ["pr-auto", "stop"],
                env={"AEGIS_CONFIG": str(config_path)},
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "stopped" in result.output.lower()
