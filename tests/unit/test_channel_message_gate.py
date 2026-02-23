"""Unit tests for ChannelMessageGate — pure, deterministic accept/reject."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from atlasbridge.core.conversation.session_binding import ConversationState
from atlasbridge.core.gate.engine import (
    GateContext,
    GateRejectReason,
    evaluate_gate,
)
from atlasbridge.core.interaction.classifier import InteractionClass


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _future_iso(minutes: int = 10) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _past_iso(minutes: int = 10) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _hash(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def _ctx(**overrides) -> GateContext:
    """Build a GateContext with sensible defaults, allowing overrides."""
    defaults = {
        "session_id": "sess-1",
        "conversation_state": ConversationState.AWAITING_INPUT,
        "active_prompt_id": "prompt-1",
        "interaction_class": InteractionClass.YES_NO,
        "prompt_expires_at": _future_iso(),
        "channel_user_id": "user-123",
        "channel_name": "telegram",
        "message_body": "y",
        "message_hash": _hash("y"),
        "identity_allowlist": frozenset({"user-123"}),
        "allow_chat_turns": False,
        "allow_interrupts": False,
        "valid_choices": (),
        "timestamp": _now_iso(),
    }
    defaults.update(overrides)
    return GateContext(**defaults)


class TestIdentityCheck:
    """Step 1: Identity must be on the allowlist."""

    def test_allowlisted_user_passes(self):
        decision = evaluate_gate(_ctx())
        assert decision.action == "accept"

    def test_non_allowlisted_user_rejected(self):
        decision = evaluate_gate(_ctx(channel_user_id="stranger"))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED

    def test_empty_allowlist_rejects_everyone(self):
        decision = evaluate_gate(_ctx(identity_allowlist=frozenset()))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED


class TestSessionExistence:
    """Step 2: Session must exist."""

    def test_no_session_id(self):
        decision = evaluate_gate(_ctx(session_id=None))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_NO_ACTIVE_SESSION

    def test_no_conversation_state(self):
        decision = evaluate_gate(_ctx(conversation_state=None))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_NO_ACTIVE_SESSION


class TestStreamingState:
    """Step 3a: STREAMING always rejects."""

    def test_streaming_rejects(self):
        decision = evaluate_gate(_ctx(conversation_state=ConversationState.STREAMING))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_BUSY_STREAMING

    def test_streaming_rejects_even_with_prompt(self):
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.STREAMING,
                active_prompt_id="prompt-1",
            )
        )
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_BUSY_STREAMING


class TestRunningState:
    """Step 3b: RUNNING rejects unless interrupt policy allows."""

    def test_running_rejects_by_default(self):
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.RUNNING,
                allow_interrupts=False,
            )
        )
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_BUSY_RUNNING

    def test_running_accepts_with_interrupt_policy(self):
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.RUNNING,
                allow_interrupts=True,
            )
        )
        assert decision.action == "accept"
        assert decision.injection_payload == "y"


class TestStoppedState:
    """STOPPED session rejects."""

    def test_stopped_rejects(self):
        decision = evaluate_gate(_ctx(conversation_state=ConversationState.STOPPED))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_NO_ACTIVE_SESSION


class TestAwaitingInputPath:
    """Step 4: AWAITING_INPUT — prompt binding, TTL, type safety, validation."""

    def test_valid_reply_accepted(self):
        decision = evaluate_gate(_ctx())
        assert decision.action == "accept"
        assert decision.injection_payload == "y"

    def test_no_active_prompt_rejected(self):
        decision = evaluate_gate(_ctx(active_prompt_id=None))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_NOT_AWAITING_INPUT

    def test_expired_ttl_rejected(self):
        decision = evaluate_gate(_ctx(prompt_expires_at=_past_iso()))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_TTL_EXPIRED

    def test_password_input_rejected(self):
        decision = evaluate_gate(_ctx(interaction_class=InteractionClass.PASSWORD_INPUT))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_UNSAFE_INPUT_TYPE

    def test_invalid_choice_rejected(self):
        decision = evaluate_gate(
            _ctx(
                interaction_class=InteractionClass.NUMBERED_CHOICE,
                valid_choices=("1", "2", "3"),
                message_body="5",
                message_hash=_hash("5"),
            )
        )
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_INVALID_CHOICE

    def test_valid_choice_accepted(self):
        decision = evaluate_gate(
            _ctx(
                interaction_class=InteractionClass.NUMBERED_CHOICE,
                valid_choices=("1", "2", "3"),
                message_body="2",
                message_hash=_hash("2"),
            )
        )
        assert decision.action == "accept"
        assert decision.injection_payload == "2"

    def test_free_text_accepted(self):
        decision = evaluate_gate(
            _ctx(
                interaction_class=InteractionClass.FREE_TEXT,
                message_body="my commit message",
                message_hash=_hash("my commit message"),
            )
        )
        assert decision.action == "accept"
        assert decision.injection_payload == "my commit message"

    def test_confirm_enter_accepted(self):
        decision = evaluate_gate(
            _ctx(
                interaction_class=InteractionClass.CONFIRM_ENTER,
                message_body="\n",
                message_hash=_hash("\n"),
            )
        )
        assert decision.action == "accept"

    def test_no_valid_choices_skips_validation(self):
        """If valid_choices is empty, don't validate the choice."""
        decision = evaluate_gate(
            _ctx(
                interaction_class=InteractionClass.NUMBERED_CHOICE,
                valid_choices=(),
                message_body="99",
                message_hash=_hash("99"),
            )
        )
        assert decision.action == "accept"


