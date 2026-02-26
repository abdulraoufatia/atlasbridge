"""Enterprise CLI commands — edition, features, cloud status."""

from __future__ import annotations

from dataclasses import dataclass

import click
from rich.console import Console

console = Console()


@dataclass
class _CloudConfig:
    """Cloud integration configuration (Phase B spec — not yet implemented)."""

    enabled: bool = False
    endpoint: str = ""
    org_id: str = ""
    api_token: str = ""
    control_channel: str = "disabled"
    stream_audit: bool = False


@click.group("cloud")
def cloud_group():
    """[EXPERIMENTAL] Cloud governance integration (Phase B)."""


@cloud_group.command("edition")
@click.option("--json", "as_json", is_flag=True, default=False)
def edition_cmd(as_json):
    """[EXPERIMENTAL] Show the current AtlasBridge edition."""
    from atlasbridge.enterprise.edition import detect_authority_mode, detect_edition

    ed = detect_edition()
    am = detect_authority_mode()
    if as_json:
        import json

        click.echo(json.dumps({"edition": ed.value, "authority_mode": am.value}))
    else:
        console.print(f"AtlasBridge edition: [bold]{ed.value}[/bold]")
        console.print(f"Authority mode: [bold]{am.value}[/bold]")


@cloud_group.command("features")
@click.option("--json", "as_json", is_flag=True, default=False)
def features_cmd(as_json):
    """[EXPERIMENTAL] Show all capabilities and their availability."""
    from atlasbridge.enterprise.edition import detect_authority_mode, detect_edition
    from atlasbridge.enterprise.registry import FeatureRegistry

    ed = detect_edition()
    am = detect_authority_mode()
    caps = FeatureRegistry.list_capabilities(ed, am)
    if as_json:
        import json

        click.echo(json.dumps(caps, indent=2))
    else:
        console.print("\n[bold]Capabilities[/bold]\n")
        for name, info in caps.items():
            status = "[green]active[/green]" if info["allowed"] else "[dim]locked[/dim]"
            console.print(f"  {name:<40} {status}  ({info['capability_class']})")
        console.print()


@cloud_group.command("status")
@click.option("--json", "as_json", is_flag=True, default=False)
def cloud_status(as_json):
    """[EXPERIMENTAL] Show cloud integration status."""
    config = _load_cloud_config()
    enabled = config.enabled and bool(config.endpoint)
    status = {
        "enabled": enabled,
        "endpoint": config.endpoint or "(not configured)",
        "control_channel": config.control_channel,
        "audit_streaming": config.stream_audit,
        "connected": False,
        "phase": "B (scaffolding only)",
    }
    if as_json:
        import json

        click.echo(json.dumps(status, indent=2))
    else:
        console.print("\n[bold]Cloud Integration Status[/bold]\n")
        for key, val in status.items():
            if isinstance(val, bool):
                label = "[green]yes[/green]" if val else "[dim]no[/dim]"
            else:
                label = str(val)
            console.print(f"  {key:<22} {label}")
        console.print("  [yellow]Phase B is scaffolding only — no cloud calls are made.[/yellow]")
        console.print()


def _load_cloud_config():
    """Load cloud config from user config, falling back to defaults."""
    try:
        from atlasbridge.core.config import _config_file_path, load_config

        cfg_path = _config_file_path()
        if not cfg_path.exists():
            return _CloudConfig()
        cfg = load_config(cfg_path)
        cloud_section = getattr(cfg, "cloud", None)
        if cloud_section and isinstance(cloud_section, dict):
            return _CloudConfig(
                **{k: v for k, v in cloud_section.items() if hasattr(_CloudConfig, k)}
            )
    except Exception:  # noqa: BLE001
        pass
    return _CloudConfig()
