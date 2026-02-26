"""
SessionsScreen — active and recent session list.

Widget tree::

    Header
    #sessions-root  (Static)
      #sessions-title  (Label)
      #sessions-table  (DataTable)
    Footer

Keybindings:
  escape — back to welcome
  r      — refresh table
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, Static


class SessionsScreen(Screen):
    """Active and recent session list."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Static(id="sessions-root"):
            yield Label("Sessions", id="sessions-title")
            tbl: DataTable = DataTable(id="sessions-table")
            tbl.add_columns("ID", "Tool", "Status", "Started")
            yield tbl
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._load_sessions)

    def _load_sessions(self) -> None:
        from atlasbridge.ui.services import SessionService

        rows = SessionService.list_sessions()
        try:
            tbl = self.query_one("#sessions-table", DataTable)
            tbl.clear()
            if not rows:
                tbl.add_row("—", "—", "No sessions found", "—")
            else:
                for row in rows:
                    tbl.add_row(
                        str(row.get("session_id", ""))[:12] + "…",
                        str(row.get("tool", "—")),
                        str(row.get("status", "—")),
                        str(row.get("created_at", "—")),
                    )
        except Exception:  # noqa: BLE001
            pass

    def action_refresh(self) -> None:
        self._load_sessions()
