"""Integration tests for chat gate message content.

Verifies that format_gate_decision() produces the correct phone-first UX:
- Busy messages: no terminal semantics, just "Queued…"
- No-session message: directs to dashboard
- Expired message: clear expired notice
"""

from __future__ import annotations

import pytest

from atlasbridge.core.gate.engine import GateDecision, GateRejectReason
from atlasbridge.core.gate.messages import format_gate_decision

TERMINAL_WORDS = ("Enter", "Esc", "arrow", "↑", "↓", "Tab", "ctrl")

BUSY_REASONS = [
    GateRejectReason.REJECT_BUSY_STREAMING,
    GateRejectReason.REJECT_BUSY_RUNNING,
    GateRejectReason.REJECT_NOT_AWAITING_INPUT,
]


def _reject_msg(reason: GateRejectReason) -> str:
    decision = GateDecision(
        action="reject",
        reason_code=reason,
        reason_message="test",
    )
    return format_gate_decision(decision)


@pytest.mark.parametrize("reason", BUSY_REASONS)
class TestBusyGateMessages:
    def test_busy_message_contains_queued(self, reason: GateRejectReason) -> None:
        text = _reject_msg(reason)
        assert "queued" in text.lower() or "Queued" in text

    @pytest.mark.parametrize("word", TERMINAL_WORDS)
    def test_busy_message_no_terminal_semantics(self, reason: GateRejectReason, word: str) -> None:
        text = _reject_msg(reason)
        assert word not in text, f"Gate message for {reason!r} contains terminal word {word!r}: {text!r}"


class TestNoSessionMessage:
    def test_no_session_references_dashboard(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_NO_ACTIVE_SESSION)
        assert "dashboard" in text.lower()

    @pytest.mark.parametrize("word", TERMINAL_WORDS)
    def test_no_session_no_terminal_semantics(self, word: str) -> None:
        text = _reject_msg(GateRejectReason.REJECT_NO_ACTIVE_SESSION)
        assert word not in text, f"No-session message contains terminal word {word!r}"


class TestExpiredMessage:
    def test_expired_mentions_expired(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_TTL_EXPIRED)
        assert "expired" in text.lower()

    @pytest.mark.parametrize("word", TERMINAL_WORDS)
    def test_expired_no_terminal_semantics(self, word: str) -> None:
        text = _reject_msg(GateRejectReason.REJECT_TTL_EXPIRED)
        assert word not in text, f"Expired message contains terminal word {word!r}"
