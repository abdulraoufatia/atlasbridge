"""
SetupWizardScreen — 4-step guided configuration flow.

Widget tree (rebuilt on each step via ``recompose()``)::

    Header
    #wizard-root  (Static)
      #wizard-title   (Label)
      #wizard-step    (Static — current step content)
      #wizard-error   (Label  — validation error, empty when ok)
      .wizard-nav     (Static — Back / Next / Finish buttons)
    Footer

Keybindings:
  enter  — advance to next step (same as "Next →")
  escape — go back one step (or close wizard if on step 0)
  h      — show channel token setup instructions
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
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
    Static,
)

from atlasbridge.ui.state import WIZARD_TOTAL, WizardState

_TELEGRAM_HELP = (
    "How to get a Telegram bot token:\n\n"
    "  1. Open Telegram and search for @BotFather\n"
    "  2. Send /newbot\n"
    "  3. Choose a display name and a username (must end in 'bot')\n"
    "  4. BotFather replies with your token\n"
    "     Format: 123456789:ABCDefghIJKLMN...\n\n"
    "  To find your user ID, message @userinfobot\n\n"
    "  Your token is stored locally and never uploaded."
)

_SLACK_HELP = (
    "How to get Slack tokens:\n\n"
    "  1. Go to https://api.slack.com/apps\n"
    "  2. Create New App → From scratch → choose workspace\n"
    "  3. OAuth & Permissions → add scopes: chat:write, users:read\n"
    "  4. Install App to Workspace\n"
    "  5. Copy Bot User OAuth Token (xoxb-...)\n"
    "  6. Basic Information → App-Level Tokens → Generate (xapp-...)\n"
    "     Scope: connections:write\n\n"
    "  To find your member ID: profile → ··· → Copy member ID\n\n"
    "  Tokens are stored locally and never uploaded."
)


class SetupWizardScreen(Screen):  # type: ignore[type-arg]
    """Interactive 4-step setup wizard."""

    BINDINGS = [
        Binding("enter", "next_step", "Next", show=False),
        Binding("escape", "cancel", "Back / Cancel", show=True),
        Binding("ctrl+n", "next_step", "Next", show=False),
        Binding("ctrl+p", "prev_step", "Back", show=False),
        Binding("h", "show_help", "Help", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._wizard = WizardState()

    # ------------------------------------------------------------------
    # Compose — called on mount and on recompose()
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Static(id="wizard-root"):
            yield Label("AtlasBridge Setup", id="wizard-title")
            yield Label(self._progress_text(), id="wizard-progress-label")
            yield ProgressBar(total=WIZARD_TOTAL - 1, show_eta=False, id="wizard-progress")
            yield self._render_step()
            yield Label("", id="wizard-error", classes="wizard-error")
            with Static(classes="wizard-nav"):
                if not self._wizard.is_first_step:
                    yield Button("← Back", id="btn-back", variant="default")
                if not self._wizard.is_last_step:
                    yield Button("Next →", id="btn-next", variant="primary")
                else:
                    yield Button("Finish", id="btn-finish", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self._focus_first_input()

    # ------------------------------------------------------------------
    # Step rendering
    # ------------------------------------------------------------------

    def _render_step(self) -> Static:
        step = self._wizard.step_name
        if step == "channel":
            return self._step_channel()
        if step == "credentials":
            return self._step_credentials()
        if step == "user_ids":
            return self._step_user_ids()
        if step == "confirm":
            return self._step_confirm()
        return Static("Done.", id="wizard-step")

    def _step_channel(self) -> Static:
        s = Static(id="wizard-step", classes="wizard-step-container")
        s.compose = lambda: [  # type: ignore[method-assign]
            Label("Step 1 of 4 — Choose a notification channel", classes="step-title"),
            Label(
                "AtlasBridge forwards prompts to your phone via this channel.",
                classes="field-label",
            ),
            RadioSet(
                RadioButton("Telegram  (recommended)", id="rb-telegram", value=True),
                RadioButton("Slack", id="rb-slack"),
                id="channel-choice",
            ),
        ]
        return s

    def _step_credentials(self) -> Static:
        s = Static(id="wizard-step", classes="wizard-step-container")
        if self._wizard.channel == "telegram":
            s.compose = lambda: [  # type: ignore[method-assign]
                Label("Step 2 of 4 — Telegram credentials", classes="step-title"),
                Label(
                    "Get your bot token from @BotFather on Telegram.\n"
                    "Press [H] for step-by-step instructions.",
                    classes="field-label",
                ),
                Label("Bot token:", classes="field-label"),
                Input(
                    placeholder="12345678:ABCDefghIJKLMNopQRSTuvwxyz12345678901",
                    password=True,
                    id="inp-token",
                    value=self._wizard.token,
                ),
            ]
        else:
            s.compose = lambda: [  # type: ignore[method-assign]
                Label("Step 2 of 4 — Slack credentials", classes="step-title"),
                Label(
                    "Create a Slack App with Socket Mode enabled.\n"
                    "Press [H] for step-by-step instructions.",
                    classes="field-label",
                ),
                Label("Bot token (xoxb-*):", classes="field-label"),
                Input(
                    placeholder="xoxb-...",
                    password=True,
                    id="inp-token",
                    value=self._wizard.token,
                ),
                Label("App-level token (xapp-*):", classes="field-label"),
                Input(
                    placeholder="xapp-...",
                    password=True,
                    id="inp-app-token",
                    value=self._wizard.app_token,
                ),
            ]
        return s

    def _step_user_ids(self) -> Static:
        s = Static(id="wizard-step", classes="wizard-step-container")
        if self._wizard.channel == "telegram":
            hint = "Numeric Telegram user IDs, comma-separated. Find yours via @userinfobot."
            placeholder = "123456789, 987654321"
        else:
            hint = (
                "Slack member IDs (e.g. U1234567890). "
                "Find in Slack: profile → ··· → Copy member ID."
            )
            placeholder = "U1234567890 U0987654321"
        s.compose = lambda: [  # type: ignore[method-assign]
            Label("Step 3 of 4 — Allowlisted user IDs", classes="step-title"),
            Label(hint, classes="field-label"),
            Label("User ID(s):", classes="field-label"),
            Input(placeholder=placeholder, id="inp-users", value=self._wizard.users),
        ]
        return s

    def _step_confirm(self) -> Static:
        s = Static(id="wizard-step", classes="wizard-step-container")
        channel = self._wizard.channel.capitalize()
        user_count = len([u for u in self._wizard.users.replace(",", " ").split() if u])
        masked = "*" * 8 + self._wizard.token[-4:] if len(self._wizard.token) > 4 else "****"
        text = (
            f"Step 4 of 4 — Confirm and save\n\n"
            f"  Channel:           {channel}\n"
            f"  Token:             {masked}\n"
            f"  Allowlisted users: {user_count}\n\n"
            "Press Finish to save your configuration."
        )
        s.compose = lambda: [Label(text, classes="step-title")]  # type: ignore[method-assign]
        return s

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def _progress_text(self) -> str:
        return f"Step {self._wizard.step + 1} of {WIZARD_TOTAL}"

    def _collect_inputs(self) -> None:
        if self._wizard.step_name == "channel":
            try:
                rs = self.query_one("#channel-choice", RadioSet)
                pressed = rs.pressed_button
                channel = "slack" if (pressed and pressed.id == "rb-slack") else "telegram"
                self._wizard = WizardState(
                    step=self._wizard.step,
                    channel=channel,
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

    def _show_error(self, msg: str) -> None:
        try:
            self.query_one("#wizard-error", Label).update(msg)
        except Exception:  # noqa: BLE001
            self.notify(msg, severity="error")

    def _clear_error(self) -> None:
        try:
            self.query_one("#wizard-error", Label).update("")
        except Exception:  # noqa: BLE001
            pass

    def _focus_first_input(self) -> None:
        """Focus the first Input widget on the current step, if any."""
        try:
            first_input = self.query("Input").first()
            first_input.focus()
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
        self._collect_inputs()
        err = self._wizard.validate_current_step()
        if err:
            self._show_error(err)
            return
        try:
            from atlasbridge.tui.services import ConfigService

            ConfigService.save(self._wizard.build_config_data())
            self._clear_error()
            from atlasbridge.ui.screens.complete import SetupCompleteScreen

            self.app.switch_screen(
                SetupCompleteScreen(
                    channel=self._wizard.channel,
                    user_count=len([u for u in self._wizard.users.replace(",", " ").split() if u]),
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Failed to save: {exc}")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_next_step(self) -> None:
        if self._wizard.is_last_step:
            self._do_finish()
            return
        self._collect_inputs()
        err = self._wizard.validate_current_step()
        if err:
            self._show_error(err)
            return
        self._clear_error()
        self._wizard = self._wizard.next()
        self.recompose()

    def action_prev_step(self) -> None:
        self._collect_inputs()
        self._clear_error()
        self._wizard = self._wizard.prev()
        self.recompose()

    def action_cancel(self) -> None:
        if self._wizard.is_first_step:
            self.app.pop_screen()
        else:
            self.action_prev_step()

    def action_show_help(self) -> None:
        channel = self._wizard.channel
        help_text = _TELEGRAM_HELP if channel == "telegram" else _SLACK_HELP
        self.notify(
            help_text, title=f"{channel.capitalize()} setup", severity="information", timeout=15
        )
