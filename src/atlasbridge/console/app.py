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
from atlasbridge.console.supervisor import ProcessSupervisor, SystemHealth, compute_health

_CSS_TEXT: str = files("atlasbridge.console.css").joinpath("console.tcss").read_text("utf-8")


# ---------------------------------------------------------------------------
# Status card (local to console — avoids cross-import with ui/components)
# ---------------------------------------------------------------------------


class _ConsoleCard(Static):
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


class ConsoleScreen(Screen):
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
        dashboard_port: int = 3737,
    ) -> None:
        super().__init__()
        self._supervisor = supervisor
        self._default_tool = default_tool
        self._dashboard_port = dashboard_port
        self._last_poll_time: str = ""
        self._last_event_time: str = ""
        self._doctor_results: list[dict] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="console-root"):
            # Safety banner
            yield Static(
                " OPERATOR CONSOLE — LOCAL EXECUTION ONLY",
                id="safety-banner",
            )
            # Health state line
            yield Label("", id="health-state")
            # Data paths
            yield Label("", id="data-paths")

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
                yield RichLog(id="doctor-results", wrap=True, markup=True)

            # Audit log
            with Vertical(id="audit-section"):
                yield Label("Audit Log (recent)", id="audit-title")
                yield RichLog(id="audit-log", wrap=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        # Set up process table columns
        table = self.query_one("#process-table", DataTable)
        table.add_columns("TYPE", "PID", "STATUS", "UPTIME", "INFO")

        # Display data paths (once, not every poll)
        self._show_data_paths()

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
        except Exception as exc:  # noqa: BLE001
            try:
                self._update_health_banner(SystemHealth.RED, error=str(exc))
            except Exception:  # noqa: BLE001
                pass

    def _update_statuses(self) -> None:
        """Update all status cards and the process table."""
        from datetime import datetime

        statuses = self._supervisor.all_status()
        self._last_poll_time = datetime.now().strftime("%H:%M:%S")

        # Compute and display health
        health = compute_health(statuses, self._doctor_results)
        self._update_health_banner(health)

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

            # Show update notification if available
            if app_state.update_available and app_state.latest_version:
                try:
                    data_label = self.query_one("#data-paths", Label)
                    data_label.update(
                        f"[yellow]Update available: {__version__} → "
                        f"{app_state.latest_version} "
                        f"(pip install -U atlasbridge)[/yellow]"
                    )
                except Exception:  # noqa: BLE001
                    pass
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

    @staticmethod
    def _audit_severity(event_type: str) -> str:
        """Map event type to a severity marker."""
        if any(k in event_type for k in ("expired", "failed", "error")):
            return "WARN"
        return "INFO"

    def _load_audit_log(self) -> None:
        """Load recent audit log entries with fixed-width columns."""
        try:
            from atlasbridge.ui.services import LogsService

            events = LogsService.read_recent(limit=20)
            log_widget = self.query_one("#audit-log", RichLog)
            log_widget.clear()
            if not events:
                log_widget.write("[dim]No audit events yet.[/dim]")
                return
            for event in events:
                ts = event.get("timestamp", "")
                if ts and len(ts) > 16:
                    ts = ts[11:16]  # HH:MM
                etype = event.get("event_type", event.get("type", ""))
                session = event.get("session_id", "")[:8]
                severity = self._audit_severity(etype)
                if severity == "WARN":
                    sev_display = f"[yellow]{severity:<4}[/yellow]"
                else:
                    sev_display = f"[dim]{severity:<4}[/dim]"
                log_widget.write(f"  {ts:<5}  {sev_display}  {etype:<24}  {session}")
            # Track last event time
            if events:
                last_ts = events[-1].get("timestamp", "")
                if last_ts and len(last_ts) > 16:
                    self._last_event_time = last_ts[11:19]  # HH:MM:SS
        except Exception as exc:  # noqa: BLE001
            try:
                log_widget = self.query_one("#audit-log", RichLog)
                log_widget.clear()
                log_widget.write(f"[red]Error loading audit log: {exc}[/red]")
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _doctor_icon(status: str) -> str:
        """Return a Rich-formatted icon for a doctor check status."""
        if status in ("ok", "pass"):
            return "[green]PASS[/green]"
        if status == "warn":
            return "[yellow]WARN[/yellow]"
        if status == "fail":
            return "[red]FAIL[/red]"
        return "[dim]SKIP[/dim]"

    def _refresh_doctor(self) -> None:
        """Run doctor checks and update the panel."""
        try:
            from atlasbridge.ui.services import DoctorService

            checks = DoctorService.run_checks()
            self._doctor_results = checks
            results_log = self.query_one("#doctor-results", RichLog)
            results_log.clear()
            if not checks:
                results_log.write("[dim]No checks available[/dim]")
                return
            for check in checks:
                status = check.get("status", "unknown")
                name = check.get("name", "?")
                detail = check.get("detail", "")
                icon = self._doctor_icon(status)
                results_log.write(f"  {icon}  {name:<20}  {detail}")
        except Exception as exc:  # noqa: BLE001
            try:
                results_log = self.query_one("#doctor-results", RichLog)
                results_log.clear()
                results_log.write(f"[red]Error: {exc}[/red]")
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Health banner + data paths
    # ------------------------------------------------------------------

    def _update_health_banner(self, health: SystemHealth, *, error: str | None = None) -> None:
        """Update the health state line below the safety banner."""
        try:
            label = self.query_one("#health-state", Label)
            if error:
                label.update(f"[RED]  Error: {error}  |  Last check: {self._last_poll_time}")
            else:
                tag = health.value.upper()
                color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}[tag]
                text = {"GREEN": "All Healthy", "YELLOW": "Degraded", "RED": "Critical"}[tag]
                parts = [f"[{color}][{tag}] {text}[/{color}]"]
                if self._last_poll_time:
                    parts.append(f"Last check: {self._last_poll_time}")
                if self._last_event_time:
                    parts.append(f"Last event: {self._last_event_time}")
                label.update("  |  ".join(parts))
            # Update CSS class for color theming
            label.remove_class("health-green", "health-yellow", "health-red")
            label.add_class(f"health-{health.value}")
        except Exception:  # noqa: BLE001
            pass

    def _show_data_paths(self) -> None:
        """Display config/data paths (once on mount)."""
        try:
            from atlasbridge.core.config import atlasbridge_dir

            cfg = atlasbridge_dir()
            # Use ~ shorthand for home directory
            display = str(cfg).replace(str(cfg.home()), "~")
            db = "sessions.db"
            log = "audit.log"
            text = f"Config: {display}/  |  DB: {db}  |  Log: {log}"
            self.query_one("#data-paths", Label).update(text)
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
        """Toggle agent: start if stopped, stop if running."""
        status = self._supervisor.agent_status()
        if status.running:
            self.notify(f"Stopping agent ({status.tool})...")
            await self._supervisor.stop_agent()
            self.notify("Agent stopped")
        else:
            self.notify(f"Starting agent ({self._default_tool})...")
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
        """Quit the console, stopping managed processes first."""
        managed = [s for s in self._supervisor.all_status() if s.running]
        if managed:
            names = ", ".join(s.name for s in managed)
            self.notify(f"Stopping {names}...")
            await self._supervisor.shutdown_all()
            self.notify("All processes stopped")
        self.app.exit()


# ---------------------------------------------------------------------------
# Console app
# ---------------------------------------------------------------------------


class ConsoleApp(App):
    """AtlasBridge Operator Console application."""

    TITLE = f"AtlasBridge Console {__version__}"
    CSS = _CSS_TEXT

    def __init__(
        self,
        default_tool: str = "claude",
        dashboard_port: int = 3737,
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


def run(default_tool: str = "claude", dashboard_port: int = 3737) -> None:
    """Entry point called from the CLI."""
    ConsoleApp(default_tool=default_tool, dashboard_port=dashboard_port).run()
