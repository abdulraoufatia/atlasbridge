"""
CLI commands: ``atlasbridge policy validate``, ``atlasbridge policy test``,
``atlasbridge policy coverage``, and ``atlasbridge policy migrate``.
"""

from __future__ import annotations

import sys

import click

from atlasbridge.core.policy.evaluator import evaluate
from atlasbridge.core.policy.explain import debug_policy, explain_decision, explain_policy
from atlasbridge.core.policy.parser import PolicyParseError, load_policy


@click.group("policy")
def policy_group() -> None:
    """Manage and test AtlasBridge policy files."""


@policy_group.command("validate")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False))
def policy_validate(policy_file: str) -> None:
    """
    Validate a policy YAML file against the AtlasBridge Policy DSL schema (v0 or v1).

    Exits 0 if valid, 1 if invalid.
    """
    try:
        policy = load_policy(policy_file)
        version = getattr(policy, "policy_version", "?")
        click.echo(
            f"✓  Policy {policy.name!r} is valid "
            f"(version={version}, "
            f"{len(policy.rules)} rule(s), mode={policy.autonomy_mode.value}, "
            f"hash={policy.content_hash()})"
        )
    except PolicyParseError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)


@policy_group.command("test")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--prompt", "prompt_text", required=True, help="Prompt text excerpt to test.")
@click.option(
    "--type",
    "prompt_type",
    default="yes_no",
    show_default=True,
    help="Prompt type: yes_no, confirm_enter, multiple_choice, free_text.",
)
@click.option(
    "--confidence",
    default="high",
    show_default=True,
    help="Confidence level: high, medium, low.",
)
@click.option("--tool", "tool_id", default="*", show_default=True, help="Tool/adapter name.")
@click.option("--repo", default="", help="Session working directory (prefix match).")
@click.option(
    "--session-tag",
    "session_tag",
    default="",
    help="Session label (v1 session_tag matching).",
)
@click.option(
    "--explain",
    is_flag=True,
    default=False,
    help="Show per-rule match details (verbose).",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Full debug trace — evaluate ALL rules with no short-circuit (implies --explain).",
)
def policy_test(
    policy_file: str,
    prompt_text: str,
    prompt_type: str,
    confidence: str,
    tool_id: str,
    repo: str,
    session_tag: str,
    explain: bool,
    debug: bool,
) -> None:
    """
    Test a policy against a synthetic prompt and show the decision.

    Example::

        atlasbridge policy test ~/.atlasbridge/policy.yaml \\
            --prompt "Continue? [y/n]" --type yes_no --explain

        # v1 session_tag matching:
        atlasbridge policy test policy_v1.yaml \\
            --prompt "Deploy?" --session-tag ci --explain
    """
    try:
        policy = load_policy(policy_file)
    except PolicyParseError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    if debug:
        click.echo(
            debug_policy(
                policy=policy,
                prompt_text=prompt_text,
                prompt_type=prompt_type,
                confidence=confidence,
                tool_id=tool_id,
                repo=repo,
                session_tag=session_tag,
            )
        )
        return

    if explain:
        click.echo(
            explain_policy(
                policy=policy,
                prompt_text=prompt_text,
                prompt_type=prompt_type,
                confidence=confidence,
                tool_id=tool_id,
                repo=repo,
                session_tag=session_tag,
            )
        )
        click.echo("")

    decision = evaluate(
        policy=policy,
        prompt_text=prompt_text,
        prompt_type=prompt_type,
        confidence=confidence,
        prompt_id="test-prompt",
        session_id="test-session",
        tool_id=tool_id,
        repo=repo,
        session_tag=session_tag,
    )

    click.echo(explain_decision(decision))


@policy_group.command("migrate")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--output",
    default="",
    help="Output path (default: overwrite in-place).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the migrated policy to stdout without writing any file.",
)
def policy_migrate(policy_file: str, output: str, dry_run: bool) -> None:
    """
    Upgrade a v0 policy file to v1 in place (or to --output path).

    The migration rewrites ``policy_version: "0"`` to ``"1"`` while
    preserving all YAML comments and formatting.  The result is validated
    against the Policy DSL v1 schema before writing.

    Example::

        # Upgrade in place (makes a backup first is not done automatically)
        atlasbridge policy migrate ~/.atlasbridge/policy.yaml

        # Preview without writing
        atlasbridge policy migrate policy.yaml --dry-run

        # Write to a new file
        atlasbridge policy migrate policy.yaml --output policy_v1.yaml
    """
    # Read source for dry-run preview, or delegate fully to migrate_v0_to_v1
    from pathlib import Path

    from atlasbridge.core.policy.migrate import MigrateError, migrate_v0_to_v1_text

    src = Path(policy_file)
    try:
        original = src.read_text(encoding="utf-8")
    except OSError as exc:
        click.echo(f"Cannot read {policy_file}: {exc}", err=True)
        sys.exit(1)

    # Validate source is a valid v0 policy
    try:
        load_policy(policy_file)
    except PolicyParseError as exc:
        click.echo(f"[error] Source is not a valid policy: {exc}", err=True)
        sys.exit(1)

    try:
        new_text = migrate_v0_to_v1_text(original)
    except MigrateError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    # Validate the migrated content
    try:
        from atlasbridge.core.policy.parser import parse_policy

        migrated_policy = parse_policy(new_text, source=f"{policy_file} (migrated)")
    except PolicyParseError as exc:
        click.echo(f"Migrated content failed validation: {exc}", err=True)
        sys.exit(1)

    if dry_run:
        click.echo(new_text, nl=False)
        click.echo(
            f"\n# Dry run: migration would produce a valid v{migrated_policy.policy_version} "
            f"policy ({len(migrated_policy.rules)} rule(s)).",
            err=True,
        )
        return

    # Write result
    dest = Path(output) if output else src
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        click.echo(f"Cannot write to {dest}: {exc}", err=True)
        sys.exit(1)

    verb = "written to" if output else "updated in place"
    click.echo(
        f"✓  Policy migrated to v{migrated_policy.policy_version} "
        f"({len(migrated_policy.rules)} rule(s)) — {verb} {dest}"
    )


@policy_group.command("coverage")
@click.argument("policy_file", type=click.Path(exists=True, dir_okay=False))
def policy_coverage(policy_file: str) -> None:
    """
    Analyze policy rule coverage and identify gaps.

    Reports which prompt types, confidence levels, and action types are covered,
    computes a coverage score (0-100), and lists any gaps.

    Example::

        atlasbridge policy coverage ~/.atlasbridge/policy.yaml
    """
    from atlasbridge.core.policy.coverage import analyze_coverage, format_coverage

    try:
        policy = load_policy(policy_file)
    except PolicyParseError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    report = analyze_coverage(policy)
    click.echo(format_coverage(report))
