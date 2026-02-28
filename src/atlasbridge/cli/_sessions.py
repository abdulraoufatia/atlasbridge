"""atlasbridge sessions — list and inspect sessions."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("sessions", invoke_without_command=True)
@click.pass_context
def sessions_group(ctx: click.Context) -> None:
    """Session lifecycle commands."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(sessions_list)


@sessions_group.command("list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option("--all", "show_all", is_flag=True, default=False, help="Include completed sessions")
@click.option("--limit", default=50, show_default=True, help="Max sessions to show")
def sessions_list(as_json: bool = False, show_all: bool = False, limit: int = 50) -> None:
    """List active and recent sessions."""
    cmd_sessions_list(as_json=as_json, show_all=show_all, limit=limit, console=console)


@sessions_group.command("show")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def sessions_show(session_id: str, as_json: bool = False) -> None:
    """Show details for a specific session."""
    cmd_sessions_show(session_id=session_id, as_json=as_json, console=console)


@sessions_group.command("trace")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option(
    "--type",
    "event_type",
    default=None,
    help="Filter by event type (e.g. prompt_detected, response_injected).",
)
def sessions_trace(session_id: str, as_json: bool = False, event_type: str | None = None) -> None:
    """Show chronological governance trace for a session."""
    cmd_sessions_trace(
        session_id=session_id, as_json=as_json, event_type=event_type, console=console
    )


def _open_db():
    """Open the AtlasBridge database if it exists, or return None."""
    from atlasbridge.core.config import load_config
    from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError

    try:
        config = load_config()
        db_path = config.db_path
        if not db_path.exists():
            return None
        from atlasbridge.core.store.database import Database

        db = Database(db_path)
        db.connect()
        return db
    except (ConfigNotFoundError, ConfigError):
        return None


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row else {}


# ------------------------------------------------------------------
# sessions list
# ------------------------------------------------------------------

_STATUS_STYLE = {
    "starting": "yellow",
    "running": "green",
    "awaiting_reply": "bold cyan",
    "completed": "dim",
    "crashed": "red",
    "canceled": "dim red",
}


def cmd_sessions_list(
    *,
    as_json: bool,
    show_all: bool,
    limit: int,
    console: Console,
) -> None:
    """List sessions from the database."""
    db = _open_db()
    if db is None:
        if as_json:
            print("[]")
        else:
            console.print("[bold]Active Sessions[/bold]\n")
            console.print("  [dim]No active sessions.[/dim]")
            console.print("\nRun [cyan]atlasbridge run <tool>[/cyan] to start a session.")
        return

    try:
        if show_all:
            rows = db.list_sessions(limit=limit)
        else:
            rows = db.list_active_sessions()

        if as_json:
            data = [_row_to_dict(r) for r in rows]
            print(json.dumps(data, indent=2, default=str))
            return

        if not rows:
            console.print("[bold]Active Sessions[/bold]\n")
            console.print("  [dim]No active sessions.[/dim]")
            console.print("\nRun [cyan]atlasbridge run <tool>[/cyan] to start a session.")
            return

        table = Table(title="Sessions", show_lines=False)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Tool", style="bold")
        table.add_column("Status")
        table.add_column("PID", justify="right")
        table.add_column("Started", style="dim")
        table.add_column("Label")

        for row in rows:
            sid = row["id"][:8]
            tool = row["tool"] or ""
            status = row["status"] or ""
            pid = str(row["pid"]) if row["pid"] else "-"
            started = (row["started_at"] or "")[:19]
            label = row["label"] or ""
            style = _STATUS_STYLE.get(status, "")
            table.add_row(sid, tool, f"[{style}]{status}[/{style}]", pid, started, label)

        console.print(table)
    finally:
        db.close()


# ------------------------------------------------------------------
# sessions show
# ------------------------------------------------------------------


def cmd_sessions_show(
    *,
    session_id: str,
    as_json: bool,
    console: Console,
) -> None:
    """Show detailed information for a single session."""
    db = _open_db()
    if db is None:
        console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        # Support short IDs — find matching session
        row = db.get_session(session_id)
        if row is None:
            # Try prefix match
            all_rows = db.list_sessions(limit=500)
            matches = [r for r in all_rows if r["id"].startswith(session_id)]
            if len(matches) == 1:
                row = db.get_session(matches[0]["id"])
            elif len(matches) > 1:
                console.print(
                    f"[yellow]Ambiguous ID '{session_id}' matches "
                    f"{len(matches)} sessions. Use more characters.[/yellow]"
                )
                sys.exit(1)

        if row is None:
            console.print(f"[red]Session not found: {session_id}[/red]")
            sys.exit(1)

        session = _row_to_dict(row)
        full_id = session["id"]
        prompts = [_row_to_dict(p) for p in db.list_prompts_for_session(full_id)]
        prompt_count = len(prompts)

        if as_json:
            session["prompts"] = prompts
            print(json.dumps(session, indent=2, default=str))
            return

        # Rich formatted output
        status = session.get("status", "")
        style = _STATUS_STYLE.get(status, "")

        console.print(f"\n[bold]Session {full_id[:8]}[/bold]")
        console.print(f"  Full ID:   {full_id}")
        console.print(f"  Tool:      {session.get('tool', '-')}")
        console.print(f"  Status:    [{style}]{status}[/{style}]")
        console.print(f"  PID:       {session.get('pid', '-')}")
        console.print(f"  CWD:       {session.get('cwd', '-')}")
        console.print(f"  Label:     {session.get('label', '-') or '-'}")
        console.print(f"  Command:   {session.get('command', '-')}")
        console.print(f"  Started:   {session.get('started_at', '-')}")
        ended = session.get("ended_at") or "-"
        console.print(f"  Ended:     {ended}")
        exit_code = session.get("exit_code")
        console.print(f"  Exit code: {exit_code if exit_code is not None else '-'}")
        console.print(f"  Prompts:   {prompt_count}")

        if prompts:
            console.print("\n[bold]Prompts[/bold]")
            prompt_table = Table(show_lines=False)
            prompt_table.add_column("ID", style="cyan", no_wrap=True)
            prompt_table.add_column("Type")
            prompt_table.add_column("Confidence")
            prompt_table.add_column("Status")
            prompt_table.add_column("Created", style="dim")

            for p in prompts:
                pid = p.get("id", "")[:8]
                ptype = p.get("prompt_type", "")
                conf = p.get("confidence", "")
                pstatus = p.get("status", "")
                created = (p.get("created_at", "") or "")[:19]
                prompt_table.add_row(pid, ptype, conf, pstatus, created)

            console.print(prompt_table)
    finally:
        db.close()


# ------------------------------------------------------------------
# sessions trace
# ------------------------------------------------------------------


def cmd_sessions_trace(
    *,
    session_id: str,
    as_json: bool,
    event_type: str | None,
    console: Console,
) -> None:
    """Render the governance trace timeline for a session."""
    from atlasbridge.core.session.trace import (
        build_session_trace,
        format_trace,
        trace_to_json,
    )

    db = _open_db()
    if db is None:
        console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        # Support short IDs via prefix match
        full_id = _resolve_session_id(db, session_id)
        if full_id is None:
            console.print(f"[red]Session not found: {session_id}[/red]")
            sys.exit(1)

        trace = build_session_trace(db, full_id)
        if trace is None:
            console.print(f"[red]Session not found: {session_id}[/red]")
            sys.exit(1)

        # Apply event type filter
        if event_type:
            trace.events = [e for e in trace.events if e.event_type == event_type]
            trace.event_count = len(trace.events)

        if as_json:
            print(trace_to_json(trace))
        else:
            console.print(format_trace(trace))
    finally:
        db.close()


def _resolve_session_id(db, session_id: str) -> str | None:
    """Resolve a short or full session ID to a full session ID."""
    row = db.get_session(session_id)
    if row is not None:
        return row["id"]
    # Try prefix match
    all_rows = db.list_sessions(limit=500)
    matches = [r for r in all_rows if r["id"].startswith(session_id)]
    if len(matches) == 1:
        return matches[0]["id"]
    return None


# ------------------------------------------------------------------
# sessions start (background launch)
# ------------------------------------------------------------------


_VALID_MODES = ("off", "assist", "full")
_VALID_ADAPTERS = ("claude", "openai", "gemini", "claude-code")


@sessions_group.command("start")
@click.option(
    "--adapter",
    default="claude",
    type=click.Choice(list(_VALID_ADAPTERS), case_sensitive=False),
    show_default=True,
    help="Agent adapter to use.",
)
@click.option(
    "--mode",
    default="off",
    type=click.Choice(list(_VALID_MODES), case_sensitive=False),
    show_default=True,
    help="Autonomy mode (off / assist / full).",
)
@click.option("--cwd", default="", help="Working directory for the session.")
@click.option("--profile", "profile_name", default="", help="Agent profile name.")
@click.option("--label", "session_label", default="", help="Human-readable session label.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output session info as JSON.")
@click.option(
    "--custom-command",
    "custom_command",
    default="",
    help="Custom command to run when adapter=custom (e.g. 'cursor', 'aider --model gpt-4o').",
)
def sessions_start(
    adapter: str,
    mode: str,
    cwd: str,
    profile_name: str,
    session_label: str,
    as_json: bool,
    custom_command: str,
) -> None:
    """Start a new session in the background.

    Launches ``atlasbridge run`` as a detached child process so the dashboard
    can start sessions without blocking.  The session ID is written to stdout
    so callers can poll the sessions list.

    To monitor any CLI tool, use ``--adapter custom --custom-command <cmd>``.
    The generic adapter works with any interactive CLI.
    """
    import shutil

    # Prefer ATLASBRIDGE_BIN (set by dashboard/operator.ts) then PATH lookup.
    # Fall back to running as a Python module (correct multi-arg form, no spaces).
    atlas_bin = os.environ.get("ATLASBRIDGE_BIN") or shutil.which("atlasbridge")

    # When --custom-command is provided, use it as the tool name so AtlasBridge
    # runs that exact command in a PTY. The generic adapter handles any tool.
    tool_to_run = custom_command.split()[0] if custom_command else adapter
    extra_tool_args = custom_command.split()[1:] if custom_command else []

    if atlas_bin:
        args = [atlas_bin, "run", tool_to_run, "--mode", mode] + extra_tool_args
    else:
        args = [
            sys.executable,
            "-m",
            "atlasbridge",
            "run",
            tool_to_run,
            "--mode",
            mode,
        ] + extra_tool_args

    if cwd:
        args += ["--cwd", cwd]
    if profile_name:
        args += ["--profile", profile_name]
    if session_label:
        args += ["--session-label", session_label]

    try:
        # Detach: new process group, stdin/out/err redirected to /dev/null
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
            print(json.dumps({"ok": True, "pid": proc.pid, "adapter": adapter, "mode": mode}))
        else:
            console.print(f"[green]Session started[/green] (PID {proc.pid})")
            console.print(f"  Adapter: {adapter}  Mode: {mode}")
            if cwd:
                console.print(f"  CWD:     {cwd}")
            console.print("\nRun [cyan]atlasbridge sessions list[/cyan] to see it appear.")

    except Exception as exc:
        if as_json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            console.print(f"[red]Failed to start session:[/red] {exc}")
        sys.exit(1)


# ------------------------------------------------------------------
# sessions reply
# ------------------------------------------------------------------


@sessions_group.command("reply")
@click.argument("session_id")
@click.argument("prompt_id")
@click.argument("value")
def sessions_reply(session_id: str, prompt_id: str, value: str) -> None:
    """Inject a reply for a pending prompt in an active session."""
    db = _open_db()
    if db is None:
        print(json.dumps({"ok": False, "error": "Database not found"}))
        sys.exit(1)

    try:
        # Resolve short session ID
        full_session_id = _resolve_session_id(db, session_id)
        if full_session_id is None:
            print(json.dumps({"ok": False, "error": f"Session not found: {session_id}"}))
            sys.exit(1)

        # Resolve short prompt ID (prefix match against pending prompts)
        prompt = db.get_prompt(prompt_id)
        if prompt is None:
            pending = db.list_pending_prompts(full_session_id)
            matches = [p for p in pending if p["id"].startswith(prompt_id)]
            if len(matches) == 1:
                prompt = db.get_prompt(matches[0]["id"])
            elif len(matches) > 1:
                print(json.dumps({"ok": False, "error": f"Ambiguous prompt ID: {prompt_id}"}))
                sys.exit(1)

        if prompt is None:
            print(json.dumps({"ok": False, "error": f"Prompt not found: {prompt_id}"}))
            sys.exit(1)

        if prompt["status"] != "awaiting_reply":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"Prompt is not awaiting reply (status: {prompt['status']})",
                    }
                )
            )
            sys.exit(1)

        if prompt["session_id"] != full_session_id:
            print(json.dumps({"ok": False, "error": "Prompt does not belong to this session"}))
            sys.exit(1)

        nonce = prompt["nonce"]
        full_prompt_id = prompt["id"]

        rows_updated = db.decide_prompt(
            prompt_id=full_prompt_id,
            new_status="reply_received",
            channel_identity="dashboard",
            response_normalized=value,
            nonce=nonce,
        )

        if rows_updated == 0:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "Prompt could not be claimed (expired or already resolved)",
                    }
                )
            )
            sys.exit(1)

        print(json.dumps({"ok": True, "prompt_id": full_prompt_id, "session_id": full_session_id}))

    finally:
        db.close()


