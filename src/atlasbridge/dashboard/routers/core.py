"""Core dashboard routes — available on all editions.

Routes registered here:
    GET /
    GET /sessions/{session_id}
    GET /settings
    GET /api/stats
    GET /api/sessions
    GET /api/settings
    GET /runtime/capabilities
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from atlasbridge.dashboard._collect import collect_settings
from atlasbridge.dashboard.repo import DashboardRepo


def make_core_router(
    repo: DashboardRepo,
    templates: Jinja2Templates,
    db_path: Path,
    trace_path: Path,
    edition_value: str,
    authority_mode_value: str,
    environment: str,
) -> APIRouter:
    """Create the APIRouter containing all Core edition routes."""
    router = APIRouter()

    # ------------------------------------------------------------------
    # HTML Routes
    # ------------------------------------------------------------------

    @router.get("/", response_class=HTMLResponse)
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

    @router.get("/sessions/{session_id}", response_class=HTMLResponse)
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

    @router.get("/settings", response_class=HTMLResponse)
    async def settings(request: Request):
        settings_data = collect_settings(
            db_path,
            trace_path,
            edition=edition_value,
            authority_mode=authority_mode_value,
        )
        return templates.TemplateResponse(
            request,
            "settings.html",
            {"settings": settings_data},
        )

    # ------------------------------------------------------------------
    # JSON API Routes
    # ------------------------------------------------------------------

    @router.get("/api/stats")
    async def api_stats():
        stats = repo.get_stats()
        return JSONResponse(stats)

    @router.get("/api/sessions")
    async def api_sessions(request: Request):
        status = request.query_params.get("status") or None
        tool = request.query_params.get("tool") or None
        q = request.query_params.get("q") or None
        sessions = repo.list_sessions(limit=100, status=status, tool=tool, q=q)
        total = repo.count_sessions(status=status, tool=tool, q=q)
        return JSONResponse({"sessions": sessions, "total": total})

    @router.get("/api/settings")
    async def api_settings():
        return JSONResponse(
            collect_settings(
                db_path,
                trace_path,
                edition=edition_value,
                authority_mode=authority_mode_value,
            )
        )

    @router.get("/runtime/capabilities")
    async def runtime_capabilities():
        """Return current runtime edition, authority mode, and capability status."""
        from atlasbridge.enterprise.edition import AuthorityMode, Edition
        from atlasbridge.enterprise.registry import REGISTRY_VERSION, FeatureRegistry

        ed_enum = (
            Edition(edition_value)
            if edition_value in Edition.__members__.values()
            else Edition.CORE
        )
        am_enum = (
            AuthorityMode(authority_mode_value)
            if authority_mode_value in AuthorityMode.__members__.values()
            else AuthorityMode.READONLY
        )

        caps = FeatureRegistry.list_capabilities(ed_enum, am_enum)
        cap_hash = FeatureRegistry.capabilities_hash(ed_enum, am_enum)

        return JSONResponse(
            {
                "edition": edition_value,
                "authority_mode": authority_mode_value,
                "enabled_capabilities": sorted(
                    cap_id for cap_id, info in caps.items() if info["allowed"]
                ),
                "enabled_capabilities_hash": cap_hash,
                "registry_version": REGISTRY_VERSION,
            }
        )

    return router
