"""
CLI commands: ``atlasbridge audit verify``.

Verifies hash chain integrity of the SQLite audit log.
"""

from __future__ import annotations

import sys

import click


@click.group("audit")
def audit_group() -> None:
    """Inspect and verify the audit event log."""


@audit_group.command("verify")
@click.option(
    "--session",
    "session_id",
    default="",
    help="Verify only events for a specific session ID.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output result as JSON.",
)
def audit_verify(session_id: str, as_json: bool) -> None:
    """Verify hash chain integrity of the audit event log.

    Reads the SQLite audit_events table and checks that each event's
    hash matches recomputation and that prev_hash links form an
    unbroken chain.  Exits 0 if valid, 1 if the chain is broken.

    Use --session to scope verification to a single session.
    """
    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    try:
        config = load_config()
        db_path = config.db_path
    except (ConfigNotFoundError, ConfigError) as exc:
        click.echo(f"Cannot load config: {exc}", err=True)
        sys.exit(1)

    if not db_path.exists():
        click.echo("No database found — nothing to verify.")
        sys.exit(0)

    from atlasbridge.core.store.database import Database

    db = Database(db_path)
    db.connect()
    try:
        from atlasbridge.core.audit.verify import (
            format_verify_result,
            verify_audit_chain,
        )

        result = verify_audit_chain(db, session_id=session_id or None)

        if as_json:
            import json

            click.echo(
                json.dumps(
                    {
                        "valid": result.valid,
                        "total_events": result.total_events,
                        "verified_events": result.verified_events,
                        "errors": result.errors,
                        "first_break_event_id": result.first_break_event_id,
                        "first_break_position": result.first_break_position,
                    },
                    indent=2,
                )
            )
        else:
            click.echo(format_verify_result(result, session_id=session_id or None))

        sys.exit(0 if result.valid else 1)
    finally:
        db.close()
