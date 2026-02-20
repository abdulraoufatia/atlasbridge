"""
Integration tests for the Aegis CLI (Click runner).

These tests exercise the full CLI stack without external services.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from aegis.cli.main import cli

VALID_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Write a minimal valid config and return its path."""
    import tomli_w

    data = {
        "telegram": {
            "bot_token": VALID_TOKEN,
            "allowed_users": [12345678],
        }
    }
    p = tmp_path / "config.toml"
    with open(p, "wb") as f:
        tomli_w.dump(data, f)
    return p


# ---------------------------------------------------------------------------
# setup command
# ---------------------------------------------------------------------------


class TestSetupCommand:
    def test_setup_writes_config(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["setup", "--token", VALID_TOKEN, "--users", "12345678"],
            catch_exceptions=False,
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code == 0
        assert "saved" in result.output.lower() or "config" in result.output.lower()

    def test_setup_bad_token_exits_nonzero(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["setup", "--token", "badtoken", "--users", "12345678"],
            env={"HOME": str(tmp_path)},
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


class TestStatusCommand:
    def test_status_no_sessions(self, runner: CliRunner, config_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["status"],
            env={"AEGIS_CONFIG": str(config_path)},
            catch_exceptions=False,
        )
        # Should not crash; either shows "No active sessions" or a table
        assert result.exit_code == 0

    def test_status_missing_config(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["status"],
            env={"HOME": str(tmp_path)},
        )
        # Should exit non-zero with helpful message
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# doctor command
# ---------------------------------------------------------------------------


class TestDoctorCommand:
    def test_doctor_with_valid_config(self, runner: CliRunner, config_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["doctor"],
            env={"AEGIS_CONFIG": str(config_path)},
            catch_exceptions=False,
        )
        # May pass or fail individual checks but shouldn't crash
        assert isinstance(result.exit_code, int)


# ---------------------------------------------------------------------------
# approvals command
# ---------------------------------------------------------------------------


class TestApprovalsCommand:
    def test_approvals_empty(self, runner: CliRunner, config_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["approvals"],
            env={"AEGIS_CONFIG": str(config_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# audit verify command
# ---------------------------------------------------------------------------


class TestAuditVerifyCommand:
    def test_verify_no_log(self, runner: CliRunner, config_path: Path, tmp_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["audit", "verify"],
            env={"AEGIS_CONFIG": str(config_path), "HOME": str(tmp_path)},
            catch_exceptions=False,
        )
        # Either "no audit log found" message (ok) or a valid verification
        assert result.exit_code == 0 or "audit" in result.output.lower()
