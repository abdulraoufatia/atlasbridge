"""atlasbridge status — daemon and session status."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.command("status")
@click.option("--json", "as_json", is_flag=True, default=False)
def status_cmd(as_json: bool) -> None:
    """Show daemon and session status."""
    cmd_status(as_json=as_json, console=console)


def _pid_file_path() -> Path:
    from atlasbridge.core.constants import PID_FILENAME, _default_data_dir

    return _default_data_dir() / PID_FILENAME


def _read_pid() -> int | None:
    try:
        return int(_pid_file_path().read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_status(as_json: bool, console: Console) -> None:
    """Show daemon and session status."""

    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    # Daemon status
    pid = _read_pid()
    if pid and _pid_alive(pid):
        daemon_status = f"running (PID {pid})"
        daemon_running = True
    elif pid:
        daemon_status = f"stale PID file (PID {pid} not alive)"
        daemon_running = False
    else:
        daemon_status = "not running"
        daemon_running = False

    # Environment
    environment = ""

    # Session + prompt data from DB
    active_sessions: list[dict] = []
    pending_prompts = 0

    try:
        config = load_config()
        environment = config.runtime.environment
        db_path = config.db_path
        if db_path.exists():
            from atlasbridge.core.store.database import Database

            db = Database(db_path)
            db.connect()
            try:
                rows = db.list_active_sessions()
                for row in rows:
                    active_sessions.append(dict(row))
                pending_rows = db.list_pending_prompts()
                pending_prompts = len(pending_rows)
            finally:
                db.close()
    except (ConfigNotFoundError, ConfigError):
        # No config yet — just show daemon status
        pass

    if as_json:
        data = {
            "daemon": daemon_status,
            "daemon_running": daemon_running,
            "environment": environment,
            "active_sessions": len(active_sessions),
            "pending_prompts": pending_prompts,
            "sessions": active_sessions,
        }
        print(json.dumps(data, indent=2))
        return

    console.print("[bold]AtlasBridge Status[/bold]\n")

    # Environment
    if environment:
        env_color = {"production": "red", "staging": "yellow"}.get(environment, "green")
        console.print(f"  Environment: [{env_color}]{environment}[/{env_color}]")

    # Daemon row
    if daemon_running:
        console.print(f"  Daemon:   [green]{daemon_status}[/green]")
    else:
        console.print(f"  Daemon:   [yellow]{daemon_status}[/yellow]")
        console.print(
            "  Run [cyan]atlasbridge start[/cyan] or [cyan]atlasbridge run <tool>[/cyan] to start."
        )

    console.print(f"  Sessions: {len(active_sessions)} active")
    console.print(f"  Prompts:  {pending_prompts} pending\n")

    if active_sessions:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Session ID", style="cyan", no_wrap=True)
        table.add_column("Tool")
        table.add_column("Status")
        table.add_column("Started")
        for s in active_sessions:
            table.add_row(
                str(s.get("id", ""))[:12],
                str(s.get("tool", "")),
                str(s.get("status", "")),
                str(s.get("started_at", ""))[:19],
            )
        console.print(table)
    else:
        console.print("  [dim]No active sessions.[/dim]")
