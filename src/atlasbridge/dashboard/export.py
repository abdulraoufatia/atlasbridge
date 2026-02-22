"""
Session export — JSON and self-contained HTML.

Exports a full session bundle (session metadata, prompts, traces, audit
events) with all text sanitized through the standard pipeline.

Usage::

    from atlasbridge.dashboard.export import export_session_json, export_session_html
    bundle = export_session_json(repo, "sess-001")
    html = export_session_html(repo, "sess-001")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atlasbridge.dashboard.sanitize import sanitize_for_display


def _build_session_bundle(
    repo: Any,
    session_id: str,
) -> dict[str, Any] | None:
    """Query and sanitize a full session bundle from the repo.

    Returns None if the session does not exist.
    """
    session = repo.get_session(session_id)
    if not session:
        return None

    prompts = repo.list_prompts_for_session(session_id)
    traces = repo.trace_entries_for_session(session_id, limit=500)
    audit_events = repo.list_audit_events(limit=500)
    # Filter audit events to this session
    session_audit = [e for e in audit_events if e.get("session_id") == session_id]

    # Sanitize all text fields in traces (repo already sanitizes DB rows)
    sanitized_traces = []
    for entry in traces:
        clean = dict(entry)
        for key in ("prompt_text", "excerpt", "response", "value"):
            if key in clean and isinstance(clean[key], str):
                clean[key] = sanitize_for_display(clean[key])
        sanitized_traces.append(clean)

    return {
        "export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": session,
        "prompts": prompts,
        "traces": sanitized_traces,
        "audit_events": session_audit,
    }


def export_session_json(
    repo: Any,
    session_id: str,
) -> dict[str, Any] | None:
    """Export a session as a sanitized JSON bundle.

    Returns None if the session does not exist.
    """
    return _build_session_bundle(repo, session_id)


def export_session_html(
    repo: Any,
    session_id: str,
) -> str | None:
    """Export a session as a self-contained HTML file.

    Returns None if the session does not exist.
    """
    bundle = _build_session_bundle(repo, session_id)
    if bundle is None:
        return None

    import html
    import json

    session = bundle["session"]
    prompts = bundle["prompts"]
    traces = bundle["traces"]
    audit_events = bundle["audit_events"]

    def _esc(val: Any) -> str:
        return html.escape(str(val)) if val is not None else ""

    # Build prompt rows
    prompt_rows = ""
    for p in prompts:
        prompt_rows += (
            f"<tr>"
            f"<td>{_esc(p.get('id'))}</td>"
            f"<td>{_esc(p.get('prompt_type'))}</td>"
            f"<td>{_esc(p.get('confidence'))}</td>"
            f"<td>{_esc(p.get('status'))}</td>"
            f"<td><code>{_esc(p.get('excerpt'))}</code></td>"
            f"<td>{_esc(p.get('created_at'))}</td>"
            f"</tr>\n"
        )

    # Build trace rows
    trace_rows = ""
    for t in traces:
        trace_rows += (
            f"<tr>"
            f"<td>{_esc(t.get('action_type'))}</td>"
            f"<td>{_esc(t.get('confidence'))}</td>"
            f"<td>{_esc(t.get('rule_id'))}</td>"
            f"<td>{_esc(t.get('timestamp'))}</td>"
            f"</tr>\n"
        )

    # Build audit rows
    audit_rows = ""
    for a in audit_events:
        audit_rows += (
            f"<tr>"
            f"<td>{_esc(a.get('id'))}</td>"
            f"<td>{_esc(a.get('event_type'))}</td>"
            f"<td>{_esc(a.get('timestamp'))}</td>"
            f"</tr>\n"
        )

    # JSON data block for machine consumption
    json_block = html.escape(json.dumps(bundle, indent=2, default=str))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AtlasBridge Session Export — {_esc(session_id)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
       background: #0d1117; color: #c9d1d9; line-height: 1.6; padding: 2rem; }}
h1 {{ font-size: 1.4rem; margin-bottom: 1rem; color: #58a6ff; }}
h2 {{ font-size: 1.1rem; margin: 1.5rem 0 0.75rem; color: #8b949e; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }}
th, td {{ padding: 0.5rem 0.75rem; text-align: left;
        border-bottom: 1px solid #30363d; font-size: 0.85rem; }}
th {{ color: #8b949e; font-weight: 600; text-transform: uppercase; font-size: 0.75rem; }}
code {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.8rem;
        background: #161b22; padding: 0.1rem 0.3rem; border-radius: 3px; }}
.banner {{ background: #1a1e24; border: 1px solid #30363d; text-align: center;
           padding: 6px; font-size: 0.75rem; font-weight: 600; color: #d29922;
           letter-spacing: 0.1em; margin-bottom: 1rem; border-radius: 4px; }}
.meta {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
         padding: 1rem; margin-bottom: 1.5rem; }}
.meta p {{ margin: 0.25rem 0; font-size: 0.9rem; }}
.meta strong {{ color: #8b949e; }}
details {{ margin-top: 1.5rem; }}
summary {{ cursor: pointer; color: #58a6ff; font-size: 0.9rem; }}
details pre {{ background: #161b22; border: 1px solid #30363d; border-radius: 4px;
              padding: 0.75rem; margin-top: 0.5rem; font-size: 0.8rem;
              white-space: pre-wrap; word-break: break-word; overflow-x: auto;
              font-family: "SFMono-Regular", Consolas, monospace; }}
.empty {{ color: #8b949e; font-style: italic; }}
</style>
</head>
<body>
<div class="banner">EXPORTED SESSION — READ-ONLY SNAPSHOT</div>
<h1>Session: {_esc(session.get("id"))}</h1>
<div class="meta">
<p><strong>Tool:</strong> {_esc(session.get("tool"))}</p>
<p><strong>Status:</strong> {_esc(session.get("status"))}</p>
<p><strong>Started:</strong> {_esc(session.get("started_at"))}</p>
<p><strong>Ended:</strong> {_esc(session.get("ended_at", "N/A"))}</p>
<p><strong>CWD:</strong> <code>{_esc(session.get("cwd"))}</code></p>
<p><strong>Exported:</strong> {_esc(bundle.get("exported_at"))}</p>
</div>

<h2>Prompts ({len(prompts)})</h2>
{
        "<p class='empty'>No prompts recorded.</p>"
        if not prompts
        else f'''<table>
<thead><tr><th>ID</th><th>Type</th><th>Confidence</th><th>Status</th><th>Excerpt</th><th>Created</th></tr></thead>
<tbody>{prompt_rows}</tbody>
</table>'''
    }

<h2>Decision Traces ({len(traces)})</h2>
{
        "<p class='empty'>No trace entries.</p>"
        if not traces
        else f'''<table>
<thead><tr><th>Action</th><th>Confidence</th><th>Rule</th><th>Timestamp</th></tr></thead>
<tbody>{trace_rows}</tbody>
</table>'''
    }

<h2>Audit Events ({len(audit_events)})</h2>
{
        "<p class='empty'>No audit events.</p>"
        if not audit_events
        else f'''<table>
<thead><tr><th>ID</th><th>Type</th><th>Timestamp</th></tr></thead>
<tbody>{audit_rows}</tbody>
</table>'''
    }

<details>
<summary>Raw JSON data</summary>
<pre>{json_block}</pre>
</details>
</body>
</html>"""
