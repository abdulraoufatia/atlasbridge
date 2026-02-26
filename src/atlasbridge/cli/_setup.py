"""atlasbridge setup — interactive first-time configuration wizard."""

from __future__ import annotations

import os
import re
import shutil
import sys

import click
from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()


@click.command("setup")
@click.option("--channel", type=click.Choice(["telegram", "slack"]), default="telegram")
@click.option("--non-interactive", is_flag=True, default=False, help="Read from env vars only")
@click.option(
    "--from-env", is_flag=True, default=False, help="Build config from ATLASBRIDGE_* env vars"
)
@click.option("--token", default="", help="Telegram bot token (non-interactive mode)")
@click.option("--users", default="", help="Comma-separated allowed Telegram user IDs")
@click.option(
    "--no-keyring", is_flag=True, default=False, help="Store tokens in config file, not OS keyring"
)
def setup_cmd(
    channel: str,
    non_interactive: bool,
    from_env: bool,
    token: str,
    users: str,
    no_keyring: bool,
) -> None:
    """Interactive first-time configuration wizard."""
    run_setup(
        channel=channel,
        non_interactive=non_interactive,
        console=console,
        token=token,
        users=users,
        from_env=from_env,
        no_keyring=no_keyring,
    )


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


def _env(*names: str) -> str:
    """Return the first non-empty env var from *names*."""
    for name in names:
        v = os.environ.get(name, "")
        if v:
            return v
    return ""


def run_setup(
    channel: str,
    non_interactive: bool,
    console: Console,
    token: str = "",  # nosec B107 — empty default, not a hardcoded credential
    users: str = "",
    from_env: bool = False,
    no_keyring: bool = False,
) -> None:
    """Run the AtlasBridge setup wizard."""
    from atlasbridge.core.config import _config_file_path, atlasbridge_dir, save_config

    console.print("[bold]AtlasBridge Setup[/bold]")

    # Detect existing config — preserve on upgrade
    cfg_path = _config_file_path()
    if cfg_path.exists() and not from_env and not non_interactive:
        console.print(f"\nExisting config found: [cyan]{cfg_path}[/cyan]")
        keep = Confirm.ask(
            "Keep existing configuration?",
            default=True,
        )
        if keep:
            console.print("[green]Config preserved.[/green] Your tokens and settings are intact.")
            console.print("Run [cyan]atlasbridge run claude[/cyan] to start supervising.")
            return

    if from_env:
        config_data = _setup_from_env(console)
    elif channel == "telegram":
        console.print(f"\nConfiguring channel: [cyan]{channel}[/cyan]\n")
        config_data = _setup_telegram(
            console=console,
            non_interactive=non_interactive,
            token=token,
            users=users,
        )
    elif channel == "slack":
        console.print(f"\nConfiguring channel: [cyan]{channel}[/cyan]\n")
        config_data = _setup_slack(
            console=console,
            non_interactive=non_interactive,
            token=token,
            users=users,
        )
    else:
        console.print(f"[red]Unknown channel: {channel!r}[/red]")
        sys.exit(1)

    # Auto-enable keyring when available (unless --no-keyring)
    use_keyring = False
    if not no_keyring:
        try:
            from atlasbridge.core.keyring_store import is_keyring_available

            use_keyring = is_keyring_available()
        except ImportError:
            pass

    try:
        cfg_path = save_config(config_data, use_keyring=use_keyring)
    except Exception as exc:
        if use_keyring:
            # Keyring storage failed — fall back to plaintext
            use_keyring = False
            try:
                cfg_path = save_config(config_data, use_keyring=False)
            except Exception as exc2:
                console.print(f"[red]Failed to save config: {exc2}[/red]")
                sys.exit(1)
        else:
            console.print(f"[red]Failed to save config: {exc}[/red]")
            sys.exit(1)

    console.print(f"\n[green]Config saved:[/green] {cfg_path}")
    if use_keyring:
        console.print("  Tokens stored in OS keyring (secure)")
    else:
        console.print("  Tokens stored in config file")
    console.print(f"AtlasBridge dir:    {atlasbridge_dir()}")

    # Linux: offer systemd service installation (Telegram only for now)
    if channel == "telegram" and sys.platform.startswith("linux") and not non_interactive:
        _maybe_install_systemd(console, str(cfg_path))

    # Optional: LLM provider for chat mode
    if not non_interactive and not from_env and sys.stdin.isatty():
        _maybe_setup_llm_provider(console, config_data, str(cfg_path))

    console.print("\n[green]Setup complete.[/green]")
    if channel == "telegram":
        console.print(
            "\n[bold]Important:[/bold] Open Telegram and send [cyan]/start[/cyan] to your bot."
        )
        console.print("This is required before AtlasBridge can deliver prompts to you.")
    console.print("\nRun [cyan]atlasbridge run claude[/cyan] to start supervising Claude Code.")
    console.print("Run [cyan]atlasbridge chat[/cyan] to chat with an LLM via your channel.")


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
        token = _env("ATLASBRIDGE_TELEGRAM_BOT_TOKEN", "AEGIS_TELEGRAM_BOT_TOKEN")

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
            "[red]No bot token provided. Set ATLASBRIDGE_TELEGRAM_BOT_TOKEN or run interactively.[/red]"
        )
        sys.exit(1)

    if not _validate_telegram_token(token):
        console.print("[red]Invalid bot token format.[/red]")
        console.print("Expected format: [dim]<8-12 digits>:<35+ alphanumeric chars>[/dim]")
        sys.exit(1)

    # Pre-flight: verify the token against Telegram API (interactive only)
    if not non_interactive:
        console.print("\nVerifying bot token with Telegram...")
        from atlasbridge.channels.telegram.verify import verify_telegram_token

        ok, detail = verify_telegram_token(token)
        if ok:
            console.print(f"  [green]\u2713[/green] {detail}")
        else:
            console.print(
                f"  [yellow]\u26a0[/yellow] Could not reach Telegram: {detail}. "
                "Token saved \u2014 verify later with: [cyan]atlasbridge doctor[/cyan]"
            )

    if not users:
        users = _env("ATLASBRIDGE_TELEGRAM_ALLOWED_USERS", "AEGIS_TELEGRAM_ALLOWED_USERS")

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
            "Set ATLASBRIDGE_TELEGRAM_ALLOWED_USERS or run interactively.[/red]"
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
    app_token: str = "",
) -> dict:
    """Collect Slack credentials and return config dict."""
    # Bot token (xoxb-*)
    bot_token = token or _env("ATLASBRIDGE_SLACK_BOT_TOKEN", "AEGIS_SLACK_BOT_TOKEN")

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
            "[red]No bot token provided. Set ATLASBRIDGE_SLACK_BOT_TOKEN or run interactively.[/red]"
        )
        sys.exit(1)

    if not _SLACK_BOT_TOKEN_RE.fullmatch(bot_token):
        console.print("[red]Invalid Slack bot token format.[/red] Expected: [dim]xoxb-...[/dim]")
        sys.exit(1)

    # App-level token (xapp-*) for Socket Mode
    app_token = app_token or _env("ATLASBRIDGE_SLACK_APP_TOKEN", "AEGIS_SLACK_APP_TOKEN")

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
            "[red]No app token provided. Set ATLASBRIDGE_SLACK_APP_TOKEN or run interactively.[/red]"
        )
        sys.exit(1)

    if not _SLACK_APP_TOKEN_RE.fullmatch(app_token):
        console.print("[red]Invalid Slack app token format.[/red] Expected: [dim]xapp-...[/dim]")
        sys.exit(1)

    # Allowed Slack user IDs (U1234567890, ...)
    allowed_raw = users or _env("ATLASBRIDGE_SLACK_ALLOWED_USERS", "AEGIS_SLACK_ALLOWED_USERS")

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
            "[red]No user IDs provided. Set ATLASBRIDGE_SLACK_ALLOWED_USERS or run interactively.[/red]"
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
# Environment variable bootstrap
# ---------------------------------------------------------------------------


