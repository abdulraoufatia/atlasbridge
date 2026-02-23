"""Channel message gate — immediate accept/reject for all channel messages."""

from atlasbridge.core.gate.engine import (
    GateContext,
    GateDecision,
    GateRejectReason,
    evaluate_gate,
)

__all__ = [
    "GateContext",
    "GateDecision",
    "GateRejectReason",
    "evaluate_gate",
]
