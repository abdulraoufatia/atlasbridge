"""
UI state types — pure Python dataclasses, no Textual imports.

These can be constructed and tested without a running Textual app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class ConfigStatus(Enum):
    NOT_FOUND = auto()
    LOADED = auto()
    ERROR = auto()


class DaemonStatus(Enum):
    UNKNOWN = auto()
    RUNNING = auto()
    STOPPED = auto()


@dataclass
class ChannelStatus:
    name: str
    configured: bool


@dataclass
class AppState:
    """Snapshot of AtlasBridge runtime state, polled periodically by the TUI."""

    config_status: ConfigStatus = ConfigStatus.NOT_FOUND
    daemon_status: DaemonStatus = DaemonStatus.UNKNOWN
    channels: list[ChannelStatus] = field(default_factory=list)
    session_count: int = 0
    pending_prompt_count: int = 0
    last_error: str = ""
    update_available: bool = False
    latest_version: str = ""

    @property
    def is_configured(self) -> bool:
        return self.config_status == ConfigStatus.LOADED

    @property
    def channel_summary(self) -> str:
        if not self.channels:
            return "none"
        configured = [c.name for c in self.channels if c.configured]
        return " + ".join(configured) if configured else "none"


# ---------------------------------------------------------------------------
# Setup wizard state machine
# ---------------------------------------------------------------------------

WIZARD_STEPS = ["channel", "credentials", "user_ids", "confirm"]
WIZARD_TOTAL = len(WIZARD_STEPS)


@dataclass
class WizardState:
    """
    Immutable-style step-by-step state for the setup wizard.

    Transitions are made by calling .next() / .prev() which return new instances.
    """

    step: int = 0
    channel: str = "telegram"
    token: str = ""
    app_token: str = ""  # Slack only
    users: str = ""
    saved: bool = False
    error: str = ""

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def next(self) -> WizardState:
        """Advance one step (clamped to last step)."""
        return WizardState(
            step=min(self.step + 1, WIZARD_TOTAL - 1),
            channel=self.channel,
            token=self.token,
            app_token=self.app_token,
            users=self.users,
            saved=self.saved,
            error="",
        )

    def prev(self) -> WizardState:
        """Go back one step (clamped to step 0)."""
        return WizardState(
            step=max(self.step - 1, 0),
            channel=self.channel,
            token=self.token,
            app_token=self.app_token,
            users=self.users,
            saved=self.saved,
            error="",
        )

    def with_error(self, msg: str) -> WizardState:
        """Return a copy with an error message set."""
        return WizardState(
            step=self.step,
            channel=self.channel,
            token=self.token,
            app_token=self.app_token,
            users=self.users,
            saved=self.saved,
            error=msg,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def step_name(self) -> str:
        return WIZARD_STEPS[self.step] if self.step < WIZARD_TOTAL else "done"

    @property
    def is_first_step(self) -> bool:
        return self.step == 0

    @property
    def is_last_step(self) -> bool:
        return self.step == WIZARD_TOTAL - 1

    @property
    def progress(self) -> float:
        """0.0 – 1.0 progress through the wizard."""
        return self.step / max(WIZARD_TOTAL - 1, 1)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_current_step(self) -> str:
        """Return an error string if the current step is invalid, else ''."""
        if self.step_name == "credentials":
            return self._validate_credentials()
        if self.step_name == "user_ids":
            return self._validate_users()
        return ""

    def _validate_credentials(self) -> str:
        import re

        if not self.token.strip():
            return "Token is required."
        if self.channel == "telegram":
            if not re.fullmatch(r"\d{8,12}:[A-Za-z0-9_\-]{35,}", self.token.strip()):
                return "Invalid Telegram token. Expected: <8-12 digits>:<35+ chars>"
        elif self.channel == "slack":
            if not re.fullmatch(r"xoxb-[A-Za-z0-9\-]+", self.token.strip()):
                return "Invalid Slack bot token. Expected: xoxb-..."
            if not re.fullmatch(r"xapp-[A-Za-z0-9\-]+", self.app_token.strip()):
                return "Invalid Slack app token. Expected: xapp-..."
        return ""

    def _validate_users(self) -> str:
        if not self.users.strip():
            return "At least one user ID is required."
        if self.channel == "telegram":
            try:
                ids = [int(u.strip()) for u in self.users.split(",") if u.strip()]
                if not ids:
                    return "Enter numeric Telegram user IDs (comma-separated)."
            except ValueError:
                return "Telegram user IDs must be numeric."
        elif self.channel == "slack":
            import re

            parts = [u.strip() for u in self.users.replace(",", " ").split() if u.strip()]
            if not parts or not all(re.fullmatch(r"U[A-Z0-9]{8,}", p) for p in parts):
                return "Slack user IDs must be like U1234567890."
        return ""

    def build_config_data(self) -> dict:
        """Build the dict to pass to save_config()."""
        if self.channel == "telegram":
            users = [int(u.strip()) for u in self.users.split(",") if u.strip()]
            return {"telegram": {"bot_token": self.token.strip(), "allowed_users": users}}
        else:
            parts = [u.strip() for u in self.users.replace(",", " ").split() if u.strip()]
            return {
                "slack": {
                    "bot_token": self.token.strip(),
                    "app_token": self.app_token.strip(),
                    "allowed_users": parts,
                }
            }


# ---------------------------------------------------------------------------
# Dynamic guidance message — pure function, no Textual dependency
# ---------------------------------------------------------------------------

_WORKFLOW_EXAMPLE = (
    "How it works:\n"
    "  1. Start daemon      atlasbridge start\n"
    "  2. Run your tool      atlasbridge run claude\n"
    "  3. Agent pauses       AtlasBridge sends prompt to your phone\n"
    "  4. Reply via Telegram/Slack\n"
    "  5. CLI resumes automatically"
)


def guidance_message(state: AppState, daemon: DaemonStatus) -> str:
    """Return contextual next-step guidance based on current system state."""
    if not state.is_configured:
        return (
            "Next step: Press [S] to run the setup wizard.\n\n"
            "You'll choose a channel (Telegram or Slack), enter your\n"
            "credentials, and allowlist your user ID. Takes ~2 minutes.\n\n"
            f"{_WORKFLOW_EXAMPLE}"
        )

    if daemon != DaemonStatus.RUNNING:
        return (
            "Next step: Start the daemon, then run a tool.\n\n"
            "  In your terminal:\n"
            "    atlasbridge run claude          (foreground, recommended)\n"
            "    atlasbridge start && atlasbridge run claude\n\n"
            f"{_WORKFLOW_EXAMPLE}"
        )

    if state.session_count == 0:
        return (
            "Daemon is running. No active sessions yet.\n\n"
            "  In your terminal:\n"
            "    atlasbridge run claude\n\n"
            "When Claude pauses for input, AtlasBridge will forward\n"
            "the prompt to your phone. Reply there to resume."
        )

    return (
        f"You have {state.session_count} active session(s).\n\n"
        "  Press [L] to view sessions, or [D] to run doctor.\n\n"
        "When your agent pauses for input, check your phone —\n"
        "AtlasBridge has already forwarded the prompt."
    )


__all__ = [
    "AppState",
    "ChannelStatus",
    "ConfigStatus",
    "DaemonStatus",
    "WIZARD_STEPS",
    "WIZARD_TOTAL",
    "WizardState",
    "guidance_message",
]
