"""atlasbridge workspace — workspace trust management."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _open_db():
    """Open the AtlasBridge database, or return None if unavailable."""
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


@click.group("workspace", invoke_without_command=True)
@click.pass_context
def workspace_group(ctx: click.Context) -> None:
    """Workspace trust management."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(workspace_list)


@workspace_group.command("trust")
@click.argument("path")
@click.option("--actor", default="cli", help="Actor granting trust (for audit log)")
def workspace_trust(path: str, actor: str) -> None:
    """Grant trust to a workspace directory."""
    from atlasbridge.core.store.workspace_trust import grant_trust

    resolved = str(Path(path).resolve())
    db = _open_db()
    if db is None:
        console.print("[red]No database found. Run atlasbridge run once to initialise.[/red]")
        sys.exit(1)

    try:
        grant_trust(resolved, db._conn, actor=actor, channel="cli")
        console.print(f"[green]Trusted:[/green] {resolved}")
    finally:
        db.close()


@workspace_group.command("revoke")
@click.argument("path")
def workspace_revoke(path: str) -> None:
    """Revoke trust for a workspace directory."""
    from atlasbridge.core.store.workspace_trust import revoke_trust

    resolved = str(Path(path).resolve())
    db = _open_db()
    if db is None:
        console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        revoke_trust(resolved, db._conn)
        console.print(f"[yellow]Revoked:[/yellow] {resolved}")
    finally:
        db.close()


@workspace_group.command("list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def workspace_list(as_json: bool = False) -> None:
    """List all workspaces and their trust status."""
    from atlasbridge.core.store.workspace_trust import list_workspaces

    db = _open_db()
    if db is None:
        if as_json:
            print("[]")
        else:
            console.print("[dim]No database found. No workspaces recorded.[/dim]")
        return

    try:
        rows = list_workspaces(db._conn)

        if as_json:
            print(json.dumps(rows, indent=2, default=str))
            return

        if not rows:
            console.print("[dim]No workspaces recorded.[/dim]")
            return

        table = Table(title="Workspace Trust", show_lines=False)
        table.add_column("Path", style="cyan")
        table.add_column("Trusted", justify="center")
        table.add_column("Actor", style="dim")
        table.add_column("Granted At", style="dim")

        for row in rows:
            trusted_str = "[green]yes[/green]" if row.get("trusted") else "[red]no[/red]"
            granted = (row.get("granted_at") or "")[:19]
            table.add_row(
                row.get("path", ""),
                trusted_str,
                row.get("actor") or "-",
                granted or "-",
            )

        console.print(table)
    finally:
        db.close()


@workspace_group.command("status")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def workspace_status(path: str, as_json: bool = False) -> None:
    """Check trust status for a specific workspace directory."""
    from atlasbridge.core.store.workspace_trust import get_workspace_status

    resolved = str(Path(path).resolve())
    db = _open_db()
    if db is None:
        if as_json:
            print(json.dumps({"path": resolved, "trusted": False, "found": False}))
        else:
            console.print("[dim]No database found.[/dim]")
        return

    try:
        record = get_workspace_status(resolved, db._conn)

        if as_json:
            if record:
                print(json.dumps(record, indent=2, default=str))
            else:
                print(json.dumps({"path": resolved, "trusted": False, "found": False}))
            return

        if record is None:
            console.print(f"[dim]Not recorded:[/dim] {resolved}")
            return

        trusted = record.get("trusted")
        style = "green" if trusted else "red"
        console.print(f"Path:    {record['path']}")
        console.print(f"Trusted: [{style}]{'yes' if trusted else 'no'}[/{style}]")
        if record.get("actor"):
            console.print(f"Actor:   {record['actor']}")
        if record.get("granted_at"):
            console.print(f"Granted: {record['granted_at'][:19]}")
        if record.get("revoked_at"):
            console.print(f"Revoked: {record['revoked_at'][:19]}")
    finally:
        db.close()
