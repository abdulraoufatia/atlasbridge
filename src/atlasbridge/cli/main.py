"""
AtlasBridge CLI entry point.

Commands:
  atlasbridge                    — launch interactive TUI (if stdout is a TTY)
  atlasbridge ui                 — launch interactive TUI (explicit)
  atlasbridge setup              — interactive first-time configuration
  atlasbridge start              — start the background daemon
  atlasbridge stop               — stop the background daemon
  atlasbridge status             — show daemon and session status
  atlasbridge run <tool> [args]  — launch a CLI tool under AtlasBridge supervision
  atlasbridge sessions           — list active sessions
  atlasbridge logs               — stream or show recent audit log
  atlasbridge doctor [--fix]     — environment and configuration health check
  atlasbridge debug bundle       — create a redacted support bundle
  atlasbridge channel add <type> — add/reconfigure a notification channel
  atlasbridge adapter list       — show available tool adapters
  atlasbridge adapters           — list installed adapters (top-level shortcut)
  atlasbridge version            — show version and feature flags
  atlasbridge lab run <scenario> — Prompt Lab: run a QA scenario (dev/CI only)
  atlasbridge lab list           — Prompt Lab: list registered scenarios
"""

from __future__ import annotations

import sys

import click
from rich.console import Console

from atlasbridge import __version__

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, "--version", "-V", message="atlasbridge %(version)s")
@click.option(
    "--log-level", default="WARNING", hidden=True, help="Log level for structured logging."
)
@click.option("--log-json", is_flag=True, default=False, hidden=True, help="Emit JSON log lines.")
@click.pass_context
def cli(ctx: click.Context, log_level: str, log_json: bool) -> None:
    """AtlasBridge — universal human-in-the-loop control plane for AI developer agents."""
    from atlasbridge.core.logging import configure_logging

    configure_logging(level=log_level, json_output=log_json)

    if ctx.invoked_subcommand is None:
        if sys.stdout.isatty():
            from atlasbridge.ui.app import run as tui_run

            tui_run()
        else:
            click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# ui (interactive TUI — explicit launch)
# ---------------------------------------------------------------------------


@cli.command()
def ui() -> None:
    """Launch the interactive terminal UI (requires a TTY)."""
    if not sys.stdout.isatty():
        err_console.print(
            "[red]Error:[/red] 'atlasbridge ui' requires an interactive terminal (TTY)."
        )
        raise SystemExit(1)
    from atlasbridge.ui.app import run as tui_run

    tui_run()


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--channel", type=click.Choice(["telegram", "slack"]), default="telegram")
@click.option("--non-interactive", is_flag=True, default=False, help="Read from env vars only")
@click.option(
    "--from-env", is_flag=True, default=False, help="Build config from ATLASBRIDGE_* env vars"
)
@click.option("--token", default="", help="Telegram bot token (non-interactive mode)")
@click.option("--users", default="", help="Comma-separated allowed Telegram user IDs")
def setup(channel: str, non_interactive: bool, from_env: bool, token: str, users: str) -> None:
    """Interactive first-time configuration wizard."""
    from atlasbridge.cli._setup import run_setup

    run_setup(
        channel=channel,
        non_interactive=non_interactive,
        console=console,
        token=token,
        users=users,
        from_env=from_env,
    )


# ---------------------------------------------------------------------------
# start / stop / status
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--foreground", "-f", is_flag=True, default=False, help="Run in foreground (do not daemonise)"
)
def start(foreground: bool) -> None:
    """Start the AtlasBridge daemon."""
    from atlasbridge.cli._daemon import cmd_start

    cmd_start(foreground=foreground, console=console)


@cli.command()
def stop() -> None:
    """Stop the running AtlasBridge daemon."""
    from atlasbridge.cli._daemon import cmd_stop

    cmd_stop(console=console)


@cli.command()
@click.option("--json", "as_json", is_flag=True, default=False)
def status(as_json: bool) -> None:
    """Show daemon and session status."""
    from atlasbridge.cli._status import cmd_status

    cmd_status(as_json=as_json, console=console)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@cli.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("tool", default="claude")
