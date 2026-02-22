"""
StatusCards — compact status summary widget for the Welcome screen.

Displays four status cards:
  • Config   — Loaded / Not found / Error
  • Daemon   — Running / Stopped / Unknown
  • Channel  — telegram / slack / none
  • Sessions — N active  (N pending)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static

from atlasbridge.ui.state import AppState, ConfigStatus, DaemonStatus


class _Card(Static):
    """Single status card."""

    DEFAULT_CSS = """
    _Card {
        width: 1fr;
        height: 5;
        padding: 0 1;
        border: tall $panel-lighten-1;
    }
    _Card Label { width: 100%; }
    _Card .card-title { color: $text-muted; text-style: bold; }
    _Card .card-value { color: $accent; }
    """

    def __init__(self, title: str, value: str, card_id: str) -> None:
        super().__init__(id=card_id)
        self._title = title
        self._value = value

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="card-title")
        yield Label(self._value, classes="card-value", id=f"{self.id}-value")

    def update_value(self, value: str) -> None:
        try:
            self.query_one(f"#{self.id}-value", Label).update(value)
        except Exception:  # noqa: BLE001
            pass


class StatusCards(Widget):
    """
    Four-card status row.

    Widget ID convention: ``id="status-cards"``
    Child card IDs: ``card-config``, ``card-daemon``, ``card-channel``, ``card-sessions``.
    """

    state: reactive[AppState] = reactive(AppState, recompose=True)

    DEFAULT_CSS = """
    StatusCards {
        layout: horizontal;
        height: 7;
        width: 100%;
    }
    """

    def __init__(self, app_state: AppState | None = None) -> None:
        super().__init__(id="status-cards")
        if app_state is not None:
            self.state = app_state

    def compose(self) -> ComposeResult:
        st = self.state if isinstance(self.state, AppState) else AppState()

        # Config card
        config_val = {
            ConfigStatus.LOADED: "Loaded",
            ConfigStatus.NOT_FOUND: "Not found",
            ConfigStatus.ERROR: "Error",
        }.get(st.config_status, "—")
        yield _Card("Config", config_val, "card-config")

        # Daemon card
        daemon_val = {
            DaemonStatus.RUNNING: "Running",
            DaemonStatus.STOPPED: "Stopped",
            DaemonStatus.UNKNOWN: "Unknown",
        }.get(st.daemon_status, "—")
        yield _Card("Daemon", daemon_val, "card-daemon")

        # Channel card
        yield _Card("Channel", st.channel_summary or "none", "card-channel")

        # Sessions card
        sessions_val = f"{st.session_count} active" + (
            f"  ({st.pending_prompt_count} pending)" if st.pending_prompt_count else ""
        )
        yield _Card("Sessions", sessions_val, "card-sessions")
