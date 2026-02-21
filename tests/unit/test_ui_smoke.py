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
