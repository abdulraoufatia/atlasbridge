"""atlasbridge sessions — list active sessions."""

from __future__ import annotations

import json

from rich.console import Console


def cmd_sessions(as_json: bool, console: Console) -> None:
    data: list = []
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        console.print("[bold]Active Sessions[/bold]\n")
        console.print("  [dim]No active sessions.[/dim]")
        console.print("\nRun [cyan]atlasbridge run <tool>[/cyan] to start a session.")