# ------------------------------------------------------------------
# sessions message
# ------------------------------------------------------------------


@sessions_group.command("message")
@click.argument("session_id")
@click.argument("text")
def sessions_message(session_id: str, text: str) -> None:
    """Send a free-text message to a running session's agent."""
    db = _open_db()
    if db is None:
        print(json.dumps({"ok": False, "error": "Database not found"}))
        sys.exit(1)

    try:
        full_session_id = _resolve_session_id(db, session_id)
        if full_session_id is None:
            print(json.dumps({"ok": False, "error": f"Session not found: {session_id}"}))
            sys.exit(1)

        row = db.get_session(full_session_id)
        if row is None or row["status"] not in ("running", "starting", "awaiting_reply"):
            print(json.dumps({"ok": False, "error": "Session is not running"}))
            sys.exit(1)

        directive_id = db.insert_operator_directive(full_session_id, text)
        print(json.dumps({"ok": True, "directive_id": directive_id, "session_id": full_session_id}))
    finally:
        db.close()


# ------------------------------------------------------------------
# sessions stop
# ------------------------------------------------------------------


@sessions_group.command("stop")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output result as JSON.")
def sessions_stop(session_id: str, as_json: bool = False) -> None:
    """Stop a running session by sending SIGTERM to its process."""
    db = _open_db()
    if db is None:
        if as_json:
            print(json.dumps({"ok": False, "error": "Database not found"}))
        else:
            console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        full_id = _resolve_session_id(db, session_id)
        if full_id is None:
            if as_json:
                print(json.dumps({"ok": False, "error": f"Session not found: {session_id}"}))
            else:
                console.print(f"[red]Session not found:[/red] {session_id}")
            sys.exit(1)

        row = db.get_session(full_id)
        if row is None:
            if as_json:
                print(json.dumps({"ok": False, "error": "Session not found"}))
            else:
                console.print(f"[red]Session not found:[/red] {session_id}")
            sys.exit(1)

        pid = row["pid"]
        status = row["status"]

        if status in ("completed", "crashed", "canceled"):
            if as_json:
                print(json.dumps({"ok": False, "error": f"Session already {status}"}))
            else:
                console.print(f"[yellow]Session already {status}.[/yellow]")
            return

        if not pid:
            # No PID means the session never fully started — mark it canceled.
            db.update_session(full_id, status="canceled")
            if as_json:
                print(json.dumps({"ok": True, "session_id": full_id, "action": "canceled"}))
            else:
                console.print(
                    f"[yellow]No PID recorded — marked session {full_id[:8]} as canceled.[/yellow]"
                )
            return

        try:
            os.kill(pid, signal.SIGTERM)
            # Also update DB directly — the daemon's finally block may not run
            # if the parent process is killed or crashes.
            db.update_session(full_id, status="canceled")
            if as_json:
                print(
                    json.dumps({"ok": True, "session_id": full_id, "pid": pid, "signal": "SIGTERM"})
                )
            else:
                console.print(f"[green]SIGTERM sent[/green] to PID {pid} (session {full_id[:8]})")
        except ProcessLookupError:
            # Process already gone — mark as canceled
            db.update_session(full_id, status="canceled")
            if as_json:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "session_id": full_id,
                            "action": "canceled",
                            "note": f"Process {pid} not found (already stopped)",
                        }
                    )
                )
            else:
                console.print(
                    f"[yellow]Process {pid} not found — marked session as canceled.[/yellow]"
                )
        except PermissionError:
            if as_json:
                print(json.dumps({"ok": False, "error": f"Permission denied to stop PID {pid}"}))
            else:
                console.print(f"[red]Permission denied:[/red] cannot stop PID {pid}")
            sys.exit(1)

    finally:
        db.close()


