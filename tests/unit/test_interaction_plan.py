"""Unit tests for InteractionPlan and build_plan."""

from __future__ import annotations

import pytest

from atlasbridge.core.interaction.classifier import InteractionClass
from atlasbridge.core.interaction.plan import build_plan


class TestBuildPlanYesNo:
    def test_has_retry(self) -> None:
        plan = build_plan(InteractionClass.YES_NO)
        assert plan.max_retries == 1

    def test_verifies_advance(self) -> None:
        plan = build_plan(InteractionClass.YES_NO)
        assert plan.verify_advance is True

    def test_display_template(self) -> None:
        plan = build_plan(InteractionClass.YES_NO)
        assert "{value}" in plan.display_template
        assert "Enter" in plan.display_template

    def test_button_layout(self) -> None:
        plan = build_plan(InteractionClass.YES_NO)
        assert plan.button_layout == "yes_no"


class TestBuildPlanConfirmEnter:
    def test_has_retry(self) -> None:
        plan = build_plan(InteractionClass.CONFIRM_ENTER)
        assert plan.max_retries == 1

    def test_display_template_says_enter(self) -> None:
        plan = build_plan(InteractionClass.CONFIRM_ENTER)
        assert "Enter" in plan.display_template

    def test_button_layout(self) -> None:
        plan = build_plan(InteractionClass.CONFIRM_ENTER)
        assert plan.button_layout == "confirm_enter"


class TestBuildPlanNumberedChoice:
    def test_has_retry(self) -> None:
        plan = build_plan(InteractionClass.NUMBERED_CHOICE)
        assert plan.max_retries == 1

    def test_display_template_shows_option(self) -> None:
        plan = build_plan(InteractionClass.NUMBERED_CHOICE)
        assert "option" in plan.display_template

    def test_button_layout(self) -> None:
        plan = build_plan(InteractionClass.NUMBERED_CHOICE)
        assert plan.button_layout == "numbered"


class TestBuildPlanFreeText:
    def test_no_retry(self) -> None:
        plan = build_plan(InteractionClass.FREE_TEXT)
        assert plan.max_retries == 0

    def test_verifies_advance(self) -> None:
        plan = build_plan(InteractionClass.FREE_TEXT)
        assert plan.verify_advance is True

    def test_button_layout_none(self) -> None:
        plan = build_plan(InteractionClass.FREE_TEXT)
        assert plan.button_layout == "none"


class TestBuildPlanPasswordInput:
    def test_suppress_value(self) -> None:
        plan = build_plan(InteractionClass.PASSWORD_INPUT)
        assert plan.suppress_value is True

    def test_no_retry_for_passwords(self) -> None:
        plan = build_plan(InteractionClass.PASSWORD_INPUT)
        assert plan.max_retries == 0

    def test_display_template_redacted(self) -> None:
        plan = build_plan(InteractionClass.PASSWORD_INPUT)
        assert "REDACTED" in plan.display_template

    def test_button_layout_none(self) -> None:
        plan = build_plan(InteractionClass.PASSWORD_INPUT)
        assert plan.button_layout == "none"


class TestBuildPlanChatInput:
    def test_no_verification(self) -> None:
        plan = build_plan(InteractionClass.CHAT_INPUT)
        assert plan.verify_advance is False

    def test_no_retry(self) -> None:
        plan = build_plan(InteractionClass.CHAT_INPUT)
        assert plan.max_retries == 0

    def test_no_escalation(self) -> None:
        plan = build_plan(InteractionClass.CHAT_INPUT)
        assert plan.escalate_on_exhaustion is False

    def test_button_layout_none(self) -> None:
        plan = build_plan(InteractionClass.CHAT_INPUT)
        assert plan.button_layout == "none"


class TestPlanImmutability:
    def test_frozen(self) -> None:
        plan = build_plan(InteractionClass.YES_NO)
        with pytest.raises(AttributeError):
            plan.max_retries = 5  # type: ignore[misc]


class TestAllPlansHaveDisplayTemplate:
    @pytest.mark.parametrize("ic", list(InteractionClass))
    def test_display_template_non_empty(self, ic: InteractionClass) -> None:
        plan = build_plan(ic)
        assert plan.display_template != ""


class TestAllPlansAppendCr:
    @pytest.mark.parametrize(
        "ic",
        [ic for ic in InteractionClass if ic != InteractionClass.RAW_TERMINAL],
    )
    def test_append_cr_true(self, ic: InteractionClass) -> None:
        plan = build_plan(ic)
        assert plan.append_cr is True

    def test_raw_terminal_no_cr(self) -> None:
        """RAW_TERMINAL never injects — it always escalates."""
        plan = build_plan(InteractionClass.RAW_TERMINAL)
        assert plan.append_cr is False
        assert plan.escalate_on_exhaustion is True
