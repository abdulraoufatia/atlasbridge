"""
ConsoleApp — AtlasBridge Operator Console.

Single-screen Textual app that manages daemon, dashboard, and agent
subprocesses with live status polling, inline diagnostics, and audit
log tailing.
"""

from __future__ import annotations

from importlib.resources import files

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, RichLog, Static

from atlasbridge import __version__
from atlasbridge.console.supervisor import ProcessSupervisor

_CSS_TEXT: str = files("atlasbridge.console.css").joinpath("console.tcss").read_text("utf-8")


# ---------------------------------------------------------------------------
# Status card (local to console — avoids cross-import with ui/components)
# ---------------------------------------------------------------------------


class _ConsoleCard(Static):  # type: ignore[type-arg]
    """Single status card for the console."""

    def __init__(self, title: str, value: str, card_id: str) -> None:
        super().__init__(id=card_id, classes="console-card")
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


# ---------------------------------------------------------------------------
# Console screen
# ---------------------------------------------------------------------------


class ConsoleScreen(Screen):  # type: ignore[type-arg]
    """Main operator console screen."""

    BINDINGS = [
        Binding("d", "toggle_daemon", "Daemon", show=True),
        Binding("a", "start_agent", "Agent", show=True),
        Binding("w", "toggle_dashboard", "Web", show=True),
        Binding("h", "health", "Health", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("q", "quit_console", "Quit", show=True),
        Binding("escape", "quit_console", "Quit", show=False),
    ]

    def __init__(
        self,
        supervisor: ProcessSupervisor,
        default_tool: str = "claude",
        dashboard_port: int = 8787,
    ) -> None:
        super().__init__()
        self._supervisor = supervisor
        self._default_tool = default_tool
        self._dashboard_port = dashboard_port

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="console-root"):
            # Safety banner
            yield Static(
                " OPERATOR CONSOLE — LOCAL EXECUTION ONLY",
                id="safety-banner",
            )

            # Status cards
            with Horizontal(id="console-cards"):
                yield _ConsoleCard("Daemon", "checking...", "card-daemon")
                yield _ConsoleCard("Dashboard", "checking...", "card-dashboard")
                yield _ConsoleCard("Agent", "checking...", "card-agent")
                yield _ConsoleCard("Channel", "checking...", "card-channel")

            # Process table
            with Vertical(id="process-section"):
                yield Label("Managed Processes", id="process-title")
                yield DataTable(id="process-table")

            # Doctor panel
            with Vertical(id="doctor-section"):
                yield Label("Doctor", id="doctor-title")
                yield Label("Press [h] to run health check", id="doctor-results")

            # Audit log
            with Vertical(id="audit-section"):
                yield Label("Audit Log (recent)", id="audit-title")
                yield RichLog(id="audit-log", wrap=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        # Set up process table columns
        table = self.query_one("#process-table", DataTable)
        table.add_columns("TYPE", "PID", "STATUS", "UPTIME", "INFO")

        # Initial poll
        self._do_poll()

        # Set up periodic polling
        self.set_interval(2.0, self._do_poll)

        # Load initial audit log
        self._load_audit_log()

    def _do_poll(self) -> None:
        """Poll all process statuses and update the UI."""
        try:
            self._update_statuses()
        except Exception:  # noqa: BLE001
            pass

    def _update_statuses(self) -> None:
        """Update all status cards and the process table."""
        statuses = self._supervisor.all_status()

        # Update cards
        for info in statuses:
            card_id = f"card-{info.name}"
            try:
                card = self.query_one(f"#{card_id}", _ConsoleCard)
                if info.running:
                    value = "Running"
                    if info.name == "agent" and info.tool:
                        value = f"Running ({info.tool})"
                    elif info.name == "dashboard" and info.port:
                        value = f"Running (:{info.port})"
                else:
                    value = "Stopped"
                card.update_value(value)
            except Exception:  # noqa: BLE001
                pass

        # Update channel card from poll_state
        try:
            from atlasbridge.ui.polling import poll_state

            app_state = poll_state()
            channel_card = self.query_one("#card-channel", _ConsoleCard)
            channel_card.update_value(app_state.channel_summary or "none")
        except Exception:  # noqa: BLE001
            pass

        # Update process table
        try:
            table = self.query_one("#process-table", DataTable)
            table.clear()
            for info in statuses:
                status_text = "[green]running[/green]" if info.running else "[dim]stopped[/dim]"
                pid_text = str(info.pid) if info.pid else "—"
                uptime_text = info.uptime_display if info.running else "—"
                extra = ""
                if info.name == "agent" and info.tool:
                    extra = info.tool
                elif info.name == "dashboard" and info.port:
                    extra = f"port {info.port}"
                table.add_row(info.name, pid_text, status_text, uptime_text, extra)
        except Exception:  # noqa: BLE001
            pass

    def _load_audit_log(self) -> None:
        """Load recent audit log entries."""
        try:
            from atlasbridge.tui.services import LogsService

            events = LogsService.read_recent(limit=20)
            log_widget = self.query_one("#audit-log", RichLog)
            if not events:
                log_widget.write("[dim]No audit events yet.[/dim]")
                return
            for event in events:
                ts = event.get("timestamp", "")
                if ts and len(ts) > 16:
                    ts = ts[11:16]  # HH:MM
                etype = event.get("event_type", event.get("type", ""))
                session = event.get("session_id", "")[:8]
                log_widget.write(f"[dim]{ts}[/dim]  {etype:<24} {session}")
        except Exception:  # noqa: BLE001
            pass

    def _refresh_doctor(self) -> None:
        """Run doctor checks and update the panel."""
        try:
            from atlasbridge.tui.services import DoctorService

            checks = DoctorService.run_checks()
            results_label = self.query_one("#doctor-results", Label)
            if not checks:
                results_label.update("No checks available")
                return
            parts = []
            for check in checks:
                status = check.get("status", "unknown")
                name = check.get("name", "?")
                icon = "[green]OK[/green]" if status == "ok" else "[red]FAIL[/red]"
                parts.append(f"{icon} {name}")
            results_label.update("  ".join(parts))
        except Exception as exc:  # noqa: BLE001
            try:
                self.query_one("#doctor-results", Label).update(f"Error: {exc}")
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def action_toggle_daemon(self) -> None:
        """Toggle daemon: start if stopped, stop if running."""
        status = self._supervisor.daemon_status()
        if status.running:
            await self._supervisor.stop_daemon()
            self.notify("Daemon stop requested")
        else:
            await self._supervisor.start_daemon()
            self.notify("Daemon start requested")
        self._do_poll()

    async def action_start_agent(self) -> None:
        """Start agent with default tool."""
        status = self._supervisor.agent_status()
        if status.running:
            await self._supervisor.stop_agent()
            self.notify("Agent stopped")
        else:
            await self._supervisor.start_agent(tool=self._default_tool)
            self.notify(f"Agent started ({self._default_tool})")
        self._do_poll()

    async def action_toggle_dashboard(self) -> None:
        """Toggle dashboard: start if stopped, stop if running."""
        status = self._supervisor.dashboard_status(self._dashboard_port)
        if status.running:
            await self._supervisor.stop_dashboard()
            self.notify("Dashboard stopped")
        else:
            await self._supervisor.start_dashboard(port=self._dashboard_port)
            self.notify(f"Dashboard starting on port {self._dashboard_port}")
        self._do_poll()

    def action_health(self) -> None:
        """Refresh doctor panel."""
        self._refresh_doctor()

    def action_refresh(self) -> None:
        """Force refresh all panels."""
        self._do_poll()
        self._load_audit_log()
        self.notify("Refreshed")

    async def action_quit_console(self) -> None:
        """Quit the console, offering to stop managed processes."""
        managed = [s for s in self._supervisor.all_status() if s.running]
        if managed:
            await self._supervisor.shutdown_all()
            self.notify("Stopped managed processes")
        self.app.exit()


# ---------------------------------------------------------------------------
# Console app
# ---------------------------------------------------------------------------


class ConsoleApp(App):  # type: ignore[type-arg]
    """AtlasBridge Operator Console application."""

    TITLE = f"AtlasBridge Console {__version__}"
    CSS = _CSS_TEXT

    def __init__(
        self,
        default_tool: str = "claude",
        dashboard_port: int = 8787,
    ) -> None:
        super().__init__()
        self._supervisor = ProcessSupervisor()
        self._default_tool = default_tool
        self._dashboard_port = dashboard_port

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(
            ConsoleScreen(
                supervisor=self._supervisor,
                default_tool=self._default_tool,
                dashboard_port=self._dashboard_port,
            )
        )


def run(default_tool: str = "claude", dashboard_port: int = 8787) -> None:
    """Entry point called from the CLI."""
    ConsoleApp(default_tool=default_tool, dashboard_port=dashboard_port).run()
