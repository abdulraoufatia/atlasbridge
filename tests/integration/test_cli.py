"""
Integration tests for the AtlasBridge CLI (Click runner).

These tests exercise the full CLI stack without external services.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from atlasbridge.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Write a minimal valid config with a temp DB path and return its path."""
    import tomli_w

    data = {
        "config_version": 1,
        "database": {
            "path": str(tmp_path / "test.db"),
        },
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
        cfg = tmp_path / "config.toml"
        result = runner.invoke(
            cli,
            ["setup", "--no-keyring", "--from-env"],
            catch_exceptions=False,
            env={"ATLASBRIDGE_CONFIG": str(cfg)},
        )
        assert result.exit_code == 0
        assert cfg.exists()

    def test_setup_non_interactive(self, runner: CliRunner, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        result = runner.invoke(
            cli,
            ["setup", "--non-interactive"],
            env={"ATLASBRIDGE_CONFIG": str(cfg)},
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


class TestStatusCommand:
    def test_status_no_sessions(self, runner: CliRunner, config_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["status"],
            env={"ATLASBRIDGE_CONFIG": str(config_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_status_json(self, runner: CliRunner, config_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["status", "--json"],
            env={"ATLASBRIDGE_CONFIG": str(config_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "daemon" in data
        assert "active_sessions" in data

    def test_status_no_config(self, runner: CliRunner, tmp_path: Path) -> None:
        # status without a config should still run (just skips DB query)
        result = runner.invoke(
            cli,
            ["status"],
            env={"HOME": str(tmp_path)},
        )
        # Should not crash — may show "not running" without a config
        assert isinstance(result.exit_code, int)


# ---------------------------------------------------------------------------
# version command
# ---------------------------------------------------------------------------


class TestVersionCommand:
    def test_version_output(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["version"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "atlasbridge" in result.output.lower()

    def test_version_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["version", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "atlasbridge" in data
        assert "python" in data


# ---------------------------------------------------------------------------
# doctor command
# ---------------------------------------------------------------------------


class TestDoctorCommand:
    def test_doctor_runs(self, runner: CliRunner, config_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["doctor"],
            env={"ATLASBRIDGE_CONFIG": str(config_path)},
            catch_exceptions=False,
        )
        assert isinstance(result.exit_code, int)

    def test_doctor_json(self, runner: CliRunner, config_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["doctor", "--json"],
            env={"ATLASBRIDGE_CONFIG": str(config_path)},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "checks" in data


# ---------------------------------------------------------------------------
# adapter list command
# ---------------------------------------------------------------------------


class TestAdapterList:
    def test_adapter_list_runs(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["adapter", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "claude" in result.output.lower()

    def test_adapter_list_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["adapter", "list", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(a["name"] == "claude" for a in data)


# ---------------------------------------------------------------------------
# adapter list
# ---------------------------------------------------------------------------


class TestAdapterListCommand:
    def test_adapter_registered(self, runner: CliRunner) -> None:
        # adapter command is registered (hidden from --help but still callable)
        assert "adapter" in cli.commands

    def test_adapter_list_exits_zero(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["adapter", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "claude" in result.output.lower()

    def test_adapter_list_shows_all_builtins(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["adapter", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        output = result.output.lower()
        for name in ("claude", "openai", "gemini"):
            assert name in output, f"expected {name!r} in adapter list output"

    def test_adapter_list_json_valid(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["adapter", "list", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 3

    def test_adapter_list_json_claude_present(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["adapter", "list", "--json"], catch_exceptions=False)
        import json

        data = json.loads(result.output)
        assert any(a["name"] == "claude" for a in data)


# ---------------------------------------------------------------------------
# sessions message command
# ---------------------------------------------------------------------------


class TestSessionsMessageCommand:
    def test_message_no_db(self, runner: CliRunner, tmp_path: Path) -> None:
        """sessions message fails gracefully when no DB exists."""
        result = runner.invoke(
            cli,
            ["sessions", "message", "nonexistent", "hello"],
            env={"ATLASBRIDGE_CONFIG": str(tmp_path / "nope.toml")},
        )
        assert result.exit_code != 0

    def test_message_session_not_found(self, runner: CliRunner, config_path: Path) -> None:
        """sessions message fails when session doesn't exist."""
        result = runner.invoke(
            cli,
            ["sessions", "message", "nonexistent-session", "hello"],
            env={"ATLASBRIDGE_CONFIG": str(config_path)},
        )
        assert result.exit_code != 0
        import json

        data = json.loads(result.output)
        assert data["ok"] is False


# ---------------------------------------------------------------------------
# lab commands
# ---------------------------------------------------------------------------


class TestLabCommands:
    def test_lab_list_runs(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["lab", "list"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_lab_list_json(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["lab", "list", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        import json

        json.loads(result.output)  # should be valid JSON
