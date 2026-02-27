"""
AtlasBridge CLI entry point.

Commands:
  atlasbridge                     — launch interactive TUI (if stdout is a TTY)
  atlasbridge ui                  — launch interactive TUI (explicit)
  atlasbridge setup               — interactive first-time configuration
  atlasbridge start               — start the background daemon
  atlasbridge stop                — stop the background daemon
  atlasbridge status              — show daemon and session status
  atlasbridge run <tool> [args]   — launch a CLI tool under AtlasBridge supervision
  atlasbridge sessions            — list active sessions
  atlasbridge logs                — stream or show recent audit log
  atlasbridge doctor [--fix]      — environment and configuration health check
  atlasbridge db archive          — archive old audit events (retention policy)
  atlasbridge debug bundle        — create a redacted support bundle
  atlasbridge channel add <type>  — add/reconfigure a notification channel
  atlasbridge adapter list        — show available tool adapters
  atlasbridge version             — show version and feature flags
  atlasbridge lab run <scenario>  — Prompt Lab: run a QA scenario (dev/CI only)
  atlasbridge lab list            — Prompt Lab: list registered scenarios
  atlasbridge policy explain      — Full policy explain (all rules, risk, alternatives)
  atlasbridge risk assess         — Deterministic risk classification
  atlasbridge replay session      — Replay a session with a policy
  atlasbridge replay diff         — Compare two policies against a session
  atlasbridge chat                — Start a chat session with an LLM provider
  atlasbridge cloud edition       — Show current edition
  atlasbridge cloud features      — Show feature flags
  atlasbridge cloud status        — Show cloud integration status
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
    """AtlasBridge — autonomous runtime for AI developer agents with human oversight."""
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

from atlasbridge.cli._adapter import adapter_group  # noqa: E402
from atlasbridge.cli._agent import agent_group  # noqa: E402
from atlasbridge.cli._audit_cmd import audit_group  # noqa: E402
from atlasbridge.cli._autopilot import autopilot_group  # noqa: E402
from atlasbridge.cli._channel import channel_group  # noqa: E402
from atlasbridge.cli._chat import chat_cmd  # noqa: E402
from atlasbridge.cli._config_cmd import config_group  # noqa: E402
from atlasbridge.cli._console import console_cmd  # noqa: E402
from atlasbridge.cli._daemon import start_cmd, stop_cmd  # noqa: E402
from atlasbridge.cli._dashboard import dashboard_group  # noqa: E402
from atlasbridge.cli._db import db_group  # noqa: E402
from atlasbridge.cli._debug import debug_group  # noqa: E402
from atlasbridge.cli._doctor import doctor_cmd  # noqa: E402
from atlasbridge.cli._enterprise import cloud_group  # noqa: E402
from atlasbridge.cli._lab import lab_group  # noqa: E402
from atlasbridge.cli._logs import logs_cmd  # noqa: E402
from atlasbridge.cli._policy_cmd import policy_group  # noqa: E402
from atlasbridge.cli._profile import profile_group  # noqa: E402
from atlasbridge.cli._providers import providers_group  # noqa: E402
from atlasbridge.cli._replay import replay_group  # noqa: E402
from atlasbridge.cli._risk import risk_group  # noqa: E402
from atlasbridge.cli._run import run_cmd  # noqa: E402
from atlasbridge.cli._sessions import sessions_group  # noqa: E402
from atlasbridge.cli._setup import setup_cmd  # noqa: E402
from atlasbridge.cli._status import status_cmd  # noqa: E402
from atlasbridge.cli._trace_cmd import trace_group  # noqa: E402
from atlasbridge.cli._version import version_cmd  # noqa: E402
from atlasbridge.cli._workspace import workspace_group  # noqa: E402

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
cli.add_command(version_cmd, "version")
cli.add_command(db_group, "db")
cli.add_command(config_group)
cli.add_command(policy_group)
cli.add_command(profile_group)
cli.add_command(autopilot_group)
cli.add_command(cloud_group)
cli.add_command(trace_group)
cli.add_command(audit_group)
cli.add_command(lab_group)
cli.add_command(dashboard_group)
cli.add_command(console_cmd)
cli.add_command(replay_group)
cli.add_command(risk_group)
cli.add_command(chat_cmd)
cli.add_command(workspace_group)
cli.add_command(providers_group)
cli.add_command(agent_group)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
