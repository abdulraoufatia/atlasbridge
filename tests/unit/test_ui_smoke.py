"""
Smoke tests for ``src/atlasbridge/ui/``.

These tests verify:
  - All ui modules are importable without error
  - Key classes can be instantiated
  - The CLI registers the `ui` command
  - ``atlasbridge ui --help`` exits 0 and mentions the expected text
"""

from __future__ import annotations

from click.testing import CliRunner

# ---------------------------------------------------------------------------
# Import smoke tests — no Textual running, just import checks
# ---------------------------------------------------------------------------


def test_ui_package_importable() -> None:
    import atlasbridge.ui  # noqa: F401


def test_ui_state_importable() -> None:
    from atlasbridge.ui.state import (
        AppState,
        ChannelStatus,
        ConfigStatus,
        DaemonStatus,
        WizardState,
    )

    assert AppState
    assert ChannelStatus
    assert ConfigStatus
    assert DaemonStatus
    assert WizardState


def test_ui_polling_importable() -> None:
    from atlasbridge.ui.polling import POLL_INTERVAL_SECONDS, poll_state

    assert POLL_INTERVAL_SECONDS == 5.0
    assert callable(poll_state)


def test_ui_app_importable() -> None:
    from atlasbridge.ui.app import AtlasBridgeApp, run

    assert AtlasBridgeApp
    assert callable(run)


# ---------------------------------------------------------------------------
# CSS resource loading regression tests (prevents StylesheetError on install)
# ---------------------------------------------------------------------------


def test_ui_css_resource_loads_non_empty() -> None:
    """CSS must be loadable via importlib.resources (works in wheel installs)."""
    from importlib.resources import files

    css = files("atlasbridge.ui.css").joinpath("atlasbridge.tcss").read_text("utf-8")
    assert len(css) > 100, "CSS content is too short — file may be empty or corrupted"
    assert "Screen" in css, "CSS should contain Screen selector"


def test_tui_css_resource_loads_non_empty() -> None:
    """Legacy TUI CSS must also be loadable via importlib.resources."""
    from importlib.resources import files

    css = files("atlasbridge.tui").joinpath("app.tcss").read_text("utf-8")
    assert len(css) > 0, "TUI CSS file should not be empty"


def test_ui_app_has_css_class_variable() -> None:
    """AtlasBridgeApp.CSS must be a non-empty string (not a file path)."""
    from atlasbridge.ui.app import AtlasBridgeApp

    assert isinstance(AtlasBridgeApp.CSS, str)
    assert len(AtlasBridgeApp.CSS) > 100
    assert "Screen" in AtlasBridgeApp.CSS


def test_tui_app_has_css_class_variable() -> None:
    """Legacy TUI AtlasBridgeApp.CSS must be a non-empty string."""
    from atlasbridge.tui.app import AtlasBridgeApp

    assert isinstance(AtlasBridgeApp.CSS, str)
    assert len(AtlasBridgeApp.CSS) > 0


def test_ui_components_importable() -> None:
    from atlasbridge.ui.components.status_cards import StatusCards

    assert StatusCards


def test_ui_screens_importable() -> None:
    from atlasbridge.ui.screens.complete import SetupCompleteScreen
    from atlasbridge.ui.screens.doctor import DoctorScreen
    from atlasbridge.ui.screens.logs import LogsScreen
    from atlasbridge.ui.screens.sessions import SessionsScreen
    from atlasbridge.ui.screens.welcome import WelcomeScreen
    from atlasbridge.ui.screens.wizard import SetupWizardScreen

    assert WelcomeScreen
    assert SetupWizardScreen
    assert SetupCompleteScreen
    assert SessionsScreen
    assert LogsScreen
    assert DoctorScreen


# ---------------------------------------------------------------------------
# State re-exports
# ---------------------------------------------------------------------------


def test_ui_state_reexports_wizard_state() -> None:
    from atlasbridge.ui.state import WIZARD_STEPS, WIZARD_TOTAL, WizardState

    ws = WizardState()
    assert ws.step == 0
    assert ws.channel == "telegram"
    assert WIZARD_TOTAL == len(WIZARD_STEPS)


def test_ui_state_reexports_app_state() -> None:
    from atlasbridge.ui.state import AppState, ConfigStatus

    state = AppState()
    assert state.config_status == ConfigStatus.NOT_FOUND
    assert not state.is_configured


