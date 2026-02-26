"""
CLI commands: ``atlasbridge audit verify`` and ``atlasbridge audit export``.

Verifies hash chain integrity and exports events from the SQLite audit log.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from typing import Any

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


def _row_to_dict(row: Any) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return {k: row[k] for k in row.keys()}


_EXPORT_COLUMNS = [
    "id",
    "event_type",
    "session_id",
    "prompt_id",
    "payload",
    "timestamp",
    "prev_hash",
    "hash",
]


@audit_group.command("export")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["jsonl", "json", "csv"]),
    default="jsonl",
    show_default=True,
    help="Output format.",
)
@click.option("--session", "session_id", default="", help="Filter by session ID.")
@click.option("--since", default="", help="Include events from this ISO timestamp.")
@click.option("--until", default="", help="Include events up to this ISO timestamp.")
def audit_export(fmt: str, session_id: str, since: str, until: str) -> None:
    """Export audit events for SIEM ingestion.

    Writes events to stdout. Default format is JSONL (one JSON object per line).
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
        click.echo("No database found — nothing to export.", err=True)
        sys.exit(0)

    from atlasbridge.core.store.database import Database

    db = Database(db_path)
    db.connect()
    try:
        rows = db.get_audit_events_filtered(
            session_id=session_id or None,
            since=since or None,
            until=until or None,
        )

        if fmt == "jsonl":
            for row in rows:
                click.echo(json.dumps(_row_to_dict(row), separators=(",", ":")))
        elif fmt == "json":
            click.echo(json.dumps([_row_to_dict(r) for r in rows], indent=2))
        elif fmt == "csv":
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(_row_to_dict(row))
            click.echo(buf.getvalue(), nl=False)
    finally:
        db.close()
