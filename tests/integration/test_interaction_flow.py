"""Integration tests for the full interaction pipeline.

Tests the flow: PromptEvent → classify → plan → inject → verify → feedback
using mocked adapter and channel, but with real InteractionEngine,
InteractionClassifier, and InteractionExecutor.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from atlasbridge.core.interaction.engine import InteractionEngine
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType, Reply
from atlasbridge.core.routing.router import PromptRouter
from atlasbridge.core.session.manager import SessionManager
from atlasbridge.core.session.models import Session


def _make_detector(initial_time: float | None = None) -> MagicMock:
    """Create a mock detector with controllable last_output_time."""
    det = MagicMock()
    t = initial_time or time.monotonic()
    type(det).last_output_time = PropertyMock(return_value=t)
    det._advance_time = t
    return det


def _make_adapter(detector: MagicMock) -> AsyncMock:
    """Create a mock adapter that advances detector time on inject."""
    adapter = AsyncMock()

    async def _inject(session_id: str, value: str, prompt_type: str) -> None:
        # Simulate the CLI producing new output after injection
        new_time = time.monotonic() + 2.0
        type(detector).last_output_time = PropertyMock(return_value=new_time)

    adapter.inject_reply.side_effect = _inject
    return adapter


def _make_channel() -> MagicMock:
    ch = MagicMock()
    ch.send_prompt = AsyncMock(return_value="msg-1")
    ch.notify = AsyncMock()
    ch.send_output = AsyncMock()
    ch.edit_prompt_message = AsyncMock()
    ch.is_allowed = MagicMock(return_value=True)
    return ch


class TestYesNoFullPipeline:
    """Full pipeline: yes/no prompt → classify → plan → inject → verify → feedback."""

    @pytest.mark.asyncio
    async def test_yes_no_prompt_flow(self) -> None:
        detector = _make_detector()
        adapter = _make_adapter(detector)
        channel = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-001", tool="claude")
        sm.register(session)

        engine = InteractionEngine(
            adapter=adapter,
            session_id="sess-001",
            detector=detector,
            channel=channel,
            session_manager=sm,
        )

        event = PromptEvent.create(
            session_id="sess-001",
            prompt_type=PromptType.TYPE_YES_NO,
            confidence=Confidence.HIGH,
            excerpt="Continue? [y/N]",
        )

        reply = Reply(
            prompt_id=event.prompt_id,
            session_id="sess-001",
            value="y",
            nonce="nonce-1",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )

        result = await engine.handle_prompt_reply(event, reply)

        assert result.success is True
        assert result.injected_value == "y"
        assert result.cli_advanced is True
        adapter.inject_reply.assert_called_once()


class TestConfirmEnterFullPipeline:
    @pytest.mark.asyncio
    async def test_confirm_enter_flow(self) -> None:
        detector = _make_detector()
        adapter = _make_adapter(detector)
        channel = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-002", tool="claude")
        sm.register(session)

        engine = InteractionEngine(
            adapter=adapter,
            session_id="sess-002",
            detector=detector,
            channel=channel,
            session_manager=sm,
        )

        event = PromptEvent.create(
            session_id="sess-002",
            prompt_type=PromptType.TYPE_CONFIRM_ENTER,
            confidence=Confidence.HIGH,
            excerpt="Press Enter to continue...",
        )

        reply = Reply(
            prompt_id=event.prompt_id,
            session_id="sess-002",
            value="",
            nonce="nonce-2",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )

        result = await engine.handle_prompt_reply(event, reply)

        assert result.success is True
        assert "Enter" in result.feedback_message


class TestPasswordRedaction:
    @pytest.mark.asyncio
    async def test_password_redacted_in_result(self) -> None:
        detector = _make_detector()
        adapter = _make_adapter(detector)
        channel = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-003", tool="claude")
        sm.register(session)

        engine = InteractionEngine(
            adapter=adapter,
            session_id="sess-003",
            detector=detector,
            channel=channel,
            session_manager=sm,
        )

        event = PromptEvent.create(
            session_id="sess-003",
            prompt_type=PromptType.TYPE_FREE_TEXT,
            confidence=Confidence.HIGH,
            excerpt="Enter password: ",
        )

        reply = Reply(
            prompt_id=event.prompt_id,
            session_id="sess-003",
            value="super_secret_123",
            nonce="nonce-3",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )

        result = await engine.handle_prompt_reply(event, reply)

        assert result.success is True
        assert "super_secret_123" not in result.feedback_message
        assert "REDACTED" in result.injected_value


class TestChatModeInput:
    @pytest.mark.asyncio
    async def test_chat_input_through_engine(self) -> None:
        detector = _make_detector()
        adapter = AsyncMock()
        # Set up _supervisors for chat input
        mock_tty = AsyncMock()
        adapter._supervisors = {"sess-004": mock_tty}
        channel = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-004", tool="claude")
        sm.register(session)

        engine = InteractionEngine(
            adapter=adapter,
            session_id="sess-004",
            detector=detector,
            channel=channel,
            session_manager=sm,
        )

        reply = Reply(
            prompt_id="",
            session_id="sess-004",
            value="check the logs",
            nonce="nonce-4",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )

        result = await engine.handle_chat_input(reply)

        assert result.success is True
        assert "check the logs" in result.feedback_message


class TestRouterWithEngineIntegration:
    """Full integration: PromptRouter + InteractionEngine."""

    @pytest.mark.asyncio
    async def test_router_uses_engine_for_prompt(self) -> None:
        detector = _make_detector()
        adapter = _make_adapter(detector)
        channel = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-005", tool="claude")
        sm.register(session)

        engine = InteractionEngine(
            adapter=adapter,
            session_id="sess-005",
            detector=detector,
            channel=channel,
            session_manager=sm,
        )

        router = PromptRouter(
            session_manager=sm,
            channel=channel,
            adapter_map={"sess-005": adapter},
            store=MagicMock(),
            interaction_engine=engine,
        )

        event = PromptEvent.create(
            session_id="sess-005",
            prompt_type=PromptType.TYPE_YES_NO,
            confidence=Confidence.HIGH,
            excerpt="Continue? [y/N]",
        )

        await router.route_event(event)

        reply = Reply(
            prompt_id=event.prompt_id,
            session_id="sess-005",
            value="y",
            nonce="nonce-5",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )

        await router.handle_reply(reply)

        # Should have used interaction engine (which calls adapter.inject_reply)
        adapter.inject_reply.assert_called_once()
        # Channel message should be edited with structured feedback
        channel.edit_prompt_message.assert_called()

    @pytest.mark.asyncio
    async def test_router_chat_mode_fallback(self) -> None:
        detector = _make_detector()
        adapter = AsyncMock()
        adapter._supervisors = {"sess-006": AsyncMock()}
        channel = _make_channel()
        sm = SessionManager()
        session = Session(session_id="sess-006", tool="claude")
        sm.register(session)

        engine = InteractionEngine(
            adapter=adapter,
            session_id="sess-006",
            detector=detector,
            channel=channel,
            session_manager=sm,
        )

        router = PromptRouter(
            session_manager=sm,
            channel=channel,
            adapter_map={"sess-006": adapter},
            store=MagicMock(),
            chat_mode_handler=engine.handle_chat_input,
        )

        # Send a free-text reply with NO active prompt — should go to chat mode
        reply = Reply(
            prompt_id="",
            session_id="sess-006",
            value="what's happening",
            nonce="nonce-6",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )

        await router.handle_reply(reply)

        # Chat mode should have been invoked (inject into PTY)
        mock_tty = adapter._supervisors["sess-006"]
        mock_tty.inject_reply.assert_called_once()


# ---------------------------------------------------------------------------
# Plan execution flow
# ---------------------------------------------------------------------------


class TestPlanExecutionFlow:
    @pytest.mark.asyncio
    async def test_plan_execute_does_not_inject(self) -> None:
        """Execute decision does NOT inject anything into the PTY."""
        channel = AsyncMock()
        channel.is_allowed = MagicMock(return_value=True)
        channel.send_prompt.return_value = "msg-100"
        sm = SessionManager()
        session = Session(session_id="sess-plan-1", tool="claude")
        sm.register(session)

        detector = _make_detector()
        adapter = _make_adapter(detector)

        router = PromptRouter(
            session_manager=sm,
            channel=channel,
            adapter_map={"sess-plan-1": adapter},
            store=MagicMock(),
        )

        reply = Reply(
            prompt_id="__plan__",
            session_id="sess-plan-1",
            value="execute",
            nonce="",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )

        await router.handle_reply(reply)

        # Execute should NOT inject into PTY
        adapter.inject_reply.assert_not_called()
        # But should notify the channel
        channel.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_cancel_uses_chat_handler(self) -> None:
        """Cancel decision goes through the chat mode handler."""
        channel = AsyncMock()
        channel.is_allowed = MagicMock(return_value=True)
        channel.send_prompt.return_value = "msg-100"
        sm = SessionManager()
        session = Session(session_id="sess-plan-2", tool="claude")
        sm.register(session)

        chat_handler = AsyncMock()

        router = PromptRouter(
            session_manager=sm,
            channel=channel,
            adapter_map={},
            store=MagicMock(),
            chat_mode_handler=chat_handler,
        )

        reply = Reply(
            prompt_id="__plan__",
            session_id="sess-plan-2",
            value="cancel",
            nonce="",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )

        await router.handle_reply(reply)

        # Cancel should go through chat handler
        chat_handler.assert_called_once()
        cancel_reply = chat_handler.call_args[0][0]
        assert "cancel" in cancel_reply.value.lower()
        # Channel should be notified
        channel.notify.assert_called()
