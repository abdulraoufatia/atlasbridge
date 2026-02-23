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
@click.option("--experimental", is_flag=True, default=False, help="Show experimental flags")
def version_cmd(as_json: bool, verbose: bool, experimental: bool) -> None:
    """Show version information and feature flags."""
    import importlib.util
    import platform
    import sys as _sys

    flags = {
        "conpty_backend": _sys.platform == "win32",
        "slack_channel": False,
        "whatsapp_channel": False,
    }
    if experimental:
        flags["windows_conpty"] = _sys.platform == "win32"
        flags["conpty_backend"] = _sys.platform == "win32"

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
