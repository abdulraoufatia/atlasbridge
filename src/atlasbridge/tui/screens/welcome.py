"""
Welcome / Overview screen — the first screen users see.

Shows different content based on whether AtlasBridge is configured:
- Not configured: onboarding copy + setup action
- Configured: live status summary + quick actions
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static


class WelcomeScreen(Screen):  # type: ignore[type-arg]
    """Welcome and quick-action hub."""

    BINDINGS = [
        Binding("s", "setup", "Setup", show=True),
        Binding("d", "doctor", "Doctor", show=True),
        Binding("r", "run_tool", "Run tool", show=False),
        Binding("l", "sessions", "Sessions", show=False),
        Binding("t", "toggle_daemon", "Start/Stop daemon", show=False),
        Binding("q", "app.quit", "Quit", show=True),
    ]

    def compose(self) -> ComposeResult:
        from atlasbridge.tui.services import ConfigService, DaemonService

        self._state = ConfigService.load_state()
        self._daemon = DaemonService.get_status()

        yield Header(show_clock=True)

        with Static(id="welcome-container"):
            yield Label("AtlasBridge", id="brand-header")
            yield Label(
                "Human-in-the-loop control plane for AI developer agents", id="brand-tagline"
            )

            if self._state.is_configured:
                yield self._configured_body()
            else:
                yield self._unconfigured_body()

            yield Label(
                "Prefer CLI? Run `atlasbridge setup --help` for non-interactive setup.",
                id="footer-tip",
            )

        yield Footer()

    def _unconfigured_body(self) -> Static:
        text = (
            "You're not set up yet. Let's fix that.\n\n"
            "AtlasBridge keeps your AI CLI sessions moving when they pause for input.\n"
            "When your agent asks a question, AtlasBridge forwards it to your phone\n"
            "(Telegram or Slack). You reply there — AtlasBridge resumes the CLI.\n\n"
            "Setup takes ~2 minutes:\n"
            "  1) Choose a channel (Telegram or Slack)\n"
            "  2) Add your credentials (kept local)\n"
            "  3) Allowlist your user ID(s)\n"
            "  4) Run a quick health check\n\n"
            "  [S] Setup AtlasBridge  (recommended)\n"
            "  [D] Run Doctor         (check environment)\n"
            "  [Q] Quit"
        )
        return Static(text, id="status-box")

    def _configured_body(self) -> Static:
        from atlasbridge.tui.state import DaemonStatus

        daemon_line = "Running" if self._daemon == DaemonStatus.RUNNING else "Not running"
        channel_line = self._state.channel_summary or "none configured"

        text = (
            "AtlasBridge is ready.\n\n"
            f"  Config:           Loaded\n"
            f"  Daemon:           {daemon_line}\n"
            f"  Channel:          {channel_line}\n"
            f"  Sessions:         {self._state.session_count}\n"
            f"  Pending prompts:  {self._state.pending_prompt_count}\n\n"
            "  [R] Run a tool      [S] Sessions\n"
            "  [L] Logs (tail)     [D] Doctor\n"
            "  [T] Start/Stop daemon\n"
            "  [Q] Quit"
        )
        return Static(text, id="status-box")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_setup(self) -> None:
        from atlasbridge.tui.screens.setup import SetupScreen

        self.app.push_screen(SetupScreen())

    def action_doctor(self) -> None:
        from atlasbridge.tui.screens.doctor import DoctorScreen

        self.app.push_screen(DoctorScreen())

    def action_run_tool(self) -> None:
        if not self._state.is_configured:
            self.notify("Run `atlasbridge setup` first.", severity="warning")
            return
        self.notify("Use `atlasbridge run claude` in your terminal.", severity="information")

    def action_sessions(self) -> None:
        from atlasbridge.tui.screens.sessions import SessionsScreen

        self.app.push_screen(SessionsScreen())

    def action_toggle_daemon(self) -> None:
        from atlasbridge.tui.state import DaemonStatus

        if self._daemon == DaemonStatus.RUNNING:
            self.notify("Use `atlasbridge stop` in your terminal to stop the daemon.")
        else:
            self.notify("Use `atlasbridge start` in your terminal to start the daemon.")
