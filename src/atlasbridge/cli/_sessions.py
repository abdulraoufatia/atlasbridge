"""atlasbridge sessions — list active sessions."""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table


def cmd_sessions(as_json: bool, console: Console) -> None:
    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    sessions: list[dict] = []

    try:
        config = load_config()
        db_path = config.db_path
        if db_path.exists():
            from atlasbridge.core.store.database import Database

            db = Database(db_path)
            db.connect()
            try:
                rows = db.list_active_sessions()
                for row in rows:
                    entry = dict(row)
                    pending = db.list_pending_prompts(session_id=entry["id"])
                    entry["pending_prompts"] = len(pending)
                    sessions.append(entry)
            finally:
                db.close()
    except (ConfigNotFoundError, ConfigError):
        if as_json:
            print(json.dumps({"error": "AtlasBridge is not configured yet."}, indent=2))
        else:
            console.print("[yellow]AtlasBridge is not configured yet.[/yellow]")
            console.print("Run [cyan]atlasbridge setup[/cyan] to get started.")
        return

    if as_json:
        print(json.dumps(sessions, indent=2, default=str))
        return

    console.print("[bold]Active Sessions[/bold]\n")

    if not sessions:
        console.print("  [dim]No active sessions.[/dim]")
        console.print("\nRun [cyan]atlasbridge run <tool>[/cyan] to start a session.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Tool")
    table.add_column("Status")
    table.add_column("Started")
    table.add_column("Pending", justify="right")
    for s in sessions:
        table.add_row(
            str(s.get("id", ""))[:12],
            str(s.get("tool", "")),
            str(s.get("status", "")),
            str(s.get("started_at", ""))[:19],
            str(s.get("pending_prompts", 0)),
        )
    console.print(table)
