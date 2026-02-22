"""Safety guard: CLI command surface must not drift."""

from __future__ import annotations

import click


def _collect_commands(group: click.Group, prefix: str = "") -> set[str]:
    """Recursively collect all command paths from a Click group."""
    commands = set()
    for name, cmd in (group.commands or {}).items():
        full = f"{prefix}{name}" if prefix else name
        commands.add(full)
        if isinstance(cmd, click.Group):
            commands |= _collect_commands(cmd, f"{full}.")
    return commands


# Frozen top-level command and group names that must exist
FROZEN_TOP_LEVEL = frozenset(
    {
        "ui",
        "setup",
        "start",
        "stop",
        "status",
        "run",
        "sessions",
        "logs",
        "doctor",
        "version",
        "debug",
        "channel",
        "adapter",
        "adapters",
        "config",
        "policy",
        "autopilot",
        "edition",
        "features",
        "cloud",
        "trace",
        "lab",
        "db",
        "pause",
        "resume",
        "dashboard",
    }
)


def test_top_level_commands_present():
    """All frozen top-level commands and groups must exist."""
    from atlasbridge.cli.main import cli

    actual = set(cli.commands.keys()) if hasattr(cli, "commands") else set()
    missing = FROZEN_TOP_LEVEL - actual
    assert not missing, (
        f"CLI commands removed: {sorted(missing)}. Removing commands is a breaking change."
    )


def test_autopilot_subcommands():
    """Autopilot group must have its frozen subcommands."""
    from atlasbridge.cli.main import cli

    autopilot = cli.commands.get("autopilot")
    assert autopilot is not None, "autopilot group missing"
    assert isinstance(autopilot, click.Group)

    expected = {"enable", "disable", "status", "mode", "explain", "history"}
    actual = set(autopilot.commands.keys())
    missing = expected - actual
    assert not missing, f"Autopilot subcommands removed: {sorted(missing)}"


def test_policy_subcommands():
    """Policy group must have its frozen subcommands."""
    from atlasbridge.cli.main import cli

    policy = cli.commands.get("policy")
    assert policy is not None, "policy group missing"
    assert isinstance(policy, click.Group)

    expected = {"validate", "test", "migrate"}
    actual = set(policy.commands.keys())
    missing = expected - actual
    assert not missing, f"Policy subcommands removed: {sorted(missing)}"
