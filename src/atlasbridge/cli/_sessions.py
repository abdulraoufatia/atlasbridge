"""atlasbridge sessions — list and inspect sessions."""

from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("sessions", invoke_without_command=True)
@click.pass_context
def sessions_group(ctx: click.Context) -> None:
    """Session lifecycle commands."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(sessions_list)


@sessions_group.command("list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option("--all", "show_all", is_flag=True, default=False, help="Include completed sessions")
@click.option("--limit", default=50, show_default=True, help="Max sessions to show")
def sessions_list(as_json: bool = False, show_all: bool = False, limit: int = 50) -> None:
    """List active and recent sessions."""
    cmd_sessions_list(as_json=as_json, show_all=show_all, limit=limit, console=console)


@sessions_group.command("show")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def sessions_show(session_id: str, as_json: bool = False) -> None:
    """Show details for a specific session."""
    cmd_sessions_show(session_id=session_id, as_json=as_json, console=console)


@sessions_group.command("trace")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option(
    "--type",
    "event_type",
    default=None,
    help="Filter by event type (e.g. prompt_detected, response_injected).",
)
def sessions_trace(session_id: str, as_json: bool = False, event_type: str | None = None) -> None:
    """Show chronological governance trace for a session."""
    cmd_sessions_trace(
        session_id=session_id, as_json=as_json, event_type=event_type, console=console
    )


def _open_db():
    """Open the AtlasBridge database if it exists, or return None."""
    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    try:
        config = load_config()
        db_path = config.db_path
        if not db_path.exists():
            return None
        from atlasbridge.core.store.database import Database

        db = Database(db_path)
        db.connect()
        return db
    except (ConfigNotFoundError, ConfigError):
        return None


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row else {}


# ------------------------------------------------------------------
# sessions list
# ------------------------------------------------------------------

_STATUS_STYLE = {
    "starting": "yellow",
    "running": "green",
    "awaiting_reply": "bold cyan",
    "completed": "dim",
    "crashed": "red",
    "canceled": "dim red",
}


def cmd_sessions_list(
    *,
    as_json: bool,
    show_all: bool,
    limit: int,
    console: Console,
) -> None:
    """List sessions from the database."""
    db = _open_db()
    if db is None:
        if as_json:
            print("[]")
        else:
            console.print("[bold]Active Sessions[/bold]\n")
            console.print("  [dim]No active sessions.[/dim]")
            console.print("\nRun [cyan]atlasbridge run <tool>[/cyan] to start a session.")
        return

    try:
        if show_all:
            rows = db.list_sessions(limit=limit)
        else:
            rows = db.list_active_sessions()

        if as_json:
            data = [_row_to_dict(r) for r in rows]
            print(json.dumps(data, indent=2, default=str))
            return

        if not rows:
            console.print("[bold]Active Sessions[/bold]\n")
            console.print("  [dim]No active sessions.[/dim]")
            console.print("\nRun [cyan]atlasbridge run <tool>[/cyan] to start a session.")
            return

        table = Table(title="Sessions", show_lines=False)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Tool", style="bold")
        table.add_column("Status")
        table.add_column("PID", justify="right")
        table.add_column("Started", style="dim")
        table.add_column("Label")

        for row in rows:
            sid = row["id"][:8]
            tool = row["tool"] or ""
            status = row["status"] or ""
            pid = str(row["pid"]) if row["pid"] else "-"
            started = (row["started_at"] or "")[:19]
            label = row["label"] or ""
            style = _STATUS_STYLE.get(status, "")
            table.add_row(sid, tool, f"[{style}]{status}[/{style}]", pid, started, label)

        console.print(table)
    finally:
        db.close()


# ------------------------------------------------------------------
# sessions show
# ------------------------------------------------------------------


def cmd_sessions_show(
    *,
    session_id: str,
    as_json: bool,
    console: Console,
) -> None:
    """Show detailed information for a single session."""
    db = _open_db()
    if db is None:
        console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        # Support short IDs — find matching session
        row = db.get_session(session_id)
        if row is None:
            # Try prefix match
            all_rows = db.list_sessions(limit=500)
            matches = [r for r in all_rows if r["id"].startswith(session_id)]
            if len(matches) == 1:
                row = db.get_session(matches[0]["id"])
            elif len(matches) > 1:
                console.print(
                    f"[yellow]Ambiguous ID '{session_id}' matches "
                    f"{len(matches)} sessions. Use more characters.[/yellow]"
                )
                sys.exit(1)

        if row is None:
            console.print(f"[red]Session not found: {session_id}[/red]")
            sys.exit(1)

        session = _row_to_dict(row)
        full_id = session["id"]
        prompts = [_row_to_dict(p) for p in db.list_prompts_for_session(full_id)]
        prompt_count = len(prompts)

        if as_json:
            session["prompts"] = prompts
            print(json.dumps(session, indent=2, default=str))
            return

        # Rich formatted output
        status = session.get("status", "")
        style = _STATUS_STYLE.get(status, "")

        console.print(f"\n[bold]Session {full_id[:8]}[/bold]")
        console.print(f"  Full ID:   {full_id}")
        console.print(f"  Tool:      {session.get('tool', '-')}")
        console.print(f"  Status:    [{style}]{status}[/{style}]")
        console.print(f"  PID:       {session.get('pid', '-')}")
        console.print(f"  CWD:       {session.get('cwd', '-')}")
        console.print(f"  Label:     {session.get('label', '-') or '-'}")
        console.print(f"  Command:   {session.get('command', '-')}")
        console.print(f"  Started:   {session.get('started_at', '-')}")
        ended = session.get("ended_at") or "-"
        console.print(f"  Ended:     {ended}")
        exit_code = session.get("exit_code")
        console.print(f"  Exit code: {exit_code if exit_code is not None else '-'}")
        console.print(f"  Prompts:   {prompt_count}")

        if prompts:
            console.print("\n[bold]Prompts[/bold]")
            prompt_table = Table(show_lines=False)
            prompt_table.add_column("ID", style="cyan", no_wrap=True)
            prompt_table.add_column("Type")
            prompt_table.add_column("Confidence")
            prompt_table.add_column("Status")
            prompt_table.add_column("Created", style="dim")

            for p in prompts:
                pid = p.get("id", "")[:8]
                ptype = p.get("prompt_type", "")
                conf = p.get("confidence", "")
                pstatus = p.get("status", "")
                created = (p.get("created_at", "") or "")[:19]
                prompt_table.add_row(pid, ptype, conf, pstatus, created)

            console.print(prompt_table)
    finally:
        db.close()


# ------------------------------------------------------------------
# sessions trace
# ------------------------------------------------------------------


def cmd_sessions_trace(
    *,
    session_id: str,
    as_json: bool,
    event_type: str | None,
    console: Console,
) -> None:
    """Render the governance trace timeline for a session."""
    from atlasbridge.core.session.trace import (
        build_session_trace,
        format_trace,
        trace_to_json,
    )

    db = _open_db()
    if db is None:
        console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        # Support short IDs via prefix match
        full_id = _resolve_session_id(db, session_id)
        if full_id is None:
            console.print(f"[red]Session not found: {session_id}[/red]")
            sys.exit(1)

        trace = build_session_trace(db, full_id)
        if trace is None:
            console.print(f"[red]Session not found: {session_id}[/red]")
            sys.exit(1)

        # Apply event type filter
        if event_type:
            trace.events = [e for e in trace.events if e.event_type == event_type]
            trace.event_count = len(trace.events)

        if as_json:
            print(trace_to_json(trace))
        else:
            console.print(format_trace(trace))
    finally:
        db.close()


def _resolve_session_id(db, session_id: str) -> str | None:
    """Resolve a short or full session ID to a full session ID."""
    row = db.get_session(session_id)
    if row is not None:
        return row["id"]
    # Try prefix match
    all_rows = db.list_sessions(limit=500)
    matches = [r for r in all_rows if r["id"].startswith(session_id)]
    if len(matches) == 1:
        return matches[0]["id"]
    return None
