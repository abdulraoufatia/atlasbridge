"""Safety regression tests for channel UX — no terminal semantics in any channel message.

Verifies:
1. Workspace trust prompt: no "Enter", "Esc", "arrow" etc.
2. Provider-related acks: no key material in any channel message
3. Busy gate messages: no terminal semantics in queued/no-session responses
4. All gate messages: phone-first UX (clean text only)
"""

from __future__ import annotations

import pytest

from atlasbridge.core.gate.engine import GateDecision, GateRejectReason
from atlasbridge.core.gate.messages import format_gate_decision
from atlasbridge.core.store.workspace_trust import build_trust_prompt

TERMINAL_WORDS = (
    "Enter",
    "Esc",
    "arrow",
    "↑",
    "↓",
    "Tab",
    "ctrl",
    "[y/n]",
    "[Y/n]",
    "[yes/no]",
    "Press",
)

ALL_REJECT_REASONS = [
    GateRejectReason.REJECT_BUSY_STREAMING,
    GateRejectReason.REJECT_BUSY_RUNNING,
    GateRejectReason.REJECT_NOT_AWAITING_INPUT,
    GateRejectReason.REJECT_NO_ACTIVE_SESSION,
    GateRejectReason.REJECT_TTL_EXPIRED,
]

SAMPLE_PATHS = [
    "/home/user/project",
    "/Users/ara/Documents/GitHub/atlasbridge",
    "/tmp/test-workspace",
]


def _reject_msg(reason: GateRejectReason) -> str:
    decision = GateDecision(action="reject", reason_code=reason, reason_message="test")
    return format_gate_decision(decision)


# ---------------------------------------------------------------------------
# Trust prompt safety
# ---------------------------------------------------------------------------


class TestTrustPromptNoTerminalSemantics:
    @pytest.mark.parametrize("path", SAMPLE_PATHS)
    @pytest.mark.parametrize("word", TERMINAL_WORDS)
    def test_no_terminal_word(self, path: str, word: str) -> None:
        msg = build_trust_prompt(path)
        assert word not in msg, f"Trust prompt for {path!r} contains terminal word {word!r}:\n{msg}"

    @pytest.mark.parametrize("path", SAMPLE_PATHS)
    def test_prompt_is_human_readable(self, path: str) -> None:
        msg = build_trust_prompt(path)
        assert path in msg
        low = msg.lower()
        assert "yes" in low or "no" in low

    def test_no_numbered_list_in_prompt(self) -> None:
        msg = build_trust_prompt("/tmp/any")
        assert "1." not in msg
        assert "2." not in msg


# ---------------------------------------------------------------------------
# Gate messages safety
# ---------------------------------------------------------------------------


class TestGateMessagesNoTerminalSemantics:
    @pytest.mark.parametrize("reason", ALL_REJECT_REASONS)
    @pytest.mark.parametrize("word", TERMINAL_WORDS)
    def test_no_terminal_word(self, reason: GateRejectReason, word: str) -> None:
        text = _reject_msg(reason)
        assert word not in text, (
            f"Gate message for {reason!r} contains terminal word {word!r}:\n{text}"
        )


class TestBusyMessageContent:
    def test_streaming_mentions_queued(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_BUSY_STREAMING)
        assert "queued" in text.lower() or "Queued" in text

    def test_running_mentions_queued(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_BUSY_RUNNING)
        assert "queued" in text.lower() or "Queued" in text

    def test_not_awaiting_mentions_queued(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_NOT_AWAITING_INPUT)
        assert "queued" in text.lower() or "Queued" in text


class TestNoSessionMessageContent:
    def test_mentions_dashboard(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_NO_ACTIVE_SESSION)
        assert "dashboard" in text.lower()

    def test_does_not_mention_cli_commands(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_NO_ACTIVE_SESSION)
        assert "atlasbridge run" not in text
        assert "$ atlasbridge" not in text


class TestExpiredMessageContent:
    def test_mentions_expired(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_TTL_EXPIRED)
        assert "expired" in text.lower()

    def test_no_internal_state_leaked(self) -> None:
        text = _reject_msg(GateRejectReason.REJECT_TTL_EXPIRED)
        assert "AWAITING_REPLY" not in text
        assert "decide_prompt" not in text


# ---------------------------------------------------------------------------
# Provider-related channel message safety
# ---------------------------------------------------------------------------


class TestProviderChannelSafety:
    def test_no_key_material_in_safe_prefix(self) -> None:
        from atlasbridge.core.store.provider_config import _safe_prefix

        full_key = "sk-secret-api-key-123456789"
        prefix = _safe_prefix(full_key)
        assert full_key not in prefix
        assert len(prefix) <= 9

    def test_safe_prefix_ends_with_dots(self) -> None:
        from atlasbridge.core.store.provider_config import _safe_prefix

        prefix = _safe_prefix("sk-ant-api03-longkey")
        assert prefix.endswith("...")
