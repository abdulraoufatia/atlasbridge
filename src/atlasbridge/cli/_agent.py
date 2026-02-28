"""atlasbridge agent — start and interact with the Expert Agent."""

from __future__ import annotations

import json
import sys

import click


@click.group("agent")
def agent_group() -> None:
    """Expert Agent — governance-specialised operational agent."""


@agent_group.command("start")
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai", "google"]),
    default=None,
    help="LLM provider to use (overrides config).",
)
@click.option("--model", default="", help="Model name (overrides config).")
@click.option("--policy", default="", help="Path to policy YAML file for tool governance.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Log decisions without sending to channel."
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON (for dashboard).")
@click.option(
    "--background",
    is_flag=True,
    default=False,
    help="Launch as a detached background process (used by dashboard).",
)
@click.option("--session-id", default="", hidden=True, help="Pre-created session ID (internal).")
def agent_start_cmd(
    provider: str | None,
    model: str,
    policy: str,
    dry_run: bool,
    as_json: bool,
    background: bool,
    session_id: str,
) -> None:
    """Start an Expert Agent session.

    The agent runs through the AtlasBridge runtime with full policy enforcement,
    SoR persistence, and audit logging.

    \b
    Examples:
      atlasbridge agent start
      atlasbridge agent start --provider anthropic --model claude-sonnet-4-5-20250514
      atlasbridge agent start --policy config/policies/strict.yaml
      atlasbridge agent start --background --json
    """
    import os
    import shutil
    import subprocess
    from pathlib import Path

    from rich.console import Console

    console = Console()

    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    try:
        config = load_config()
    except ConfigNotFoundError:
        if as_json:
            click.echo(
                json.dumps({"ok": False, "error": "Not configured. Run atlasbridge setup first."})
            )
        else:
            console.print("[red]Not configured.[/red] Run [cyan]atlasbridge setup[/cyan] first.")
        raise SystemExit(1) from None
    except ConfigError as exc:
        if as_json:
            click.echo(json.dumps({"ok": False, "error": str(exc)}))
        else:
            console.print(f"[red]Config error:[/red] {exc}")
        raise SystemExit(1) from exc

    provider_name = provider or config.chat.provider.name
    if not provider_name:
        err = "No LLM provider configured."
        if as_json:
            click.echo(json.dumps({"ok": False, "error": err}))
        else:
            console.print(
                f"[red]{err}[/red]\n"
                "Set one with:\n"
                "  [cyan]atlasbridge agent start --provider anthropic[/cyan]\n"
                "  [cyan]ATLASBRIDGE_LLM_PROVIDER=anthropic[/cyan]"
            )
        raise SystemExit(1)

    api_key = ""
    if config.chat.provider.api_key:
        api_key = config.chat.provider.api_key.get_secret_value()
    if not api_key:
        api_key = os.environ.get("ATLASBRIDGE_LLM_API_KEY", "")
    if not api_key:
        # Fall back to standard provider-specific env vars
        provider_env_keys = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        env_name = provider_env_keys.get(provider_name, "")
        if env_name:
            api_key = os.environ.get(env_name, "")
    if not api_key:
        err = (
            f"No API key for provider {provider_name!r}. "
            f"Set ATLASBRIDGE_LLM_API_KEY or configure [chat.provider] in config.toml."
        )
        if as_json:
            click.echo(json.dumps({"ok": False, "error": err}))
        else:
            console.print(f"[red]{err}[/red]")
        raise SystemExit(1)

    model_name = model or config.chat.provider.model

    # --background: pre-create session in DB, then launch a detached child
    if background:
        import uuid
        from pathlib import Path

        from atlasbridge.core.config import get_config_dir
        from atlasbridge.core.store.database import Database

        sid = str(uuid.uuid4())
        db_path = Path(get_config_dir()) / "atlasbridge.db"
        db = Database(db_path)
        db.connect()
        try:
            db.save_session(sid, f"agent:{provider_name}", ["agent"], label="Expert Agent")
        finally:
            db.close()

        atlas_bin = os.environ.get("ATLASBRIDGE_BIN") or shutil.which("atlasbridge")
        if atlas_bin:
            args = [atlas_bin, "agent", "start"]
        else:
            args = [sys.executable, "-m", "atlasbridge", "agent", "start"]
        args += ["--session-id", sid]
        if provider:
            args += ["--provider", provider_name]
        if model:
            args += ["--model", model]
        if policy:
            args += ["--policy", policy]
        if dry_run:
            args += ["--dry-run"]

        try:
            with open(os.devnull) as devnull_r, open(os.devnull, "w") as devnull_w:
                proc = subprocess.Popen(
                    args,
                    stdin=devnull_r,
                    stdout=devnull_w,
                    stderr=devnull_w,
                    close_fds=True,
                    start_new_session=True,
                )
            if as_json:
                click.echo(
                    json.dumps(
                        {
                            "ok": True,
                            "pid": proc.pid,
                            "session_id": sid,
                            "provider": provider_name,
                            "model": model_name,
                        }
                    )
                )
            else:
                console.print(
                    f"[green]Agent started in background[/green] (PID {proc.pid}, session {sid[:8]})"
                )
        except Exception as exc:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(exc)}))
            else:
                console.print(f"[red]Failed to start agent:[/red] {exc}")
            sys.exit(1)
        return

    # Foreground mode: run the agent directly
    daemon_config: dict = {
        "mode": "agent",
        "dry_run": dry_run,
        "data_dir": str(Path(config.database.path).parent) if config.database.path else "",
        "session_id": session_id or "",
        "chat": {
            "provider_name": provider_name,
            "api_key": api_key,
            "model": model_name,
            "tools_enabled": True,
            "max_history": config.chat.max_history_messages,
            "system_prompt": "",  # Agent builds its own
        },
        "channels": {},
    }

    if policy:
        daemon_config["policy_file"] = policy

    console.print(f"[bold]AtlasBridge Expert Agent[/bold] — {provider_name}")
    if model_name:
        console.print(f"Model: [cyan]{model_name}[/cyan]")
    console.print("Mode: [cyan]agent[/cyan] (governance-specialised)")
    console.print("Waiting for messages on your configured channel...\n")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    import asyncio

    from atlasbridge.core.daemon.manager import DaemonManager

    manager = DaemonManager(daemon_config)
    try:
        asyncio.run(manager.start())
    except KeyboardInterrupt:
        console.print("\n[dim]Agent session ended.[/dim]")


