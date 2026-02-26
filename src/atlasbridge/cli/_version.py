"""Version information CLI command."""

from __future__ import annotations

import click
from rich.console import Console

from atlasbridge import __version__

console = Console()


@click.command()
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show install path, config path, and build info",
)
def version_cmd(as_json: bool, verbose: bool) -> None:
    """Show version information and feature flags."""
    import importlib.util
    import platform
    import sys as _sys

    flags = {
        "slack_channel": False,
        "whatsapp_channel": False,
    }

    # Resolve install path (location of the atlasbridge package)
    spec = importlib.util.find_spec("atlasbridge")
    install_path = str(spec.origin) if spec and spec.origin else "unknown"

    # Resolve config path
    try:
        from atlasbridge.core.constants import _default_data_dir

        config_path = str(_default_data_dir() / "config.toml")
    except Exception:  # noqa: BLE001
        config_path = "unknown"

    # Resolve commit SHA from package metadata (populated by setuptools-scm if used)
    commit_sha = "n/a"

    # Check for updates
    update_available = False
    latest_version = ""
    try:
        from atlasbridge.core.version_check import check_version

        vs = check_version()
        update_available = vs.update_available
        latest_version = vs.latest or ""
    except Exception:  # noqa: BLE001
        pass

    if as_json:
        import json

        data: dict = {
            "atlasbridge": __version__,
            "python": _sys.version.split()[0],
            "platform": _sys.platform,
            "arch": platform.machine(),
            "feature_flags": flags,
        }
        if verbose:
            data["install_path"] = install_path
            data["config_path"] = config_path
            data["commit"] = commit_sha
        if update_available:
            data["update_available"] = True
            data["latest_version"] = latest_version
        click.echo(json.dumps(data, indent=2))
    else:
        console.print(f"atlasbridge {__version__}")
        console.print(f"Python {_sys.version.split()[0]}")
        console.print(f"Platform: {_sys.platform} {platform.machine()}")
        if verbose:
            console.print(f"Install:  {install_path}")
            console.print(f"Config:   {config_path}")
            console.print(f"Commit:   {commit_sha}")
        console.print("\nFeature flags:")
        for flag, enabled in flags.items():
            status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
            console.print(f"  {flag:<22} {status}")

        if update_available:
            console.print(f"\n[yellow]Update available:[/yellow] {__version__} → {latest_version}")
            console.print("[dim]  pip install --upgrade atlasbridge[/dim]")
