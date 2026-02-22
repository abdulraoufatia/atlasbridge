"""
FastAPI dashboard application — localhost-only, read-only.

Provides a server-rendered web dashboard for viewing sessions, prompts,
decision traces, and audit integrity from local storage.

Usage::

    from atlasbridge.dashboard.app import create_app, start_server
    app = create_app()
    start_server(host="127.0.0.1", port=8787)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from atlasbridge.dashboard.repo import DashboardRepo
from atlasbridge.dashboard.sanitize import is_loopback

_HERE = Path(__file__).resolve().parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


def _default_db_path() -> Path:
    from atlasbridge.core.config import atlasbridge_dir
    from atlasbridge.core.constants import DB_FILENAME

    return atlasbridge_dir() / DB_FILENAME


def _default_trace_path() -> Path:
    from atlasbridge.core.autopilot.trace import TRACE_FILENAME
    from atlasbridge.core.config import atlasbridge_dir

    return atlasbridge_dir() / TRACE_FILENAME


def create_app(
    db_path: Path | None = None,
    trace_path: Path | None = None,
) -> FastAPI:
    """Create the FastAPI dashboard application."""
    db_path = db_path or _default_db_path()
    trace_path = trace_path or _default_trace_path()

    app = FastAPI(
        title="AtlasBridge Dashboard",
        description="Read-only governance view — local execution only",
        docs_url=None,
        redoc_url=None,
    )

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    repo = DashboardRepo(db_path, trace_path)
    repo.connect()

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        stats = repo.get_stats()
        sessions = repo.list_sessions(limit=20)
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "stats": stats,
                "sessions": sessions,
                "db_available": repo.db_available,
            },
        )

    @app.get("/sessions/{session_id}", response_class=HTMLResponse)
    async def session_detail(request: Request, session_id: str):
        session = repo.get_session(session_id)
        prompts = repo.list_prompts_for_session(session_id) if session else []
        # Get trace entries for this session
        all_traces = repo.trace_tail(200)
        session_traces = [t for t in all_traces if t.get("session_id") == session_id]
        return templates.TemplateResponse(
            "session_detail.html",
            {
                "request": request,
                "session": session,
                "prompts": prompts,
                "traces": session_traces,
                "db_available": repo.db_available,
            },
        )

    @app.get("/traces/{index}", response_class=HTMLResponse)
    async def trace_detail(request: Request, index: int):
        entries = repo.trace_tail(index + 1)
        entry = entries[index] if index < len(entries) else None
        return templates.TemplateResponse(
            "trace_detail.html",
            {
                "request": request,
                "entry": entry,
                "index": index,
                "trace_available": repo.trace_available,
            },
        )

    @app.get("/integrity", response_class=HTMLResponse)
    async def integrity(request: Request):
        trace_valid, trace_errors = repo.verify_integrity()
        audit_valid, audit_errors = repo.verify_audit_integrity()
        audit_events = repo.list_audit_events(limit=50)
        return templates.TemplateResponse(
            "integrity.html",
            {
                "request": request,
                "trace_valid": trace_valid,
                "trace_errors": trace_errors,
                "audit_valid": audit_valid,
                "audit_errors": audit_errors,
                "audit_events": audit_events,
                "db_available": repo.db_available,
                "trace_available": repo.trace_available,
            },
        )

    @app.post("/api/integrity/verify")
    async def api_verify_integrity():
        trace_valid, trace_errors = repo.verify_integrity()
        audit_valid, audit_errors = repo.verify_audit_integrity()
        return JSONResponse(
            {
                "trace": {"valid": trace_valid, "errors": trace_errors},
                "audit": {"valid": audit_valid, "errors": audit_errors},
            }
        )

    return app


def start_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    open_browser: bool = True,
    db_path: Path | None = None,
    trace_path: Path | None = None,
) -> None:
    """Start the dashboard server (blocking)."""
    if not is_loopback(host):
        raise ValueError(
            f"Dashboard must bind to a loopback address for safety. "
            f"Got: {host!r}. Use 127.0.0.1, ::1, or localhost."
        )

    import uvicorn

    app = create_app(db_path=db_path, trace_path=trace_path)

    if open_browser:
        import threading
        import webbrowser

        def _open():
            import time

            time.sleep(1.0)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
