"""CLI subcommand: atlasbridge monitor — manage AI conversation monitors."""

from __future__ import annotations

import asyncio

import click


@click.group("monitor")
def monitor_group() -> None:
    """Monitor AI conversations across desktop apps, VS Code, and browser."""


@monitor_group.command("desktop")
@click.option(
    "--dashboard-url",
    default="http://localhost:5000",
    help="Dashboard URL for relaying captured data.",
)
@click.option(
    "--poll-interval",
    default=3.0,
    type=float,
    help="Polling interval in seconds.",
)
def desktop_cmd(dashboard_url: str, poll_interval: float) -> None:
    """Monitor macOS desktop AI apps (Claude Desktop, ChatGPT)."""
    from atlasbridge.monitors.desktop import run_desktop_monitor

    asyncio.run(run_desktop_monitor(dashboard_url=dashboard_url, poll_interval=poll_interval))


@monitor_group.command("vscode")
@click.option(
    "--dashboard-url",
    default="http://localhost:5000",
    help="Dashboard URL for relaying captured data.",
)
@click.option(
    "--poll-interval",
    default=5.0,
    type=float,
    help="Polling interval in seconds.",
)
def vscode_cmd(dashboard_url: str, poll_interval: float) -> None:
    """Monitor Claude Code sessions running in VS Code."""
    from atlasbridge.monitors.vscode import run_vscode_monitor

    asyncio.run(run_vscode_monitor(dashboard_url=dashboard_url, poll_interval=poll_interval))


@monitor_group.command("status")
def status_cmd() -> None:
    """Show which monitors are available and their status."""
    import platform

    click.echo("Monitor Status")
    click.echo("=" * 40)

    # Desktop monitor
    click.echo("\nDesktop Monitor (macOS Accessibility API)")
    if platform.system() != "Darwin":
        click.echo("  Status: unavailable (macOS only)")
    else:
        try:
            from atlasbridge.monitors.desktop import _check_accessibility_imports

            if _check_accessibility_imports():
                from atlasbridge.monitors.desktop import check_accessibility_permission

                if check_accessibility_permission():
                    click.echo("  Status: ready")
                else:
                    click.echo("  Status: permission required")
                    click.echo("  Fix: System Settings > Privacy & Security > Accessibility")
            else:
                click.echo("  Status: missing dependency")
                click.echo("  Fix: pip install atlasbridge[desktop-monitor]")
        except Exception as exc:
            click.echo(f"  Status: error ({exc})")

    # VS Code monitor
    click.echo("\nVS Code / Claude Code Monitor")
    try:
        from atlasbridge.monitors.vscode import find_claude_processes, find_claude_sessions

        sessions = find_claude_sessions()
        processes = find_claude_processes()
        click.echo(f"  Lock files: {len(sessions)} found")
        click.echo(f"  Processes: {len(processes)} found")
        if sessions:
            for cs in sessions:
                click.echo(f"    - port={cs.port} pid={cs.pid}")
        click.echo("  Status: ready")
    except Exception as exc:
        click.echo(f"  Status: error ({exc})")

    # Browser extension
    click.echo("\nBrowser Extension (Chrome)")
    click.echo("  Status: install from extension/ directory")
    click.echo("  Load: chrome://extensions > Load unpacked > extension/dist/")
