"""
AtlasBridge UI — Textual application shell.

Launched by ``atlasbridge`` (no args, TTY) or ``atlasbridge ui``.
"""

from __future__ import annotations

from importlib.resources import files

from textual.app import App, ComposeResult
from textual.binding import Binding

from atlasbridge import __version__

_CSS_TEXT: str = files("atlasbridge.ui.css").joinpath("atlasbridge.tcss").read_text("utf-8")


class AtlasBridgeApp(App):  # type: ignore[type-arg]
    """AtlasBridge interactive terminal UI."""

    TITLE = f"AtlasBridge {__version__}"
    CSS = _CSS_TEXT

    BINDINGS = [
        Binding("ctrl+c", "app.quit", "Quit", show=False, priority=True),
        Binding("q", "app.quit", "Quit", show=False),
    ]

    def compose(self) -> ComposeResult:
        # The welcome screen is pushed in on_mount; compose yields nothing here.
        return iter([])

    def on_mount(self) -> None:
        from atlasbridge.ui.screens.welcome import WelcomeScreen

        self.push_screen(WelcomeScreen())


def run() -> None:
    """Entry point called from the CLI."""
    AtlasBridgeApp().run()
