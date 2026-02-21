"""Unit tests for prompt-to-injection latency tracking."""

from __future__ import annotations

import time

from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptStatus, PromptType
from atlasbridge.core.prompt.state import PromptStateMachine


def _make_event() -> PromptEvent:
    return PromptEvent.create(
        session_id="test-session",
        prompt_type=PromptType.TYPE_YES_NO,
        confidence=Confidence.HIGH,
        excerpt="Continue? [y/N]",
    )


class TestLatencyTracking:
    def test_latency_none_before_resolution(self) -> None:
        sm = PromptStateMachine(event=_make_event())
        assert sm.latency_ms is None

    def test_latency_set_on_resolution(self) -> None:
        sm = PromptStateMachine(event=_make_event())
        sm.transition(PromptStatus.ROUTED, "test")
        sm.transition(PromptStatus.AWAITING_REPLY, "test")
        sm.transition(PromptStatus.REPLY_RECEIVED, "test")
        sm.transition(PromptStatus.INJECTED, "test")
        sm.transition(PromptStatus.RESOLVED, "test")
        assert sm.latency_ms is not None
        assert sm.latency_ms >= 0

    def test_latency_tracks_real_time(self) -> None:
        sm = PromptStateMachine(event=_make_event())
        sm.transition(PromptStatus.ROUTED, "test")
        sm.transition(PromptStatus.AWAITING_REPLY, "test")
        time.sleep(0.05)  # 50ms
        sm.transition(PromptStatus.REPLY_RECEIVED, "test")
        sm.transition(PromptStatus.INJECTED, "test")
        sm.transition(PromptStatus.RESOLVED, "test")
        assert sm.latency_ms is not None
        assert sm.latency_ms >= 40  # Allow some tolerance

    def test_resolved_at_only_set_on_resolved(self) -> None:
        sm = PromptStateMachine(event=_make_event())
        sm.transition(PromptStatus.ROUTED, "test")
        assert sm.resolved_at is None
        sm.transition(PromptStatus.AWAITING_REPLY, "test")
        assert sm.resolved_at is None
        sm.transition(PromptStatus.REPLY_RECEIVED, "test")
        assert sm.resolved_at is None
        sm.transition(PromptStatus.INJECTED, "test")
        assert sm.resolved_at is None
        sm.transition(PromptStatus.RESOLVED, "test")
        assert sm.resolved_at is not None
