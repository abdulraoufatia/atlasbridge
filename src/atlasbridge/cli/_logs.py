"""atlasbridge logs — show recent audit log events."""

from __future__ import annotations

import json
import time

from rich.console import Console
from rich.table import Table


def cmd_logs(session_id: str, tail: bool, limit: int, as_json: bool, console: Console) -> None:
    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    try:
        config = load_config()
        db_path = config.db_path
    except (ConfigNotFoundError, ConfigError):
        if as_json:
            print(json.dumps({"error": "AtlasBridge is not configured yet."}, indent=2))
        else:
            console.print("[yellow]AtlasBridge is not configured yet.[/yellow]")
            console.print("Run [cyan]atlasbridge setup[/cyan] to get started.")
        return

    if not db_path.exists():
        if as_json:
            print(json.dumps([], indent=2))
        else:
            console.print("[bold]Audit Log[/bold]\n")
            console.print("  [dim]No database found. Start a session first.[/dim]")
        return

    from atlasbridge.core.store.database import Database

    db = Database(db_path)
    db.connect()
    try:
        if tail:
            _tail_loop(db, session_id, limit, as_json, console)
        else:
            _show_events(db, session_id, limit, as_json, console)
    finally:
        db.close()


def _show_events(db: object, session_id: str, limit: int, as_json: bool, console: Console) -> None:
    rows = db.get_recent_audit_events(limit=limit)
    events = [dict(r) for r in rows]

    if session_id:
        events = [e for e in events if str(e.get("session_id", "")).startswith(session_id)]

    if as_json:
        print(json.dumps(events, indent=2, default=str))
        return

    console.print("[bold]Audit Log[/bold]\n")

    if not events:
        console.print("  [dim]No log entries.[/dim]")
        return

    _print_table(events, console)


def _tail_loop(db: object, session_id: str, limit: int, as_json: bool, console: Console) -> None:
    if not as_json:
        console.print("[bold]Audit Log[/bold] [dim](following — Ctrl+C to stop)[/dim]\n")

    last_timestamp = ""
    # Show initial batch
    rows = db.get_recent_audit_events(limit=limit)
    events = [dict(r) for r in rows]
    if session_id:
        events = [e for e in events if str(e.get("session_id", "")).startswith(session_id)]

    if events:
        if as_json:
            for e in events:
                print(json.dumps(e, default=str))
        else:
            _print_table(events, console)
        last_timestamp = str(events[0].get("timestamp", ""))

    try:
        while True:
            time.sleep(2.0)
            rows = db.get_recent_audit_events(limit=20)
            new_events = []
            for r in rows:
                e = dict(r)
                ts = str(e.get("timestamp", ""))
                if ts > last_timestamp:
                    new_events.append(e)
            if session_id:
                new_events = [
                    e for e in new_events if str(e.get("session_id", "")).startswith(session_id)
                ]
            if new_events:
                new_events.reverse()  # oldest first
                if as_json:
                    for e in new_events:
                        print(json.dumps(e, default=str))
                else:
                    _print_table(new_events, console)
                last_timestamp = str(new_events[-1].get("timestamp", ""))
    except KeyboardInterrupt:
        if not as_json:
            console.print("\n[dim]Stopped.[/dim]")


def _print_table(events: list[dict], console: Console) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Timestamp", no_wrap=True)
    table.add_column("Event")
    table.add_column("Session", style="cyan")
    table.add_column("Prompt", style="dim")
    table.add_column("Details", max_width=40)
    for e in events:
        payload = str(e.get("payload", "{}"))
        if len(payload) > 40:
            payload = payload[:37] + "..."
        table.add_row(
            str(e.get("timestamp", ""))[:19],
            str(e.get("event_type", "")),
            str(e.get("session_id", ""))[:12],
            str(e.get("prompt_id", ""))[:12],
            payload,
        )
    console.print(table)
