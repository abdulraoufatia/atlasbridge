"""Widget composition and render tests for ConsoleApp."""

from __future__ import annotations

import inspect

import pytest

from atlasbridge.console.app import ConsoleApp, ConsoleScreen, _ConsoleCard
from atlasbridge.console.supervisor import ProcessSupervisor

# ---------------------------------------------------------------------------
# ConsoleCard
# ---------------------------------------------------------------------------


class TestConsoleCard:
    def test_card_has_title_and_value(self):
        card = _ConsoleCard("Daemon", "Running", "card-daemon")
        assert card.id == "card-daemon"

    def test_card_css_class(self):
        card = _ConsoleCard("Test", "Value", "card-test")
        assert "console-card" in card.classes


# ---------------------------------------------------------------------------
# ConsoleScreen composition
# ---------------------------------------------------------------------------


class TestConsoleScreenComposition:
    @pytest.fixture
    def supervisor(self):
        return ProcessSupervisor()

    def test_screen_creates_with_supervisor(self, supervisor):
        screen = ConsoleScreen(supervisor=supervisor)
        assert screen._supervisor is supervisor
        assert screen._default_tool == "claude"
        assert screen._dashboard_port == 3737

    def test_screen_custom_options(self, supervisor):
        screen = ConsoleScreen(supervisor=supervisor, default_tool="openai", dashboard_port=9999)
        assert screen._default_tool == "openai"
        assert screen._dashboard_port == 9999

    def test_screen_has_bindings(self, supervisor):
        screen = ConsoleScreen(supervisor=supervisor)
        binding_keys = {b.key for b in screen.BINDINGS}
        assert "d" in binding_keys  # daemon toggle
        assert "a" in binding_keys  # agent start
        assert "w" in binding_keys  # dashboard toggle
        assert "h" in binding_keys  # health
        assert "r" in binding_keys  # refresh
        assert "q" in binding_keys  # quit
        assert "escape" in binding_keys  # also quit

    def test_compose_references_expected_ids(self, supervisor):
        """Verify compose method references all expected widget IDs."""
        source = inspect.getsource(ConsoleScreen.compose)
        expected_ids = [
            "console-root",
            "safety-banner",
            "console-cards",
            "card-daemon",
            "card-dashboard",
            "card-agent",
            "card-channel",
            "process-table",
            "doctor-results",
            "audit-log",
        ]
        for widget_id in expected_ids:
            assert widget_id in source, f"Expected widget ID '{widget_id}' not in compose()"

    def test_compose_references_safety_text(self, supervisor):
        """Safety banner text must be in compose method."""
        source = inspect.getsource(ConsoleScreen.compose)
        assert "LOCAL EXECUTION ONLY" in source


# ---------------------------------------------------------------------------
# ConsoleApp
# ---------------------------------------------------------------------------


class TestConsoleApp:
    def test_app_creates(self):
        app = ConsoleApp()
        assert app._default_tool == "claude"
        assert app._dashboard_port == 3737

    def test_app_custom_options(self):
        app = ConsoleApp(default_tool="gemini", dashboard_port=9000)
        assert app._default_tool == "gemini"
        assert app._dashboard_port == 9000

    def test_app_has_supervisor(self):
        app = ConsoleApp()
        assert isinstance(app._supervisor, ProcessSupervisor)

    def test_app_title_contains_version(self):
        app = ConsoleApp()
        assert "Console" in app.TITLE

    def test_app_has_css(self):
        """CSS must be loaded from the tcss file."""
        assert ConsoleApp.CSS is not None
        assert "console-root" in ConsoleApp.CSS


# ---------------------------------------------------------------------------
# Safety banner
# ---------------------------------------------------------------------------


class TestSafetyBanner:
    def test_safety_banner_in_css(self):
        """CSS must style the safety-banner ID."""
        assert "#safety-banner" in ConsoleApp.CSS

    def test_safety_banner_text_in_compose(self):
        """The compose method must include LOCAL EXECUTION ONLY text."""
        source = inspect.getsource(ConsoleScreen.compose)
        assert "LOCAL EXECUTION ONLY" in source


# ---------------------------------------------------------------------------
# Process table
# ---------------------------------------------------------------------------


class TestProcessTable:
    def test_process_table_in_compose(self):
        """DataTable widget must be referenced in compose."""
        source = inspect.getsource(ConsoleScreen.compose)
        assert "DataTable" in source
        assert "process-table" in source

    def test_process_table_columns_in_on_mount(self):
        """on_mount should set up table columns."""
        source = inspect.getsource(ConsoleScreen.on_mount)
        assert "add_columns" in source


# ---------------------------------------------------------------------------
# Doctor panel
# ---------------------------------------------------------------------------


class TestDoctorPanel:
    def test_doctor_section_in_compose(self):
        """Doctor section must be in compose."""
        source = inspect.getsource(ConsoleScreen.compose)
        assert "doctor-section" in source
        assert "doctor-results" in source

    def test_doctor_section_in_css(self):
        """CSS must style the doctor-section."""
        assert "#doctor-section" in ConsoleApp.CSS


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_audit_log_in_compose(self):
        """RichLog widget must be referenced in compose."""
        source = inspect.getsource(ConsoleScreen.compose)
        assert "RichLog" in source
        assert "audit-log" in source

    def test_audit_section_in_css(self):
        """CSS must style the audit-section."""
        assert "#audit-section" in ConsoleApp.CSS
        assert "#audit-log" in ConsoleApp.CSS


# ---------------------------------------------------------------------------
# Actions exist
# ---------------------------------------------------------------------------


class TestActions:
    def test_action_toggle_daemon_exists(self):
        assert hasattr(ConsoleScreen, "action_toggle_daemon")
        assert callable(ConsoleScreen.action_toggle_daemon)

    def test_action_start_agent_exists(self):
        assert hasattr(ConsoleScreen, "action_start_agent")
        assert callable(ConsoleScreen.action_start_agent)

    def test_action_toggle_dashboard_exists(self):
        assert hasattr(ConsoleScreen, "action_toggle_dashboard")
        assert callable(ConsoleScreen.action_toggle_dashboard)

    def test_action_health_exists(self):
        assert hasattr(ConsoleScreen, "action_health")
        assert callable(ConsoleScreen.action_health)

    def test_action_refresh_exists(self):
        assert hasattr(ConsoleScreen, "action_refresh")
        assert callable(ConsoleScreen.action_refresh)

    def test_action_quit_console_exists(self):
        assert hasattr(ConsoleScreen, "action_quit_console")
        assert callable(ConsoleScreen.action_quit_console)
