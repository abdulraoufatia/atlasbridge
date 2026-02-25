"""
CLI command: ``atlasbridge risk assess``.

Deterministic risk classification for a given context.
"""

from __future__ import annotations

import json

import click

from atlasbridge.core.risk import RiskClassifier, RiskInput


@click.group("risk")
def risk_group() -> None:
    """Deterministic risk classification."""


@risk_group.command("assess")
@click.option(
    "--prompt-type",
    "prompt_type",
    default="yes_no",
    show_default=True,
    help="Prompt type: yes_no, confirm_enter, multiple_choice, free_text.",
)
@click.option(
    "--action",
    "action_type",
    default="auto_reply",
    show_default=True,
    help="Action type: auto_reply, require_human, deny, notify_only.",
)
@click.option(
    "--confidence",
    default="high",
    show_default=True,
    help="Confidence level: high, medium, low.",
)
@click.option("--branch", default="", help="Git branch name.")
@click.option("--ci-status", "ci_status", default="", help="CI status: passing, failing, unknown.")
@click.option(
    "--file-scope",
    "file_scope",
    default="",
    help="File scope: general, config, infrastructure, secrets.",
)
@click.option(
    "--command",
    "command_pattern",
    default="",
    help="Command text for destructive pattern detection.",
)
@click.option("--environment", default="", help="Environment: dev, staging, production.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
def risk_assess(
    prompt_type: str,
    action_type: str,
    confidence: str,
    branch: str,
    ci_status: str,
    file_scope: str,
    command_pattern: str,
    environment: str,
    output_json: bool,
) -> None:
    """
    Assess risk for a given context.

    Computes a deterministic risk score (0-100) with traceable factors.

    Example::

        atlasbridge risk assess --action auto_reply --branch main --ci-status failing
        atlasbridge risk assess --prompt-type free_text --confidence low --json
    """
    inp = RiskInput(
        prompt_type=prompt_type,
        action_type=action_type,
        confidence=confidence,
        branch=branch,
        ci_status=ci_status,
        file_scope=file_scope,
        command_pattern=command_pattern,
        environment=environment,
    )

    assessment = RiskClassifier.classify(inp)

    if output_json:
        click.echo(json.dumps(assessment.to_dict(), indent=2))
    else:
        click.echo(f"Risk Score:    {assessment.score}/100")
        click.echo(f"Category:      {assessment.category.value.upper()}")
        click.echo(f"Input Hash:    {assessment.input_hash}")
        click.echo("")
        if assessment.factors:
            click.echo("Factors:")
            for f in assessment.factors:
                click.echo(f"  - {f.name} (+{f.weight}): {f.description}")
        else:
            click.echo("Factors:       (none)")
        click.echo("")
        click.echo(f"Explanation:   {assessment.explanation}")
