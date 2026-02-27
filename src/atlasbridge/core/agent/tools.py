"""
Governed tools for the AtlasBridge Expert Agent.

Risk levels:
  safe      — read-only operations on runtime data
  moderate  — policy validation/testing, no state mutation
  dangerous — operator-level actions (mode changes, kill switch)

All tool executors return structured JSON with action, trace_id, and result fields.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from atlasbridge.tools.registry import Tool, ToolRegistry

logger = structlog.get_logger()

# Module-level reference set by the engine at startup
_db: Any = None
_config: dict[str, Any] = {}


def set_agent_context(db: Any, config: dict[str, Any] | None = None) -> None:
    """Set the shared database and config references for tool executors."""
    global _db, _config  # noqa: PLW0603
    _db = db
    _config = config or {}


def _json_result(action: str, **kwargs: Any) -> str:
    """Format a structured tool result."""
    payload: dict[str, Any] = {"action": action}
    payload.update(kwargs)
    return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------------------
# Safe (read-only) tools
# ---------------------------------------------------------------------------


async def _ab_list_sessions(args: dict[str, Any]) -> str:
    limit = args.get("limit", 20)
    rows = _db.list_sessions(limit=limit)
    sessions = [
        {
            "id": r["id"],
            "tool": r["tool"],
            "status": r["status"],
            "started_at": r["started_at"],
            "label": r["label"],
        }
        for r in rows
    ]
    return _json_result("list_sessions", count=len(sessions), sessions=sessions)


async def _ab_get_session(args: dict[str, Any]) -> str:
    session_id = args.get("session_id", "")
    if not session_id:
        return _json_result("get_session", error="session_id is required")
    row = _db.get_session(session_id)
    if row is None:
        return _json_result("get_session", error=f"Session not found: {session_id}")
    prompts = _db.list_prompts_for_session(session_id)
    return _json_result(
        "get_session",
        session={
            "id": row["id"],
            "tool": row["tool"],
            "status": row["status"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "pid": row["pid"],
            "cwd": row["cwd"],
            "label": row["label"],
        },
        prompt_count=len(prompts),
    )


async def _ab_list_prompts(args: dict[str, Any]) -> str:
    session_id = args.get("session_id", "")
    if session_id:
        rows = _db.list_prompts_for_session(session_id)
    else:
        rows = _db.list_pending_prompts()
    prompts = [
        {
            "id": r["id"],
            "session_id": r["session_id"],
            "prompt_type": r["prompt_type"],
            "confidence": r["confidence"],
            "status": r["status"],
            "excerpt": r["excerpt"][:100],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return _json_result("list_prompts", count=len(prompts), prompts=prompts)


async def _ab_get_audit_events(args: dict[str, Any]) -> str:
    session_id = args.get("session_id")
    since = args.get("since")
    until = args.get("until")
    rows = _db.get_audit_events_filtered(session_id=session_id, since=since, until=until)
    events = [
        {
            "id": r["id"],
            "event_type": r["event_type"],
            "session_id": r["session_id"],
            "timestamp": r["timestamp"],
            "payload_preview": r["payload"][:200],
        }
        for r in rows[:100]
    ]
    return _json_result("get_audit_events", count=len(events), events=events)


async def _ab_get_traces(args: dict[str, Any]) -> str:
    session_id = args.get("session_id", "")
    if not session_id:
        return _json_result("get_traces", error="session_id is required")
    rows = _db.get_audit_events_for_session(session_id)
    trace = [
        {
            "event_type": r["event_type"],
            "timestamp": r["timestamp"],
            "hash": r["hash"][:16],
        }
        for r in rows
    ]
    return _json_result("get_traces", session_id=session_id, count=len(trace), trace=trace)


async def _ab_check_integrity(args: dict[str, Any]) -> str:
    rows = _db.get_recent_audit_events(limit=500)
    if not rows:
        return _json_result("check_integrity", status="empty", message="No audit events found")

    # Verify hash chain
    broken = []
    for i in range(len(rows) - 1, 0, -1):
        current = rows[i]
        previous = rows[i - 1]
        if current["prev_hash"] and current["prev_hash"] != previous["hash"]:
            broken.append({"event_id": current["id"], "expected": previous["hash"][:16]})
            if len(broken) >= 5:
                break

    if broken:
        return _json_result(
            "check_integrity", status="broken", breaks=broken, total_checked=len(rows)
        )
    return _json_result("check_integrity", status="valid", total_checked=len(rows))


async def _ab_get_config(args: dict[str, Any]) -> str:
    safe_config = {}
    for key, value in _config.items():
        if key in ("telegram", "slack", "chat"):
            # Redact channel tokens
            safe_config[key] = {
                k: ("***" if "token" in k.lower() or "key" in k.lower() else v)
                for k, v in (value if isinstance(value, dict) else {}).items()
            }
        else:
            safe_config[key] = value
    return _json_result("get_config", config=safe_config)


async def _ab_get_policy(args: dict[str, Any]) -> str:
    policy_file = _config.get("policy_file", "")
    if not policy_file:
        return _json_result("get_policy", error="No policy file configured")
    try:
        from pathlib import Path

        content = Path(policy_file).read_text(encoding="utf-8")
        return _json_result("get_policy", policy_file=policy_file, content=content[:5000])
    except Exception as exc:
        return _json_result("get_policy", error=str(exc))


async def _ab_explain_decision(args: dict[str, Any]) -> str:
    prompt_id = args.get("prompt_id", "")
    if not prompt_id:
        return _json_result("explain_decision", error="prompt_id is required")
    prompt = _db.get_prompt(prompt_id)
    if prompt is None:
        return _json_result("explain_decision", error=f"Prompt not found: {prompt_id}")
    events = _db.get_audit_events_filtered(session_id=prompt["session_id"])
    related = [
        {"event_type": e["event_type"], "timestamp": e["timestamp"], "payload": e["payload"][:200]}
        for e in events
        if prompt_id in (e.get("prompt_id", "") or e["payload"])
    ]
    return _json_result(
        "explain_decision",
        prompt={
            "id": prompt["id"],
            "type": prompt["prompt_type"],
            "confidence": prompt["confidence"],
            "status": prompt["status"],
            "response": prompt["response_normalized"],
        },
        related_events=related[:20],
    )


async def _ab_get_stats(args: dict[str, Any]) -> str:
    sessions = _db.list_sessions(limit=1000)
    active = [s for s in sessions if s["status"] not in ("completed", "crashed", "canceled")]
    audit_count = _db.count_audit_events()
    return _json_result(
        "get_stats",
        total_sessions=len(sessions),
        active_sessions=len(active),
        audit_events=audit_count,
    )


# ---------------------------------------------------------------------------
# Moderate tools
# ---------------------------------------------------------------------------


async def _ab_validate_policy(args: dict[str, Any]) -> str:
    policy_path = args.get("path", "")
    if not policy_path:
        return _json_result("validate_policy", error="path is required")
    try:
        proc = await asyncio.create_subprocess_exec(
            "atlasbridge",
            "policy",
            "validate",
            policy_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        output = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        return _json_result(
            "validate_policy",
            path=policy_path,
            valid=proc.returncode == 0,
            output=output[:2000],
            errors=err[:2000] if err else None,
        )
    except Exception as exc:
        return _json_result("validate_policy", error=str(exc))


async def _ab_test_policy(args: dict[str, Any]) -> str:
    policy_path = args.get("path", "")
    prompt = args.get("prompt", "")
    prompt_type = args.get("prompt_type", "yes_no")
    if not policy_path or not prompt:
        return _json_result("test_policy", error="path and prompt are required")
    try:
        cmd = [
            "atlasbridge",
            "policy",
            "test",
            policy_path,
            "--prompt",
            prompt,
            "--type",
            prompt_type,
            "--explain",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        output = stdout.decode("utf-8", errors="replace")
        return _json_result("test_policy", path=policy_path, output=output[:3000])
    except Exception as exc:
        return _json_result("test_policy", error=str(exc))


# ---------------------------------------------------------------------------
# Dangerous tools (always gated)
# ---------------------------------------------------------------------------


async def _ab_set_mode(args: dict[str, Any]) -> str:
    mode = args.get("mode", "")
    if mode not in ("off", "assist", "full"):
        return _json_result("set_mode", error=f"Invalid mode: {mode}. Must be off/assist/full")
    try:
        proc = await asyncio.create_subprocess_exec(
            "atlasbridge",
            "autopilot",
            "mode",
            mode,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        out = stdout.decode()[:500]
        return _json_result("set_mode", mode=mode, success=proc.returncode == 0, output=out)
    except Exception as exc:
        return _json_result("set_mode", error=str(exc))


async def _ab_kill_switch(args: dict[str, Any]) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "atlasbridge",
            "autopilot",
            "disable",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        out = stdout.decode()[:500]
        return _json_result("kill_switch", success=proc.returncode == 0, output=out)
    except Exception as exc:
        return _json_result("kill_switch", error=str(exc))


# ---------------------------------------------------------------------------
# Registry factory
# ---------------------------------------------------------------------------


def get_agent_registry() -> ToolRegistry:
    """Create a ToolRegistry with all Expert Agent tools."""
    registry = ToolRegistry()

    # Safe tools
    for name, desc, params, executor in [
        (
            "ab_list_sessions",
            "List recent sessions with status, tool, and timestamps.",
            {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}},
            _ab_list_sessions,
        ),
        (
            "ab_get_session",
            "Get detailed information about a specific session including prompt count.",
            {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
            _ab_get_session,
        ),
        (
            "ab_list_prompts",
            "List prompts, optionally filtered by session_id. Shows type, confidence, status.",
            {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
            },
            _ab_list_prompts,
        ),
        (
            "ab_get_audit_events",
            "Query audit events with optional session_id, since, and until filters.",
            {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "since": {"type": "string", "description": "ISO timestamp"},
                    "until": {"type": "string", "description": "ISO timestamp"},
                },
            },
            _ab_get_audit_events,
        ),
        (
            "ab_get_traces",
            "Get the governance trace (audit event chain) for a session.",
            {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
            _ab_get_traces,
        ),
        (
            "ab_check_integrity",
            "Verify the audit log hash chain integrity.",
            {"type": "object", "properties": {}},
            _ab_check_integrity,
        ),
        (
            "ab_get_config",
            "Read the current runtime configuration (tokens redacted).",
            {"type": "object", "properties": {}},
            _ab_get_config,
        ),
        (
            "ab_get_policy",
            "Read the active policy file content.",
            {"type": "object", "properties": {}},
            _ab_get_policy,
        ),
        (
            "ab_explain_decision",
            "Explain why a specific prompt was auto-replied, escalated, or denied.",
            {
                "type": "object",
                "properties": {"prompt_id": {"type": "string"}},
                "required": ["prompt_id"],
            },
            _ab_explain_decision,
        ),
        (
            "ab_get_stats",
            "Get system statistics: session counts, audit event counts.",
            {"type": "object", "properties": {}},
            _ab_get_stats,
        ),
    ]:
        registry.register(
            Tool(
                name=name,
                description=desc,
                parameters=params,
                risk_level="safe",
                executor=executor,
            )
        )

    # Moderate tools
    registry.register(
        Tool(
            name="ab_validate_policy",
            description="Validate a policy YAML file against the schema.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to policy YAML file"},
                },
                "required": ["path"],
            },
            risk_level="moderate",
            executor=_ab_validate_policy,
        )
    )
    registry.register(
        Tool(
            name="ab_test_policy",
            description="Simulate a prompt against a policy file and show the decision.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to policy YAML file"},
                    "prompt": {"type": "string", "description": "Prompt text to test"},
                    "prompt_type": {"type": "string", "default": "yes_no"},
                },
                "required": ["path", "prompt"],
            },
            risk_level="moderate",
            executor=_ab_test_policy,
        )
    )

    # Dangerous tools
    registry.register(
        Tool(
            name="ab_set_mode",
            description="Change the autonomy mode (off/assist/full). Requires human approval.",
            parameters={
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["off", "assist", "full"]}},
                "required": ["mode"],
            },
            risk_level="dangerous",
            executor=_ab_set_mode,
        )
    )
    registry.register(
        Tool(
            name="ab_kill_switch",
            description="Emergency: disable autopilot immediately. Requires human approval.",
            parameters={"type": "object", "properties": {}},
            risk_level="dangerous",
            executor=_ab_kill_switch,
        )
    )

    return registry
