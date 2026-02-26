"""
DoctorScreen — environment and configuration health check.

Widget tree::

    Header
    #doctor-root  (Static)
      #doctor-title   (Label)
      #checks-body    (Label — result lines, updated after mount)
    Footer

Keybindings:
  escape — back to welcome
  r      — re-run checks
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static


class DoctorScreen(Screen):
    """Environment and configuration health check."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("r", "refresh_checks", "Re-run", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Static(id="doctor-root"):
            yield Label("AtlasBridge Doctor", id="doctor-title")
            yield Label("Checking environment…", id="checks-body")
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._run_checks)

    def _run_checks(self) -> None:
        from atlasbridge.ui.services import DoctorService

        checks = DoctorService.run_checks()
        lines = []
        for c in checks:
            status = c.get("status", "?")
            name = c.get("name", "?")
            detail = c.get("detail", "")
            icon = {"pass": "✓", "warn": "⚠", "fail": "✗", "skip": "─"}.get(status, "─")
            lines.append(f"  {icon}  {name}: {detail}")

        all_pass = all(c.get("status") in ("pass", "skip") for c in checks)
        lines.append("")
        lines.append("All checks passed ✓" if all_pass else "Some checks need attention.")

        try:
            self.query_one("#checks-body", Label).update("\n".join(lines))
        except Exception:  # noqa: BLE001
            pass

    def action_refresh_checks(self) -> None:
        try:
            self.query_one("#checks-body", Label).update("Re-checking…")
        except Exception:  # noqa: BLE001
            pass
        self.call_after_refresh(self._run_checks)
