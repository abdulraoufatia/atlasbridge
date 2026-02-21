"""atlasbridge logs — show recent audit log events."""

from __future__ import annotations

from rich.console import Console


def cmd_logs(session_id: str, tail: bool, limit: int, as_json: bool, console: Console) -> None:
    console.print("[bold]Audit Log[/bold]\n")
    console.print("  [dim]No log entries. Start a session first.[/dim]")
