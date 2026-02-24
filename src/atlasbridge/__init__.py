"""
AtlasBridge — Universal Human-in-the-Loop Control Plane for AI Developer Agents.

AtlasBridge sits between you and your AI coding agent. Whenever your agent pauses
and requires human input — approval, confirmation, a choice, or clarification —
AtlasBridge forwards that prompt to your phone. You respond from your phone.
AtlasBridge relays your decision back to the CLI. Execution resumes.

Package layout (src/atlasbridge/):
  core/       — daemon, scheduler, session, prompt, routing, store, audit
  os/tty/     — PTY supervisor per platform (macOS, Linux)
  adapters/   — CLI tool adapters (Claude Code, OpenAI, ...)
  channels/   — notification channels (Telegram, Slack, ...)
  cli/        — Click CLI entry point
"""

__version__ = "1.1.3"
__all__ = ["__version__"]
