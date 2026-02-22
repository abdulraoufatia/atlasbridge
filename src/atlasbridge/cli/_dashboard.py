"""CLI commands for the local dashboard."""

from __future__ import annotations

import socket

import click


@click.group("dashboard")
def dashboard_group() -> None:
    """Local read-only governance dashboard."""


@dashboard_group.command("start")
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Bind address (must be loopback)",
)
@click.option("--port", default=8787, show_default=True, help="Port to listen on")
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Do not open browser automatically",
)
def dashboard_start(host: str, port: int, no_browser: bool) -> None:
    """Start the local dashboard server."""
    # Guard: fastapi must be installed
    try:
        import fastapi  # noqa: F401
    except ImportError as exc:
        click.echo(
            "Error: Dashboard dependencies not installed.\n"
            "Install them with:\n\n"
            "  pip install 'atlasbridge[dashboard]'\n",
            err=True,
        )
        raise SystemExit(1) from exc

    # Guard: host must be loopback
    from atlasbridge.dashboard.sanitize import is_loopback

    if not is_loopback(host):
        click.echo(
            f"Error: Dashboard must bind to a loopback address for safety.\n"
            f"Got: {host!r}. Use 127.0.0.1, ::1, or localhost.",
            err=True,
        )
        raise SystemExit(1)

    from atlasbridge.dashboard.app import start_server

    click.echo(f"Starting dashboard at http://{host}:{port}")
    start_server(host=host, port=port, open_browser=not no_browser)


@dashboard_group.command("status")
@click.option("--port", default=8787, show_default=True, help="Port to check")
def dashboard_status(port: int) -> None:
    """Check if the dashboard server is running."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            click.echo(f"Dashboard is running on port {port}")
        else:
            click.echo(f"Dashboard is not running on port {port}")
    finally:
        sock.close()
