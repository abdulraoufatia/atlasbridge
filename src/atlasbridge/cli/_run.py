"""atlasbridge run — launch a CLI tool under AtlasBridge supervision."""

from __future__ import annotations

import asyncio
import sys

from rich.console import Console


def cmd_run(
    tool: str, command: list[str], label: str, cwd: str, console: Console, policy_file: str = ""
) -> None:
    """Load config and run the tool under AtlasBridge supervision (foreground)."""
    import atlasbridge.adapters  # noqa: F401 — registers all built-in adapters
    from atlasbridge.adapters.base import AdapterRegistry
    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    # Validate the adapter exists before loading config / starting the daemon.
    try:
        AdapterRegistry.get(tool)
    except KeyError:
        available = ", ".join(sorted(AdapterRegistry.list_all().keys())) or "(none)"
        console.print(f"[red]Unknown adapter:[/red] {tool!r}")
        console.print(f"Available: {available}")
        console.print("Run [cyan]atlasbridge adapter list[/cyan] for details.")
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

    # Build a human-readable channel summary
    channel_parts = []
    if config.telegram:
        channel_parts.append(f"Telegram ({len(config.telegram.allowed_users)} user(s))")
    if config.slack:
        channel_parts.append(f"Slack ({len(config.slack.allowed_users)} user(s))")
    channel_str = " + ".join(channel_parts) or "no channel configured"

    console.print(f"[bold]AtlasBridge[/bold] supervising: [cyan]{' '.join(command)}[/cyan]")
    console.print(f"Prompts will arrive via: {channel_str}")
    console.print()
    console.print("[dim]How it works:[/dim]")
    console.print("  When the CLI asks a question, AtlasBridge sends it to your channel.")
    console.print("  Reply there (tap a button or type a response) to answer the prompt.")
    console.print()
    console.print("[dim]Useful commands:[/dim]")
    console.print("  [cyan]atlasbridge sessions[/cyan]  — list active sessions")
    console.print("  [cyan]atlasbridge status[/cyan]    — check daemon status")
    console.print("  [cyan]atlasbridge logs[/cyan]      — view audit log")
    console.print("  [cyan]Ctrl+C[/cyan]               — stop this session")
    console.print()

    # Validate policy file if provided
    if policy_file:
        from atlasbridge.core.policy.parser import PolicyParseError, load_policy

        try:
            load_policy(policy_file)
        except PolicyParseError as exc:
            console.print(f"[red]Policy error:[/red] {exc}")
            sys.exit(1)

    try:
        asyncio.run(
            _run_async(
                tool=tool,
                command=command,
                label=label,
                cwd=cwd,
                config=config,
                policy_file=policy_file,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)


async def _run_async(
    tool: str, command: list[str], label: str, cwd: str, config: object, policy_file: str = ""
) -> None:
    from atlasbridge.core.daemon.manager import DaemonManager

    # Convert AtlasBridgeConfig to the dict format DaemonManager expects
    cfg_dict = _config_to_dict(
        tool=tool, command=command, label=label, cwd=cwd, config=config, policy_file=policy_file
    )

    manager = DaemonManager(cfg_dict)
    await manager.start()


def _config_to_dict(
    tool: str, command: list[str], label: str, cwd: str, config: object, policy_file: str = ""
) -> dict:
    """Convert AtlasBridgeConfig + run params into the DaemonManager config dict."""
    from pathlib import Path

    db_path = config.db_path  # type: ignore[union-attr]
    channels: dict[str, object] = {}

    if config.telegram is not None:  # type: ignore[union-attr]
        channels["telegram"] = {
            "bot_token": config.telegram.bot_token.get_secret_value(),  # type: ignore[union-attr]
            "allowed_user_ids": config.telegram.allowed_users,  # type: ignore[union-attr]
        }

    if config.slack is not None:  # type: ignore[union-attr]
        channels["slack"] = {
            "bot_token": config.slack.bot_token.get_secret_value(),  # type: ignore[union-attr]
            "app_token": config.slack.app_token.get_secret_value(),  # type: ignore[union-attr]
            "allowed_user_ids": config.slack.allowed_users,  # type: ignore[union-attr]
        }

    result: dict = {
        "data_dir": str(db_path.parent),
        "tool": tool,
        "command": command,
        "label": label,
        "cwd": cwd or str(Path.cwd()),
        "channels": channels,
        "prompts": {
            "timeout_seconds": config.prompts.timeout_seconds,  # type: ignore[union-attr]
            "stuck_timeout_seconds": config.prompts.stuck_timeout_seconds,  # type: ignore[union-attr]
        },
    }
    if policy_file:
        result["policy_file"] = policy_file
    return result
