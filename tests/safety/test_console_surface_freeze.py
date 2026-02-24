"""Safety guard: console command surface is frozen."""

from __future__ import annotations

import click
from click.testing import CliRunner


def test_console_command_exists():
    """Console command must exist as a top-level command."""
    from atlasbridge.cli.main import cli

    assert "console" in cli.commands, "console command missing from CLI"


def test_console_is_not_a_group():
    """Console is a standalone command, not a group."""
    from atlasbridge.cli.main import cli

    cmd = cli.commands["console"]
    assert not isinstance(cmd, click.Group), "console should be a command, not a group"


def test_console_has_tool_option():
    """Console must have --tool option."""
    from atlasbridge.cli.main import cli

    cmd = cli.commands["console"]
    param_names = [p.name for p in cmd.params]
    assert "tool" in param_names, "console missing --tool option"


def test_console_has_dashboard_port_option():
    """Console must have --dashboard-port option."""
    from atlasbridge.cli.main import cli

    cmd = cli.commands["console"]
    param_names = [p.name for p in cmd.params]
    assert "dashboard_port" in param_names, "console missing --dashboard-port option"


def test_console_tool_default_is_claude():
    """Console --tool must default to 'claude'."""
    from atlasbridge.cli.main import cli

    cmd = cli.commands["console"]
    tool_param = next(p for p in cmd.params if p.name == "tool")
    assert tool_param.default == "claude", (
        f"console --tool default changed from 'claude' to '{tool_param.default}'"
    )


def test_console_dashboard_port_default():
    """Console --dashboard-port must default to 3737."""
    from atlasbridge.cli.main import cli

    cmd = cli.commands["console"]
    port_param = next(p for p in cmd.params if p.name == "dashboard_port")
    assert port_param.default == 3737, (
        f"console --dashboard-port default changed from 3737 to {port_param.default}"
    )


def test_console_help_text():
    """Console help must mention key concepts."""
    runner = CliRunner()
    result = runner.invoke(
        __import__("atlasbridge.cli.main", fromlist=["cli"]).cli,
        ["console", "--help"],
    )
    assert result.exit_code == 0
    output = result.output.lower()
    assert "daemon" in output or "console" in output, "console help missing expected keywords"
