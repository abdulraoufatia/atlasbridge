"""CLI command for the operator console."""

from __future__ import annotations

import sys

import click


@click.command("console")
@click.option("--tool", default="claude", show_default=True, help="Default agent tool to launch")
@click.option("--dashboard-port", default=3737, show_default=True, help="Dashboard server port")
def console_cmd(tool: str, dashboard_port: int) -> None:
    """Launch the operator console (manages daemon, agent, dashboard)."""
    if not sys.stdout.isatty():
        click.echo(
            "Error: 'atlasbridge console' requires an interactive terminal (TTY).",
            err=True,
        )
        raise SystemExit(1)

    from atlasbridge.console.app import run as console_run

    console_run(default_tool=tool, dashboard_port=dashboard_port)
