"""atlasbridge setup — interactive first-time configuration wizard."""

from __future__ import annotations

import os
import re
import shutil
import sys

from rich.console import Console
from rich.prompt import Confirm, Prompt

_TELEGRAM_TOKEN_RE = re.compile(r"\d{8,12}:[A-Za-z0-9_\-]{35,}")
_SLACK_BOT_TOKEN_RE = re.compile(r"xoxb-[A-Za-z0-9\-]+")
_SLACK_APP_TOKEN_RE = re.compile(r"xapp-[A-Za-z0-9\-]+")
_SLACK_USER_ID_RE = re.compile(r"U[A-Z0-9]{8,}")


def _validate_telegram_token(token: str) -> bool:
    return bool(_TELEGRAM_TOKEN_RE.fullmatch(token.strip()))


def _validate_telegram_users(users_str: str) -> list[int] | None:
    try:
        return [int(u.strip()) for u in users_str.split(",") if u.strip()]
    except ValueError:
        return None


def _validate_slack_users(users_str: str) -> list[str] | None:
    parts = [u.strip() for u in users_str.replace(",", " ").split() if u.strip()]
    if not parts:
        return None
    if all(_SLACK_USER_ID_RE.fullmatch(p) for p in parts):
        return parts
    return None


def run_setup(
    channel: str,
    non_interactive: bool,
    console: Console,
    token: str = "",  # nosec B107 — empty default, not a hardcoded credential
    users: str = "",
) -> None:
    """Run the Aegis setup wizard."""
    from atlasbridge.core.config import atlasbridge_dir, save_config
    from atlasbridge.core.exceptions import ConfigError

    console.print("[bold]AtlasBridge Setup[/bold]")
    console.print(f"\nConfiguring channel: [cyan]{channel}[/cyan]\n")

    if channel == "telegram":
        config_data = _setup_telegram(
            console=console,
            non_interactive=non_interactive,
            token=token,
            users=users,
        )
    elif channel == "slack":
        config_data = _setup_slack(
            console=console,
            non_interactive=non_interactive,
            token=token,
            users=users,
        )
    else:
        console.print(f"[red]Unknown channel: {channel!r}[/red]")
        sys.exit(1)

    try:
        cfg_path = save_config(config_data)
    except ConfigError as exc:
        console.print(f"[red]Failed to save config: {exc}[/red]")
        sys.exit(1)

    console.print(f"\n[green]Config saved:[/green] {cfg_path}")
    console.print(f"AtlasBridge dir:    {atlasbridge_dir()}")

    # Linux: offer systemd service installation (Telegram only for now)
    if channel == "telegram" and sys.platform.startswith("linux") and not non_interactive:
        _maybe_install_systemd(console, str(cfg_path))

    console.print("\n[green]Setup complete.[/green]")
    console.print("Run [cyan]atlasbridge run claude[/cyan] to start supervising Claude Code.")


# ---------------------------------------------------------------------------
# Telegram wizard
# ---------------------------------------------------------------------------


def _setup_telegram(
    console: Console,
    non_interactive: bool,
    token: str,
    users: str,
) -> dict:
    """Collect Telegram credentials and return config dict."""
    if not token:
        token = os.environ.get("AEGIS_TELEGRAM_BOT_TOKEN", "")

    if not token and not non_interactive:
        console.print("Get your bot token from @BotFather on Telegram.\n")
        while True:
            token = Prompt.ask("[bold]Telegram bot token[/bold]").strip()
            if _validate_telegram_token(token):
                break
            console.print(
                "[red]Invalid token format.[/red] "
                "Expected: [dim]12345678:ABCDEFGHIJKLMNOPQRSTUVWXYZabcde...[/dim]"
            )

    if not token:
        console.print(
            "[red]No bot token provided. Set AEGIS_TELEGRAM_BOT_TOKEN or run interactively.[/red]"
        )
        sys.exit(1)

    if not _validate_telegram_token(token):
        console.print("[red]Invalid bot token format.[/red]")
        console.print("Expected format: [dim]<8-12 digits>:<35+ alphanumeric chars>[/dim]")
        sys.exit(1)

    if not users:
        users = os.environ.get("AEGIS_TELEGRAM_ALLOWED_USERS", "")

    if not users and not non_interactive:
        console.print("\nYour Telegram user ID (find it by messaging @userinfobot).\n")
        while True:
            users = Prompt.ask("[bold]Allowed Telegram user ID(s)[/bold] (comma-separated)").strip()
            parsed = _validate_telegram_users(users)
            if parsed:
                break
            console.print("[red]Please enter numeric user IDs separated by commas.[/red]")

    if not users:
        console.print(
            "[red]No user IDs provided. "
            "Set AEGIS_TELEGRAM_ALLOWED_USERS or run interactively.[/red]"
        )
        sys.exit(1)

    parsed_users = _validate_telegram_users(users)
    if not parsed_users:
        console.print(f"[red]Invalid user IDs: {users!r}[/red]")
        sys.exit(1)

    return {
        "telegram": {
            "bot_token": token,
            "allowed_users": parsed_users,
        }
    }


