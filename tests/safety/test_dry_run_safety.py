"""Safety tests: dry-run mode must NEVER inject into PTY or send channel messages."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.interaction.classifier import InteractionClass
from atlasbridge.core.interaction.executor import InteractionExecutor
from atlasbridge.core.interaction.plan import build_plan
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType
from atlasbridge.core.routing.router import PromptRouter
from atlasbridge.core.session.manager import SessionManager
from atlasbridge.core.session.models import Session


def _event(
    session_id: str = "test-session",
    prompt_type: PromptType = PromptType.TYPE_YES_NO,
    excerpt: str = "Continue? [y/n]",
) -> PromptEvent:
    return PromptEvent.create(
        session_id=session_id,
        prompt_type=prompt_type,
        confidence=Confidence.HIGH,
        excerpt=excerpt,
    )


# ---------------------------------------------------------------------------
# Safety: executor MUST NOT call adapter.inject_reply in dry-run mode
# ---------------------------------------------------------------------------


class TestDryRunExecutorNoInjection:
    """Critical safety invariant: dry-run mode must never inject into PTY."""

    @pytest.mark.asyncio
    @pytest.mark.safety
    async def test_execute_does_not_call_inject_reply(self):
        adapter = AsyncMock()
        adapter.inject_reply = AsyncMock()
        detector = MagicMock()
        detector.last_output_time = time.monotonic()
        notify = AsyncMock()

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="test-session",
            detector=detector,
            notify_fn=notify,
            dry_run=True,
        )

        for ic in InteractionClass:
            plan = build_plan(ic)
            result = await executor.execute(plan, "test-value", "yes_no")
            assert result.success is True
            assert "[DRY RUN]" in result.feedback_message

        adapter.inject_reply.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.safety
    async def test_chat_input_does_not_inject(self):
        adapter = AsyncMock()
        tty = AsyncMock()
        adapter._supervisors = {"test-session": tty}
        detector = MagicMock()
        detector.last_output_time = time.monotonic()
        detector.mark_injected = MagicMock()
        notify = AsyncMock()

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="test-session",
            detector=detector,
            notify_fn=notify,
            dry_run=True,
        )

        result = await executor.execute_chat_input("hello world")
        assert result.success is True
        assert "[DRY RUN]" in result.feedback_message
        tty.inject_reply.assert_not_called()
        detector.mark_injected.assert_not_called()


# ---------------------------------------------------------------------------
# Safety: router MUST NOT send prompts to channel in dry-run mode
# ---------------------------------------------------------------------------


class TestDryRunRouterNoChannelSend:
    """Critical safety invariant: dry-run mode must never send to channel."""

    @pytest.mark.asyncio
    @pytest.mark.safety
    async def test_dispatch_does_not_call_channel_send(self):
        sm = SessionManager()
        session = Session(session_id="test-session", tool="claude", command=["claude"])
        sm.register(session)

        channel = AsyncMock()
        channel.send_prompt = AsyncMock()

        router = PromptRouter(
            session_manager=sm,
            channel=channel,
            adapter_map={},
            store=MagicMock(),
            dry_run=True,
        )

        event = _event(session_id="test-session")
        await router.route_event(event)

        channel.send_prompt.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.safety
    async def test_dispatch_with_none_channel(self):
        """Dry-run with no channel must not raise."""
        sm = SessionManager()
        session = Session(session_id="test-session", tool="claude", command=["claude"])
        sm.register(session)

        router = PromptRouter(
            session_manager=sm,
            channel=None,
            adapter_map={},
            store=MagicMock(),
            dry_run=True,
        )

        event = _event(session_id="test-session")
        await router.route_event(event)  # Should not raise
