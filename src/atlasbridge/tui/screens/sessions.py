"""Sessions screen — lists active and recent AtlasBridge sessions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, Static


class SessionsScreen(Screen):  # type: ignore[type-arg]
    """Active and recent session list."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Static(id="sessions-container"):
            yield Label("Sessions", id="wizard-title")
            tbl: DataTable = DataTable(id="sessions-table")  # type: ignore[type-arg]
            tbl.add_columns("ID", "Tool", "Status", "Started")
            yield tbl
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._load_sessions)

    def _load_sessions(self) -> None:
        from atlasbridge.tui.services import SessionService

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
