"""atlasbridge debug bundle — create a redacted support bundle."""

from __future__ import annotations

import json
import platform
import re
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console

_console = Console()


@click.group("debug")
def debug_group() -> None:
    """Debugging utilities."""


@debug_group.command("bundle")
@click.option("--output", default="", help="Output path for the bundle")
@click.option("--include-logs", default=500, help="Number of log lines to include")
@click.option("--no-redact", is_flag=True, default=False, help="Include secrets unredacted")
def debug_bundle_cmd(output: str, include_logs: int, no_redact: bool) -> None:
    """Create a redacted support bundle."""
    cmd_debug_bundle(
        output=output, include_logs=include_logs, redact=not no_redact, console=_console
    )


# Patterns for secrets to redact
_TOKEN_PATTERNS = [
    re.compile(r"\d{8,12}:[A-Za-z0-9_-]{35,}"),  # Telegram bot tokens
    re.compile(r"xoxb-[A-Za-z0-9-]+"),  # Slack bot tokens
    re.compile(r"xapp-[A-Za-z0-9-]+"),  # Slack app tokens
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # API keys
]

_SENSITIVE_KEYS = {"token", "secret", "password", "key", "api_key", "bot_token", "app_token"}


def _redact_text(text: str) -> str:
    """Replace known secret patterns with <REDACTED>."""
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub("<REDACTED>", text)
    return text


def _redact_dict(d: dict) -> dict:
    """Recursively redact sensitive keys in a dict."""
    result = {}
    for k, v in d.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            result[k] = "<REDACTED>"
        elif isinstance(v, dict):
            result[k] = _redact_dict(v)
        elif isinstance(v, str):
            result[k] = _redact_text(v)
        else:
            result[k] = v
    return result


def cmd_debug_bundle(output: str, include_logs: int, redact: bool, console: Console) -> None:
    import atlasbridge

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not output:
        output = f"atlasbridge-debug-{timestamp}.tar.gz"

    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir)

        # 1. version.json
        version_info = {
            "atlasbridge_version": atlasbridge.__version__,
            "python_version": sys.version,
            "platform": sys.platform,
            "machine": platform.machine(),
            "timestamp": timestamp,
        }
        _write_json(staging / "version.json", version_info)

        # 2. doctor.json
        doctor_results = _collect_doctor()
        _write_json(staging / "doctor.json", doctor_results)

        # 3. config.toml (redacted)
        _collect_config(staging, redact)

        # 4. db_stats.json
        db_stats = _collect_db_stats()
        _write_json(staging / "db_stats.json", db_stats)

        # 5. recent_audit.json
        audit_events = _collect_audit_events(include_logs)
        if redact:
            audit_events = [_redact_dict(e) for e in audit_events]
        _write_json(staging / "recent_audit.json", audit_events)

        # 6. platform.json
        platform_info = {
            "sys_platform": sys.platform,
            "machine": platform.machine(),
            "architecture": platform.architecture()[0],
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "node": platform.node(),
        }
        _write_json(staging / "platform.json", platform_info)

        # Create tarball
        with tarfile.open(output, "w:gz") as tar:
            for path in sorted(staging.iterdir()):
                tar.add(str(path), arcname=path.name)

    console.print("[bold]Debug Bundle[/bold]\n")
    console.print(f"  Bundle saved to: [cyan]{output}[/cyan]")
    console.print("  Contains 6 diagnostic files.")
    if redact:
        console.print("  Secrets have been [green]redacted[/green].")
    else:
        console.print("  [yellow]WARNING: secrets are NOT redacted.[/yellow]")


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


def _collect_doctor() -> list[dict]:
    try:
        from atlasbridge.cli._doctor import (
            _check_bot_token,
            _check_config,
            _check_db,
            _check_platform,
            _check_python_version,
        )

        return [
            _check_python_version(),
            _check_platform(),
            _check_config(),
            _check_bot_token(),
            _check_db(),
        ]
    except Exception as exc:  # noqa: BLE001
        return [{"name": "doctor", "status": "error", "detail": str(exc)}]


def _collect_config(staging: Path, redact: bool) -> None:
    try:
        from atlasbridge.core.config import load_config

        config = load_config()
        config_path = config.config_path
        if config_path and config_path.exists():
            text = config_path.read_text()
            if redact:
                text = _redact_text(text)
            (staging / "config.toml").write_text(text)
    except Exception:  # noqa: BLE001
        (staging / "config.toml").write_text("# Config not available\n")


def _collect_db_stats() -> dict:
    try:
        from atlasbridge.core.config import load_config
        from atlasbridge.core.store.database import Database
        from atlasbridge.core.store.migrations import get_user_version

        config = load_config()
        db_path = config.db_path
        if not db_path.exists():
            return {"exists": False}

        db = Database(db_path)
        db.connect()
        try:
            version = get_user_version(db._db)
            tables = {}
            for table in ("sessions", "prompts", "replies", "audit_events"):
                try:
                    row = db._db.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
                    tables[table] = row[0] if row else 0
                except Exception:  # noqa: BLE001
                    tables[table] = -1
            return {
                "exists": True,
                "path": str(db_path),
                "size_kb": round(db_path.stat().st_size / 1024, 1),
                "schema_version": version,
                "tables": tables,
            }
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return {"exists": False, "error": str(exc)}


def _collect_audit_events(limit: int) -> list[dict]:
    try:
        from atlasbridge.core.config import load_config
        from atlasbridge.core.store.database import Database

        config = load_config()
        db_path = config.db_path
        if not db_path.exists():
            return []

        db = Database(db_path)
        db.connect()
        try:
            rows = db.get_recent_audit_events(limit=limit)
            return [dict(r) for r in rows]
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        return []