@agent_group.command("message")
@click.argument("session_id")
@click.argument("text")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON.")
def agent_message_cmd(session_id: str, text: str, as_json: bool) -> None:
    """Send a message to a running Expert Agent session."""
    from pathlib import Path

    from atlasbridge.core.config import get_config_dir
    from atlasbridge.core.store.database import Database

    db_path = Path(get_config_dir()) / "atlasbridge.db"
    if not db_path.exists():
        click.echo(
            json.dumps({"ok": False, "error": "Database not found"})
            if as_json
            else "Database not found",
            err=True,
        )
        sys.exit(1)

    db = Database(db_path)
    db.connect()
    try:
        session = db.get_session(session_id)
        if session is None:
            msg = f"Session not found: {session_id}"
            click.echo(json.dumps({"ok": False, "error": msg}) if as_json else msg, err=True)
            sys.exit(1)

        # Store the message as an agent turn for the dashboard to pick up
        import uuid

        turn_id = str(uuid.uuid4())
        turns = db.list_agent_turns(session_id, limit=1000)
        turn_number = len(turns) + 1

        # Find trace_id from existing turns
        trace_id = turns[0]["trace_id"] if turns else str(uuid.uuid4())

        db.save_agent_turn(
            turn_id=turn_id,
            session_id=session_id,
            trace_id=trace_id,
            turn_number=turn_number,
            role="user",
            content=text,
            state="intake",
        )

        result = {"ok": True, "turn_id": turn_id, "session_id": session_id}
        if as_json:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Message sent. Turn ID: {turn_id[:8]}")
    finally:
        db.close()


