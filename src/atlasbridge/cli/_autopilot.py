"""
CLI commands: ``atlasbridge autopilot`` subcommands.

    autopilot enable        -- enable autopilot (set state to RUNNING)
    autopilot disable       -- disable autopilot (set state to PAUSED)
    autopilot status        -- show current state + active policy
    autopilot mode          -- set autonomy mode (off|assist|full)
    autopilot explain       -- show last N decisions from the trace
    autopilot history       -- show last N state transitions
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from atlasbridge.core.autopilot.engine import HISTORY_FILENAME, STATE_FILENAME, AutopilotState
from atlasbridge.core.autopilot.trace import TRACE_FILENAME, DecisionTrace
from atlasbridge.core.policy.parser import PolicyParseError, default_policy, load_policy


def _state_path(data_dir: Path) -> Path:
    return data_dir / STATE_FILENAME


def _trace_path(data_dir: Path) -> Path:
    return data_dir / TRACE_FILENAME


def _history_path(data_dir: Path) -> Path:
    return data_dir / HISTORY_FILENAME


def _read_state(data_dir: Path) -> AutopilotState:
    p = _state_path(data_dir)
    if not p.exists():
        return AutopilotState.RUNNING
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return AutopilotState(data.get("state", "running"))
    except (OSError, json.JSONDecodeError, ValueError):
        return AutopilotState.RUNNING


def _write_state(data_dir: Path, state: AutopilotState) -> None:
    p = _state_path(data_dir)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    p.write_text(json.dumps({"state": state.value}), encoding="utf-8")


@click.group("autopilot")
def autopilot_group() -> None:
    """Manage the AtlasBridge autopilot engine."""


@autopilot_group.command("enable")
@click.pass_context
def autopilot_enable(ctx: click.Context) -> None:
    """Enable the autopilot engine (resume from paused state)."""
    from atlasbridge.core.config import atlasbridge_dir

    data_dir = atlasbridge_dir()
    current = _read_state(data_dir)
    if current == AutopilotState.RUNNING:
        click.echo("Autopilot is already running.")
        return
    if current == AutopilotState.STOPPED:
        click.echo("Autopilot is stopped (daemon not running). Start the daemon first.", err=True)
        sys.exit(1)
    _write_state(data_dir, AutopilotState.RUNNING)
    click.echo("Autopilot enabled (state: running).")


@autopilot_group.command("disable")
@click.pass_context
def autopilot_disable(ctx: click.Context) -> None:
    """Pause the autopilot engine — all prompts will be forwarded to you."""
    from atlasbridge.core.config import atlasbridge_dir

    data_dir = atlasbridge_dir()
    current = _read_state(data_dir)
    if current == AutopilotState.PAUSED:
        click.echo("Autopilot is already paused.")
        return
    if current == AutopilotState.STOPPED:
        click.echo("Autopilot is stopped (daemon not running).", err=True)
        sys.exit(1)
    _write_state(data_dir, AutopilotState.PAUSED)
    click.echo("Autopilot paused — all prompts will be forwarded to you.")


@autopilot_group.command("status")
def autopilot_status() -> None:
    """Show autopilot state, active policy, and recent decisions."""
    from atlasbridge.core.config import atlasbridge_dir

    data_dir = atlasbridge_dir()
    state = _read_state(data_dir)

    state_emoji = {"running": "▶", "paused": "⏸", "stopped": "■"}.get(state.value, "?")
    click.echo(f"  State:        {state_emoji}  {state.value.upper()}")

    # Policy info
    policy_path = data_dir / "policy.yaml"
    if policy_path.exists():
        try:
            policy = load_policy(policy_path)
            click.echo(f"  Policy:       {policy.name!r}  ({len(policy.rules)} rules)")
            click.echo(f"  Mode:         {policy.autonomy_mode.value}")
            click.echo(f"  Policy hash:  {policy.content_hash()}")
        except PolicyParseError as exc:
            click.echo(f"  Policy:       INVALID — {exc}", err=True)
    else:
        p = default_policy()
        click.echo(f"  Policy:       {p.name!r} (built-in safe default — no policy.yaml found)")
        click.echo(f"  Mode:         {p.autonomy_mode.value}")

    # Recent decisions
    trace = DecisionTrace(_trace_path(data_dir))
    recent = trace.tail(5)
    if recent:
        click.echo(f"\n  Last {len(recent)} decision(s):")
        for entry in recent:
            click.echo(
                f"    [{entry.get('timestamp', '?')[:19]}] "
                f"rule={entry.get('matched_rule_id') or '(none)':<25}  "
                f"action={entry.get('action_type', '?'):<14}  "
                f"type={entry.get('prompt_type', '?')}"
            )
    else:
        click.echo("\n  No decisions recorded yet.")


@autopilot_group.command("mode")
@click.argument("mode", type=click.Choice(["off", "assist", "full"], case_sensitive=False))
def autopilot_mode(mode: str) -> None:
    """
    Set the autonomy mode in the active policy file.

    MODE must be one of: off, assist, full.

    Requires a policy.yaml file in the AtlasBridge data directory.
    Edit the YAML directly for full control.
    """
    from atlasbridge.core.config import atlasbridge_dir

    data_dir = atlasbridge_dir()
    policy_path = data_dir / "policy.yaml"
    if not policy_path.exists():
        click.echo(
            f"No policy.yaml found at {policy_path}.\n"
            "Create one first or copy from: atlasbridge policy validate --help",
            err=True,
        )
        sys.exit(1)

    # Simple in-place YAML field update (avoid full re-serialise to preserve comments)
    try:
        text = policy_path.read_text(encoding="utf-8")
    except OSError as exc:
        click.echo(f"Cannot read policy file: {exc}", err=True)
        sys.exit(1)

    import re

    updated = re.sub(
        r"^(autonomy_mode\s*:\s*).*$",
        rf"\g<1>{mode}",
        text,
        flags=re.MULTILINE,
    )
    if updated == text:
        # Field not found — append
        updated = text.rstrip() + f"\nautonomy_mode: {mode}\n"

    try:
        policy_path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        click.echo(f"Cannot write policy file: {exc}", err=True)
        sys.exit(1)

    # Validate after write
    try:
        load_policy(policy_path)
    except PolicyParseError as exc:
        click.echo(f"Policy is now invalid: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Autonomy mode set to {mode!r} in {policy_path}")


@autopilot_group.command("explain")
@click.option("-n", "--last", default=20, show_default=True, help="Number of decisions to show.")
@click.option("--json", "as_json", is_flag=True, help="Output as raw JSONL.")
def autopilot_explain(last: int, as_json: bool) -> None:
    """Show the last N autopilot decisions from the decision trace."""
    from atlasbridge.core.config import atlasbridge_dir

    data_dir = atlasbridge_dir()
    trace = DecisionTrace(_trace_path(data_dir))
    entries = trace.tail(last)

    if not entries:
        click.echo("No autopilot decisions recorded yet.")
        return

    if as_json:
        for entry in entries:
            click.echo(json.dumps(entry, ensure_ascii=False))
        return

    click.echo(f"Last {len(entries)} autopilot decision(s):\n")
    for entry in entries:
        ts = entry.get("timestamp", "?")[:19]
        rule = entry.get("matched_rule_id") or "(none)"
        action = entry.get("action_type", "?")
        val = entry.get("action_value", "")
        ptype = entry.get("prompt_type", "?")
        conf = entry.get("confidence", "?")
        expl = entry.get("explanation", "")
        click.echo(f"  [{ts}]  {action:<14}  rule={rule:<30}  type={ptype}  conf={conf}")
        if val:
            click.echo(f"           value={val!r}")
        if expl:
            click.echo(f"           {expl}")
        click.echo("")


@autopilot_group.command("history")
@click.option("-n", "--last", default=20, show_default=True, help="Number of transitions to show.")
@click.option("--json", "as_json", is_flag=True, help="Output as raw JSONL.")
def autopilot_history(last: int, as_json: bool) -> None:
    """Show the last N autopilot state transitions (pause/resume/stop history)."""
    from atlasbridge.core.config import atlasbridge_dir

    data_dir = atlasbridge_dir()
    path = _history_path(data_dir)

    if not path.exists():
        click.echo("No autopilot state transitions recorded yet.")
        return

    lines: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        click.echo(f"Cannot read history file: {exc}", err=True)
        sys.exit(1)

    entries: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    recent = entries[-last:] if len(entries) > last else entries

    if not recent:
        click.echo("No autopilot state transitions recorded yet.")
        return

    if as_json:
        for entry in recent:
            click.echo(json.dumps(entry, ensure_ascii=False))
        return

    click.echo(f"Last {len(recent)} state transition(s):\n")
    for entry in recent:
        ts = entry.get("timestamp", "?")[:19]
        from_s = entry.get("from_state", "?")
        to_s = entry.get("to_state", "?")
        by = entry.get("triggered_by", "unknown")
        click.echo(f"  [{ts}]  {from_s:<8} → {to_s:<8}  triggered_by={by}")


# ---------------------------------------------------------------------------
# pause / resume (convenience aliases)
# ---------------------------------------------------------------------------


@click.command("pause")
@click.option(
    "--all",
    "pause_all",
    is_flag=True,
    default=False,
    help="Pause autopilot across all active sessions (shows session count).",
)
def pause_cmd(pause_all: bool) -> None:
    """Pause the autopilot — all prompts will be forwarded to you."""
    autopilot_disable.main(standalone_mode=False)

    if pause_all:
        try:
            from atlasbridge.core.config import atlasbridge_dir
            from atlasbridge.core.constants import DB_FILENAME
            from atlasbridge.core.store.database import Database

            data_dir = atlasbridge_dir()
            db_path = data_dir / DB_FILENAME
            if db_path.exists():
                db = Database(db_path)
                db.connect()
                try:
                    active_sessions = db.list_active_sessions()
                    count = len(active_sessions)
                finally:
                    db.close()
                click.echo(f"Active sessions affected: {count}")
            else:
                click.echo("No database found — no active sessions.")
        except Exception:  # noqa: BLE001
            pass  # DB query is best-effort; pause itself already succeeded


@click.command("resume")
def resume_cmd() -> None:
    """Resume the autopilot after a pause."""
    autopilot_enable.main(standalone_mode=False)
