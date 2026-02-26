"""Unit tests for UI state types — no Textual imports required."""

from __future__ import annotations

import pytest

from atlasbridge.ui.state import (
    WIZARD_STEPS,
    WIZARD_TOTAL,
    AppState,
    ChannelStatus,
    ConfigStatus,
    DaemonStatus,
    WizardState,
)

# ---------------------------------------------------------------------------
# AppState
# ---------------------------------------------------------------------------


class TestAppState:
    def test_defaults(self) -> None:
        state = AppState()
        assert state.config_status == ConfigStatus.NOT_FOUND
        assert state.daemon_status == DaemonStatus.UNKNOWN
        assert state.channels == []
        assert state.session_count == 0
        assert state.pending_prompt_count == 0
        assert state.last_error == ""

    def test_is_configured_false_when_not_found(self) -> None:
        state = AppState(config_status=ConfigStatus.NOT_FOUND)
        assert not state.is_configured

    def test_is_configured_true_when_loaded(self) -> None:
        state = AppState(config_status=ConfigStatus.LOADED)
        assert state.is_configured

    def test_is_configured_false_when_error(self) -> None:
        state = AppState(config_status=ConfigStatus.ERROR)
        assert not state.is_configured

    def test_channel_summary_no_channels(self) -> None:
        state = AppState()
        assert state.channel_summary == "none"

    def test_channel_summary_one_configured(self) -> None:
        state = AppState(channels=[ChannelStatus("telegram", True)])
        assert state.channel_summary == "telegram"

    def test_channel_summary_two_configured(self) -> None:
        state = AppState(channels=[ChannelStatus("telegram", True), ChannelStatus("slack", True)])
        assert state.channel_summary == "telegram + slack"

    def test_channel_summary_skips_unconfigured(self) -> None:
        state = AppState(channels=[ChannelStatus("telegram", False), ChannelStatus("slack", True)])
        assert state.channel_summary == "slack"

    def test_channel_summary_all_unconfigured(self) -> None:
        state = AppState(channels=[ChannelStatus("telegram", False), ChannelStatus("slack", False)])
        assert state.channel_summary == "none"


# ---------------------------------------------------------------------------
# WizardState — constants
# ---------------------------------------------------------------------------


def test_wizard_steps_has_four_items() -> None:
    assert len(WIZARD_STEPS) == 4
    assert WIZARD_TOTAL == 4


def test_wizard_steps_order() -> None:
    assert WIZARD_STEPS == ["channel", "credentials", "user_ids", "confirm"]


# ---------------------------------------------------------------------------
# WizardState — navigation
# ---------------------------------------------------------------------------


class TestWizardNavigation:
    def test_initial_step_is_zero(self) -> None:
        w = WizardState()
        assert w.step == 0
        assert w.step_name == "channel"

    def test_next_advances_step(self) -> None:
        w = WizardState()
        w2 = w.next()
        assert w2.step == 1
        assert w2.step_name == "credentials"

    def test_next_is_non_mutating(self) -> None:
        w = WizardState()
        _ = w.next()
        assert w.step == 0

    def test_next_clamps_at_last_step(self) -> None:
        w = WizardState(step=WIZARD_TOTAL - 1)
        w2 = w.next()
        assert w2.step == WIZARD_TOTAL - 1

    def test_prev_goes_back(self) -> None:
        w = WizardState(step=2)
        w2 = w.prev()
        assert w2.step == 1

    def test_prev_clamps_at_zero(self) -> None:
        w = WizardState(step=0)
        w2 = w.prev()
        assert w2.step == 0

    def test_next_clears_error(self) -> None:
        w = WizardState(step=0, error="some error")
        w2 = w.next()
        assert w2.error == ""

    def test_prev_clears_error(self) -> None:
        w = WizardState(step=2, error="some error")
        w2 = w.prev()
        assert w2.error == ""

    def test_with_error_sets_message(self) -> None:
        w = WizardState()
        w2 = w.with_error("bad token")
        assert w2.error == "bad token"
        assert w2.step == 0

    def test_with_error_is_non_mutating(self) -> None:
        w = WizardState()
        _ = w.with_error("x")
        assert w.error == ""

    def test_is_first_step_true(self) -> None:
        assert WizardState(step=0).is_first_step is True

    def test_is_first_step_false(self) -> None:
        assert WizardState(step=1).is_first_step is False

    def test_is_last_step_true(self) -> None:
        assert WizardState(step=WIZARD_TOTAL - 1).is_last_step is True

    def test_is_last_step_false(self) -> None:
        assert WizardState(step=0).is_last_step is False

    def test_progress_at_start(self) -> None:
        assert WizardState(step=0).progress == 0.0

    def test_progress_at_end(self) -> None:
        assert WizardState(step=WIZARD_TOTAL - 1).progress == pytest.approx(1.0)

    def test_progress_midpoint(self) -> None:
        # step=1, total=4 → 1/3 ≈ 0.333
        assert WizardState(step=1).progress == pytest.approx(1 / 3)

    def test_step_name_beyond_total_returns_done(self) -> None:
        w = WizardState(step=99)
        assert w.step_name == "done"

    def test_navigation_preserves_fields(self) -> None:
        w = WizardState(channel="slack", token="xoxb-abc", app_token="xapp-xyz", users="U123")
        w2 = w.next()
        assert w2.channel == "slack"
        assert w2.token == "xoxb-abc"
        assert w2.app_token == "xapp-xyz"
        assert w2.users == "U123"


