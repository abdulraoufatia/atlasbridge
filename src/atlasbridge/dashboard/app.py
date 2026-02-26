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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from atlasbridge.dashboard.repo import DashboardRepo
from atlasbridge.dashboard.sanitize import is_loopback, redact_query_params

_access_log = logging.getLogger("atlasbridge.dashboard.access")

_HERE = Path(__file__).resolve().parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

# Integrity verify throttle — 10-second cooldown
_VERIFY_COOLDOWN_SECONDS = 10.0


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


def _collect_settings(
    db_path: Path,
    trace_path: Path,
    edition: str = "",
    authority_mode: str = "",
) -> dict:
    """Gather read-only settings data for the settings page."""
    import atlasbridge
    from atlasbridge.cli._doctor import (
        _check_adapters,
        _check_config,
        _check_database,
        _check_platform,
        _check_ptyprocess,
        _check_python_version,
        _check_ui_assets,
    )
    from atlasbridge.core.config import _config_file_path, atlasbridge_dir
    from atlasbridge.core.constants import AUDIT_FILENAME
    from atlasbridge.enterprise.edition import (
        detect_authority_mode,
        detect_edition,
    )
    from atlasbridge.enterprise.registry import FeatureRegistry

    ed = detect_edition() if not edition else None
    am = detect_authority_mode() if not authority_mode else None
    ed_val = edition or (ed.value if ed else "core")
    am_val = authority_mode or (am.value if am else "readonly")

    config_dir = atlasbridge_dir()
    config_file = _config_file_path()

    checks_raw = [
        _check_python_version(),
        _check_platform(),
        _check_ptyprocess(),
        _check_config(),
        _check_database(),
        _check_adapters(),
        _check_ui_assets(),
    ]
    diagnostics = [c for c in checks_raw if c is not None]

    # Resolve edition/authority for registry call
    from atlasbridge.enterprise.edition import AuthorityMode, Edition

    ed_enum = Edition(ed_val) if ed_val in Edition.__members__.values() else Edition.CORE
    am_enum = (
        AuthorityMode(am_val)
        if am_val in AuthorityMode.__members__.values()
        else AuthorityMode.READONLY
    )

    vi = sys.version_info
    data: dict = {
        "runtime": {
            "edition": ed_enum.value,
            "authority_mode": am_enum.value,
            "version": atlasbridge.__version__,
            "python_version": f"{vi.major}.{vi.minor}.{vi.micro}",
            "platform": sys.platform,
        },
        "config_paths": {
            "config_dir": str(config_dir),
            "config_file": str(config_file),
            "db_path": str(db_path),
            "audit_log": str(config_dir / AUDIT_FILENAME),
            "trace_file": str(trace_path),
        },
        "dashboard": {
            "host": "127.0.0.1",
            "port": 8787,
            "loopback_only": True,
        },
        "diagnostics": diagnostics,
        "capabilities": FeatureRegistry.list_capabilities(ed_enum, am_enum),
    }

    return data


