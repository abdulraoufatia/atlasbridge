"""atlasbridge run — launch a CLI tool under AtlasBridge supervision."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console

console = Console()


@click.command("run", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
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
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run the full pipeline (detect/classify/policy/plan) without injecting into the PTY.",
)
@click.option(
    "--profile",
    "profile_name",
    default="",
    help="Agent profile name (provides defaults for label, policy, adapter).",
)
def run_cmd(
    tool: str,
    tool_args: tuple[str, ...],
    session_label: str,
    cwd: str,
    policy_file: str,
    dry_run: bool,
    profile_name: str,
) -> None:
    """Launch a CLI tool under AtlasBridge supervision."""
    # Apply profile defaults — explicit CLI flags always win
    if profile_name:
        from atlasbridge.core.profile import ProfileStore

        store = ProfileStore()
        profile = store.get(profile_name)
        if profile is None:
            console.print(f"[red]Profile {profile_name!r} not found.[/red]")
            console.print("Run [cyan]atlasbridge profile list[/cyan] to see available profiles.")
            sys.exit(1)
        if not session_label and profile.session_label:
            session_label = profile.session_label
        if not policy_file and profile.policy_file:
            policy_file = profile.policy_file
        if tool == "claude" and profile.adapter != "claude":
            tool = profile.adapter

    command = [tool] + list(tool_args)
    cmd_run(
        tool=tool,
        command=command,
        label=session_label,
        cwd=cwd,
        policy_file=policy_file,
        dry_run=dry_run,
        console=console,
    )


def cmd_run(
    tool: str,
    command: list[str],
    label: str,
    cwd: str,
    console: Console,
    policy_file: str = "",
    dry_run: bool = False,
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

    if dry_run:
        console.print("[bold yellow][DRY RUN][/bold yellow] No injection will occur.")
        console.print()
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
                dry_run=dry_run,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)


async def _run_async(
    tool: str,
    command: list[str],
    label: str,
    cwd: str,
    config: object,
    policy_file: str = "",
    dry_run: bool = False,
) -> None:
    from atlasbridge.core.daemon.manager import DaemonManager

    # Stop any existing daemon to prevent two processes competing for
    # the Telegram long-poll.  ``atlasbridge run`` starts its own daemon
    # internally, so a standalone daemon would silently intercept replies
    # and reject them with "No active session".
    _stop_existing_daemon()

    # Convert AtlasBridgeConfig to the dict format DaemonManager expects
    cfg_dict = _config_to_dict(
        tool=tool,
        command=command,
        label=label,
        cwd=cwd,
        config=config,
        policy_file=policy_file,
        dry_run=dry_run,
    )

    manager = DaemonManager(cfg_dict)
    await manager.start()


def _stop_existing_daemon() -> None:
    """Stop an existing AtlasBridge daemon if one is running.

    ``atlasbridge run`` includes its own daemon, so a standalone daemon
    would compete for the Telegram long-poll and intercept replies meant
    for the agent session.
    """
    import os
    import signal
    import time

    from atlasbridge.cli._daemon import _pid_alive, _read_pid

    pid = _read_pid()
    if pid is None or not _pid_alive(pid):
        return

    # Don't kill ourselves
    if pid == os.getpid():
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return

    # Wait briefly for graceful shutdown
    for _ in range(10):
        time.sleep(0.2)
        if not _pid_alive(pid):
            console.print("[dim]Stopped existing daemon to avoid polling conflict.[/dim]")
            return

    # Force kill if still alive
    try:
        os.kill(pid, signal.SIGKILL)
        console.print("[dim]Force-stopped existing daemon.[/dim]")
    except (ProcessLookupError, PermissionError):
        pass


def _config_to_dict(
    tool: str,
    command: list[str],
    label: str,
    cwd: str,
    config: object,
    policy_file: str = "",
    dry_run: bool = False,
) -> dict:
    """Convert AtlasBridgeConfig + run params into the DaemonManager config dict."""
    from pathlib import Path

    db_path = config.db_path
    channels: dict[str, object] = {}

    if config.telegram is not None:
        channels["telegram"] = {
            "bot_token": config.telegram.bot_token.get_secret_value(),
            "allowed_user_ids": config.telegram.allowed_users,
        }

    if config.slack is not None:
        channels["slack"] = {
            "bot_token": config.slack.bot_token.get_secret_value(),
            "app_token": config.slack.app_token.get_secret_value(),
            "allowed_user_ids": config.slack.allowed_users,
        }

    result: dict = {
        "data_dir": str(db_path.parent),
        "tool": tool,
        "command": command,
        "label": label,
        "cwd": cwd or str(Path.cwd()),
        "channels": channels,
        "prompts": {
            "timeout_seconds": config.prompts.timeout_seconds,
            "stuck_timeout_seconds": config.prompts.stuck_timeout_seconds,
        },
    }
    if policy_file:
        result["policy_file"] = policy_file
    if dry_run:
        result["dry_run"] = True
    return result
