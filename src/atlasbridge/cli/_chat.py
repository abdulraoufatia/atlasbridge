"""atlasbridge chat — start a chat session with an LLM provider via Telegram."""

from __future__ import annotations

import click


@click.command("chat")
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai", "google"]),
    default=None,
    help="LLM provider to use (overrides config).",
)
@click.option("--model", default="", help="Model name (overrides config).")
@click.option("--no-tools", is_flag=True, default=False, help="Disable tool use.")
@click.option("--policy", default="", help="Path to policy YAML file for tool governance.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Log decisions without sending to channel."
)
def chat_cmd(provider, model, no_tools, policy, dry_run):
    """Start a chat session with an LLM provider.

    Users interact via Telegram (or other configured channel).
    The LLM can use tools governed by your policy rules.

    \b
    Examples:
      atlasbridge chat
      atlasbridge chat --provider openai --model gpt-4o
      atlasbridge chat --no-tools
      atlasbridge chat --policy config/policies/chat-strict.yaml
    """
    import asyncio

    from rich.console import Console

    console = Console()

    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    try:
        config = load_config()
    except ConfigNotFoundError:
        console.print("[red]Not configured.[/red] Run [cyan]atlasbridge setup[/cyan] first.")
        raise SystemExit(1) from None
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise SystemExit(1) from exc

    # Resolve provider — CLI flag > config > error
    provider_name = provider or config.chat.provider.name
    if not provider_name:
        console.print(
            "[red]No LLM provider configured.[/red]\n"
            "Set one with:\n"
            "  [cyan]atlasbridge setup[/cyan] (interactive)\n"
            "  [cyan]atlasbridge chat --provider anthropic[/cyan]\n"
            "  [cyan]ATLASBRIDGE_LLM_PROVIDER=anthropic[/cyan]"
        )
        raise SystemExit(1)

    # Resolve API key — config > env
    api_key = ""
    if config.chat.provider.api_key:
        api_key = config.chat.provider.api_key.get_secret_value()
    if not api_key:
        import os

        api_key = os.environ.get("ATLASBRIDGE_LLM_API_KEY", "")
    if not api_key:
        console.print(
            f"[red]No API key for provider {provider_name!r}.[/red]\n"
            "Set one with:\n"
            f"  [cyan]ATLASBRIDGE_LLM_API_KEY=sk-...[/cyan]\n"
            "  or add it to config.toml under [chat.provider]"
        )
        raise SystemExit(1)

    model_name = model or config.chat.provider.model

    # Build daemon config dict
    daemon_config = {
        "mode": "chat",
        "dry_run": dry_run,
        "chat": {
            "provider_name": provider_name,
            "api_key": api_key,
            "model": model_name,
            "tools_enabled": not no_tools and config.chat.tools_enabled,
            "max_history": config.chat.max_history_messages,
            "system_prompt": config.chat.provider.system_prompt,
            "max_tokens": config.chat.provider.max_tokens,
        },
        "channels": {},
    }

    if policy:
        daemon_config["policy_file"] = policy

    # Wire channel config
    if config.telegram:
        daemon_config["channels"]["telegram"] = {
            "bot_token": config.telegram.bot_token.get_secret_value(),
            "allowed_user_ids": config.telegram.allowed_users,
        }
    if config.slack:
        daemon_config["channels"]["slack"] = {
            "bot_token": config.slack.bot_token.get_secret_value(),
            "app_token": config.slack.app_token.get_secret_value(),
            "allowed_user_ids": config.slack.allowed_users,
        }

    console.print(f"[bold]AtlasBridge Chat[/bold] — {provider_name}")
    if model_name:
        console.print(f"Model: [cyan]{model_name}[/cyan]")
    console.print(
        f"Tools: [cyan]{'enabled' if daemon_config['chat']['tools_enabled'] else 'disabled'}[/cyan]"
    )
    console.print("Waiting for messages on your configured channel...\n")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    from atlasbridge.core.daemon.manager import DaemonManager

    manager = DaemonManager(daemon_config)
    try:
        asyncio.run(manager.start())
    except KeyboardInterrupt:
        console.print("\n[dim]Chat session ended.[/dim]")