# ---------------------------------------------------------------------------
# WizardState — validation: credentials
# ---------------------------------------------------------------------------


class TestValidateCredentials:
    def _at_credentials(self, **kwargs) -> WizardState:  # type: ignore[no-untyped-def]
        return WizardState(step=1, **kwargs)

    def test_no_error_on_non_credentials_step(self) -> None:
        w = WizardState(step=0, token="")
        assert w.validate_current_step() == ""

    def test_empty_token_returns_error(self) -> None:
        w = self._at_credentials(channel="telegram", token="")
        assert "required" in w.validate_current_step().lower()

    def test_valid_telegram_token_passes(self) -> None:
        valid = "123456789:ABCDefghIJKLMNopQRSTuvwxyz12345678901"
        w = self._at_credentials(channel="telegram", token=valid)
        assert w.validate_current_step() == ""

    def test_short_id_telegram_fails(self) -> None:
        w = self._at_credentials(channel="telegram", token="1234:short")
        assert w.validate_current_step() != ""

    def test_valid_slack_tokens_passes(self) -> None:
        w = self._at_credentials(
            channel="slack",
            token="xoxb-valid-bot-token-abcdef",
            app_token="xapp-valid-app-token-xyz",
        )
        assert w.validate_current_step() == ""

    def test_invalid_slack_bot_token_fails(self) -> None:
        w = self._at_credentials(
            channel="slack",
            token="bad-token",
            app_token="xapp-valid-app-token-xyz",
        )
        assert w.validate_current_step() != ""

    def test_invalid_slack_app_token_fails(self) -> None:
        w = self._at_credentials(
            channel="slack",
            token="xoxb-valid-bot-token-abcdef",
            app_token="bad-app-token",
        )
        assert w.validate_current_step() != ""


# ---------------------------------------------------------------------------
# WizardState — validation: user_ids
# ---------------------------------------------------------------------------


class TestValidateUsers:
    def _at_users(self, **kwargs) -> WizardState:  # type: ignore[no-untyped-def]
        return WizardState(step=2, **kwargs)

    def test_empty_users_returns_error(self) -> None:
        w = self._at_users(channel="telegram", users="")
        assert w.validate_current_step() != ""

    def test_valid_telegram_user_ids(self) -> None:
        w = self._at_users(channel="telegram", users="123456789")
        assert w.validate_current_step() == ""

    def test_multiple_telegram_user_ids(self) -> None:
        w = self._at_users(channel="telegram", users="123456789, 987654321")
        assert w.validate_current_step() == ""

    def test_non_numeric_telegram_user_id_fails(self) -> None:
        w = self._at_users(channel="telegram", users="abc123")
        assert w.validate_current_step() != ""

    def test_valid_slack_user_ids(self) -> None:
        w = self._at_users(channel="slack", users="U1234567890")
        assert w.validate_current_step() == ""

    def test_multiple_slack_user_ids(self) -> None:
        w = self._at_users(channel="slack", users="U1234567890 U0987654321")
        assert w.validate_current_step() == ""

    def test_invalid_slack_user_id_fails(self) -> None:
        w = self._at_users(channel="slack", users="invalid-id")
        assert w.validate_current_step() != ""


# ---------------------------------------------------------------------------
# WizardState — build_config_data
# ---------------------------------------------------------------------------


class TestBuildConfigData:
    def test_telegram_config_structure(self) -> None:
        w = WizardState(
            channel="telegram",
            token="123456789:ABCDefghIJKLMNopQRSTuvwxyz12345678901",
            users="111, 222",
        )
        data = w.build_config_data()
        assert "telegram" in data
        assert data["telegram"]["bot_token"] == "123456789:ABCDefghIJKLMNopQRSTuvwxyz12345678901"
        assert data["telegram"]["allowed_users"] == [111, 222]

    def test_slack_config_structure(self) -> None:
        w = WizardState(
            channel="slack",
            token="xoxb-bot-token",
            app_token="xapp-app-token",
            users="U1234567890",
        )
        data = w.build_config_data()
        assert "slack" in data
        assert data["slack"]["bot_token"] == "xoxb-bot-token"
        assert data["slack"]["app_token"] == "xapp-app-token"
        assert data["slack"]["allowed_users"] == ["U1234567890"]

    def test_telegram_strips_whitespace(self) -> None:
        w = WizardState(
            channel="telegram",
            token="  123456789:ABCDefghIJKLMNopQRSTuvwxyz12345678901  ",
            users="  111  ,  222  ",
        )
        data = w.build_config_data()
        assert data["telegram"]["bot_token"] == "123456789:ABCDefghIJKLMNopQRSTuvwxyz12345678901"
        assert data["telegram"]["allowed_users"] == [111, 222]