@click.argument("tool_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--session-label", default="", help="Human-readable label for this session")
@click.option("--cwd", default="", help="Working directory for the tool")
@click.option(
    "--policy",
    "policy_file",
    default="",
    help="Path to a policy YAML file (v0 or v1) for this session.",
)
def run(
    tool: str, tool_args: tuple[str, ...], session_label: str, cwd: str, policy_file: str
) -> None:
    """Launch a CLI tool under AtlasBridge supervision."""
    from atlasbridge.cli._run import cmd_run

    command = [tool] + list(tool_args)
    cmd_run(
        tool=tool,
        command=command,
        label=session_label,
        cwd=cwd,
        policy_file=policy_file,
        console=console,
    )


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------


@cli.group(invoke_without_command=True)
@click.pass_context
def sessions(ctx: click.Context) -> None:
    """Session lifecycle commands."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(sessions_list)


@sessions.command("list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option("--all", "show_all", is_flag=True, default=False, help="Include completed sessions")
@click.option("--limit", default=50, show_default=True, help="Max sessions to show")
def sessions_list(as_json: bool = False, show_all: bool = False, limit: int = 50) -> None:
    """List active and recent sessions."""
    from atlasbridge.cli._sessions import cmd_sessions_list

    cmd_sessions_list(as_json=as_json, show_all=show_all, limit=limit, console=console)


@sessions.command("show")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def sessions_show(session_id: str, as_json: bool = False) -> None:
    """Show details for a specific session."""
    from atlasbridge.cli._sessions import cmd_sessions_show

    cmd_sessions_show(session_id=session_id, as_json=as_json, console=console)


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--session", "session_id", default="", help="Filter by session ID prefix")
@click.option("--tail", is_flag=True, default=False, help="Follow log output")
@click.option("--limit", default=50, help="Number of recent events to show")
@click.option("--json", "as_json", is_flag=True, default=False)
def logs(session_id: str, tail: bool, limit: int, as_json: bool) -> None:
    """Show recent audit log events."""
    from atlasbridge.cli._logs import cmd_logs

    cmd_logs(session_id=session_id, tail=tail, limit=limit, as_json=as_json, console=console)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--fix", is_flag=True, default=False, help="Auto-repair fixable issues")
@click.option("--json", "as_json", is_flag=True, default=False)
def doctor(fix: bool, as_json: bool) -> None:
    """Environment and configuration health check."""
    from atlasbridge.cli._doctor import cmd_doctor

    cmd_doctor(fix=fix, as_json=as_json, console=console)


# ---------------------------------------------------------------------------
# debug
# ---------------------------------------------------------------------------


@cli.group()
def debug() -> None:
    """Debugging utilities."""


@debug.command("bundle")
@click.option("--output", default="", help="Output path for the bundle")
@click.option("--include-logs", default=500, help="Number of log lines to include")
@click.option("--no-redact", is_flag=True, default=False, help="Include secrets unredacted")
def debug_bundle(output: str, include_logs: int, no_redact: bool) -> None:
    """Create a redacted support bundle."""
    from atlasbridge.cli._debug import cmd_debug_bundle

    cmd_debug_bundle(
        output=output, include_logs=include_logs, redact=not no_redact, console=console
    )


# ---------------------------------------------------------------------------
# channel
# ---------------------------------------------------------------------------


@cli.group()
def channel() -> None:
    """Notification channel management."""


@channel.command("add")
@click.argument("channel_type", metavar="TYPE", type=click.Choice(["telegram", "slack"]))
@click.option("--token", default="", help="Bot token")
@click.option("--users", default="", help="Comma-separated user IDs")
def channel_add(channel_type: str, token: str, users: str) -> None:
    """Add or reconfigure a notification channel."""
    from atlasbridge.cli._channel import cmd_channel_add

    cmd_channel_add(channel_type=channel_type, token=token, users=users, console=console)


# ---------------------------------------------------------------------------
# adapter
# ---------------------------------------------------------------------------


@cli.group()
def adapter() -> None:
    """Tool adapter management."""


@adapter.command("list")
@click.option("--json", "as_json", is_flag=True, default=False)
def adapter_list(as_json: bool) -> None:
    """Show available tool adapters."""
    import atlasbridge.adapters  # noqa: F401 — registers all built-in adapters
    from atlasbridge.adapters.base import AdapterRegistry

    adapters = AdapterRegistry.list_all()
    if as_json:
        import json

        rows = [
            {
                "name": name,
                "tool_name": cls.tool_name,
                "description": cls.description,
                "min_version": cls.min_tool_version,
            }
            for name, cls in adapters.items()
        ]
        click.echo(json.dumps(rows, indent=2))
    else:
        console.print("\n[bold]Available Adapters[/bold]\n")
        for name, cls in adapters.items():
            console.print(
                f"  [cyan]{name:<12}[/cyan] {cls.description or '—'}"
                + (f"  (min: {cls.min_tool_version})" if cls.min_tool_version else "")
            )
        console.print()


# ---------------------------------------------------------------------------
# adapters (top-level shortcut)
# ---------------------------------------------------------------------------


@cli.command("adapters")
@click.option("--json", "as_json", is_flag=True, default=False, help="Machine-readable JSON output")
def adapters_cmd(as_json: bool) -> None:
    """List installed tool adapters."""
    import shutil

    import atlasbridge.adapters  # noqa: F401 — registers all built-in adapters
    from atlasbridge.adapters.base import AdapterRegistry

    registry = AdapterRegistry.list_all()

    if not registry:
        err_console.print(
            "[red]Error:[/red] No adapters found. Reinstall: pip install -U atlasbridge"
        )
        raise SystemExit(1)

    if as_json:
        import json

        rows = []
        for name, cls in sorted(registry.items()):
            rows.append(
                {
                    "name": name,
                    "kind": "llm",
                    "enabled": bool(shutil.which(cls.tool_name) if cls.tool_name else False),
                    "source": "builtin",
                    "tool_name": cls.tool_name,
                    "description": cls.description,
                    "min_version": cls.min_tool_version,
                }
            )
        click.echo(json.dumps({"adapters": rows, "count": len(rows)}, indent=2))
    else:
        console.print("\n[bold]Installed Adapters[/bold]\n")
        for name, cls in sorted(registry.items()):
            on_path = bool(shutil.which(cls.tool_name)) if cls.tool_name else False
            status = "[green]on PATH[/green]" if on_path else "[dim]not on PATH[/dim]"
            desc = cls.description or "—"
            ver = f"  (min: {cls.min_tool_version})" if cls.min_tool_version else ""
            console.print(f"  [cyan]{name:<14}[/cyan] {desc}{ver}  {status}")
        console.print(f"\n  {len(registry)} adapter(s) registered.\n")


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show install path, config path, and build info",
)
@click.option("--experimental", is_flag=True, default=False, help="Show experimental flags")
def version(as_json: bool, verbose: bool, experimental: bool) -> None:
    """Show version information and feature flags."""
    import importlib.util
    import platform
    import sys as _sys

    flags = {
        "conpty_backend": False,
        "slack_channel": False,
        "whatsapp_channel": False,
    }
    if experimental:
        flags["windows_conpty"] = _sys.platform == "win32"

    # Resolve install path (location of the atlasbridge package)
    spec = importlib.util.find_spec("atlasbridge")
    install_path = str(spec.origin) if spec and spec.origin else "unknown"

    # Resolve config path
    try:
        from atlasbridge.core.constants import _default_data_dir

        config_path = str(_default_data_dir() / "config.toml")
    except Exception:  # noqa: BLE001
        config_path = "unknown"

    # Resolve commit SHA from package metadata (populated by setuptools-scm if used)
    commit_sha = "n/a"

    if as_json:
        import json

        data: dict = {
            "atlasbridge": __version__,
            "python": _sys.version.split()[0],
            "platform": _sys.platform,
            "arch": platform.machine(),
            "feature_flags": flags,
        }
        if verbose:
            data["install_path"] = install_path
            data["config_path"] = config_path
            data["commit"] = commit_sha
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"atlasbridge {__version__}")
        console.print(f"Python {_sys.version.split()[0]}")
        console.print(f"Platform: {_sys.platform} {platform.machine()}")
        if verbose:
            console.print(f"Install:  {install_path}")
            console.print(f"Config:   {config_path}")
            console.print(f"Commit:   {commit_sha}")
        console.print("\nFeature flags:")
        for flag, enabled in flags.items():
            status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
            console.print(f"  {flag:<22} {status}")


# ---------------------------------------------------------------------------
# db
# ---------------------------------------------------------------------------


@cli.group()
def db() -> None:
    """Database inspection and management."""


@db.command("info")
@click.option("--json", "as_json", is_flag=True, default=False)
def db_info(as_json: bool) -> None:
    """Show database path, schema version, and table stats."""
    from atlasbridge.core.config import atlasbridge_dir
    from atlasbridge.core.constants import DB_FILENAME

    db_path = atlasbridge_dir() / DB_FILENAME

    if not db_path.exists():
        if as_json:
            import json as _json

            click.echo(_json.dumps({"exists": False, "path": str(db_path)}))
        else:
            console.print(f"Database does not exist yet: {db_path}")
            console.print("It will be created on the first [cyan]atlasbridge run[/cyan].")
        return

    import sqlite3

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        from atlasbridge.core.store.migrations import LATEST_SCHEMA_VERSION, get_user_version

        version = get_user_version(conn)
        tables = {}
        for table in ("sessions", "prompts", "replies", "audit_events"):
            try:
                row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
                tables[table] = row[0] if row else 0
            except Exception:  # noqa: BLE001
                tables[table] = -1  # table missing

        size_kb = db_path.stat().st_size / 1024

        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "exists": True,
                        "path": str(db_path),
                        "schema_version": version,
                        "latest_version": LATEST_SCHEMA_VERSION,
                        "size_kb": round(size_kb, 1),
                        "tables": tables,
                    },
                    indent=2,
                )
            )
        else:
            console.print(f"[bold]Database[/bold]: {db_path}")
            console.print(f"Schema version: {version} (latest: {LATEST_SCHEMA_VERSION})")
            console.print(f"Size: {size_kb:.1f} KB")
            console.print("\nTable row counts:")
            for table, count in tables.items():
                status = f"{count}" if count >= 0 else "[red]missing[/red]"
                console.print(f"  {table:<16} {status}")
    finally:
        conn.close()


@db.command("migrate")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Show pending migrations without applying them."
)
@click.option(
    "--json", "as_json", is_flag=True, default=False, help="Machine-readable JSON output."
)
def db_migrate(dry_run: bool, as_json: bool) -> None:
    """Run (or preview) pending schema migrations."""
    from atlasbridge.core.config import atlasbridge_dir
    from atlasbridge.core.constants import DB_FILENAME

    db_path = atlasbridge_dir() / DB_FILENAME

    if not db_path.exists():
        if as_json:
            import json as _json

            click.echo(_json.dumps({"status": "no_database", "path": str(db_path)}))
        else:
            console.print(f"Database does not exist yet: {db_path}")
            console.print("It will be created on the first [cyan]atlasbridge run[/cyan].")
        return

    import sqlite3

    from atlasbridge.core.store.migrations import LATEST_SCHEMA_VERSION, get_user_version

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        current = get_user_version(conn)
        pending = list(range(current, LATEST_SCHEMA_VERSION))

        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "path": str(db_path),
                        "current_version": current,
                        "latest_version": LATEST_SCHEMA_VERSION,
                        "pending_migrations": [f"v{v} -> v{v + 1}" for v in pending],
                        "dry_run": dry_run,
                        "status": "up_to_date"
                        if not pending
                        else ("dry_run" if dry_run else "applied"),
                    },
                    indent=2,
                )
            )
            if not pending or dry_run:
                return

        if not pending:
            if not as_json:
                console.print(f"[green]Database is up to date[/green] (v{current}).")
            return

        if dry_run:
            if not as_json:
                console.print(f"[bold]Database[/bold]: {db_path}")
                console.print(f"Current schema version: {current}")
                console.print(f"Latest schema version:  {LATEST_SCHEMA_VERSION}")
                console.print(f"\n[yellow]Pending migrations ({len(pending)}):[/yellow]")
                for v in pending:
                    console.print(f"  v{v} -> v{v + 1}")
                console.print("\nRun without [cyan]--dry-run[/cyan] to apply.")
            return

        # Apply migrations
        conn.close()
        conn = None  # type: ignore[assignment]

        from atlasbridge.core.store.database import Database

        database = Database(db_path)
        database.connect()
        database.close()
        console.print(
            f"[green]Migrations applied successfully[/green] (v{current} -> v{LATEST_SCHEMA_VERSION})."
        )
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

from atlasbridge.cli._config_cmd import config_group  # noqa: E402

cli.add_command(config_group)


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------

from atlasbridge.cli._policy_cmd import policy_group  # noqa: E402

cli.add_command(policy_group)


# ---------------------------------------------------------------------------
# autopilot
# ---------------------------------------------------------------------------

from atlasbridge.cli._autopilot import autopilot_group  # noqa: E402

cli.add_command(autopilot_group)


# ---------------------------------------------------------------------------
# enterprise (edition, features, cloud)
# ---------------------------------------------------------------------------

from atlasbridge.cli._enterprise import cloud_group, edition_cmd, features_cmd  # noqa: E402

cli.add_command(edition_cmd)
cli.add_command(features_cmd)
cli.add_command(cloud_group)


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------

from atlasbridge.cli._trace_cmd import trace_group  # noqa: E402

cli.add_command(trace_group)


# ---------------------------------------------------------------------------
# pause / resume (convenience aliases for autopilot disable / enable)
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--all",
    "pause_all",
    is_flag=True,
    default=False,
    help="Pause autopilot across all active sessions (shows session count).",
)
def pause(pause_all: bool) -> None:
    """Pause the autopilot — all prompts will be forwarded to you."""
    from atlasbridge.cli._autopilot import autopilot_disable

    autopilot_disable.main(standalone_mode=False)

    if pause_all:
        try:
            from atlasbridge.core.config import atlasbridge_dir
            from atlasbridge.core.constants import DB_FILENAME
            from atlasbridge.core.store.database import Database

            data_dir = atlasbridge_dir()
            db_path = data_dir / DB_FILENAME
            if db_path.exists():
                db = Database(db_path)
                db.connect()
                try:
                    sessions = db.list_active_sessions()
                    count = len(sessions)
                finally:
                    db.close()
                click.echo(f"Active sessions affected: {count}")
            else:
                click.echo("No database found — no active sessions.")
        except Exception:  # noqa: BLE001
            pass  # DB query is best-effort; pause itself already succeeded


@cli.command()
def resume() -> None:
    """Resume the autopilot after a pause."""
    from atlasbridge.cli._autopilot import autopilot_enable

    autopilot_enable.main(standalone_mode=False)


# ---------------------------------------------------------------------------
# lab (Prompt Lab — dev/CI only)
# ---------------------------------------------------------------------------


@cli.group()
def lab() -> None:
    """Prompt Lab — deterministic QA scenario runner (dev/CI)."""


@lab.command("list")
@click.option("--json", "as_json", is_flag=True, default=False)
def lab_list(as_json: bool) -> None:
    """List all registered Prompt Lab scenarios."""
    from atlasbridge.cli._lab import cmd_lab_list

    cmd_lab_list(as_json=as_json, console=console)


@lab.command("run")
@click.argument("scenario", default="")
@click.option("--all", "run_all", is_flag=True, default=False, help="Run all scenarios")
@click.option("--filter", "pattern", default="", help="Run scenarios matching pattern")
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.option("--json", "as_json", is_flag=True, default=False)
def lab_run(scenario: str, run_all: bool, pattern: str, verbose: bool, as_json: bool) -> None:
    """Run one or more Prompt Lab QA scenarios."""
    from atlasbridge.cli._lab import cmd_lab_run

    cmd_lab_run(
        scenario=scenario,
        run_all=run_all,
        pattern=pattern,
        verbose=verbose,
        as_json=as_json,
        console=console,
    )


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

from atlasbridge.cli._dashboard import dashboard_group  # noqa: E402

cli.add_command(dashboard_group)


# ---------------------------------------------------------------------------
# console (operator console)
# ---------------------------------------------------------------------------

from atlasbridge.cli._console import console_cmd  # noqa: E402

cli.add_command(console_cmd)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
