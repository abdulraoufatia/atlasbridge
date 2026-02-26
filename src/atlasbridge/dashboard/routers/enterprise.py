"""Enterprise dashboard routes — registered only when edition is ENTERPRISE.

Routes registered here:
    GET  /traces
    GET  /traces/{index}
    GET  /integrity
    GET  /enterprise/settings
    GET  /api/sessions/{session_id}/export
    POST /api/integrity/verify

This router is NEVER mounted on a Core edition app. Routes here do not exist
in the Core router table — they return 404 by router absence, not by handler
logic.

Double-layer enforcement for authority-gated routes:
  Layer 1 — router mount: this module is not included on Core.
  Layer 2 — route handler: authority-requiring handlers call require_capability()
            at entry, so Enterprise + READONLY mode is also denied at 404.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from atlasbridge.dashboard._collect import collect_settings
from atlasbridge.dashboard.repo import DashboardRepo
from atlasbridge.enterprise.edition import AuthorityMode, Edition
from atlasbridge.enterprise.guard import require_capability

# Integrity verify throttle — 10-second cooldown per app instance
_VERIFY_COOLDOWN_SECONDS = 10.0


def make_enterprise_router(
    repo: DashboardRepo,
    templates: Jinja2Templates,
    db_path: Path,
    trace_path: Path,
    edition: Edition,
    authority_mode: AuthorityMode,
) -> APIRouter:
    """Create the APIRouter containing all Enterprise-only routes."""
    router = APIRouter()

    # Per-router throttle state for integrity verify
    last_verify: dict[str, float] = {"ts": 0.0}

    # ------------------------------------------------------------------
    # HTML Routes
    # ------------------------------------------------------------------

    @router.get("/traces", response_class=HTMLResponse)
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

    @router.get("/traces/{index}", response_class=HTMLResponse)
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

    @router.get("/integrity", response_class=HTMLResponse)
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

    @router.get("/enterprise/settings", response_class=HTMLResponse)
    async def enterprise_settings(request: Request):
        # Layer 2 guard: AUTHORITY capability required — denies READONLY mode
        require_capability(edition, authority_mode, "authority.enterprise_settings")
        settings_data = collect_settings(
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

    @router.get("/api/sessions/{session_id}/export")
    async def api_session_export(session_id: str):
        from atlasbridge.dashboard.export import export_session_json

        bundle = export_session_json(repo, session_id)
        if bundle is None:
            return JSONResponse({"error": "Session not found"}, status_code=404)
        return JSONResponse(bundle)

    @router.post("/api/integrity/verify")
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

    return router
