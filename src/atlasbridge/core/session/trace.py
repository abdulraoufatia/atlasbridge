"""
Session trace timeline — reconstruct chronological governance narrative.

Builds a timeline from audit events and prompt records for a given session.

Usage::

    timeline = build_session_trace(db, session_id)
    print(format_trace(timeline))
    # or: json_str = trace_to_json(timeline)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from atlasbridge.core.store.database import Database

# ---------------------------------------------------------------------------
# Event type labels for human display
# ---------------------------------------------------------------------------

_EVENT_LABELS: dict[str, str] = {
    "session_started": "Session Started",
    "session_ended": "Session Ended",
    "prompt_detected": "Prompt Detected",
    "prompt_routed": "Prompt Routed",
    "reply_received": "Reply Received",
    "response_injected": "Response Injected",
    "prompt_expired": "Prompt Expired",
    "prompt_canceled": "Prompt Canceled",
    "duplicate_callback_ignored": "Duplicate Callback Ignored",
    "late_reply_rejected": "Late Reply Rejected",
    "invalid_callback": "Invalid Callback",
    "telegram_polling_failed": "Telegram Polling Failed",
    "daemon_restarted": "Daemon Restarted",
    "channel_message_accepted": "Channel Message Accepted",
    "channel_message_rejected": "Channel Message Rejected",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TraceEvent:
    """A single event in the session trace timeline."""

    timestamp: str
    event_type: str
    label: str
    prompt_id: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionTrace:
    """Complete trace timeline for one session."""

    session_id: str
    tool: str
    status: str
    started_at: str
    ended_at: str | None
    events: list[TraceEvent] = field(default_factory=list)
    prompt_count: int = 0
    event_count: int = 0


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_session_trace(db: Database, session_id: str) -> SessionTrace | None:
    """
    Build a chronological trace timeline for a session.

    Returns None if the session does not exist.
    """
    session = db.get_session(session_id)
    if session is None:
        return None

    trace = SessionTrace(
        session_id=session["id"],
        tool=session["tool"] or "",
        status=session["status"] or "",
        started_at=session["started_at"] or "",
        ended_at=session["ended_at"],
    )

    # Collect audit events
    audit_rows = db.get_audit_events_for_session(session_id)
    for row in audit_rows:
        payload = _parse_payload(row["payload"])
        event = TraceEvent(
            timestamp=row["timestamp"] or "",
            event_type=row["event_type"] or "",
            label=_EVENT_LABELS.get(row["event_type"], row["event_type"]),
            prompt_id=row["prompt_id"] or "",
            details=payload,
        )
        trace.events.append(event)

    # Enrich with prompt lifecycle data
    prompts = db.list_prompts_for_session(session_id)
    trace.prompt_count = len(prompts)
    trace.event_count = len(trace.events)

    return trace


def _parse_payload(raw: str) -> dict[str, Any]:
    """Parse a JSON payload string, returning empty dict on failure."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_trace(trace: SessionTrace) -> str:
    """Format a SessionTrace as a human-readable ASCII timeline."""
    lines: list[str] = []

    lines.append(f"Session Trace: {trace.session_id[:12]}")
    lines.append(f"Tool: {trace.tool}  Status: {trace.status}")
    lines.append(f"Started: {trace.started_at}")
    if trace.ended_at:
        lines.append(f"Ended:   {trace.ended_at}")
    lines.append(f"Events: {trace.event_count}  Prompts: {trace.prompt_count}")
    lines.append("")
    lines.append("Timeline:")
    lines.append("-" * 70)

    if not trace.events:
        lines.append("  (no events recorded)")
        return "\n".join(lines)

    for i, event in enumerate(trace.events):
        ts = event.timestamp[:19] if event.timestamp else "?"
        connector = "|" if i < len(trace.events) - 1 else "`"

        lines.append(f"  {ts}  {connector}-- {event.label}")

        # Show key details inline
        detail_parts = _format_event_details(event)
        for part in detail_parts:
            pad = "|" if i < len(trace.events) - 1 else " "
            lines.append(f"  {'':19s}  {pad}   {part}")

    lines.append("-" * 70)
    return "\n".join(lines)


def _format_event_details(event: TraceEvent) -> list[str]:
    """Extract the most relevant details for inline display."""
    parts: list[str] = []
    d = event.details

    if event.event_type == "prompt_detected":
        if d.get("prompt_type"):
            parts.append(f"type={d['prompt_type']}")
        if d.get("confidence"):
            parts.append(f"confidence={d['confidence']}")
        if d.get("trigger"):
            parts.append(f"trigger={d['trigger']}")
    elif event.event_type == "prompt_routed":
        if d.get("channel"):
            parts.append(f"channel={d['channel']}")
    elif event.event_type == "reply_received":
        if d.get("channel_identity"):
            parts.append(f"from={d['channel_identity']}")
        if d.get("value_length"):
            parts.append(f"length={d['value_length']}")
    elif event.event_type == "response_injected":
        if d.get("prompt_type"):
            parts.append(f"type={d['prompt_type']}")
        if d.get("latency_ms"):
            parts.append(f"latency={d['latency_ms']}ms")
    elif event.event_type == "session_started":
        if d.get("tool"):
            parts.append(f"tool={d['tool']}")
    elif event.event_type == "session_ended":
        if d.get("exit_code") is not None:
            parts.append(f"exit_code={d['exit_code']}")
        if d.get("crashed"):
            parts.append("CRASHED")
    elif event.event_type == "channel_message_accepted":
        if d.get("accept_type"):
            parts.append(f"accept_type={d['accept_type']}")
    elif event.event_type == "channel_message_rejected":
        if d.get("reason_code"):
            parts.append(f"reason={d['reason_code']}")

    if event.prompt_id:
        parts.append(f"prompt={event.prompt_id[:8]}")

    return parts


def trace_to_json(trace: SessionTrace) -> str:
    """Serialize a SessionTrace as JSON."""
    data = {
        "session_id": trace.session_id,
        "tool": trace.tool,
        "status": trace.status,
        "started_at": trace.started_at,
        "ended_at": trace.ended_at,
        "prompt_count": trace.prompt_count,
        "event_count": trace.event_count,
        "events": [
            {
                "timestamp": e.timestamp,
                "event_type": e.event_type,
                "label": e.label,
                "prompt_id": e.prompt_id,
                "details": e.details,
            }
            for e in trace.events
        ],
    }
    return json.dumps(data, indent=2, default=str)
