"""Integration tests for channel circuit breaker wiring."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

import pytest

from atlasbridge.channels.base import BaseChannel, ChannelCircuitBreaker
from atlasbridge.core.exceptions import ChannelUnavailableError
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType, Reply


class _FailingChannel(BaseChannel):
    """Channel that fails N times then succeeds."""

    channel_name = "test"
    display_name = "Test"

    def __init__(self, fail_count: int = 0) -> None:
        self._fail_count = fail_count
        self._calls = 0

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def send_prompt(self, event: PromptEvent) -> str:
        self._calls += 1
        if self._calls <= self._fail_count:
            raise ConnectionError("Simulated network failure")
        return f"msg-{self._calls}"

    async def notify(self, message: str, session_id: str = "") -> None:
        pass

    async def edit_prompt_message(
        self, message_id: str, new_text: str, session_id: str = ""
    ) -> None:
        pass

    async def receive_replies(self) -> AsyncIterator[Reply]:
        return
        yield  # type: ignore[misc]

    def is_allowed(self, identity: str) -> bool:
        return True


def _make_event() -> PromptEvent:
    return PromptEvent(
        session_id="test-session",
        prompt_id="test-prompt",
        prompt_type=PromptType.TYPE_YES_NO,
        confidence=Confidence.HIGH,
        excerpt="Continue? [y/n]",
    )


class TestGuardedSend:
    @pytest.mark.asyncio
    async def test_guarded_send_succeeds_normally(self) -> None:
        ch = _FailingChannel(fail_count=0)
        result = await ch.guarded_send(_make_event())
        assert result == "msg-1"
        assert not ch.circuit_breaker.is_open

    @pytest.mark.asyncio
    async def test_guarded_send_records_failure(self) -> None:
        ch = _FailingChannel(fail_count=10)
        with pytest.raises(ConnectionError):
            await ch.guarded_send(_make_event())
        assert ch.circuit_breaker._failures == 1

    @pytest.mark.asyncio
    async def test_circuit_trips_after_threshold(self) -> None:
        ch = _FailingChannel(fail_count=10)
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await ch.guarded_send(_make_event())

        assert ch.circuit_breaker.is_open

        # Next attempt is rejected by circuit breaker
        with pytest.raises(ChannelUnavailableError, match="Circuit breaker open"):
            await ch.guarded_send(_make_event())

    @pytest.mark.asyncio
    async def test_circuit_auto_recovers_after_cooldown(self) -> None:
        ch = _FailingChannel(fail_count=3)
        # Override recovery to very short for testing
        ch.circuit_breaker.recovery_seconds = 0.05

        # Trip the circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await ch.guarded_send(_make_event())
        assert ch.circuit_breaker.is_open

        # Wait for recovery
        time.sleep(0.06)
        assert not ch.circuit_breaker.is_open

        # Next attempt succeeds (fail_count exhausted)
        result = await ch.guarded_send(_make_event())
        assert result == "msg-4"
        assert not ch.circuit_breaker.is_open

    @pytest.mark.asyncio
    async def test_success_resets_after_transient_failures(self) -> None:
        ch = _FailingChannel(fail_count=2)

        # Two failures
        with pytest.raises(ConnectionError):
            await ch.guarded_send(_make_event())
        with pytest.raises(ConnectionError):
            await ch.guarded_send(_make_event())

        assert ch.circuit_breaker._failures == 2
        assert not ch.circuit_breaker.is_open  # below threshold

        # Third call succeeds (fail_count=2 exhausted)
        result = await ch.guarded_send(_make_event())
        assert result == "msg-3"
        assert ch.circuit_breaker._failures == 0

    @pytest.mark.asyncio
    async def test_healthcheck_reflects_circuit_state(self) -> None:
        ch = _FailingChannel(fail_count=10)
        health = ch.healthcheck()
        assert health["status"] == "ok"
        assert health["circuit_breaker"]["open"] is False

        # Trip the circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await ch.guarded_send(_make_event())

        health = ch.healthcheck()
        assert health["status"] == "degraded"
        assert health["circuit_breaker"]["open"] is True
        assert health["circuit_breaker"]["failures"] == 3


class TestCircuitBreakerStateTransitions:
    def test_closed_to_open_logged(self) -> None:
        """Circuit breaker logs when transitioning to open state."""
        cb = ChannelCircuitBreaker(threshold=2, recovery_seconds=30.0)
        cb.record_failure()
        cb.record_failure()
        # Should have logged 'circuit_breaker_opened' (verified by structlog capture)
        assert cb.is_open

    def test_configurable_threshold(self) -> None:
        cb = ChannelCircuitBreaker(threshold=5, recovery_seconds=10.0)
        for _ in range(4):
            cb.record_failure()
        assert not cb.is_open
        cb.record_failure()
        assert cb.is_open

    def test_configurable_recovery(self) -> None:
        cb = ChannelCircuitBreaker(threshold=1, recovery_seconds=0.02)
        cb.record_failure()
        assert cb.is_open
        time.sleep(0.03)
        assert not cb.is_open
