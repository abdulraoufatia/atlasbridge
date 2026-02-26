"""
SetupWizardScreen — 4-step guided configuration flow.

Steps:
  0 — Choose channel (Telegram / Slack)
  1 — Enter credentials (token, masked; app_token for Slack)
  2 — Enter allowlisted user IDs
  3 — Confirm + save

Widget tree (rebuilt on each step via ``recompose()``)::

    Header
    #wizard-root  (Container)
      #wizard-title       (Label)
      #wizard-progress-label (Label)
      #wizard-progress    (ProgressBar)
      #wizard-step        (Container — current step content)
        ... step-specific widgets (Input, RadioSet, etc.)
      #wizard-error       (Label  — validation error, empty when ok)
      .wizard-nav         (Container — Back / Next / Finish buttons)
    Footer

Keybindings:
  enter  — advance to next step (same as "Next →")
  escape — go back one step (or close wizard if on step 0)
  h      — show channel token setup instructions
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

from atlasbridge.ui.state import WIZARD_TOTAL, WizardState

_TELEGRAM_HELP = (
    "How to get a Telegram bot token:\n\n"
    "  1. Open Telegram and search for @BotFather\n"
    "  2. Send /newbot\n"
    "  3. Choose a display name and a username (must end in 'bot')\n"
    "  4. BotFather replies with your token\n"
    "     Format: 123456789:ABCDefghIJKLMN...\n"
    "  5. Open a chat with your bot and send /start\n"
    "     This is required before AtlasBridge can deliver prompts.\n\n"
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


class SetupWizardScreen(Screen):
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
        with Container(id="wizard-root"):
            yield Label("AtlasBridge Setup", id="wizard-title")
            yield Label(self._progress_text(), id="wizard-progress-label")
            yield ProgressBar(total=WIZARD_TOTAL - 1, show_eta=False, id="wizard-progress")
            yield from self._render_step()
            yield Label("", id="wizard-error", classes="wizard-error")
            with Container(classes="wizard-nav"):
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
    # Step rendering — yields widgets directly (no monkey-patching)
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
        with Container(id="wizard-step"):
            yield Label("Step 1 of 4 — Choose a notification channel", classes="step-title")
            yield Label(
                "AtlasBridge forwards prompts to your phone via this channel.",
                classes="field-label",
            )
            yield RadioSet(
                RadioButton("Telegram  (recommended)", id="rb-telegram", value=True),
                RadioButton("Slack", id="rb-slack"),
                id="channel-choice",
            )

    def _step_credentials(self) -> ComposeResult:
        if self._wizard.channel == "telegram":
            with Container(id="wizard-step"):
                yield Label("Step 2 of 4 — Telegram credentials", classes="step-title")
                yield Label(
                    "Get your bot token from @BotFather on Telegram.\n"
                    "Press [H] for step-by-step instructions.",
                    classes="field-label",
                )
                yield Label("Bot token:", classes="field-label")
                yield Input(
                    placeholder="Paste your token here",
                    password=True,
                    id="inp-token",
                    value=self._wizard.token,
                )
        else:
            with Container(id="wizard-step"):
                yield Label("Step 2 of 4 — Slack credentials", classes="step-title")
                yield Label(
                    "Create a Slack App with Socket Mode enabled.\n"
                    "Press [H] for step-by-step instructions.",
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
            hint = (
                "Slack member IDs (e.g. U1234567890). "
                "Find in Slack: profile → ··· → Copy member ID."
            )
            placeholder = "U1234567890 U0987654321"
        with Container(id="wizard-step"):
            yield Label("Step 3 of 4 — Allowlisted user IDs", classes="step-title")
            yield Label(hint, classes="field-label")
            yield Label("User ID(s):", classes="field-label")
            yield Input(placeholder=placeholder, id="inp-users", value=self._wizard.users)

    def _step_confirm(self) -> ComposeResult:
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
        if self._wizard.channel == "telegram":
            text += "\n\n  \u26a0 Remember: send /start to your bot in Telegram first."
        with Container(id="wizard-step"):
            yield Label(text, classes="step-title")

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

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            await self.action_next_step()
        elif event.button.id == "btn-back":
            await self.action_prev_step()
        elif event.button.id == "btn-finish":
            self._do_finish()

    def _do_finish(self) -> None:
        self._collect_inputs()
        err = self._wizard.validate_current_step()
        if err:
            self._show_error(err)
            return
        try:
            from atlasbridge.ui.services import ConfigService

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

    async def action_next_step(self) -> None:
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
        await self.recompose()

    async def action_prev_step(self) -> None:
        self._collect_inputs()
        self._clear_error()
        self._wizard = self._wizard.prev()
        await self.recompose()

    async def action_cancel(self) -> None:
        if self._wizard.is_first_step:
            self.app.pop_screen()
        else:
            await self.action_prev_step()

    def action_show_help(self) -> None:
        channel = self._wizard.channel
        help_text = _TELEGRAM_HELP if channel == "telegram" else _SLACK_HELP
        self.notify(
            help_text, title=f"{channel.capitalize()} setup", severity="information", timeout=15
        )
