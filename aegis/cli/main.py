"""
Aegis CLI — entry point for all user-facing commands.

Commands
--------
setup           Interactive setup wizard (Telegram token, user IDs)
run             Launch a tool under Aegis supervision (foreground)
status          Show daemon / session status
doctor          Check environment and config health
approvals       List pending or recent prompts
logs            Tail the Aegis log file
install-service Install macOS launchd service
uninstall-service Remove macOS launchd service
audit verify    Verify the audit log hash chain
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from aegis.core.constants import PromptStatus
from aegis.core.exceptions import AegisError, ConfigNotFoundError

console = Console()
err_console = Console(stderr=True)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="aegis-cli", prog_name="aegis")
@click.option("--debug", is_flag=True, envvar="AEGIS_DEBUG", help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """Aegis — secure remote interactive bridge for AI CLI tools."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    _configure_logging(debug)


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--token", envvar="AEGIS_TELEGRAM_BOT_TOKEN", help="Telegram bot token.")
@click.option("--users", envvar="AEGIS_TELEGRAM_ALLOWED_USERS", help="Comma-separated Telegram user IDs.")
@click.option("--timeout", type=int, default=600, show_default=True, help="Prompt timeout (seconds).")
@click.option("--free-text", is_flag=True, default=False, help="Enable free-text prompt forwarding.")
def setup(token: str | None, users: str | None, timeout: int, free_text: bool) -> None:
    """Run the interactive setup wizard."""
    from aegis.core.config import save_config

    console.print("[bold]Aegis Setup[/bold]")

    if not token:
        token = click.prompt("Telegram bot token (from @BotFather)")
    if not users:
        users = click.prompt("Your Telegram user ID(s), comma-separated")

    user_ids = [int(u.strip()) for u in users.split(",") if u.strip()]

    config_data: dict[str, Any] = {
        "telegram": {
            "bot_token": token,
            "allowed_users": user_ids,
        },
        "prompts": {
            "timeout_seconds": timeout,
            "free_text_enabled": free_text,
        },
    }

    # Validate before writing
    try:
        from aegis.core.config import AegisConfig
        AegisConfig.model_validate(config_data)
    except Exception as exc:
        err_console.print(f"[red]Validation error:[/red] {exc}")
        sys.exit(2)

    try:
        path = save_config(config_data)
        console.print(f"[green]✓[/green] Config saved to {path}")
        console.print("\nRun [bold]aegis doctor[/bold] to verify your setup.")
    except AegisError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        sys.exit(exc.exit_code)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@cli.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("command", nargs=-1, required=True)
@click.option("--session-id", default=None, hidden=True, help="Override session ID.")
@click.pass_context
def run(ctx: click.Context, command: tuple[str, ...], session_id: str | None) -> None:
    """
    Launch COMMAND under Aegis supervision.

    All prompts will be routed to your Telegram before being answered.

    Examples:

      aegis run claude

      aegis run -- claude --model opus
    """
    try:
        from aegis.core.config import load_config
        config = load_config()
    except ConfigNotFoundError as exc:
        err_console.print(f"[red]{exc}[/red]")
        sys.exit(2)
    except AegisError as exc:
        err_console.print(f"[red]Config error:[/red] {exc}")
        sys.exit(2)

    try:
        exit_code = asyncio.run(_run_supervised(list(command), config, session_id))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        exit_code = 130
    except AegisError as exc:
        err_console.print(f"[red]Aegis error:[/red] {exc}")
        exit_code = exc.exit_code

    sys.exit(exit_code)


async def _run_supervised(
    command: list[str],
    config: Any,
    session_id: str | None,
) -> int:
    from aegis.audit.writer import AuditWriter
    from aegis.bridge.pty_supervisor import PTYSupervisor
    from aegis.channels.telegram.bot import TelegramBot
    from aegis.store.database import Database

    db = Database(config.db_path)
    db.connect()

    audit = AuditWriter(config.audit_path)
    audit.open()

    response_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    bot = TelegramBot(
        token=config.telegram.bot_token.get_secret_value(),
        allowed_users=config.telegram.allowed_users,
        db=db,
        response_queue=response_queue,
        poll_timeout=30,
        free_text_max_chars=config.prompts.free_text_max_chars,
        tool_name=command[0],
    )

    sid = session_id or str(uuid.uuid4())
    supervisor = PTYSupervisor(
        command=command,
        config=config,
        db=db,
        audit=audit,
        bot=bot,
        session_id=sid,
    )

    try:
        await bot.start()
        return await supervisor.run()
    finally:
        await bot.close()
        audit.close()
        db.close()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@cli.command()
