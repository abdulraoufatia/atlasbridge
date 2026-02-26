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

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from atlasbridge.dashboard.repo import DashboardRepo
from atlasbridge.dashboard.sanitize import is_loopback, redact_query_params

_access_log = logging.getLogger("atlasbridge.dashboard.access")

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


def _timeago(value: str | None) -> str:
    """Jinja2 filter: convert ISO timestamp to '2h ago' style string."""
    from datetime import datetime, timezone

    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        return f"{months}mo ago"
    except (ValueError, TypeError):
        return str(value)


class _AccessLogMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, redacted query, status, and elapsed time."""

    async def dispatch(self, request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        query = redact_query_params(str(request.query_params)) if request.query_params else ""
        _access_log.info(
            "dashboard_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": query,
                "status": response.status_code,
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )
        return response


def create_app(
    db_path: Path | None = None,
    trace_path: Path | None = None,
    environment: str = "",
) -> FastAPI:
    """Create the FastAPI dashboard application."""
    from atlasbridge.enterprise.edition import Edition, detect_authority_mode, detect_edition
    from atlasbridge.enterprise.guard import FeatureUnavailableError

    db_path = db_path or _default_db_path()
    trace_path = trace_path or _default_trace_path()

    # Resolve edition and authority mode once at startup
    edition = detect_edition()
    authority_mode = detect_authority_mode()

    app = FastAPI(
        title="AtlasBridge Dashboard",
        description="Read-only governance view — local execution only",
        docs_url=None,
        redoc_url=None,
    )

    # Store on app state for route handlers
    app.state.edition = edition
    app.state.authority_mode = authority_mode

    # Exception handler: FeatureUnavailableError → 404 JSON
    @app.exception_handler(FeatureUnavailableError)
    async def _feature_unavailable_handler(
        request: Request,
        exc: FeatureUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(
            {
                "error": f"Capability unavailable: {exc.capability_id}",
                "reason": exc.decision.reason_code,
            },
            status_code=404,
        )

    app.add_middleware(_AccessLogMiddleware)

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    templates.env.filters["timeago"] = _timeago
    templates.env.globals["edition"] = edition.value
    templates.env.globals["authority_mode"] = authority_mode.value
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    repo = DashboardRepo(db_path, trace_path)
    repo.connect()

    # ------------------------------------------------------------------
    # Mount routers — edition-aware
    # ------------------------------------------------------------------

    from atlasbridge.dashboard.routers.core import make_core_router

    app.include_router(
        make_core_router(
            repo=repo,
            templates=templates,
            db_path=db_path,
            trace_path=trace_path,
            edition_value=edition.value,
            authority_mode_value=authority_mode.value,
            environment=environment,
        )
    )

    if edition == Edition.ENTERPRISE:
        from atlasbridge.dashboard.routers.enterprise import make_enterprise_router

        app.include_router(
            make_enterprise_router(
                repo=repo,
                templates=templates,
                db_path=db_path,
                trace_path=trace_path,
                edition=edition,
                authority_mode=authority_mode,
            )
        )

    return app


def start_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    open_browser: bool = True,
    db_path: Path | None = None,
    trace_path: Path | None = None,
    *,
    allow_non_loopback: bool = False,
    environment: str = "",
) -> None:
    """Start the dashboard server (blocking)."""
    if not is_loopback(host) and not allow_non_loopback:
        raise ValueError(
            f"Dashboard must bind to a loopback address for safety. "
            f"Got: {host!r}. Use 127.0.0.1, ::1, or localhost."
        )

    import uvicorn

    app = create_app(db_path=db_path, trace_path=trace_path, environment=environment)

    if open_browser:
        import threading
        import webbrowser

        def _open():
            import time

            time.sleep(1.0)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