# ---------------------------------------------------------------------------
# Slack wizard
# ---------------------------------------------------------------------------


def _setup_slack(
    console: Console,
    non_interactive: bool,
    token: str,
    users: str,
) -> dict:
    """Collect Slack credentials and return config dict."""
    # Bot token (xoxb-*)
    bot_token = token or os.environ.get("AEGIS_SLACK_BOT_TOKEN", "")

    if not bot_token and not non_interactive:
        console.print(
            "Get your Bot User OAuth Token (xoxb-*) from your Slack App's "
            "[link=https://api.slack.com/apps]OAuth & Permissions[/link] page.\n"
        )
        while True:
            bot_token = Prompt.ask("[bold]Slack bot token[/bold] (xoxb-*)").strip()
            if _SLACK_BOT_TOKEN_RE.fullmatch(bot_token):
                break
            console.print("[red]Invalid bot token.[/red] Expected format: [dim]xoxb-...[/dim]")

    if not bot_token:
        console.print(
            "[red]No bot token provided. Set AEGIS_SLACK_BOT_TOKEN or run interactively.[/red]"
        )
        sys.exit(1)

    if not _SLACK_BOT_TOKEN_RE.fullmatch(bot_token):
        console.print("[red]Invalid Slack bot token format.[/red] Expected: [dim]xoxb-...[/dim]")
        sys.exit(1)

    # App-level token (xapp-*) for Socket Mode
    app_token = os.environ.get("AEGIS_SLACK_APP_TOKEN", "")

    if not app_token and not non_interactive:
        console.print(
            "\nGet your App-Level Token (xapp-*) from your Slack App's "
            "Basic Information → App-Level Tokens (enable Socket Mode first).\n"
        )
        while True:
            app_token = Prompt.ask("[bold]Slack app token[/bold] (xapp-*)").strip()
            if _SLACK_APP_TOKEN_RE.fullmatch(app_token):
                break
            console.print("[red]Invalid app token.[/red] Expected format: [dim]xapp-...[/dim]")

    if not app_token:
        console.print(
            "[red]No app token provided. Set AEGIS_SLACK_APP_TOKEN or run interactively.[/red]"
        )
        sys.exit(1)

    if not _SLACK_APP_TOKEN_RE.fullmatch(app_token):
        console.print("[red]Invalid Slack app token format.[/red] Expected: [dim]xapp-...[/dim]")
        sys.exit(1)

    # Allowed Slack user IDs (U1234567890, ...)
    allowed_raw = users or os.environ.get("AEGIS_SLACK_ALLOWED_USERS", "")

    if not allowed_raw and not non_interactive:
        console.print(
            "\nEnter the Slack user IDs of people permitted to reply "
            "(e.g. [dim]U1234567890[/dim]).\n"
            "Find your user ID in Slack: click your name → Profile → ··· → Copy member ID.\n"
        )
        while True:
            allowed_raw = Prompt.ask(
                "[bold]Allowed Slack user ID(s)[/bold] (space or comma-separated)"
            ).strip()
            parsed = _validate_slack_users(allowed_raw)
            if parsed:
                break
            console.print("[red]Please enter valid Slack user IDs (e.g. U1234567890).[/red]")

    if not allowed_raw:
        console.print(
            "[red]No user IDs provided. Set AEGIS_SLACK_ALLOWED_USERS or run interactively.[/red]"
        )
        sys.exit(1)

    parsed_users = _validate_slack_users(allowed_raw)
    if not parsed_users:
        console.print(f"[red]Invalid Slack user IDs: {allowed_raw!r}[/red]")
        sys.exit(1)

    return {
        "slack": {
            "bot_token": bot_token,
            "app_token": app_token,
            "allowed_users": parsed_users,
        }
    }


# ---------------------------------------------------------------------------
# Linux systemd helper
# ---------------------------------------------------------------------------


def _maybe_install_systemd(console: Console, config_path: str) -> None:
    """Offer to install the systemd user service on Linux."""
    if not shutil.which("systemctl"):
        return
    if not sys.stdin.isatty():
        return  # Not a real interactive terminal — skip the prompt

    from atlasbridge.os.systemd.service import (
        enable_service,
        generate_unit_file,
        install_service,
        is_systemd_available,
        reload_daemon,
    )

    if not is_systemd_available():
        return

    console.print()
    install = Confirm.ask(
        "[bold]Install systemd user service?[/bold] "
        "(enables [cyan]systemctl --user start aegis[/cyan])",
        default=True,
    )
    if not install:
        console.print("[dim]Skipped systemd service installation.[/dim]")
        return

    aegis_bin = shutil.which("atlasbridge") or "atlasbridge"
    unit = generate_unit_file(exec_path=aegis_bin, config_path=config_path)
    try:
        unit_path = install_service(unit)
        reload_daemon()
        enable_service()
        console.print(f"[green]Service installed:[/green] {unit_path}")
        console.print("Start now: [cyan]systemctl --user start aegis[/cyan]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Could not install service: {exc}[/yellow]")
        console.print(
            "You can install manually later with [cyan]atlasbridge setup --install-service[/cyan]."
        )
