"""atlasbridge debug bundle — create a redacted support bundle."""

from __future__ import annotations

from rich.console import Console


def cmd_debug_bundle(output: str, include_logs: int, redact: bool, console: Console) -> None:
    console.print("[bold]Debug Bundle[/bold]")
    console.print("[yellow]Debug bundle not yet implemented (v0.2.0)[/yellow]")
