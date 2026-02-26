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


def test_ui_app_has_css_class_variable() -> None:
    """AtlasBridgeApp.CSS must be a non-empty string (not a file path)."""
    from atlasbridge.ui.app import AtlasBridgeApp

    assert isinstance(AtlasBridgeApp.CSS, str)
    assert len(AtlasBridgeApp.CSS) > 100
    assert "Screen" in AtlasBridgeApp.CSS


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

    # Point config lookup at a non-existent path via ATLASBRIDGE_CONFIG so no config file exists.
    monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(tmp_path / "config.toml"))
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


def test_wizard_uses_container_not_static() -> None:
    """Wizard steps must use Container (not Static) so Input widgets render."""
    import inspect

    from atlasbridge.ui.screens.wizard import SetupWizardScreen

    src = inspect.getsource(SetupWizardScreen)
    assert "from textual.containers import Container" in inspect.getsource(
        inspect.getmodule(SetupWizardScreen)  # type: ignore[arg-type]
    ), "wizard must import Container from textual.containers"
    # Step methods must not monkey-patch compose on Static
    assert "s.compose = lambda" not in src, "Must not monkey-patch compose on Static"


def test_wizard_state_step_transitions_preserve_data() -> None:
    """Navigating forward and back preserves all entered data."""
    from atlasbridge.ui.state import WizardState

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


# ---------------------------------------------------------------------------
# Dynamic guidance messages
# ---------------------------------------------------------------------------


def test_guidance_not_configured() -> None:
    """Unconfigured state shows setup prompt and workflow example."""
    from atlasbridge.ui.state import AppState, DaemonStatus, guidance_message

    msg = guidance_message(AppState(), DaemonStatus.UNKNOWN)
    assert "setup wizard" in msg.lower()
    assert "How it works" in msg
    assert "atlasbridge run claude" in msg


def test_guidance_configured_daemon_stopped() -> None:
    """Configured but daemon not running shows start instructions."""
    from atlasbridge.ui.state import (
        AppState,
        ConfigStatus,
        DaemonStatus,
        guidance_message,
    )

    state = AppState(config_status=ConfigStatus.LOADED)
    msg = guidance_message(state, DaemonStatus.STOPPED)
    assert "start the daemon" in msg.lower()
    assert "atlasbridge run claude" in msg
    assert "How it works" in msg


def test_guidance_daemon_running_no_sessions() -> None:
    """Daemon running with no sessions shows run tool prompt."""
    from atlasbridge.ui.state import (
        AppState,
        ConfigStatus,
        DaemonStatus,
        guidance_message,
    )

    state = AppState(config_status=ConfigStatus.LOADED, session_count=0)
    msg = guidance_message(state, DaemonStatus.RUNNING)
    assert "no active sessions" in msg.lower()
    assert "atlasbridge run claude" in msg


def test_guidance_active_sessions() -> None:
    """Active sessions shows session count and management hint."""
    from atlasbridge.ui.state import (
        AppState,
        ConfigStatus,
        DaemonStatus,
        guidance_message,
    )

    state = AppState(config_status=ConfigStatus.LOADED, session_count=3)
    msg = guidance_message(state, DaemonStatus.RUNNING)
    assert "3 active session" in msg
    assert "[L]" in msg


def test_guidance_is_importable_from_ui_state() -> None:
    """guidance_message must be accessible via ui.state."""
    from atlasbridge.ui.state import guidance_message

    assert callable(guidance_message)


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


# ---------------------------------------------------------------------------
# Module architecture — tui/ fully removed
# ---------------------------------------------------------------------------


def test_tui_package_does_not_exist() -> None:
    """tui/ was removed — no atlasbridge.tui package should exist."""
    from pathlib import Path

    tui_dir = Path(__file__).resolve().parents[2] / "src" / "atlasbridge" / "tui"
    assert not tui_dir.exists(), "src/atlasbridge/tui/ should have been removed"


def test_no_tui_imports_in_src() -> None:
    """No source file should import from atlasbridge.tui."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "atlasbridge"
    violations: list[str] = []
    for pyfile in src.rglob("*.py"):
        try:
            tree = ast.parse(pyfile.read_text(), filename=str(pyfile))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("atlasbridge.tui"):
                    violations.append(f"{pyfile.name}: {node.module}")
    assert not violations, "Found tui imports in src/:\n" + "\n".join(
        f"  - {v}" for v in violations
    )