# ---------------------------------------------------------------------------
# Polling function — called without infrastructure (returns graceful default)
# ---------------------------------------------------------------------------


def test_poll_state_returns_app_state_when_no_config(tmp_path, monkeypatch) -> None:
    from atlasbridge.ui.polling import poll_state
    from atlasbridge.ui.state import AppState, ConfigStatus

    # Point atlasbridge_dir at an empty tmp dir so no config file exists.
    monkeypatch.setenv("ATLASBRIDGE_DATA_DIR", str(tmp_path))
    result = poll_state()
    assert isinstance(result, AppState)
    assert result.config_status in (ConfigStatus.NOT_FOUND, ConfigStatus.ERROR)


# ---------------------------------------------------------------------------
# CLI smoke — `ui` command is registered
# ---------------------------------------------------------------------------


def test_cli_has_ui_command() -> None:
    from atlasbridge.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ui" in result.output


def test_cli_ui_help_exits_zero() -> None:
    from atlasbridge.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["ui", "--help"])
    assert result.exit_code == 0
    assert "TUI" in result.output or "terminal" in result.output.lower()


# ---------------------------------------------------------------------------
# Wizard screen — help constants, recompose-based navigation
# ---------------------------------------------------------------------------


def test_wizard_screen_has_help_constants() -> None:
    """SetupWizardScreen exposes Telegram and Slack help text constants."""
    from atlasbridge.ui.screens.wizard import _SLACK_HELP, _TELEGRAM_HELP

    assert "BotFather" in _TELEGRAM_HELP
    assert "@userinfobot" in _TELEGRAM_HELP
    assert "xoxb" in _SLACK_HELP
    assert "xapp" in _SLACK_HELP


def test_wizard_screen_has_h_binding() -> None:
    """SetupWizardScreen should bind 'h' for help."""
    from atlasbridge.ui.screens.wizard import SetupWizardScreen

    keys = [b.key for b in SetupWizardScreen.BINDINGS]
    assert "h" in keys


def test_wizard_screen_uses_recompose() -> None:
    """action_next_step and action_prev_step must call recompose, not refresh."""
    import inspect

    from atlasbridge.ui.screens.wizard import SetupWizardScreen

    next_src = inspect.getsource(SetupWizardScreen.action_next_step)
    prev_src = inspect.getsource(SetupWizardScreen.action_prev_step)
    assert "recompose" in next_src, "action_next_step should use recompose()"
    assert "recompose" in prev_src, "action_prev_step should use recompose()"
    assert "refresh(layout" not in next_src, "Must not use refresh(layout=True)"
    assert "refresh(layout" not in prev_src, "Must not use refresh(layout=True)"


def test_tui_setup_screen_uses_recompose() -> None:
    """Legacy tui SetupScreen._refresh_screen must use recompose."""
    import inspect

    from atlasbridge.tui.screens.setup import SetupScreen

    src = inspect.getsource(SetupScreen._refresh_screen)
    assert "recompose" in src
    assert "refresh(layout" not in src


def test_wizard_state_step_transitions_preserve_data() -> None:
    """Navigating forward and back preserves all entered data."""
    from atlasbridge.tui.state import WizardState

    w = WizardState(channel="slack", token="xoxb-test", app_token="xapp-test", users="U123")
    w2 = w.next()
    w3 = w2.prev()
    assert w3.channel == "slack"
    assert w3.token == "xoxb-test"
    assert w3.app_token == "xapp-test"
    assert w3.users == "U123"


def test_channel_token_setup_docs_exist() -> None:
    """docs/channel-token-setup.md must exist and contain key sections."""
    from pathlib import Path

    doc = Path(__file__).resolve().parents[2] / "docs" / "channel-token-setup.md"
    assert doc.exists(), f"Expected {doc} to exist"
    content = doc.read_text()
    assert "Telegram Bot Token" in content
    assert "Slack Bot Token" in content
    assert "BotFather" in content
    assert "xoxb-" in content
    assert "xapp-" in content


def test_cli_ui_non_tty_exits_nonzero(monkeypatch) -> None:
    """``atlasbridge ui`` without a TTY should exit 1."""
    import sys as _sys

    from atlasbridge.cli.main import cli

    runner = CliRunner()
    # CliRunner provides a non-TTY stdout by default
    monkeypatch.setattr(_sys.stdout, "isatty", lambda: False, raising=False)
    result = runner.invoke(cli, ["ui"])
    # Should exit 1 (TTY required)
    assert result.exit_code != 0
