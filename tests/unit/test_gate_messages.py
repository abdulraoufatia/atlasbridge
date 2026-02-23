"""Unit tests for gate decision message formatter."""

from __future__ import annotations

import pytest

from atlasbridge.core.gate.engine import (
    AcceptType,
    GateDecision,
    GateRejectReason,
)
from atlasbridge.core.gate.messages import (
    _ACCEPT_MESSAGES,
    _REJECT_HEADLINES,
    _REJECT_NEXT_ACTIONS,
    format_gate_decision,
)


class TestAcceptMessages:
    """Accept decisions produce brief confirmations."""

    def test_reply_accept(self):
        decision = GateDecision(
            action="accept",
            injection_payload="y",
            accept_type=AcceptType.REPLY,
        )
        msg = format_gate_decision(decision)
        assert msg == "\u2713 Sent to session."

    def test_chat_turn_accept(self):
        decision = GateDecision(
            action="accept",
            injection_payload="hello",
            accept_type=AcceptType.CHAT_TURN,
        )
        msg = format_gate_decision(decision)
        assert msg == "\u2713 Message sent."

    def test_interrupt_accept(self):
        decision = GateDecision(
            action="accept",
            injection_payload="stop",
            accept_type=AcceptType.INTERRUPT,
        )
        msg = format_gate_decision(decision)
        assert msg == "\u2713 Interrupt sent to session."

    def test_accept_without_type_defaults_to_reply(self):
        decision = GateDecision(action="accept", injection_payload="y")
        msg = format_gate_decision(decision)
        assert msg == "\u2713 Sent to session."

    def test_all_accept_messages_are_single_line(self):
        for accept_type in AcceptType:
            msg = _ACCEPT_MESSAGES[accept_type]
            assert "\n" not in msg, f"{accept_type} message has newline"

    def test_all_accept_messages_contain_checkmark(self):
        for accept_type in AcceptType:
            msg = _ACCEPT_MESSAGES[accept_type]
            assert "\u2713" in msg, f"{accept_type} missing checkmark"


class TestRejectMessages:
    """Reject decisions produce headline + next action."""

    @pytest.mark.parametrize("reason", list(GateRejectReason))
    def test_every_reason_has_headline(self, reason):
        assert reason in _REJECT_HEADLINES, f"Missing headline for {reason}"
        assert len(_REJECT_HEADLINES[reason]) > 0

    @pytest.mark.parametrize("reason", list(GateRejectReason))
    def test_every_reason_has_next_action(self, reason):
        assert reason in _REJECT_NEXT_ACTIONS, f"Missing next action for {reason}"
        assert len(_REJECT_NEXT_ACTIONS[reason]) > 0

    @pytest.mark.parametrize("reason", list(GateRejectReason))
    def test_reject_message_contains_next_action(self, reason):
        decision = GateDecision(
            action="reject",
            reason_code=reason,
            reason_message="test",
            next_action_hint="test",
        )
        msg = format_gate_decision(decision)
        next_action = _REJECT_NEXT_ACTIONS[reason]
        assert next_action in msg

    @pytest.mark.parametrize("reason", list(GateRejectReason))
    def test_reject_message_under_200_chars(self, reason):
        decision = GateDecision(
            action="reject",
            reason_code=reason,
            reason_message="test",
            next_action_hint="test",
        )
        msg = format_gate_decision(decision)
        assert len(msg) < 200, f"{reason} message is {len(msg)} chars: {msg}"

    def test_reject_without_reason_code(self):
        decision = GateDecision(action="reject")
        msg = format_gate_decision(decision)
        assert msg == "Message not sent."


class TestNoSecretLeakage:
    """Formatted messages must never contain internal identifiers."""

    _FORBIDDEN_PATTERNS = [
        "session_id",
        "prompt_id",
        "policy_rule",
        "sess-",
        "prompt-",
    ]

    @pytest.mark.parametrize("reason", list(GateRejectReason))
    def test_reject_messages_have_no_internal_ids(self, reason):
        decision = GateDecision(
            action="reject",
            reason_code=reason,
            reason_message="test",
            next_action_hint="test",
        )
        msg = format_gate_decision(decision)
        for pattern in self._FORBIDDEN_PATTERNS:
            assert pattern not in msg.lower(), f"{reason} message contains '{pattern}': {msg}"

    def test_accept_messages_have_no_internal_ids(self):
        for accept_type in AcceptType:
            msg = _ACCEPT_MESSAGES[accept_type]
            for pattern in self._FORBIDDEN_PATTERNS:
                assert pattern not in msg.lower(), (
                    f"{accept_type} message contains '{pattern}': {msg}"
                )


class TestUnsafeInputType:
    """REJECT_UNSAFE_INPUT_TYPE must clearly say 'use the terminal'."""

    def test_headline_mentions_local_input(self):
        headline = _REJECT_HEADLINES[GateRejectReason.REJECT_UNSAFE_INPUT_TYPE]
        assert "local input" in headline.lower() or "terminal" in headline.lower()

    def test_next_action_mentions_terminal(self):
        action = _REJECT_NEXT_ACTIONS[GateRejectReason.REJECT_UNSAFE_INPUT_TYPE]
        assert "terminal" in action.lower()


class TestMessageFormat:
    """Verify the two-line format: headline + next action."""

    @pytest.mark.parametrize("reason", list(GateRejectReason))
    def test_reject_has_two_lines(self, reason):
        decision = GateDecision(
            action="reject",
            reason_code=reason,
            reason_message="test",
            next_action_hint="test",
        )
        msg = format_gate_decision(decision)
        lines = msg.split("\n")
        assert len(lines) == 2, f"{reason} should have 2 lines, got {len(lines)}: {msg}"

    @pytest.mark.parametrize("reason", list(GateRejectReason))
    def test_headline_ends_with_period_or_similar(self, reason):
        headline = _REJECT_HEADLINES[reason]
        assert headline[-1] in ".!?", f"{reason} headline doesn't end with punctuation: {headline}"