# ------------------------------------------------------------------
# sessions pause
# ------------------------------------------------------------------


@sessions_group.command("pause")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output result as JSON.")
def sessions_pause(session_id: str, as_json: bool = False) -> None:
    """Pause a running session by sending SIGSTOP to its process."""
    db = _open_db()
    if db is None:
        if as_json:
            print(json.dumps({"ok": False, "error": "Database not found"}))
        else:
            console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        full_id = _resolve_session_id(db, session_id)
        if full_id is None:
            if as_json:
                print(json.dumps({"ok": False, "error": f"Session not found: {session_id}"}))
            else:
                console.print(f"[red]Session not found:[/red] {session_id}")
            sys.exit(1)

        row = db.get_session(full_id)
        if row is None:
            if as_json:
                print(json.dumps({"ok": False, "error": "Session not found"}))
            else:
                console.print(f"[red]Session not found:[/red] {session_id}")
            sys.exit(1)

        pid = row["pid"]
        status = row["status"]

        if status not in ("running", "awaiting_reply"):
            if as_json:
                print(
                    json.dumps({"ok": False, "error": f"Cannot pause session in '{status}' state"})
                )
            else:
                console.print(f"[yellow]Cannot pause — session is {status}.[/yellow]")
            return

        if not pid:
            if as_json:
                print(json.dumps({"ok": False, "error": "No PID recorded for session"}))
            else:
                console.print("[red]No PID recorded for this session.[/red]")
            sys.exit(1)

        try:
            os.kill(pid, signal.SIGSTOP)
            db.update_session(full_id, status="paused")
            if as_json:
                print(
                    json.dumps({"ok": True, "session_id": full_id, "pid": pid, "signal": "SIGSTOP"})
                )
            else:
                console.print(
                    f"[green]SIGSTOP sent[/green] to PID {pid} (session {full_id[:8]}) — paused"
                )
        except ProcessLookupError:
            if as_json:
                print(json.dumps({"ok": False, "error": f"Process {pid} not found"}))
            else:
                console.print(f"[yellow]Process {pid} not found.[/yellow]")
        except PermissionError:
            if as_json:
                print(json.dumps({"ok": False, "error": f"Permission denied to pause PID {pid}"}))
            else:
                console.print(f"[red]Permission denied:[/red] cannot pause PID {pid}")
            sys.exit(1)

    finally:
        db.close()


