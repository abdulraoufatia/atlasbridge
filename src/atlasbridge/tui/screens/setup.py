"""
Setup Wizard screen — multi-step configuration flow.

Steps:
  0 — Choose channel (Telegram / Slack)
  1 — Enter credentials (token, masked; app_token for Slack)
  2 — Enter allowlisted user IDs
  3 — Confirm + save + run doctor
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
)

from atlasbridge.tui.state import WIZARD_TOTAL, WizardState


class SetupScreen(Screen):  # type: ignore[type-arg]
    """Interactive setup wizard."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel / back", show=True),
        Binding("ctrl+n", "next_step", "Next", show=False),
        Binding("ctrl+p", "prev_step", "Back", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._wizard = WizardState()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="setup-container"):
            yield Label("AtlasBridge Setup", id="wizard-title")
            yield Label(self._progress_text(), id="progress-label")
            yield ProgressBar(total=WIZARD_TOTAL - 1, show_eta=False, id="wizard-progress")
            yield from self._render_step()
            yield Label("", id="error-label", classes="error-label")
            with Container(classes="wizard-nav"):
                if not self._wizard.is_first_step:
                    yield Button("← Back", id="btn-back", variant="default")
                if not self._wizard.is_last_step:
                    yield Button("Next →", id="btn-next", variant="primary", classes="primary")
                else:
                    yield Button("Finish", id="btn-finish", variant="success")
        yield Footer()

    # ------------------------------------------------------------------
    # Step rendering
    # ------------------------------------------------------------------

    def _render_step(self) -> ComposeResult:
        step = self._wizard.step_name
        if step == "channel":
            yield from self._step_channel()
        elif step == "credentials":
            yield from self._step_credentials()
        elif step == "user_ids":
            yield from self._step_user_ids()
        elif step == "confirm":
            yield from self._step_confirm()

    def _step_channel(self) -> ComposeResult:
        with Container(id="step-body"):
            yield Label("Step 1 of 4 — Choose a notification channel", classes="step-title")
            yield Label(
                "AtlasBridge will forward prompts to your phone via this channel.",
                classes="field-label",
            )
            yield RadioSet(
                RadioButton("Telegram  (recommended)", id="rb-telegram", value=True),
                RadioButton("Slack", id="rb-slack"),
                id="channel-choice",
            )

    def _step_credentials(self) -> ComposeResult:
        if self._wizard.channel == "telegram":
            with Container(id="step-body"):
                yield Label("Step 2 of 4 — Telegram credentials", classes="step-title")
                yield Label(
                    "Get your bot token from @BotFather on Telegram.", classes="field-label"
                )
                yield Label("Bot token:", classes="field-label")
                yield Input(
                    placeholder="Paste your token here",
                    password=True,
                    id="inp-token",
                    value=self._wizard.token,
                )
        else:
            with Container(id="step-body"):
                yield Label("Step 2 of 4 — Slack credentials", classes="step-title")
                yield Label(
                    "Create a Slack App with Socket Mode enabled.\n"
                    "Bot token (xoxb-*) from OAuth & Permissions.\n"
                    "App-Level token (xapp-*) from Basic Information → App-Level Tokens.",
                    classes="field-label",
                )
                yield Label("Bot token (xoxb-*):", classes="field-label")
                yield Input(
                    placeholder="Paste your bot token here",
                    password=True,
                    id="inp-token",
                    value=self._wizard.token,
                )
                yield Label("App-level token (xapp-*):", classes="field-label")
                yield Input(
                    placeholder="Paste your app-level token here",
                    password=True,
                    id="inp-app-token",
                    value=self._wizard.app_token,
                )

    def _step_user_ids(self) -> ComposeResult:
        if self._wizard.channel == "telegram":
            hint = "Numeric Telegram user IDs, comma-separated. Find yours via @userinfobot."
            placeholder = "123456789, 987654321"
        else:
            hint = "Slack member IDs (e.g. U1234567890). Find in Slack: profile → ··· → Copy member ID."
            placeholder = "U1234567890 U0987654321"
        with Container(id="step-body"):
            yield Label("Step 3 of 4 — Allowlisted user IDs", classes="step-title")
            yield Label(hint, classes="field-label")
            yield Label("User ID(s):", classes="field-label")
            yield Input(placeholder=placeholder, id="inp-users", value=self._wizard.users)

    def _step_confirm(self) -> ComposeResult:
        channel = self._wizard.channel.capitalize()
        user_count = len([u for u in self._wizard.users.replace(",", " ").split() if u])
        if self._wizard.saved:
            cfg_path = ""
            try:
                from atlasbridge.core.config import atlasbridge_dir

                cfg_path = str(atlasbridge_dir() / "config.toml")
            except Exception:  # noqa: BLE001
                pass
            text = (
                "✓  Setup complete!\n\n"
                f"  Channel:           {channel}\n"
                f"  Allowlisted users: {user_count}\n"
                f"  Config path:       {cfg_path}\n\n"
                "Next steps:\n"
                "  • [T] Start daemon now\n"
                "  • Run `atlasbridge run claude` to supervise Claude Code\n"
                "  • Run `atlasbridge doctor` to verify your environment"
            )
        else:
            text = (
                f"Step 4 of 4 — Confirm and save\n\n"
                f"  Channel:           {channel}\n"
                f"  Token:             {'*' * 8 + self._wizard.token[-4:] if len(self._wizard.token) > 4 else '****'}\n"
                f"  Allowlisted users: {user_count}\n\n"
                "Press Finish to save your configuration."
            )
        with Container(id="step-body"):
            yield Label(text, classes="step-title")

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def _progress_text(self) -> str:
        return f"Step {self._wizard.step + 1} of {WIZARD_TOTAL}"

    def _collect_current_inputs(self) -> None:
        """Read current Input widget values into _wizard before advancing."""
        if self._wizard.step_name == "channel":
            try:
                rs = self.query_one("#channel-choice", RadioSet)
                pressed = rs.pressed_button
                if pressed and pressed.id == "rb-slack":
                    self._wizard = WizardState(
                        step=self._wizard.step,
                        channel="slack",
                        token=self._wizard.token,
                        app_token=self._wizard.app_token,
                        users=self._wizard.users,
                    )
                else:
                    self._wizard = WizardState(
                        step=self._wizard.step,
                        channel="telegram",
                        token=self._wizard.token,
                        app_token=self._wizard.app_token,
                        users=self._wizard.users,
                    )
            except Exception:  # noqa: BLE001
                pass
        elif self._wizard.step_name == "credentials":
            try:
                token = self.query_one("#inp-token", Input).value
                app_token = ""
                try:
                    app_token = self.query_one("#inp-app-token", Input).value
                except Exception:  # noqa: BLE001
                    pass
                self._wizard = WizardState(
                    step=self._wizard.step,
                    channel=self._wizard.channel,
                    token=token,
                    app_token=app_token,
                    users=self._wizard.users,
                )
            except Exception:  # noqa: BLE001
                pass
        elif self._wizard.step_name == "user_ids":
            try:
                users = self.query_one("#inp-users", Input).value
                self._wizard = WizardState(
                    step=self._wizard.step,
                    channel=self._wizard.channel,
                    token=self._wizard.token,
                    app_token=self._wizard.app_token,
                    users=users,
                )
            except Exception:  # noqa: BLE001
                pass

    def _refresh_screen(self) -> None:
        self.recompose()

    def _show_error(self, msg: str) -> None:
        try:
            self.query_one("#error-label", Label).update(msg)
        except Exception:  # noqa: BLE001
            self.notify(msg, severity="error")

    def _clear_error(self) -> None:
        try:
            self.query_one("#error-label", Label).update("")
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.action_next_step()
        elif event.button.id == "btn-back":
            self.action_prev_step()
        elif event.button.id == "btn-finish":
            self._do_finish()

    def _do_finish(self) -> None:
        """Save config and show completion."""
        self._collect_current_inputs()
        err = self._wizard.validate_current_step()
        if err:
            self._show_error(err)
            return
        if not self._wizard.saved:
            try:
                from atlasbridge.tui.services import ConfigService

                ConfigService.save(self._wizard.build_config_data())
                self._wizard = WizardState(
                    step=self._wizard.step,
                    channel=self._wizard.channel,
                    token=self._wizard.token,
                    app_token=self._wizard.app_token,
                    users=self._wizard.users,
                    saved=True,
                )
                self._clear_error()
                self._refresh_screen()
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"Failed to save: {exc}")
        else:
            self.app.pop_screen()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_next_step(self) -> None:
        self._collect_current_inputs()
        err = self._wizard.validate_current_step()
        if err:
            self._show_error(err)
            return
        self._clear_error()
        self._wizard = self._wizard.next()
        self._refresh_screen()

    def action_prev_step(self) -> None:
        self._clear_error()
        self._wizard = self._wizard.prev()
        self._refresh_screen()

    def action_cancel(self) -> None:
        if self._wizard.is_first_step:
            self.app.pop_screen()
        else:
            self.action_prev_step()
