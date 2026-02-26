"""
WelcomeScreen — the first screen users see.

Widget tree::

    #welcome-root  (Static — outer scroll container)
      #welcome-grid  (Static — two-column grid when configured)
        #brand-header   (Label)
        #brand-tagline  (Label)
        #status-cards   (StatusCards — only when configured)
        #guidance       (Static — dynamic next-step guidance)
        #welcome-body   (Static — first-run copy OR configured quick-actions)
      #welcome-footer-tip  (Label)

Keybindings:
  s  — open Setup Wizard
  d  — open Doctor screen
  r  — run a tool (notify if not configured)
  q  — quit
  esc — quit
  ?   — show help
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static


class WelcomeScreen(Screen):
    """Welcome screen and quick-action hub."""

    BINDINGS = [
        Binding("s", "setup", "Setup", show=True),
        Binding("d", "doctor", "Doctor", show=True),
        Binding("r", "run_tool", "Run tool", show=False),
        Binding("l", "sessions", "Sessions", show=False),
        Binding("q", "app.quit", "Quit", show=True),
        Binding("escape", "app.quit", "Quit", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
    ]

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        from atlasbridge.ui.services import ConfigService, DaemonService
        from atlasbridge.ui.state import guidance_message

        self._app_state = ConfigService.load_state()
        self._daemon_status = DaemonService.get_status()

        yield Header(show_clock=True)

        with Static(id="welcome-root"):
            with Static(id="welcome-grid"):
                yield Label("AtlasBridge", id="brand-header")
                yield Label(
                    "Autonomous runtime for AI developer agents with human oversight",
                    id="brand-tagline",
                )

                if self._app_state.is_configured:
                    from atlasbridge.ui.components.status_cards import StatusCards

                    yield StatusCards(self._app_state)

                # Dynamic guidance panel
                yield Static(
                    guidance_message(self._app_state, self._daemon_status),
                    id="guidance",
                )

                if self._app_state.is_configured:
                    yield self._configured_body()
                else:
                    yield self._first_run_body()

            yield Label(
                "Prefer the CLI? Run `atlasbridge setup --help` for non-interactive setup.",
                id="welcome-footer-tip",
            )

        yield Footer()

    # ------------------------------------------------------------------
    # Body helpers
    # ------------------------------------------------------------------

    def _first_run_body(self) -> Static:
        text = (
            "  [S] Setup AtlasBridge  (recommended)\n"
            "  [D] Run Doctor         (check environment)\n"
            "  [Q] Quit"
        )
        return Static(text, id="welcome-body")

    def _configured_body(self) -> Static:
        text = "  [S] Re-run Setup    [L] Sessions\n  [D] Doctor          [Q] Quit"
        return Static(text, id="welcome-body")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_setup(self) -> None:
        from atlasbridge.ui.screens.wizard import SetupWizardScreen

        self.app.push_screen(SetupWizardScreen())

    def action_doctor(self) -> None:
        from atlasbridge.ui.screens.doctor import DoctorScreen

        self.app.push_screen(DoctorScreen())

    def action_run_tool(self) -> None:
        if not self._app_state.is_configured:
            self.notify("Run `atlasbridge setup` first.", severity="warning")
            return
        self.notify("Use `atlasbridge run claude` in your terminal.", severity="information")

    def action_sessions(self) -> None:
        from atlasbridge.ui.screens.sessions import SessionsScreen

        self.app.push_screen(SessionsScreen())

    def action_show_help(self) -> None:
        self.notify(
            "s=Setup  d=Doctor  r=Run  l=Sessions  q=Quit",
            title="Keyboard shortcuts",
            severity="information",
            timeout=6,
        )
