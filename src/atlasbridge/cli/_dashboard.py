"""CLI commands for the local dashboard."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
from pathlib import Path

import click


@click.group("dashboard")
def dashboard_group() -> None:
    """Local read-only governance dashboard."""


# ---------------------------------------------------------------------------
# Node.js dashboard (default)
# ---------------------------------------------------------------------------


def _find_dashboard_dir() -> Path | None:
    """Locate the dashboard directory (repo, CWD, or bundled+runtime).

    Returns the directory from which the Node.js dashboard can be started,
    or None if no dashboard is available.
    """
    # 1. Repo development: src/atlasbridge/cli/_dashboard.py → repo-root/dashboard/
    pkg_dir = Path(__file__).resolve().parent.parent.parent.parent
    candidate = pkg_dir / "dashboard"
    if candidate.is_dir() and (candidate / "package.json").exists():
        return candidate

    # 2. CWD fallback (user is in the repo root)
    cwd_candidate = Path.cwd() / "dashboard"
    if cwd_candidate.is_dir() and (cwd_candidate / "package.json").exists():
        return cwd_candidate

    # 3. Bundled dashboard (pip install) → set up runtime directory
    bundled = Path(__file__).resolve().parent.parent / "_dashboard_dist"
    if bundled.is_dir() and (bundled / "index.cjs").exists():
        return _setup_dashboard_runtime(bundled)

    return None


def _setup_dashboard_runtime(bundled_dir: Path) -> Path | None:
    """Set up a writable runtime directory from the bundled dashboard dist.

    Copies the bundled dist files to the config directory and installs
    the required Node.js native dependency (better-sqlite3) on first run.
    """
    from atlasbridge.core.config import atlasbridge_dir

    runtime_dir = atlasbridge_dir() / "dashboard-runtime"
    marker = runtime_dir / ".version"

    # Read bundled version (file size of index.cjs as a simple fingerprint)
    bundled_entry = bundled_dir / "index.cjs"
    bundled_fingerprint = str(bundled_entry.stat().st_size)

    # Check if runtime is already set up and current
    if (
        marker.exists()
        and marker.read_text(encoding="utf-8").strip() == bundled_fingerprint
        and (runtime_dir / "index.cjs").exists()
        and (runtime_dir / "node_modules").is_dir()
    ):
        return runtime_dir

    # Set up or update runtime directory
    click.echo("Setting up dashboard runtime (first run)...")
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Copy bundled files
    for item in bundled_dir.iterdir():
        dest = runtime_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Install better-sqlite3 (native Node.js addon required by the dashboard)
    npm = shutil.which("npm")
    if npm is None:
        click.echo(
            "Error: npm is required to set up the dashboard but was not found.\n"
            "Install Node.js (v18+) from https://nodejs.org",
            err=True,
        )
        return None

    click.echo("Installing dashboard dependencies...")
    result = subprocess.run(
        [npm, "install", "--production", "better-sqlite3"],
        cwd=str(runtime_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(
            f"Error: Failed to install dashboard dependencies.\n{result.stderr}",
            err=True,
        )
        return None

    # Write version marker
    marker.write_text(bundled_fingerprint, encoding="utf-8")
    click.echo("Dashboard runtime ready.")
    return runtime_dir


def _node_available() -> bool:
    return shutil.which("node") is not None


def _npx_available() -> bool:
    return shutil.which("npx") is not None


def _start_node_dashboard(host: str, port: int, no_browser: bool, dashboard_dir: Path) -> None:
    """Start the Node.js TypeScript dashboard."""
    from atlasbridge.core.autopilot.trace import TRACE_FILENAME
    from atlasbridge.core.config import atlasbridge_dir
    from atlasbridge.core.constants import DB_FILENAME

    config_dir = atlasbridge_dir()

    env = {
        **os.environ,
        "HOST": host,
        "PORT": str(port),
        "NODE_ENV": "production",
        "ATLASBRIDGE_DB_PATH": str(config_dir / DB_FILENAME),
        "ATLASBRIDGE_TRACE_PATH": str(config_dir / TRACE_FILENAME),
        "ATLASBRIDGE_CONFIG": str(config_dir),
    }

    # Prefer pre-built dist, fall back to dev mode via npx tsx
    # Bundled runtime: index.cjs is directly in dashboard_dir
    bundled_entry = dashboard_dir / "index.cjs"
    # Repo development: index.cjs is in dashboard_dir/dist/
    dist_entry = dashboard_dir / "dist" / "index.cjs"

    if bundled_entry.exists():
        cmd = ["node", str(bundled_entry)]
    elif dist_entry.exists():
        cmd = ["node", str(dist_entry)]
    elif _npx_available():
        cmd = ["npx", "tsx", "server/index.ts"]
        env["NODE_ENV"] = "development"
    else:
        click.echo(
            "Error: Dashboard not built and npx not available.\n"
            "Run 'cd dashboard && npm install && npm run build' first,\n"
            "or install Node.js to use dev mode.",
            err=True,
        )
        raise SystemExit(1)

    click.echo(f"Starting dashboard at http://{host}:{port}")

    if not no_browser:
        import threading
        import webbrowser

        def _open_browser() -> None:
            import time

            time.sleep(2)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    proc = subprocess.Popen(cmd, env=env, cwd=str(dashboard_dir))

    def _signal_handler(signum: int, _frame: object) -> None:
        proc.terminate()
        proc.wait(timeout=5)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Legacy Python dashboard
# ---------------------------------------------------------------------------


def _start_legacy_dashboard(
    host: str, port: int, no_browser: bool, i_understand_risk: bool
) -> None:
    """Start the legacy Python FastAPI dashboard."""
    try:
        import fastapi  # noqa: F401
    except ImportError as exc:
        click.echo(
            "Error: Legacy dashboard dependencies not installed.\n"
            "Install them with:\n\n"
            "  pip install 'atlasbridge[dashboard]'\n",
            err=True,
        )
        raise SystemExit(1) from exc

    from atlasbridge.dashboard.app import start_server

    click.echo(f"Starting legacy dashboard at http://{host}:{port}")
    start_server(
        host=host,
        port=port,
        open_browser=not no_browser,
        allow_non_loopback=i_understand_risk,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dashboard_group.command("start")
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Bind address (default: loopback only)",
)
@click.option("--port", default=3737, show_default=True, help="Port to listen on")
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Do not open browser automatically",
)
@click.option(
    "--edition",
    type=click.Choice(["core", "enterprise"], case_sensitive=False),
    default=None,
    help="Dashboard edition (default: core). Enterprise adds extended views.",
)
@click.option(
    "--legacy",
    is_flag=True,
    default=False,
    help="Use the legacy Python FastAPI dashboard (port 8787)",
)
@click.option(
    "--i-understand-risk",
    is_flag=True,
    default=False,
    hidden=True,
    help="Allow binding to non-loopback addresses (DANGEROUS)",
)
def dashboard_start(
    host: str,
    port: int,
    no_browser: bool,
    edition: str | None,
    legacy: bool,
    i_understand_risk: bool,
) -> None:
    """Start the local dashboard server."""
    from atlasbridge.dashboard.sanitize import is_loopback

    # Edition resolution: CLI flag > env var > default ("core")
    if edition is not None:
        os.environ["ATLASBRIDGE_EDITION"] = edition
    elif not os.environ.get("ATLASBRIDGE_EDITION"):
        os.environ["ATLASBRIDGE_EDITION"] = "core"

    if not is_loopback(host) and not i_understand_risk:
        click.echo(
            "Error: Binding to a non-loopback address exposes the dashboard "
            "to your network.\n"
            "The dashboard has NO authentication — anyone on the network can view "
            "session data.\n\n"
            "If you understand the risk and want to proceed, add:\n\n"
            "  --i-understand-risk\n\n"
            f"Got: --host {host!r}. Without the flag, only loopback "
            "(127.0.0.1, ::1, localhost) is allowed.",
            err=True,
        )
        raise SystemExit(1)

    if legacy:
        # Legacy defaults to port 8787 unless user overrode
        if port == 3737:
            port = 8787
        _start_legacy_dashboard(host, port, no_browser, i_understand_risk)
        return

    # Node.js dashboard (default)
    if not _node_available():
        click.echo(
            "Error: Node.js is required for the dashboard but was not found.\n"
            "Install Node.js (v18+) from https://nodejs.org\n\n"
            "Alternatively, use the legacy Python dashboard:\n\n"
            "  atlasbridge dashboard start --legacy\n",
            err=True,
        )
        raise SystemExit(1)

    dashboard_dir = _find_dashboard_dir()
    if dashboard_dir is None:
        click.echo(
            "Error: Dashboard could not be set up.\n"
            "Ensure Node.js (v18+) and npm are installed: https://nodejs.org\n\n"
            "Alternatively, use the legacy Python dashboard:\n\n"
            "  atlasbridge dashboard start --legacy\n",
            err=True,
        )
        raise SystemExit(1)

    _start_node_dashboard(host, port, no_browser, dashboard_dir)


@dashboard_group.command("status")
@click.option("--port", default=3737, show_default=True, help="Port to check")
def dashboard_status(port: int) -> None:
    """Check if the dashboard server is running."""
    import json
    import urllib.request

    # Try Node.js dashboard endpoint (localhost-only, safe)
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/overview", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310
            data = json.loads(resp.read())
            if "activeSessions" in data:
                click.echo(f"Dashboard is running on port {port}")
                return
    except Exception:  # noqa: BLE001
        pass

    # Try legacy FastAPI dashboard endpoint (localhost-only, safe)
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/stats", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310
            data = json.loads(resp.read())
            if "active_sessions" in data:
                click.echo(f"Dashboard is running on port {port} (legacy)")
                return
    except Exception:  # noqa: BLE001
        pass

    # Neither endpoint matched — check if port is in use by something else
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            click.echo(f"Port {port} is in use by another service (not AtlasBridge dashboard)")
        else:
            click.echo(f"Dashboard is not running on port {port}")
    finally:
        sock.close()


@dashboard_group.command("export")
@click.option(
    "--session",
    "session_id",
    required=True,
    help="Session ID to export",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "html"]),
    default="json",
    show_default=True,
    help="Export format",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    help="Output file path (default: stdout for JSON, session_<id>.html for HTML)",
)
def dashboard_export(session_id: str, fmt: str, output_path: str | None) -> None:
    """Export a session as JSON or self-contained HTML."""
    from atlasbridge.core.config import atlasbridge_dir
    from atlasbridge.core.constants import DB_FILENAME
    from atlasbridge.dashboard.repo import DashboardRepo

    config_dir = atlasbridge_dir()
    db_path = config_dir / DB_FILENAME

    from atlasbridge.core.autopilot.trace import TRACE_FILENAME

    trace_path = config_dir / TRACE_FILENAME

    repo = DashboardRepo(db_path, trace_path)
    repo.connect()

    try:
        if fmt == "json":
            from atlasbridge.dashboard.export import export_session_json

            bundle = export_session_json(repo, session_id)
            if bundle is None:
                click.echo(f"Error: Session {session_id!r} not found.", err=True)
                raise SystemExit(1)

            import json

            content = json.dumps(bundle, indent=2, default=str)

            if output_path:
                Path(output_path).write_text(content, encoding="utf-8")
                click.echo(f"Exported JSON to {output_path}")
            else:
                click.echo(content)
        else:
            from atlasbridge.dashboard.export import export_session_html

            html = export_session_html(repo, session_id)
            if html is None:
                click.echo(f"Error: Session {session_id!r} not found.", err=True)
                raise SystemExit(1)

            if output_path is None:
                output_path = f"session_{session_id}.html"

            Path(output_path).write_text(html, encoding="utf-8")
            click.echo(f"Exported HTML to {output_path}")
    finally:
        repo.close()
