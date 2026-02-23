"""Channel message gate — immediate accept/reject for all channel messages."""

from atlasbridge.core.gate.engine import (
    AcceptType,
    GateContext,
    GateDecision,
    GateRejectReason,
    evaluate_gate,
)
from atlasbridge.core.gate.messages import format_gate_decision

__all__ = [
    "AcceptType",
    "GateContext",
    "GateDecision",
    "GateRejectReason",
    "evaluate_gate",
    "format_gate_decision",
]
