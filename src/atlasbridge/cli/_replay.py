"""
CLI commands: ``atlasbridge replay <session_id>``.

Deterministic session replay — re-evaluate governance decisions
against the original or an alternative policy.
"""

from __future__ import annotations

import sys

import click

from atlasbridge.core.policy.parser import PolicyParseError, load_policy


@click.group("replay")
def replay_group() -> None:
    """Deterministic session replay — re-evaluate governance decisions."""


@replay_group.command("session")
@click.argument("session_id")
@click.option(
    "--policy",
    "policy_file",
    default="",
    type=click.Path(exists=True, dir_okay=False),
    help="Policy file to evaluate against. If omitted, uses default (all require_human).",
)
@click.option("--branch", default="", help="Git branch context for risk classification.")
@click.option("--ci-status", "ci_status", default="", help="CI status: passing, failing, unknown.")
@click.option("--environment", default="", help="Environment: dev, staging, production.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
def replay_session(
    session_id: str,
    policy_file: str,
    branch: str,
    ci_status: str,
    environment: str,
    output_json: bool,
) -> None:
    """
    Replay a session — re-evaluate all governance decisions.

    Loads the session from the database and re-evaluates every prompt
    against the given policy (or default). Shows what the policy would
    decide for each prompt, with risk assessment.

    Example::

        atlasbridge replay session sess-abc123
        atlasbridge replay session sess-abc123 --policy policy.yaml --json
    """
    from atlasbridge.core.config import find_config_dir
    from atlasbridge.core.replay import ReplayEngine
    from atlasbridge.core.store.database import Database

    config_dir = find_config_dir()
    db_path = config_dir / "atlasbridge.db"
    if not db_path.exists():
        click.echo(f"Database not found at {db_path}", err=True)
        sys.exit(1)

    db = Database(db_path)
    db.connect()
    try:
        engine = ReplayEngine(db)
        snapshot = engine.load_session(session_id)

        policy = None
        if policy_file:
            try:
                policy = load_policy(policy_file)
            except PolicyParseError as exc:
                click.echo(str(exc), err=True)
                sys.exit(1)

        report = engine.replay(
            snapshot,
            policy,
            branch=branch,
            ci_status=ci_status,
            environment=environment,
        )

        if output_json:
            click.echo(report.to_json())
        else:
            click.echo(report.to_text())
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    finally:
        db.close()


@replay_group.command("diff")
@click.argument("session_id")
@click.option(
    "--original-policy",
    "original_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Original policy file.",
)
@click.option(
    "--alt-policy",
    "alt_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Alternative policy file to compare.",
)
@click.option("--branch", default="", help="Git branch context.")
@click.option("--ci-status", "ci_status", default="", help="CI status.")
@click.option("--environment", default="", help="Environment context.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
def replay_diff(
    session_id: str,
    original_file: str,
    alt_file: str,
    branch: str,
    ci_status: str,
    environment: str,
    output_json: bool,
) -> None:
    """
    Compare two policies against the same session.

    Shows what decisions would change if you switch from the original
    policy to the alternative policy.

    Example::

        atlasbridge replay diff sess-abc123 \\
            --original-policy current.yaml \\
            --alt-policy proposed.yaml
    """
    from atlasbridge.core.config import find_config_dir
    from atlasbridge.core.replay import ReplayEngine
    from atlasbridge.core.store.database import Database

    config_dir = find_config_dir()
    db_path = config_dir / "atlasbridge.db"
    if not db_path.exists():
        click.echo(f"Database not found at {db_path}", err=True)
        sys.exit(1)

    db = Database(db_path)
    db.connect()
    try:
        engine = ReplayEngine(db)
        snapshot = engine.load_session(session_id)

        try:
            original = load_policy(original_file)
            alt = load_policy(alt_file)
        except PolicyParseError as exc:
            click.echo(str(exc), err=True)
            sys.exit(1)

        report = engine.replay_diff(
            snapshot,
            original,
            alt,
            branch=branch,
            ci_status=ci_status,
            environment=environment,
        )

        if output_json:
            click.echo(report.to_json())
        else:
            click.echo(report.to_text())
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    finally:
        db.close()
