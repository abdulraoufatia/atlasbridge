"""atlasbridge channel add — add/reconfigure a notification channel."""

from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console()


@click.group("channel")
def channel_group() -> None:
    """Notification channel management."""


@channel_group.command("add")
@click.argument("channel_type", metavar="TYPE", type=click.Choice(["telegram", "slack"]))
@click.option("--token", default="", help="Bot token")
@click.option("--app-token", default="", help="App-level token (Slack Socket Mode)")
@click.option("--users", default="", help="Comma-separated user IDs")
def channel_add_cmd(channel_type: str, token: str, app_token: str, users: str) -> None:
    """Add or reconfigure a notification channel."""
    cmd_channel_add(
        channel_type=channel_type, token=token, app_token=app_token, users=users, console=console
    )


@channel_group.command("remove")
@click.argument("channel_type", metavar="TYPE", type=click.Choice(["telegram", "slack"]))
def channel_remove_cmd(channel_type: str) -> None:
    """Remove a notification channel from config."""
    from atlasbridge.core.config import load_config, save_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    existing_data: dict = {}
    try:
        cfg = load_config()
        if cfg.telegram is not None:
            existing_data["telegram"] = {
                "bot_token": cfg.telegram.bot_token.get_secret_value(),
                "allowed_users": cfg.telegram.allowed_users,
            }
        if cfg.slack is not None:
            existing_data["slack"] = {
                "bot_token": cfg.slack.bot_token.get_secret_value(),
                "app_token": cfg.slack.app_token.get_secret_value(),
                "allowed_users": cfg.slack.allowed_users,
            }
    except ConfigNotFoundError:
        console.print(f"[yellow]No config found — {channel_type} was not configured.[/yellow]")
        return
    except ConfigError as exc:
        console.print(f"[red]Cannot load config: {exc}[/red]")
        sys.exit(1)

    if channel_type not in existing_data:
        console.print(f"[yellow]{channel_type.capitalize()} channel is not configured.[/yellow]")
        return

    existing_data.pop(channel_type)

    try:
        save_config(existing_data)
    except ConfigError as exc:
        console.print(f"[red]Failed to save config: {exc}[/red]")
        sys.exit(1)

    console.print(f"[green]{channel_type.capitalize()} channel removed.[/green]")


def cmd_channel_add(
    channel_type: str, token: str, app_token: str, users: str, console: Console
) -> None:
    """Add or reconfigure a notification channel in the existing config."""
    from atlasbridge.core.config import load_config, save_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    # Load existing config (may or may not exist)
    existing_data: dict = {}
    try:
        cfg = load_config()
        # Reconstruct a minimal serialisable dict from the loaded config
        if cfg.telegram is not None:
            existing_data["telegram"] = {
                "bot_token": cfg.telegram.bot_token.get_secret_value(),
                "allowed_users": cfg.telegram.allowed_users,
            }
        if cfg.slack is not None:
            existing_data["slack"] = {
                "bot_token": cfg.slack.bot_token.get_secret_value(),
                "app_token": cfg.slack.app_token.get_secret_value(),
                "allowed_users": cfg.slack.allowed_users,
            }
    except ConfigNotFoundError:
        pass  # No existing config — start fresh
    except ConfigError as exc:
        console.print(f"[red]Cannot load existing config: {exc}[/red]")
        sys.exit(1)

    console.print(f"[bold]Configuring {channel_type} channel...[/bold]\n")

    if channel_type == "telegram":
        from atlasbridge.cli._setup import _setup_telegram

        new_section = _setup_telegram(
            console=console,
            non_interactive=bool(token and users),
            token=token,
            users=users,
        )
        existing_data.update(new_section)

    elif channel_type == "slack":
        from atlasbridge.cli._setup import _setup_slack

        new_section = _setup_slack(
            console=console,
            non_interactive=bool(token),
            token=token,
            app_token=app_token,
            users=users,
        )
        existing_data.update(new_section)

    else:
        console.print(f"[red]Unknown channel type: {channel_type!r}[/red]")
        sys.exit(1)

    try:
        cfg_path = save_config(existing_data)
    except ConfigError as exc:
        console.print(f"[red]Failed to save config: {exc}[/red]")
        sys.exit(1)

    console.print(f"\n[green]{channel_type.capitalize()} channel configured.[/green]")
    console.print(f"Config saved to: {cfg_path}")