@agent_group.command("approve")
@click.argument("session_id")
@click.argument("plan_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON.")
def agent_approve_cmd(session_id: str, plan_id: str, as_json: bool) -> None:
    """Approve a gated plan in an Expert Agent session."""
    from pathlib import Path

    from atlasbridge.core.config import get_config_dir
    from atlasbridge.core.store.database import Database

    db_path = Path(get_config_dir()) / "atlasbridge.db"
    db = Database(db_path)
    db.connect()
    try:
        plan = db.get_agent_plan(plan_id)
        if plan is None:
            msg = f"Plan not found: {plan_id}"
            click.echo(json.dumps({"ok": False, "error": msg}) if as_json else msg, err=True)
            sys.exit(1)

        db.update_agent_plan(plan_id, status="approved", resolved_by="human")
        result = {"ok": True, "plan_id": plan_id, "status": "approved"}
        click.echo(json.dumps(result) if as_json else f"Plan {plan_id[:8]} approved.")
    finally:
        db.close()


@agent_group.command("deny")
@click.argument("session_id")
@click.argument("plan_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON.")
def agent_deny_cmd(session_id: str, plan_id: str, as_json: bool) -> None:
    """Deny a gated plan in an Expert Agent session."""
    from pathlib import Path

    from atlasbridge.core.config import get_config_dir
    from atlasbridge.core.store.database import Database

    db_path = Path(get_config_dir()) / "atlasbridge.db"
    db = Database(db_path)
    db.connect()
    try:
        plan = db.get_agent_plan(plan_id)
        if plan is None:
            msg = f"Plan not found: {plan_id}"
            click.echo(json.dumps({"ok": False, "error": msg}) if as_json else msg, err=True)
            sys.exit(1)

        db.update_agent_plan(plan_id, status="denied", resolved_by="human")
        result = {"ok": True, "plan_id": plan_id, "status": "denied"}
        click.echo(json.dumps(result) if as_json else f"Plan {plan_id[:8]} denied.")
    finally:
        db.close()


@agent_group.command("state")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON.")
def agent_state_cmd(session_id: str, as_json: bool) -> None:
    """Get the current state of an Expert Agent session."""
    from pathlib import Path

    from atlasbridge.core.config import get_config_dir
    from atlasbridge.core.store.database import Database

    db_path = Path(get_config_dir()) / "atlasbridge.db"
    db = Database(db_path)
    db.connect()
    try:
        session = db.get_session(session_id)
        if session is None:
            msg = f"Session not found: {session_id}"
            click.echo(json.dumps({"ok": False, "error": msg}) if as_json else msg, err=True)
            sys.exit(1)

        turns = db.list_agent_turns(session_id)
        plans = db.list_agent_plans(session_id, limit=1)
        # Derive state from latest records
        latest_turn = turns[-1] if turns else None
        latest_plan = plans[0] if plans else None

        state = "ready"
        if latest_plan and latest_plan["status"] == "proposed":
            state = "gate"
        elif latest_turn and latest_turn["state"] in ("intake", "plan", "execute"):
            state = latest_turn["state"]

        result = {
            "session_id": session_id,
            "session_status": session["status"],
            "agent_state": state,
            "total_turns": len(turns),
            "latest_turn_id": latest_turn["id"] if latest_turn else None,
            "latest_plan_id": latest_plan["id"] if latest_plan else None,
            "latest_plan_status": latest_plan["status"] if latest_plan else None,
        }

        if as_json:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Session: {session_id[:8]}")
            click.echo(f"Status:  {session['status']}")
            click.echo(f"Agent:   {state}")
            click.echo(f"Turns:   {len(turns)}")
            if latest_plan:
                click.echo(f"Plan:    {latest_plan['id'][:8]} ({latest_plan['status']})")
    finally:
        db.close()
