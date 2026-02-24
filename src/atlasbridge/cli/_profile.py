"""atlasbridge profile — manage agent profiles."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("profile")
def profile_group() -> None:
    """Manage agent profiles (reusable session defaults)."""


@profile_group.command("list")
def profile_list() -> None:
    """List all agent profiles."""
    from atlasbridge.core.profile import ProfileStore

    store = ProfileStore()
    profiles = store.list_profiles()
    default_name = store.get_default()

    if not profiles:
        console.print("[dim]No profiles found.[/dim]")
        console.print("Create one with: [cyan]atlasbridge profile create <name>[/cyan]")
        return

    table = Table(title="Agent Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Label")
    table.add_column("Adapter")
    table.add_column("Policy")
    table.add_column("Default", justify="center")

    for p in profiles:
        is_default = "yes" if p.name == default_name else ""
        table.add_row(
            p.name,
            p.session_label or "[dim]-[/dim]",
            p.adapter,
            p.policy_file or "[dim]-[/dim]",
            is_default,
        )

    console.print(table)


@profile_group.command("show")
@click.argument("name")
def profile_show(name: str) -> None:
    """Show details of a profile."""
    import yaml

    from atlasbridge.core.profile import ProfileStore

    store = ProfileStore()
    profile = store.get(name)
    if profile is None:
        console.print(f"[red]Profile {name!r} not found.[/red]")
        raise SystemExit(1)

    console.print(f"[bold]Profile: {profile.name}[/bold]")
    if store.get_default() == name:
        console.print("[green](default)[/green]")
    console.print()
    console.print(yaml.safe_dump(profile.model_dump(), default_flow_style=False, sort_keys=False))


@profile_group.command("create")
@click.argument("name")
@click.option(
    "--label", "session_label", default="", help="Session label (maps to session_tag in policy)"
)
@click.option("--policy", "policy_file", default="", help="Path to policy YAML file")
@click.option("--adapter", default="claude", help="Default adapter name")
@click.option("--description", default="", help="Human-readable description")
def profile_create(
    name: str,
    session_label: str,
    policy_file: str,
    adapter: str,
    description: str,
) -> None:
    """Create a new agent profile."""
    from pydantic import ValidationError

    from atlasbridge.core.profile import AgentProfile, ProfileStore

    store = ProfileStore()
    if store.get(name) is not None:
        console.print(f"[red]Profile {name!r} already exists.[/red] Use delete first.")
        raise SystemExit(1)

    try:
        profile = AgentProfile(
            name=name,
            description=description,
            session_label=session_label,
            policy_file=policy_file,
            adapter=adapter,
        )
    except ValidationError as exc:
        console.print(f"[red]Invalid profile:[/red] {exc}")
        raise SystemExit(1) from None

    path = store.save(profile)
    console.print(f"[green]Created profile {name!r}[/green] at {path}")


@profile_group.command("delete")
@click.argument("name")
def profile_delete(name: str) -> None:
    """Delete an agent profile."""
    from atlasbridge.core.profile import ProfileStore

    store = ProfileStore()
    if not store.delete(name):
        console.print(f"[red]Profile {name!r} not found.[/red]")
        raise SystemExit(1)
    console.print(f"[green]Deleted profile {name!r}.[/green]")


@profile_group.command("set-default")
@click.argument("name")
def profile_set_default(name: str) -> None:
    """Set a profile as the default for `atlasbridge run`."""
    from atlasbridge.core.profile import ProfileStore

    store = ProfileStore()
    try:
        store.set_default(name)
    except FileNotFoundError:
        console.print(f"[red]Profile {name!r} does not exist.[/red]")
        raise SystemExit(1) from None
    console.print(f"[green]Default profile set to {name!r}.[/green]")
