"""atlasbridge ui — launch the interactive TUI."""

from __future__ import annotations

import sys

import click
from rich.console import Console

err_console = Console(stderr=True)


@click.command("ui")
def ui_cmd() -> None:
    """Launch the interactive terminal UI (requires a TTY)."""
    if not sys.stdout.isatty():
        err_console.print(
            "[red]Error:[/red] 'atlasbridge ui' requires an interactive terminal (TTY)."
        )
        raise SystemExit(1)
    from atlasbridge.ui.app import run as tui_run

    tui_run()
