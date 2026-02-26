"""atlasbridge providers — AI provider key management."""

from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()

_VALID_PROVIDERS = ("openai", "anthropic", "gemini")


def _open_db():
    """Open the AtlasBridge database, or return None if unavailable."""
    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    try:
        config = load_config()
        db_path = config.db_path
        if not db_path.exists():
            return None
        from atlasbridge.core.store.database import Database

        db = Database(db_path)
        db.connect()
        return db
    except (ConfigNotFoundError, ConfigError):
        return None


@click.group("providers", invoke_without_command=True)
@click.pass_context
def providers_group(ctx: click.Context) -> None:
    """AI provider key management."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(providers_list)


@providers_group.command("list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def providers_list(as_json: bool = False) -> None:
    """List configured AI providers."""
    from atlasbridge.core.store.provider_config import list_providers

    db = _open_db()
    if db is None:
        if as_json:
            print("[]")
        else:
            console.print("[dim]No database found. No providers configured.[/dim]")
        return

    try:
        rows = list_providers(db._conn)

        if as_json:
            print(json.dumps(rows, indent=2, default=str))
            return

        if not rows:
            console.print("[dim]No providers configured.[/dim]")
            console.print(
                "\nRun [cyan]atlasbridge providers add <provider> <key>[/cyan] to add one."
            )
            return

        table = Table(title="AI Providers", show_lines=False)
        table.add_column("Provider", style="cyan")
        table.add_column("Status")
        table.add_column("Key prefix", style="dim")
        table.add_column("Validated", style="dim")

        status_style = {
            "configured": "yellow",
            "validated": "green",
            "invalid": "red",
        }

        for row in rows:
            status = row.get("status", "")
            style = status_style.get(status, "")
            validated = (row.get("validated_at") or "")[:19] or "-"
            table.add_row(
                row.get("provider", ""),
                f"[{style}]{status}[/{style}]",
                row.get("key_prefix") or "-",
                validated,
            )

        console.print(table)
    finally:
        db.close()


@providers_group.command("add")
@click.argument("provider", type=click.Choice(list(_VALID_PROVIDERS), case_sensitive=False))
@click.argument("key")
def providers_add(provider: str, key: str) -> None:
    """Store an API key for a provider.

    The key is stored securely in the OS keychain (or encrypted file fallback).
    It is NEVER stored in the database.

    API usage is billed by your provider.
    """
    from atlasbridge.core.store.provider_config import store_key

    provider = provider.lower()
    db = _open_db()
    if db is None:
        console.print("[red]No database found. Run atlasbridge run once to initialise.[/red]")
        sys.exit(1)

    try:
        store_key(provider, key, db._conn)
        console.print(f"[green]Stored key for {provider}.[/green]")
        console.print("[dim]API usage is billed by your provider.[/dim]")
    finally:
        db.close()


@providers_group.command("validate")
@click.argument("provider", type=click.Choice(list(_VALID_PROVIDERS), case_sensitive=False))
def providers_validate(provider: str) -> None:
    """Validate the stored API key for a provider."""
    from atlasbridge.core.store.provider_config import validate_key

    provider = provider.lower()
    db = _open_db()
    if db is None:
        console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        result = validate_key(provider, db._conn)
        if result.get("status") == "validated":
            console.print(f"[green]Validated:[/green] {provider}")
        else:
            error = result.get("error", "Unknown error")
            console.print(f"[red]Invalid:[/red] {provider} — {error}")
            sys.exit(1)
    finally:
        db.close()


@providers_group.command("remove")
@click.argument("provider", type=click.Choice(list(_VALID_PROVIDERS), case_sensitive=False))
def providers_remove(provider: str) -> None:
    """Remove the stored API key for a provider."""
    from atlasbridge.core.store.provider_config import remove_key

    provider = provider.lower()
    db = _open_db()
    if db is None:
        console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        remove_key(provider, db._conn)
        console.print(f"[yellow]Removed:[/yellow] {provider}")
    finally:
        db.close()