def status() -> None:
    """Show active Aegis sessions."""
    try:
        from aegis.core.config import load_config
        config = load_config()
    except AegisError as exc:
        err_console.print(f"[red]{exc}[/red]")
        sys.exit(exc.exit_code)

    from aegis.store.database import Database

    db = Database(config.db_path)
    db.connect()
    try:
        sessions = db.list_active_sessions()
    finally:
        db.close()

    if not sessions:
        console.print("[dim]No active sessions.[/dim]")
        return

    table = Table(title="Active Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Tool")
    table.add_column("PID")
    table.add_column("CWD")
    table.add_column("Started")

    for s in sessions:
        table.add_row(
            s.id[:8],
            s.tool,
            str(s.pid or "—"),
            s.cwd,
            s.started_at[:19].replace("T", " "),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@cli.command()
def doctor() -> None:
    """Check environment and configuration health."""
    ok = True

    def _check(label: str, fn: Any) -> None:
        nonlocal ok
        try:
            result = fn()
            console.print(f"[green]✓[/green] {label}" + (f": {result}" if result else ""))
        except Exception as exc:
            console.print(f"[red]✗[/red] {label}: {exc}")
            ok = False

    _check("Python ≥ 3.11", lambda: _require_python())
    _check("Config file readable", lambda: _check_config())
    _check("Telegram token format", lambda: _check_telegram_token())
    _check("ptyprocess installed", lambda: __import__("ptyprocess"))
    _check("httpx installed", lambda: __import__("httpx"))
    _check("pydantic installed", lambda: __import__("pydantic"))
    _check("Database writable", lambda: _check_db())

    if ok:
        console.print("\n[bold green]All checks passed.[/bold green]")
    else:
        console.print("\n[bold red]Some checks failed. Run 'aegis setup' to configure.[/bold red]")
        sys.exit(1)


def _require_python() -> str:
    v = sys.version_info
    if (v.major, v.minor) < (3, 11):
        raise RuntimeError(f"Python {v.major}.{v.minor} < 3.11")
    return f"{v.major}.{v.minor}.{v.micro}"


def _check_config() -> str:
    from aegis.core.config import load_config
    cfg = load_config()
    return str(cfg._config_path)


def _check_telegram_token() -> str:
    from aegis.core.config import load_config
    cfg = load_config()
    tok = cfg.telegram.bot_token.get_secret_value()
    return f"{tok[:8]}…"


def _check_db() -> str:
    from aegis.core.config import load_config
    from aegis.store.database import Database
    cfg = load_config()
    db = Database(cfg.db_path)
    db.connect()
    db.close()
    return str(cfg.db_path)


# ---------------------------------------------------------------------------
# approvals
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--session", default=None, help="Filter by session ID prefix.")
@click.option("--all", "show_all", is_flag=True, help="Show all prompts, not just pending.")
def approvals(session: str | None, show_all: bool) -> None:
    """List pending (or recent) prompts."""
    try:
        from aegis.core.config import load_config
        config = load_config()
    except AegisError as exc:
        err_console.print(f"[red]{exc}[/red]")
        sys.exit(exc.exit_code)

    from aegis.store.database import Database

    db = Database(config.db_path)
    db.connect()
    try:
        if show_all:
            prompts = db.list_prompts_for_session(session or "", limit=50) if session else _list_recent(db)
        else:
            prompts = db.list_pending_prompts(session_id=_expand_session_id(db, session))
    finally:
        db.close()

    if not prompts:
        console.print("[dim]No prompts found.[/dim]")
        return

    table = Table(title="Prompts")
    table.add_column("ID", style="cyan")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Excerpt")
    table.add_column("Expires")

    for p in prompts:
        table.add_row(
            p.short_id,
            p.input_type.replace("TYPE_", ""),
            p.status,
            p.excerpt[:60],
            p.expires_at[:19].replace("T", " "),
        )

    console.print(table)


def _list_recent(db: Any) -> list[Any]:
    from aegis.store.database import Database
    # Return last 50 prompts across all sessions
    sessions = db.list_active_sessions()
    prompts = []
    for s in sessions:
        prompts.extend(db.list_prompts_for_session(s.id, limit=10))
    return sorted(prompts, key=lambda p: p.created_at, reverse=True)[:50]


def _expand_session_id(db: Any, prefix: str | None) -> str | None:
    if not prefix:
        return None
    sessions = db.list_active_sessions()
    for s in sessions:
        if s.id.startswith(prefix):
            return s.id
    return prefix  # return as-is; may be a full UUID


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


@cli.command()
@click.option("-n", "lines", default=50, show_default=True, help="Number of lines to show.")
@click.option("-f", "--follow", is_flag=True, help="Follow the log file (like tail -f).")
def logs(lines: int, follow: bool) -> None:
    """View Aegis log output."""
    try:
        from aegis.core.config import load_config
        config = load_config()
    except AegisError as exc:
        err_console.print(f"[red]{exc}[/red]")
        sys.exit(exc.exit_code)

    log_path = config.log_path
    if not log_path.exists():
        console.print("[dim]No log file yet.[/dim]")
        return

    if follow:
        os.execvp("tail", ["tail", "-f", str(log_path)])
    else:
        import subprocess
        subprocess.run(["tail", f"-n{lines}", str(log_path)])


# ---------------------------------------------------------------------------
# audit subcommand group
# ---------------------------------------------------------------------------


@cli.group()
def audit() -> None:
    """Audit log commands."""


@audit.command("verify")
def audit_verify() -> None:
    """Verify the integrity of the audit log hash chain."""
    try:
        from aegis.core.config import load_config
        config = load_config()
    except AegisError as exc:
        err_console.print(f"[red]{exc}[/red]")
        sys.exit(exc.exit_code)

    from aegis.audit.writer import verify_chain

    audit_path = config.audit_path
    if not audit_path.exists():
        console.print("[dim]No audit log found.[/dim]")
        return

    ok, count, error = verify_chain(audit_path)
    if ok:
        console.print(f"[green]✓[/green] Audit chain intact ({count} entries)")
    else:
        console.print(f"[red]✗[/red] Audit chain BROKEN: {error}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# macOS launchd service
# ---------------------------------------------------------------------------


@cli.command("install-service")
def install_service() -> None:
    """Install Aegis as a macOS launchd user service."""
    if sys.platform != "darwin":
        err_console.print("[red]install-service is only supported on macOS.[/red]")
        sys.exit(1)

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "com.aegis-cli.aegis.plist"

    aegis_bin = _find_aegis_bin()
    if not aegis_bin:
        err_console.print("[red]Could not locate the 'aegis' binary in PATH.[/red]")
        sys.exit(1)

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.aegis-cli.aegis</string>
    <key>ProgramArguments</key>
    <array>
        <string>{aegis_bin}</string>
        <string>status</string>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/.aegis/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/.aegis/launchd.err</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_content)
    plist_path.chmod(0o644)
    console.print(f"[green]✓[/green] Plist written to {plist_path}")
    console.print("\nTo activate: [bold]launchctl load {plist_path}[/bold]")


@cli.command("uninstall-service")
def uninstall_service() -> None:
    """Remove the macOS launchd service plist."""
    if sys.platform != "darwin":
        err_console.print("[red]uninstall-service is only supported on macOS.[/red]")
        sys.exit(1)

    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.aegis-cli.aegis.plist"
    if plist_path.exists():
        plist_path.unlink()
        console.print(f"[green]✓[/green] Removed {plist_path}")
    else:
        console.print("[dim]No service plist found.[/dim]")


def _find_aegis_bin() -> str | None:
    import shutil
    return shutil.which("aegis")


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