# ------------------------------------------------------------------
# sessions resume
# ------------------------------------------------------------------


@sessions_group.command("resume")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output result as JSON.")
def sessions_resume(session_id: str, as_json: bool = False) -> None:
    """Resume a paused session by sending SIGCONT to its process."""
    db = _open_db()
    if db is None:
        if as_json:
            print(json.dumps({"ok": False, "error": "Database not found"}))
        else:
            console.print("[red]No database found.[/red]")
        sys.exit(1)

    try:
        full_id = _resolve_session_id(db, session_id)
        if full_id is None:
            if as_json:
                print(json.dumps({"ok": False, "error": f"Session not found: {session_id}"}))
            else:
                console.print(f"[red]Session not found:[/red] {session_id}")
            sys.exit(1)

        row = db.get_session(full_id)
        if row is None:
            if as_json:
                print(json.dumps({"ok": False, "error": "Session not found"}))
            else:
                console.print(f"[red]Session not found:[/red] {session_id}")
            sys.exit(1)

        pid = row["pid"]
        status = row["status"]

        if status != "paused":
            if as_json:
                print(
                    json.dumps({"ok": False, "error": f"Session is not paused (status: {status})"})
                )
            else:
                console.print(f"[yellow]Session is not paused — status is {status}.[/yellow]")
            return

        if not pid:
            if as_json:
                print(json.dumps({"ok": False, "error": "No PID recorded for session"}))
            else:
                console.print("[red]No PID recorded for this session.[/red]")
            sys.exit(1)

        try:
            os.kill(pid, signal.SIGCONT)
            db.update_session(full_id, status="running")
            if as_json:
                print(
                    json.dumps({"ok": True, "session_id": full_id, "pid": pid, "signal": "SIGCONT"})
                )
            else:
                console.print(
                    f"[green]SIGCONT sent[/green] to PID {pid} (session {full_id[:8]}) — resumed"
                )
        except ProcessLookupError:
            if as_json:
                print(json.dumps({"ok": False, "error": f"Process {pid} not found"}))
            else:
                console.print(f"[yellow]Process {pid} not found.[/yellow]")
        except PermissionError:
            if as_json:
                print(json.dumps({"ok": False, "error": f"Permission denied to resume PID {pid}"}))
            else:
                console.print(f"[red]Permission denied:[/red] cannot resume PID {pid}")
            sys.exit(1)

    finally:
        db.close()
