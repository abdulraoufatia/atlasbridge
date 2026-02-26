"""Edition-mode CLI commands — launch dashboard + runtime per edition."""

from __future__ import annotations

import os
import threading

import click
from rich.console import Console

console = Console()


def _start_dashboard_background(port: int) -> threading.Thread:
    """Start the dashboard in a background daemon thread."""

    def _run() -> None:
        try:
            from atlasbridge.dashboard.app import start_server

            start_server(
                host="127.0.0.1",
                port=port,
                open_browser=False,
            )
        except Exception:  # noqa: BLE001
            pass  # Dashboard failure is non-fatal

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def _launch_edition(edition: str, tool: str, dashboard_port: int) -> None:
    """Set the edition env var, start dashboard, and run the supervised tool."""
    os.environ["ATLASBRIDGE_EDITION"] = edition
    os.environ.setdefault("ATLASBRIDGE_AUTHORITY_MODE", "readonly")

    from atlasbridge.enterprise.edition import detect_authority_mode, detect_edition
    from atlasbridge.enterprise.registry import FeatureRegistry

    ed = detect_edition()
    am = detect_authority_mode()
    cap_hash = FeatureRegistry.capabilities_hash(ed, am)

    console.print(f"[bold]AtlasBridge[/bold] edition: [cyan]{ed.value}[/cyan]")
    console.print(f"Authority mode: [cyan]{am.value}[/cyan]")
    console.print(f"Capabilities hash: [dim]{cap_hash[:16]}...[/dim]")
    console.print(f"Dashboard: http://127.0.0.1:{dashboard_port}/settings")
    console.print()

    # Start dashboard in background
    try:
        import fastapi  # noqa: F401

        _start_dashboard_background(dashboard_port)
    except ImportError:
        console.print(
            "[dim]Dashboard unavailable (install with: pip install 'atlasbridge[dashboard]')[/dim]"
        )

    # Run supervised tool in foreground
    from atlasbridge.cli._run import cmd_run

    cmd_run(
        tool=tool,
        command=[tool],
        label=f"{ed.value} session",
        cwd="",
        console=console,
    )


@click.command("community")
@click.argument("tool", default="claude")
@click.option("--dashboard-port", default=8787, show_default=True, help="Dashboard server port")
def community_cmd(tool: str, dashboard_port: int) -> None:
    """Launch AtlasBridge in Core edition (deprecated alias for 'core')."""
    console.print("[yellow]Note: 'community' is deprecated. Using 'core' edition.[/yellow]")
    _launch_edition("core", tool, dashboard_port)


@click.command("core")
@click.argument("tool", default="claude")
@click.option("--dashboard-port", default=8787, show_default=True, help="Dashboard server port")
def core_cmd(tool: str, dashboard_port: int) -> None:
    """Launch AtlasBridge in Core edition (local governance + tooling)."""
    _launch_edition("core", tool, dashboard_port)


@click.command("enterprise")
@click.argument("tool", default="claude")
@click.option("--dashboard-port", default=8787, show_default=True, help="Dashboard server port")
def enterprise_cmd(tool: str, dashboard_port: int) -> None:
    """Launch AtlasBridge in Enterprise edition (authority capabilities)."""
    _launch_edition("enterprise", tool, dashboard_port)
