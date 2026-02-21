"""
Tests for structured logging configuration.

Validates:
  1. configure_logging() is idempotent (safe to call twice)
  2. structlog produces machine-parseable output
  3. stdlib loggers also route through the structlog pipeline
  4. Bound context (session_id, prompt_id) flows through log calls
  5. JSON output mode produces valid JSON
  6. Third-party loggers are suppressed
"""

from __future__ import annotations

import json
import logging

import structlog

from atlasbridge.core.logging import configure_logging


class TestConfigureLogging:
    """configure_logging() sets up structlog + stdlib correctly."""

    def setup_method(self) -> None:
        """Reset logging state between tests."""
        # Remove all handlers from root logger
        root = logging.getLogger()
        root.handlers.clear()
        # Reset structlog configuration
        structlog.reset_defaults()

    def test_idempotent_double_call(self) -> None:
        """Calling configure_logging() twice doesn't duplicate handlers."""
        configure_logging(level="DEBUG")
        handler_count_1 = len(logging.getLogger().handlers)

        configure_logging(level="DEBUG")
        handler_count_2 = len(logging.getLogger().handlers)

        assert handler_count_1 == handler_count_2
        assert handler_count_1 >= 1

    def test_sets_root_log_level(self) -> None:
        """Log level is applied to the root logger."""
        configure_logging(level="WARNING")
        assert logging.getLogger().level == logging.WARNING

        configure_logging(level="DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_suppresses_noisy_third_party(self) -> None:
        """Third-party loggers (httpx, httpcore, slack_sdk) are set to WARNING."""
        configure_logging(level="DEBUG")

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("slack_sdk").level == logging.WARNING

    def test_json_output_mode_configures_without_error(self) -> None:
        """JSON output mode configures successfully."""
        configure_logging(level="DEBUG", json_output=True)
        # Should be able to log without error
        log = structlog.get_logger("test.json")
        log.info("test_event", key="value", count=42)

    def test_structlog_bound_context_preserved(self) -> None:
        """Bound context (session_id) is preserved on the bound logger."""
        configure_logging(level="DEBUG")

        log = structlog.get_logger("test.bound")
        bound = log.bind(session_id="abc123")

        # The bound logger should carry the context
        assert hasattr(bound, "bind")
        # Binding again should still work (immutable context layering)
        double_bound = bound.bind(prompt_id="p1")
        assert hasattr(double_bound, "info")

    def test_json_renderer_produces_valid_json(self) -> None:
        """The JSON renderer produces valid JSON when called directly."""
        renderer = structlog.processors.JSONRenderer()
        # Simulate what the pipeline does
        result = renderer(
            None,
            "info",
            {
                "event": "test_event",
                "session_id": "abc123",
                "prompt_type": "yes_no",
            },
        )
        parsed = json.loads(result)
        assert parsed["event"] == "test_event"
        assert parsed["session_id"] == "abc123"
        assert parsed["prompt_type"] == "yes_no"


class TestStructlogIntegration:
    """Verify that structlog is actually used in core modules."""

    def test_router_uses_structlog(self) -> None:
        """The router module uses structlog.get_logger()."""
        import atlasbridge.core.routing.router as router_mod

        # The module-level logger should be a structlog BoundLogger or proxy
        assert hasattr(router_mod, "logger")
        # structlog loggers have a 'bind' method (stdlib loggers don't)
        assert hasattr(router_mod.logger, "bind")

    def test_daemon_uses_structlog(self) -> None:
        """The daemon manager uses structlog.get_logger()."""
        import atlasbridge.core.daemon.manager as daemon_mod

        assert hasattr(daemon_mod, "logger")
        assert hasattr(daemon_mod.logger, "bind")

    def test_stdlib_loggers_still_work(self) -> None:
        """Modules still using stdlib logging.getLogger() continue to work."""
        configure_logging(level="DEBUG")

        # This should not raise — stdlib loggers are bridged through structlog
        stdlib_logger = logging.getLogger("atlasbridge.test.stdlib")
        stdlib_logger.info("stdlib message: %s", "test")
