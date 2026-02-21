"""
AtlasBridge TUI — main Textual application.

Launched by `atlasbridge` (no args, if stdout is a TTY) or `atlasbridge ui`.
"""

from __future__ import annotations

from importlib.resources import files

from textual.app import App, ComposeResult
from textual.binding import Binding

from atlasbridge import __version__

_CSS_TEXT: str = files("atlasbridge.tui").joinpath("app.tcss").read_text("utf-8")


class AtlasBridgeApp(App):  # type: ignore[type-arg]
    """AtlasBridge interactive terminal UI."""

    TITLE = f"AtlasBridge {__version__}"
    CSS = _CSS_TEXT

    BINDINGS = [
        Binding("ctrl+c", "app.quit", "Quit", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        # Screens are pushed dynamically; compose just shows the welcome screen.
        from atlasbridge.tui.screens.welcome import WelcomeScreen

        return WelcomeScreen().compose()

    def on_mount(self) -> None:
        from atlasbridge.tui.screens.welcome import WelcomeScreen

        self.push_screen(WelcomeScreen())


def run() -> None:
    """Entry point called from the CLI."""
    AtlasBridgeApp().run()