class TestIdlePath:
    """Step 5: IDLE — chat turns policy check."""

    def test_idle_rejects_without_chat_turns(self):
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.IDLE,
                allow_chat_turns=False,
                active_prompt_id=None,
            )
        )
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_POLICY_DENY

    def test_idle_accepts_with_chat_turns(self):
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.IDLE,
                allow_chat_turns=True,
                active_prompt_id=None,
            )
        )
        assert decision.action == "accept"


class TestEvaluationOrder:
    """Verify that the evaluation order is correct."""

    def test_identity_checked_before_session_state(self):
        """Non-allowlisted user should be rejected even with valid session."""
        decision = evaluate_gate(
            _ctx(
                channel_user_id="stranger",
                conversation_state=ConversationState.AWAITING_INPUT,
            )
        )
        assert decision.reason_code == GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED

    def test_session_checked_before_state(self):
        """Missing session should be caught before state checks."""
        decision = evaluate_gate(_ctx(session_id=None))
        assert decision.reason_code == GateRejectReason.REJECT_NO_ACTIVE_SESSION

    def test_streaming_checked_before_prompt_binding(self):
        """STREAMING rejects even if prompt binding exists."""
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.STREAMING,
                active_prompt_id="prompt-1",
            )
        )
        assert decision.reason_code == GateRejectReason.REJECT_BUSY_STREAMING

    def test_ttl_checked_before_type_safety(self):
        """Expired TTL rejects even for safe input types."""
        decision = evaluate_gate(
            _ctx(
                prompt_expires_at=_past_iso(),
                interaction_class=InteractionClass.YES_NO,
            )
        )
        assert decision.reason_code == GateRejectReason.REJECT_TTL_EXPIRED

    def test_type_safety_checked_before_choice_validation(self):
        """PASSWORD_INPUT rejects even if the choice would be valid."""
        decision = evaluate_gate(
            _ctx(
                interaction_class=InteractionClass.PASSWORD_INPUT,
                valid_choices=("1", "2"),
                message_body="1",
            )
        )
        assert decision.reason_code == GateRejectReason.REJECT_UNSAFE_INPUT_TYPE


class TestPureFunction:
    """The gate must be a pure function with no mutations."""

    def test_context_is_frozen(self):
        ctx = _ctx()
        with pytest.raises(AttributeError):
            ctx.session_id = "mutated"  # type: ignore[misc]

    def test_decision_is_frozen(self):
        decision = evaluate_gate(_ctx())
        with pytest.raises(AttributeError):
            decision.action = "mutated"  # type: ignore[misc]

    def test_same_inputs_same_output(self):
        ts = _now_iso()
        expires = _future_iso()
        ctx1 = _ctx(timestamp=ts, prompt_expires_at=expires)
        ctx2 = _ctx(timestamp=ts, prompt_expires_at=expires)
        d1 = evaluate_gate(ctx1)
        d2 = evaluate_gate(ctx2)
        assert d1.action == d2.action
        assert d1.reason_code == d2.reason_code
        assert d1.injection_payload == d2.injection_payload


class TestReasonMessages:
    """Every rejection includes a human-friendly message and hint."""

    @pytest.mark.parametrize(
        "reason",
        list(GateRejectReason),
    )
    def test_all_reasons_have_messages(self, reason):
        from atlasbridge.core.gate.engine import _NEXT_ACTION_HINTS, _REASON_MESSAGES

        assert reason in _REASON_MESSAGES, f"Missing message for {reason}"
        assert reason in _NEXT_ACTION_HINTS, f"Missing hint for {reason}"
        assert len(_REASON_MESSAGES[reason]) > 0
        assert len(_NEXT_ACTION_HINTS[reason]) > 0

    def test_reject_decision_has_message(self):
        decision = evaluate_gate(_ctx(channel_user_id="stranger"))
        assert decision.reason_message != ""
        assert decision.next_action_hint != ""

    def test_accept_decision_has_no_reason(self):
        decision = evaluate_gate(_ctx())
        assert decision.reason_code is None
        assert decision.reason_message == ""
