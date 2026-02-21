"""
Structured logging configuration for AtlasBridge.

Uses structlog to provide machine-parseable, context-rich log output.
All log entries include a timestamp and can carry bound context
(session_id, prompt_id) that flows through the entire prompt lifecycle.

Setup:
    Call ``configure_logging()`` once at process startup (before any
    subsystem emits a log).  Every module then uses::

        import structlog
        logger = structlog.get_logger()

    Bound loggers carry context automatically::

        log = logger.bind(session_id="abc123")
        log.info("prompt_detected", prompt_type="yes_no", confidence="high")
        # → {"event": "prompt_detected", "session_id": "abc123",
        #    "prompt_type": "yes_no", "confidence": "high",
        #    "timestamp": "2026-02-21T...", "level": "info"}

Why structlog over stdlib logging:
    1. Key-value pairs instead of format strings → machine-parseable
    2. Bound context (session_id) flows without passing it to every call
    3. Processors pipeline → add timestamps, filter secrets, format output
    4. In dev: coloured console output.  In production: JSON lines.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(
    *,
    level: str = "INFO",
    json_output: bool = False,
) -> None:
    """
    Configure structlog + stdlib logging for the process.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, emit JSON lines (for production / log aggregation).
                     If False, emit coloured human-readable output (for dev).

    Call this once, early in the process lifetime.  Calling it again is
    safe but has no effect (idempotent guard).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors applied to every log entry
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        # Production: JSON lines for log aggregation (ELK, Datadog, CloudWatch)
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Development: coloured, human-readable console output
        renderer = structlog.dev.ConsoleRenderer(
            colors=sys.stderr.isatty(),
        )

    structlog.configure(
        processors=[
            *shared_processors,
            # Prepare for stdlib integration
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib root logger so that modules using logging.getLogger()
    # also emit structured output through the same pipeline.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Idempotent: don't add duplicate handlers on repeated calls
    if not any(
        isinstance(h, logging.StreamHandler)
        and isinstance(getattr(h, "formatter", None), structlog.stdlib.ProcessorFormatter)
        for h in root.handlers
    ):
        root.addHandler(handler)

    root.setLevel(log_level)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("slack_sdk").setLevel(logging.WARNING)
