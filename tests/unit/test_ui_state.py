"""Unit tests for UI state types — no Textual imports required."""

from __future__ import annotations

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


def test_wizard_steps_has_one_item() -> None:
    assert len(WIZARD_STEPS) == 1
    assert WIZARD_TOTAL == 1


def test_wizard_steps_order() -> None:
    assert WIZARD_STEPS == ["confirm"]


# ---------------------------------------------------------------------------
# WizardState — navigation
# ---------------------------------------------------------------------------


class TestWizardNavigation:
    def test_initial_step_is_zero(self) -> None:
        w = WizardState()
        assert w.step == 0
        assert w.step_name == "confirm"

    def test_next_clamps_at_last_step(self) -> None:
        w = WizardState(step=WIZARD_TOTAL - 1)
        w2 = w.next()
        assert w2.step == WIZARD_TOTAL - 1

    def test_next_is_non_mutating(self) -> None:
        w = WizardState()
        _ = w.next()
        assert w.step == 0

    def test_prev_clamps_at_zero(self) -> None:
        w = WizardState(step=0)
        w2 = w.prev()
        assert w2.step == 0

    def test_next_clears_error(self) -> None:
        w = WizardState(step=0, error="some error")
        w2 = w.next()
        assert w2.error == ""

    def test_prev_clears_error(self) -> None:
        w = WizardState(step=0, error="some error")
        w2 = w.prev()
        assert w2.error == ""

    def test_with_error_sets_message(self) -> None:
        w = WizardState()
        w2 = w.with_error("bad input")
        assert w2.error == "bad input"
        assert w2.step == 0

    def test_with_error_is_non_mutating(self) -> None:
        w = WizardState()
        _ = w.with_error("x")
        assert w.error == ""

    def test_is_first_step_true(self) -> None:
        assert WizardState(step=0).is_first_step is True

    def test_is_last_step_true(self) -> None:
        assert WizardState(step=WIZARD_TOTAL - 1).is_last_step is True

    def test_progress_at_start(self) -> None:
        assert WizardState(step=0).progress == 0.0

    def test_step_name_beyond_total_returns_done(self) -> None:
        w = WizardState(step=99)
        assert w.step_name == "done"


# ---------------------------------------------------------------------------
# WizardState — validation (channels removed — validate_current_step
# always returns empty string)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_validate_returns_empty(self) -> None:
        w = WizardState()
        assert w.validate_current_step() == ""


# ---------------------------------------------------------------------------
# WizardState — build_config_data (channels removed — returns empty dict)
# ---------------------------------------------------------------------------


class TestBuildConfigData:
    def test_returns_empty_dict(self) -> None:
        w = WizardState()
        assert w.build_config_data() == {}