def _setup_from_env(console: Console) -> dict:
    """Build config dict entirely from ATLASBRIDGE_* (or AEGIS_*) env vars."""
    config_data: dict = {}

    # Telegram
    tg_token = _env("ATLASBRIDGE_TELEGRAM_BOT_TOKEN", "AEGIS_TELEGRAM_BOT_TOKEN")
    tg_users = _env("ATLASBRIDGE_TELEGRAM_ALLOWED_USERS", "AEGIS_TELEGRAM_ALLOWED_USERS")
    if tg_token and tg_users:
        if not _validate_telegram_token(tg_token):
            console.print("[red]Invalid ATLASBRIDGE_TELEGRAM_BOT_TOKEN format.[/red]")
            sys.exit(1)
        parsed_users = _validate_telegram_users(tg_users)
        if not parsed_users:
            console.print(f"[red]Invalid ATLASBRIDGE_TELEGRAM_ALLOWED_USERS: {tg_users!r}[/red]")
            sys.exit(1)
        config_data["telegram"] = {"bot_token": tg_token, "allowed_users": parsed_users}

    # Slack
    slack_bot = _env("ATLASBRIDGE_SLACK_BOT_TOKEN", "AEGIS_SLACK_BOT_TOKEN")
    slack_app = _env("ATLASBRIDGE_SLACK_APP_TOKEN", "AEGIS_SLACK_APP_TOKEN")
    slack_users = _env("ATLASBRIDGE_SLACK_ALLOWED_USERS", "AEGIS_SLACK_ALLOWED_USERS")
    if slack_bot and slack_app and slack_users:
        if not _SLACK_BOT_TOKEN_RE.fullmatch(slack_bot):
            console.print("[red]Invalid ATLASBRIDGE_SLACK_BOT_TOKEN format.[/red]")
            sys.exit(1)
        if not _SLACK_APP_TOKEN_RE.fullmatch(slack_app):
            console.print("[red]Invalid ATLASBRIDGE_SLACK_APP_TOKEN format.[/red]")
            sys.exit(1)
        parsed_slack = _validate_slack_users(slack_users)
        if not parsed_slack:
            console.print(f"[red]Invalid ATLASBRIDGE_SLACK_ALLOWED_USERS: {slack_users!r}[/red]")
            sys.exit(1)
        config_data["slack"] = {
            "bot_token": slack_bot,
            "app_token": slack_app,
            "allowed_users": parsed_slack,
        }

    if not config_data:
        console.print("[red]No channel environment variables found.[/red]")
        console.print("Set ATLASBRIDGE_TELEGRAM_BOT_TOKEN + ATLASBRIDGE_TELEGRAM_ALLOWED_USERS")
        console.print(
            "  or ATLASBRIDGE_SLACK_BOT_TOKEN + ATLASBRIDGE_SLACK_APP_TOKEN"
            " + ATLASBRIDGE_SLACK_ALLOWED_USERS"
        )
        sys.exit(1)

    # Optional overrides
    if level := _env("ATLASBRIDGE_LOG_LEVEL", "AEGIS_LOG_LEVEL"):
        config_data.setdefault("logging", {})["level"] = level
    if db := _env("ATLASBRIDGE_DB_PATH", "AEGIS_DB_PATH"):
        config_data.setdefault("database", {})["path"] = db
    if timeout := _env("ATLASBRIDGE_APPROVAL_TIMEOUT_SECONDS", "AEGIS_APPROVAL_TIMEOUT_SECONDS"):
        config_data.setdefault("prompts", {})["timeout_seconds"] = int(timeout)

    console.print("\nBuilding config from environment variables...")
    channels = []
    if "telegram" in config_data:
        channels.append("Telegram")
    if "slack" in config_data:
        channels.append("Slack")
    console.print(f"Detected channel(s): [cyan]{', '.join(channels)}[/cyan]")

    return config_data


