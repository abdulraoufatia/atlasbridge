"""Safety tests: channel messages are always policy-gated, never queued.

Categories:
  1. No Queue Exists — static analysis (BLOCKED: requires #158 router integration)
  2. Gate Required — verify gate module structure and contracts
  3. Injection Safety — runtime per-state gate behavior
  4. Invariant Preservation — all correctness invariants hold through gate

See issue #162 for full specification.
"""

from __future__ import annotations

import ast
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from atlasbridge.core.conversation.session_binding import ConversationState
from atlasbridge.core.gate.engine import (
    GateContext,
    GateRejectReason,
    evaluate_gate,
)
from atlasbridge.core.interaction.classifier import InteractionClass

SRC = Path(__file__).resolve().parent.parent.parent / "src" / "atlasbridge"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _future_iso(minutes: int = 10) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _past_iso(minutes: int = 10) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _hash(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def _ctx(**overrides) -> GateContext:
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


def _collect_imports(path: Path) -> list[str]:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


# ---------------------------------------------------------------------------
# Category 2: Gate Required (structural verification)
# ---------------------------------------------------------------------------


@pytest.mark.safety
class TestGateRequired:
    """Verify the gate module exists and is structurally correct."""

    def test_gate_module_exists(self):
        gate_path = SRC / "core" / "gate" / "engine.py"
        assert gate_path.exists(), "core/gate/engine.py not found"

    def test_gate_exports_evaluate_gate(self):
        assert callable(evaluate_gate)

    def test_gate_has_no_channel_imports(self):
        imports = _collect_imports(SRC / "core" / "gate" / "engine.py")
        for imp in imports:
            assert not imp.startswith("atlasbridge.channels"), f"Gate imports channel: {imp}"
            assert not imp.startswith("atlasbridge.adapters"), f"Gate imports adapter: {imp}"

    def test_gate_has_no_ui_imports(self):
        for pyfile in (SRC / "core" / "gate").glob("*.py"):
            imports = _collect_imports(pyfile)
            for imp in imports:
                for forbidden in ("atlasbridge.ui", "atlasbridge.tui", "atlasbridge.console"):
                    assert not imp.startswith(forbidden), f"{pyfile.name} imports {imp}"

    def test_gate_decision_is_frozen(self):
        decision = evaluate_gate(_ctx())
        with pytest.raises(AttributeError):
            decision.action = "mutated"  # type: ignore[misc]

    def test_gate_context_is_frozen(self):
        ctx = _ctx()
        with pytest.raises(AttributeError):
            ctx.session_id = "mutated"  # type: ignore[misc]

    def test_all_reject_reasons_have_messages(self):
        from atlasbridge.core.gate.engine import _NEXT_ACTION_HINTS, _REASON_MESSAGES

        for reason in GateRejectReason:
            assert reason in _REASON_MESSAGES, f"Missing message for {reason}"
            assert reason in _NEXT_ACTION_HINTS, f"Missing hint for {reason}"


# ---------------------------------------------------------------------------
# Category 3: Injection Safety (runtime per-state)
# ---------------------------------------------------------------------------


@pytest.mark.safety
class TestInjectionSafety:
    """Every conversation state rejects or accepts deterministically."""

    def test_streaming_always_rejects(self):
        decision = evaluate_gate(_ctx(conversation_state=ConversationState.STREAMING))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_BUSY_STREAMING

    def test_running_rejects_without_interrupt_policy(self):
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

    def test_stopped_always_rejects(self):
        decision = evaluate_gate(_ctx(conversation_state=ConversationState.STOPPED))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_NO_ACTIVE_SESSION

    def test_password_prompt_always_rejected_via_channel(self):
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.AWAITING_INPUT,
                interaction_class=InteractionClass.PASSWORD_INPUT,
            )
        )
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_UNSAFE_INPUT_TYPE

    def test_idle_rejects_without_chat_turns_policy(self):
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.IDLE,
                allow_chat_turns=False,
                active_prompt_id=None,
            )
        )
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_POLICY_DENY

    def test_no_session_always_rejects(self):
        decision = evaluate_gate(_ctx(session_id=None))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_NO_ACTIVE_SESSION


# ---------------------------------------------------------------------------
# Category 4: Invariant Preservation (all 7 correctness invariants)
# ---------------------------------------------------------------------------


@pytest.mark.safety
class TestInvariantPreservation:
    """Gate must not weaken existing correctness invariants."""

    def test_identity_allowlist_enforced(self):
        """Non-allowlisted user must be rejected."""
        decision = evaluate_gate(_ctx(channel_user_id="stranger"))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED

    def test_empty_allowlist_rejects_everyone(self):
        decision = evaluate_gate(_ctx(identity_allowlist=frozenset()))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED

    def test_ttl_enforced(self):
        """Expired prompts must be rejected by gate."""
        decision = evaluate_gate(_ctx(prompt_expires_at=_past_iso()))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_TTL_EXPIRED

    def test_session_binding_enforced(self):
        """Missing session rejects regardless of other valid fields."""
        decision = evaluate_gate(_ctx(session_id=None, conversation_state=None))
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_NO_ACTIVE_SESSION

    def test_no_injection_without_prompt(self):
        """AWAITING_INPUT with no active prompt rejects."""
        decision = evaluate_gate(
            _ctx(
                conversation_state=ConversationState.AWAITING_INPUT,
                active_prompt_id=None,
            )
        )
        assert decision.action == "reject"
        assert decision.reason_code == GateRejectReason.REJECT_NOT_AWAITING_INPUT

    def test_free_text_choice_accepted_for_normalizer(self):
        """Gate accepts free-text replies; normalizer handles choice mapping."""
        decision = evaluate_gate(
            _ctx(
                interaction_class=InteractionClass.NUMBERED_CHOICE,
                valid_choices=("1", "2", "3"),
                message_body="99",
                message_hash=_hash("99"),
            )
        )
        # Gate no longer validates choices — the interaction engine's
        # normalizer maps natural language (yes/no/allow/deny) to option
        # numbers post-gate.
        assert decision.action == "accept"

    def test_gate_is_pure_function(self):
        """Same inputs produce same outputs (determinism)."""
        ts = _now_iso()
        expires = _future_iso()
        ctx1 = _ctx(timestamp=ts, prompt_expires_at=expires)
        ctx2 = _ctx(timestamp=ts, prompt_expires_at=expires)
        d1 = evaluate_gate(ctx1)
        d2 = evaluate_gate(ctx2)
        assert d1.action == d2.action
        assert d1.reason_code == d2.reason_code
        assert d1.injection_payload == d2.injection_payload

    def test_evaluation_order_identity_first(self):
        """Identity check happens before session state check."""
        decision = evaluate_gate(
            _ctx(
                channel_user_id="stranger",
                conversation_state=ConversationState.AWAITING_INPUT,
            )
        )
        assert decision.reason_code == GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED

    def test_evaluation_order_session_before_state(self):
        """Session existence checked before state."""
        decision = evaluate_gate(_ctx(session_id=None))
        assert decision.reason_code == GateRejectReason.REJECT_NO_ACTIVE_SESSION

    def test_evaluation_order_ttl_before_type_safety(self):
        """TTL checked before input type safety."""
        decision = evaluate_gate(
            _ctx(
                prompt_expires_at=_past_iso(),
                interaction_class=InteractionClass.YES_NO,
            )
        )
        assert decision.reason_code == GateRejectReason.REJECT_TTL_EXPIRED
