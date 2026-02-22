"""atlasbridge start / stop — daemon lifecycle commands."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

from rich.console import Console


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
    except (ProcessLookupError, PermissionError):
        return False


def cmd_start(foreground: bool, console: Console) -> None:
    """Start the AtlasBridge daemon (foreground or background)."""
    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    # Check if already running
    existing_pid = _read_pid()
    if existing_pid and _pid_alive(existing_pid):
        console.print(
            f"[yellow]AtlasBridge daemon is already running (PID {existing_pid}).[/yellow]"
        )
        console.print("Use [cyan]atlasbridge stop[/cyan] to stop it first.")
        sys.exit(1)

    try:
        config = load_config()
    except ConfigNotFoundError as exc:
        console.print(f"[red]Not configured:[/red] {exc}")
        console.print("Run [cyan]atlasbridge setup[/cyan] first.")
        sys.exit(1)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        sys.exit(1)

    if foreground:
        console.print("[bold]Starting AtlasBridge daemon[/bold] (foreground)...")
        console.print("Press Ctrl+C to stop.\n")
        import asyncio

        from atlasbridge.core.daemon.manager import DaemonManager

        cfg_dict = _build_daemon_config(config)
        try:
            asyncio.run(DaemonManager(cfg_dict).start())
        except KeyboardInterrupt:
            console.print("\n[yellow]Daemon stopped.[/yellow]")
    else:
        # Fork into background
        pid_file = _pid_file_path()
        pid_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        child_pid = os.fork()
        if child_pid == 0:
            # Child process — become daemon
            os.setsid()
            import asyncio

            from atlasbridge.core.daemon.manager import DaemonManager

            cfg_dict = _build_daemon_config(config)
            asyncio.run(DaemonManager(cfg_dict).start())
            sys.exit(0)
        else:
            # Parent — report the child PID
            console.print(f"[green]AtlasBridge daemon started[/green] (PID {child_pid})")
            console.print(f"PID file: {pid_file}")
            console.print(
                "Use [cyan]atlasbridge status[/cyan] to check and [cyan]atlasbridge stop[/cyan] to stop."
            )


def cmd_stop(console: Console) -> None:
    """Stop the running AtlasBridge daemon."""
    pid = _read_pid()
    if pid is None:
        console.print("[yellow]AtlasBridge daemon is not running (no PID file).[/yellow]")
        return

    if not _pid_alive(pid):
        console.print(f"[yellow]No process with PID {pid}. Cleaning up stale PID file.[/yellow]")
        _pid_file_path().unlink(missing_ok=True)
        return

    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Sent SIGTERM to AtlasBridge daemon (PID {pid}).[/green]")
        console.print("Use [cyan]atlasbridge status[/cyan] to confirm it stopped.")
    except PermissionError:
        console.print(f"[red]Cannot send SIGTERM to PID {pid}: permission denied.[/red]")
        sys.exit(1)


def _build_daemon_config(config: object) -> dict:
    """Convert AtlasBridgeConfig into DaemonManager config dict."""
    bot_token = config.telegram.bot_token.get_secret_value()
    allowed_users = config.telegram.allowed_users
    db_path = config.db_path

    return {
        "data_dir": str(db_path.parent),
        "channels": {
            "telegram": {
                "bot_token": bot_token,
                "allowed_user_ids": allowed_users,
            }
        },
        "prompts": {
            "timeout_seconds": config.prompts.timeout_seconds,
            "stuck_timeout_seconds": config.prompts.stuck_timeout_seconds,
        },
    }