# ---------------------------------------------------------------------------
# LLM provider setup (optional, for chat mode)
# ---------------------------------------------------------------------------


def _maybe_setup_llm_provider(console: Console, config_data: dict, cfg_path: str) -> None:
    """Optionally configure an LLM provider for chat mode."""
    console.print()
    setup_llm = Confirm.ask(
        "[bold]Set up an LLM provider for chat mode?[/bold] "
        "(talk to Claude/GPT/Gemini via Telegram)",
        default=False,
    )
    if not setup_llm:
        return

    provider = Prompt.ask(
        "[bold]LLM provider[/bold]",
        choices=["anthropic", "openai", "google"],
        default="anthropic",
    )

    api_key = Prompt.ask(f"[bold]{provider} API key[/bold]").strip()
    if not api_key:
        console.print("[yellow]No API key entered. Skipping LLM setup.[/yellow]")
        return

    model = Prompt.ask(
        "[bold]Model[/bold] (leave blank for default)",
        default="",
    ).strip()

    config_data.setdefault("chat", {})["provider"] = {
        "name": provider,
        "api_key": api_key,
    }
    if model:
        config_data["chat"]["provider"]["model"] = model

    # Re-save config with the new chat section
    from atlasbridge.core.config import save_config
    from atlasbridge.core.exceptions import ConfigError

    try:
        from pathlib import Path

        save_config(config_data, Path(cfg_path) if cfg_path else None)
        console.print(f"[green]LLM provider configured:[/green] {provider}")
        if model:
            console.print(f"  Model: [cyan]{model}[/cyan]")
    except ConfigError as exc:
        console.print(f"[yellow]Could not save LLM config: {exc}[/yellow]")


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
        "(enables [cyan]systemctl --user start atlasbridge[/cyan])",
        default=True,
    )
    if not install:
        console.print("[dim]Skipped systemd service installation.[/dim]")
        return

    atlasbridge_bin = shutil.which("atlasbridge") or "atlasbridge"
    unit = generate_unit_file(exec_path=atlasbridge_bin, config_path=config_path)
    try:
        unit_path = install_service(unit)
        reload_daemon()
        enable_service()
        console.print(f"[green]Service installed:[/green] {unit_path}")
        console.print("Start now: [cyan]systemctl --user start atlasbridge[/cyan]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Could not install service: {exc}[/yellow]")
        console.print(
            "You can install manually later with [cyan]atlasbridge setup --install-service[/cyan]."
        )
