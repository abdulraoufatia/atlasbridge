"""
AtlasBridge CLI entry point.

Commands:
  atlasbridge                    — launch interactive TUI (if stdout is a TTY)
  atlasbridge ui                 — launch interactive TUI (explicit)
  atlasbridge setup              — interactive first-time configuration
  atlasbridge start              — start the background daemon
  atlasbridge stop               — stop the background daemon
  atlasbridge status             — show daemon and session status
  atlasbridge run <tool> [args]  — launch a CLI tool under AtlasBridge supervision
  atlasbridge sessions           — list active sessions
  atlasbridge logs               — stream or show recent audit log
  atlasbridge doctor [--fix]     — environment and configuration health check
  atlasbridge db archive         — archive old audit events (retention policy)
  atlasbridge debug bundle       — create a redacted support bundle
  atlasbridge channel add <type> — add/reconfigure a notification channel
  atlasbridge adapter list       — show available tool adapters
  atlasbridge adapters           — list installed adapters (top-level shortcut)
  atlasbridge version            — show version and feature flags
  atlasbridge lab run <scenario> — Prompt Lab: run a QA scenario (dev/CI only)
  atlasbridge lab list           — Prompt Lab: list registered scenarios
"""

from __future__ import annotations

import sys

import click

from atlasbridge import __version__

# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, "--version", "-V", message="atlasbridge %(version)s")
@click.option(
    "--log-level", default="WARNING", hidden=True, help="Log level for structured logging."
)
@click.option("--log-json", is_flag=True, default=False, hidden=True, help="Emit JSON log lines.")
@click.pass_context
def cli(ctx: click.Context, log_level: str, log_json: bool) -> None:
    """AtlasBridge — universal human-in-the-loop control plane for AI developer agents."""
    from atlasbridge.core.logging import configure_logging

    configure_logging(level=log_level, json_output=log_json)

    if ctx.invoked_subcommand is None:
        if sys.stdout.isatty():
            from atlasbridge.ui.app import run as tui_run

            tui_run()
        else:
            click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# ui (interactive TUI — explicit launch)
# ---------------------------------------------------------------------------


@cli.command()
def ui() -> None:
    """Launch the interactive terminal UI (requires a TTY)."""
    if not sys.stdout.isatty():
        from rich.console import Console

        Console(stderr=True).print(
            "[red]Error:[/red] 'atlasbridge ui' requires an interactive terminal (TTY)."
        )
        raise SystemExit(1)
    from atlasbridge.ui.app import run as tui_run

    tui_run()


# ---------------------------------------------------------------------------
# Register all subcommands from extracted modules
# ---------------------------------------------------------------------------

from atlasbridge.cli._adapter import adapter_group, adapters_cmd  # noqa: E402
from atlasbridge.cli._audit_cmd import audit_group  # noqa: E402
from atlasbridge.cli._autopilot import autopilot_group, pause_cmd, resume_cmd  # noqa: E402
from atlasbridge.cli._channel import channel_group  # noqa: E402
from atlasbridge.cli._config_cmd import config_group  # noqa: E402
from atlasbridge.cli._console import console_cmd  # noqa: E402
from atlasbridge.cli._daemon import start_cmd, stop_cmd  # noqa: E402
from atlasbridge.cli._dashboard import dashboard_group  # noqa: E402
from atlasbridge.cli._db import db_group  # noqa: E402
from atlasbridge.cli._debug import debug_group  # noqa: E402
from atlasbridge.cli._doctor import doctor_cmd  # noqa: E402
from atlasbridge.cli._enterprise import cloud_group, edition_cmd, features_cmd  # noqa: E402
from atlasbridge.cli._lab import lab_group  # noqa: E402
from atlasbridge.cli._logs import logs_cmd  # noqa: E402
from atlasbridge.cli._policy_cmd import policy_group  # noqa: E402
from atlasbridge.cli._run import run_cmd  # noqa: E402
from atlasbridge.cli._sessions import sessions_group  # noqa: E402
from atlasbridge.cli._setup import setup_cmd  # noqa: E402
from atlasbridge.cli._status import status_cmd  # noqa: E402
from atlasbridge.cli._trace_cmd import trace_group  # noqa: E402
from atlasbridge.cli._version import version_cmd  # noqa: E402

cli.add_command(setup_cmd)
cli.add_command(start_cmd)
cli.add_command(stop_cmd)
cli.add_command(status_cmd)
cli.add_command(run_cmd)
cli.add_command(sessions_group)
cli.add_command(logs_cmd)
cli.add_command(doctor_cmd)
cli.add_command(debug_group)
cli.add_command(channel_group)
cli.add_command(adapter_group, "adapter")
cli.add_command(adapters_cmd)
cli.add_command(version_cmd, "version")
cli.add_command(db_group, "db")
cli.add_command(config_group)
cli.add_command(policy_group)
cli.add_command(autopilot_group)
cli.add_command(cloud_group)
cli.add_command(edition_cmd)
cli.add_command(features_cmd)
cli.add_command(trace_group)
cli.add_command(audit_group)
cli.add_command(pause_cmd)
cli.add_command(resume_cmd)
cli.add_command(lab_group)
cli.add_command(dashboard_group)
cli.add_command(console_cmd)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
