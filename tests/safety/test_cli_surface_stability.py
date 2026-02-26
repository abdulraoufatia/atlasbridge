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
        "config",
        "policy",
        "autopilot",
        "cloud",
        "trace",
        "lab",
        "db",
        "dashboard",
        "console",
        "replay",
        "risk",
        "audit",
        "chat",
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


def test_dashboard_subcommands():
    """Dashboard group must have its frozen subcommands."""
    from atlasbridge.cli.main import cli

    dashboard = cli.commands.get("dashboard")
    assert dashboard is not None, "dashboard group missing"
    assert isinstance(dashboard, click.Group)

    expected = {"start", "status", "export"}
    actual = set(dashboard.commands.keys())
    missing = expected - actual
    assert not missing, f"Dashboard subcommands removed: {sorted(missing)}"


def test_config_subcommands():
    """Config group must have its frozen subcommands."""
    from atlasbridge.cli.main import cli

    config = cli.commands.get("config")
    assert config is not None, "config group missing"
    assert isinstance(config, click.Group)

    expected = {"show", "validate", "migrate"}
    actual = set(config.commands.keys())
    missing = expected - actual
    assert not missing, f"Config subcommands removed: {sorted(missing)}"


def test_cloud_subcommands():
    """Cloud group must have its frozen subcommands."""
    from atlasbridge.cli.main import cli

    cloud = cli.commands.get("cloud")
    assert cloud is not None, "cloud group missing"
    assert isinstance(cloud, click.Group)

    expected = {"status", "edition", "features"}
    actual = set(cloud.commands.keys())
    missing = expected - actual
    assert not missing, f"Cloud subcommands removed: {sorted(missing)}"


def test_db_subcommands():
    """DB group must have its frozen subcommands."""
    from atlasbridge.cli.main import cli

    db = cli.commands.get("db")
    assert db is not None, "db group missing"
    assert isinstance(db, click.Group)

    expected = {"archive", "info", "migrate"}
    actual = set(db.commands.keys())
    missing = expected - actual
    assert not missing, f"DB subcommands removed: {sorted(missing)}"


def test_audit_subcommands():
    """Audit group must have its frozen subcommands."""
    from atlasbridge.cli.main import cli

    audit = cli.commands.get("audit")
    assert audit is not None, "audit group missing"
    assert isinstance(audit, click.Group)

    expected = {"verify", "export"}
    actual = set(audit.commands.keys())
    missing = expected - actual
    assert not missing, f"Audit subcommands removed: {sorted(missing)}"


def test_lab_subcommands():
    """Lab group must have its frozen subcommands."""
    from atlasbridge.cli.main import cli

    lab = cli.commands.get("lab")
    assert lab is not None, "lab group missing"
    assert isinstance(lab, click.Group)

    expected = {"list", "run"}
    actual = set(lab.commands.keys())
    missing = expected - actual
    assert not missing, f"Lab subcommands removed: {sorted(missing)}"
