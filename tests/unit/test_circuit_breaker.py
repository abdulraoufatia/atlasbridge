"""Unit tests for the ChannelCircuitBreaker."""

from __future__ import annotations

import time

from atlasbridge.channels.base import ChannelCircuitBreaker


class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        cb = ChannelCircuitBreaker()
        assert not cb.is_open

    def test_stays_closed_below_threshold(self) -> None:
        cb = ChannelCircuitBreaker(threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_open

    def test_opens_at_threshold(self) -> None:
        cb = ChannelCircuitBreaker(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

    def test_success_resets(self) -> None:
        cb = ChannelCircuitBreaker(threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open
        cb.record_success()
        assert not cb.is_open

    def test_auto_closes_after_recovery_window(self) -> None:
        cb = ChannelCircuitBreaker(threshold=1, recovery_seconds=0.05)
        cb.record_failure()
        assert cb.is_open
        time.sleep(0.06)
        assert not cb.is_open  # half-open probe

    def test_reset_clears_state(self) -> None:
        cb = ChannelCircuitBreaker(threshold=1)
        cb.record_failure()
        assert cb.is_open
        cb.reset()
        assert not cb.is_open

    def test_base_channel_has_circuit_breaker_property(self) -> None:
        """BaseChannel subclasses get a circuit_breaker via lazy property."""
        from collections.abc import AsyncIterator

        from atlasbridge.channels.base import BaseChannel
        from atlasbridge.core.prompt.models import PromptEvent, Reply

        class DummyChannel(BaseChannel):
            channel_name = "test"
            display_name = "Test"

            async def start(self) -> None:
                pass

            async def close(self) -> None:
                pass

            async def send_prompt(self, event: PromptEvent) -> str:
                return "1"

            async def notify(self, message: str, session_id: str = "") -> None:
                pass

            async def send_output(self, text: str, session_id: str = "") -> None:
                pass

            async def edit_prompt_message(
                self,
                message_id: str,
                new_text: str,
                session_id: str = "",
            ) -> None:
                pass

            async def receive_replies(self) -> AsyncIterator[Reply]:
                return
                yield  # type: ignore[misc]

            def is_allowed(self, identity: str) -> bool:
                return True

        ch = DummyChannel()
        cb = ch.circuit_breaker
        assert isinstance(cb, ChannelCircuitBreaker)
        # Same instance on second access (lazy init, not recreated)
        assert ch.circuit_breaker is cb
