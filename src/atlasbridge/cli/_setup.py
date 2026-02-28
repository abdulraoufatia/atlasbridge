"""atlasbridge setup — interactive first-time configuration wizard."""

from __future__ import annotations

import os
import shutil
import sys

import click
from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()


@click.command("setup")
@click.option("--non-interactive", is_flag=True, default=False, help="Read from env vars only")
@click.option(
    "--from-env", is_flag=True, default=False, help="Build config from ATLASBRIDGE_* env vars"
)
@click.option(
    "--no-keyring", is_flag=True, default=False, help="Store tokens in config file, not OS keyring"
)
def setup_cmd(
    non_interactive: bool,
    from_env: bool,
    no_keyring: bool,
) -> None:
    """Interactive first-time configuration wizard."""
    run_setup(
        non_interactive=non_interactive,
        console=console,
        from_env=from_env,
        no_keyring=no_keyring,
    )


def _env(*names: str) -> str:
    """Return the first non-empty env var from *names*."""
    for name in names:
        v = os.environ.get(name, "")
        if v:
            return v
    return ""


def run_setup(
    non_interactive: bool,
    console: Console,
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

    config_data: dict = {}
    if from_env:
        config_data = _setup_from_env(console)

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

    # Linux: offer systemd service installation
    if sys.platform.startswith("linux") and not non_interactive:
        _maybe_install_systemd(console, str(cfg_path))

    # Optional: LLM provider for chat mode
    if not non_interactive and not from_env and sys.stdin.isatty():
        _maybe_setup_llm_provider(console, config_data, str(cfg_path))

    console.print("\n[green]Setup complete.[/green]")
    console.print("\nRun [cyan]atlasbridge run claude[/cyan] to start supervising Claude Code.")
    console.print("Run [cyan]atlasbridge chat[/cyan] to chat with an LLM.")


# ---------------------------------------------------------------------------
# Environment variable bootstrap
# ---------------------------------------------------------------------------


def _setup_from_env(console: Console) -> dict:
    """Build config dict entirely from ATLASBRIDGE_* (or AEGIS_*) env vars."""
    config_data: dict = {}

    # Optional overrides
    if level := _env("ATLASBRIDGE_LOG_LEVEL", "AEGIS_LOG_LEVEL"):
        config_data.setdefault("logging", {})["level"] = level
    if db := _env("ATLASBRIDGE_DB_PATH", "AEGIS_DB_PATH"):
        config_data.setdefault("database", {})["path"] = db
    if timeout := _env("ATLASBRIDGE_APPROVAL_TIMEOUT_SECONDS", "AEGIS_APPROVAL_TIMEOUT_SECONDS"):
        config_data.setdefault("prompts", {})["timeout_seconds"] = int(timeout)

    console.print("\nBuilding config from environment variables...")

    return config_data


# ---------------------------------------------------------------------------
# LLM provider setup (optional, for chat mode)
# ---------------------------------------------------------------------------


def _maybe_setup_llm_provider(console: Console, config_data: dict, cfg_path: str) -> None:
    """Optionally configure an LLM provider for chat mode."""
    console.print()
    setup_llm = Confirm.ask(
        "[bold]Set up an LLM provider for chat mode?[/bold] "
        "(talk to Claude/GPT/Gemini via the dashboard)",
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
