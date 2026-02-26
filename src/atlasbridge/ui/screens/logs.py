"""
LogsScreen — tail the AtlasBridge audit log (last 100 events).

Widget tree::

    Header
    #logs-root  (Static)
      #logs-title  (Label)
      #log-view    (RichLog)
    Footer

Keybindings:
  escape — back to welcome
  r      — refresh log
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, RichLog, Static


class LogsScreen(Screen):
    """Audit log tail view."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Static(id="logs-root"):
            yield Label("Audit Log", id="logs-title")
            yield RichLog(highlight=True, markup=True, id="log-view")
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._load_logs)

    def _load_logs(self) -> None:
        from atlasbridge.ui.services import LogsService

        events = LogsService.read_recent(100)
        try:
            log = self.query_one("#log-view", RichLog)
            log.clear()
            if not events:
                log.write("[dim]No audit log events found.[/dim]")
                return
            for evt in events:
                ts = evt.get("timestamp", "?")
                event_type = evt.get("event_type", "?")
                detail = evt.get("detail", "")
                log.write(f"[dim]{ts}[/dim]  [cyan]{event_type:<25}[/cyan]  {detail}")
        except Exception:  # noqa: BLE001
            pass

    def action_refresh(self) -> None:
        self._load_logs()
