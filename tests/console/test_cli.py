"""CLI integration tests for the console command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from atlasbridge.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


class TestConsoleCommand:
    def test_console_command_exists(self, runner):
        """The console command must be registered."""
        result = runner.invoke(cli, ["console", "--help"])
        assert result.exit_code == 0
        assert "console" in result.output.lower()

    def test_console_help_contains_keywords(self, runner):
        """Help text should describe what the console does."""
        result = runner.invoke(cli, ["console", "--help"])
        assert result.exit_code == 0
        assert "operator console" in result.output.lower() or "daemon" in result.output.lower()

    def test_console_requires_tty(self, runner):
        """Non-TTY invocation should produce an error."""
        # CliRunner does not provide a TTY — so the command should exit with error
        result = runner.invoke(cli, ["console"])
        assert result.exit_code != 0
        assert "tty" in result.output.lower() or "terminal" in result.output.lower()

    def test_console_default_tool(self, runner):
        """Default tool option should be 'claude'."""
        result = runner.invoke(cli, ["console", "--help"])
        assert "claude" in result.output

    def test_console_custom_tool_option(self, runner):
        """--tool option should be accepted."""
        result = runner.invoke(cli, ["console", "--help"])
        assert "--tool" in result.output

    def test_console_custom_port_option(self, runner):
        """--dashboard-port option should be accepted."""
        result = runner.invoke(cli, ["console", "--help"])
        assert "--dashboard-port" in result.output

    def test_console_in_top_level_help(self, runner):
        """The console command should appear in the top-level help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "console" in result.output