def create_app(
    db_path: Path | None = None,
    trace_path: Path | None = None,
    environment: str = "",
) -> FastAPI:
    """Create the FastAPI dashboard application."""
    from atlasbridge.enterprise.edition import detect_authority_mode, detect_edition
    from atlasbridge.enterprise.guard import FeatureUnavailableError, require_capability
    from atlasbridge.enterprise.registry import FeatureRegistry

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

    # Module-level throttle state for integrity verify
    last_verify: dict[str, float] = {"ts": 0.0}

    # ------------------------------------------------------------------
    # HTML Routes
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        status = request.query_params.get("status") or None
        tool = request.query_params.get("tool") or None
        q = request.query_params.get("q") or None
        stats = repo.get_stats()
        sessions = repo.list_sessions(limit=20, status=status, tool=tool, q=q)
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "stats": stats,
                "sessions": sessions,
                "db_available": repo.db_available,
                "filter_status": status or "",
                "filter_tool": tool or "",
                "filter_q": q or "",
                "environment": environment,
            },
        )

    @app.get("/sessions/{session_id}", response_class=HTMLResponse)
    async def session_detail(request: Request, session_id: str):
        session = repo.get_session(session_id)
        prompts = repo.list_prompts_for_session(session_id) if session else []
        session_traces = repo.trace_entries_for_session(session_id, limit=100) if session else []
        return templates.TemplateResponse(
            request,
            "session_detail.html",
            {
                "session": session,
                "prompts": prompts,
                "traces": session_traces,
                "db_available": repo.db_available,
            },
        )

    @app.get("/traces", response_class=HTMLResponse)
    async def traces_list(request: Request):
        page = int(request.query_params.get("page") or 1)
        per_page = 20
        action_type = request.query_params.get("action_type") or None
        confidence = request.query_params.get("confidence") or None
        entries, total = repo.trace_page(
            page=page, per_page=per_page, action_type=action_type, confidence=confidence
        )
        total_pages = max(1, (total + per_page - 1) // per_page)
        return templates.TemplateResponse(
            request,
            "traces.html",
            {
                "entries": entries,
                "page": page,
                "total_pages": total_pages,
                "total": total,
                "trace_available": repo.trace_available,
                "filter_action_type": action_type or "",
                "filter_confidence": confidence or "",
            },
        )

    @app.get("/traces/{index}", response_class=HTMLResponse)
    async def trace_detail(request: Request, index: int):
        entries = repo.trace_tail(index + 1)
        entry = entries[index] if index < len(entries) else None
        return templates.TemplateResponse(
            request,
            "trace_detail.html",
            {
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
            request,
            "integrity.html",
            {
                "trace_valid": trace_valid,
                "trace_errors": trace_errors,
                "audit_valid": audit_valid,
                "audit_errors": audit_errors,
                "audit_events": audit_events,
                "db_available": repo.db_available,
                "trace_available": repo.trace_available,
            },
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings(request: Request):
        settings_data = _collect_settings(
            db_path,
            trace_path,
            edition=edition.value,
            authority_mode=authority_mode.value,
        )
        return templates.TemplateResponse(
            request,
            "settings.html",
            {"settings": settings_data},
        )

    @app.get("/enterprise/settings", response_class=HTMLResponse)
    async def enterprise_settings(request: Request):
        require_capability(edition, authority_mode, "authority.enterprise_settings")
        settings_data = _collect_settings(
            db_path,
            trace_path,
            edition=edition.value,
            authority_mode=authority_mode.value,
        )
        return templates.TemplateResponse(
            request,
            "settings.html",
            {"settings": settings_data},
        )

    # ------------------------------------------------------------------
    # JSON API Routes
    # ------------------------------------------------------------------

    @app.get("/api/stats")
    async def api_stats():
        stats = repo.get_stats()
        return JSONResponse(stats)

    @app.get("/api/sessions")
    async def api_sessions(request: Request):
        status = request.query_params.get("status") or None
        tool = request.query_params.get("tool") or None
        q = request.query_params.get("q") or None
        sessions = repo.list_sessions(limit=100, status=status, tool=tool, q=q)
        total = repo.count_sessions(status=status, tool=tool, q=q)
        return JSONResponse({"sessions": sessions, "total": total})

    @app.get("/api/sessions/{session_id}/export")
    async def api_session_export(session_id: str):
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, session_id)
        if bundle is None:
            return JSONResponse({"error": "Session not found"}, status_code=404)
        return JSONResponse(bundle)

    @app.post("/api/integrity/verify")
    async def api_verify_integrity():
        now = time.monotonic()
        if now - last_verify["ts"] < _VERIFY_COOLDOWN_SECONDS:
            return JSONResponse(
                {"error": "Too many requests. Try again later."},
                status_code=429,
            )
        last_verify["ts"] = now
        trace_valid, trace_errors = repo.verify_integrity()
        audit_valid, audit_errors = repo.verify_audit_integrity()
        return JSONResponse(
            {
                "trace": {"valid": trace_valid, "errors": trace_errors},
                "audit": {"valid": audit_valid, "errors": audit_errors},
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    @app.get("/api/settings")
    async def api_settings():
        return JSONResponse(
            _collect_settings(
                db_path,
                trace_path,
                edition=edition.value,
                authority_mode=authority_mode.value,
            )
        )

    @app.get("/runtime/capabilities")
    async def runtime_capabilities():
        """Return current runtime edition, authority mode, and capability status."""
        from atlasbridge.enterprise.registry import REGISTRY_VERSION

        caps = FeatureRegistry.list_capabilities(edition, authority_mode)
        cap_hash = FeatureRegistry.capabilities_hash(edition, authority_mode)

        return JSONResponse(
            {
                "edition": edition.value,
                "authority_mode": authority_mode.value,
                "enabled_capabilities": sorted(
                    cap_id for cap_id, info in caps.items() if info["allowed"]
                ),
                "enabled_capabilities_hash": cap_hash,
                "registry_version": REGISTRY_VERSION,
            }
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
