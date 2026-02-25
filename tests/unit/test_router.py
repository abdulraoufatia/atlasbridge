"""Unit tests for atlasbridge.core.routing.router — PromptRouter forward/return paths."""

from __future__ import annotations

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptStatus, PromptType, Reply
from atlasbridge.core.routing.router import PromptRouter
from atlasbridge.core.session.manager import SessionManager
from atlasbridge.core.session.models import Session


def _session(tool: str = "claude") -> Session:
    return Session(session_id=str(uuid.uuid4()), tool=tool)


def _mock_store() -> MagicMock:
    """Create a store mock with delivery tracking methods properly configured."""
    store = MagicMock()
    store.was_delivered.return_value = False
    store.record_delivery.return_value = True
    return store


def _event(
    session_id: str,
    confidence: Confidence = Confidence.HIGH,
    excerpt: str = "Continue? [y/N]",
) -> PromptEvent:
    return PromptEvent.create(
        session_id=session_id,
        prompt_type=PromptType.TYPE_YES_NO,
        confidence=confidence,
        excerpt=excerpt,
    )


def _reply(prompt_id: str, session_id: str, value: str = "y") -> Reply:
    from datetime import datetime

    return Reply(
        prompt_id=prompt_id,
        session_id=session_id,
        value=value,
        nonce="test-nonce",
        channel_identity="telegram:12345",
        timestamp=datetime.now(UTC).isoformat(),
    )


@pytest.fixture
def session_manager() -> SessionManager:
    return SessionManager()


@pytest.fixture
def mock_channel() -> AsyncMock:
    channel = AsyncMock()
    channel.send_prompt.return_value = "msg-100"
    # is_allowed is a sync method — use MagicMock so it doesn't return a coroutine
    channel.is_allowed = MagicMock(return_value=True)
    # get_allowed_identities is sync — use MagicMock
    channel.get_allowed_identities = MagicMock(return_value=["telegram:12345"])
    channel.channel_name = "telegram"
    return channel


@pytest.fixture
def mock_adapter() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def session(session_manager: SessionManager) -> Session:
    s = _session()
    session_manager.register(s)
    return s


@pytest.fixture
def router(session_manager: SessionManager, mock_channel: AsyncMock) -> PromptRouter:
    return PromptRouter(
        session_manager=session_manager,
        channel=mock_channel,
        adapter_map={},
        store=_mock_store(),
    )


# ---------------------------------------------------------------------------
# Forward path
# ---------------------------------------------------------------------------


class TestRouteEvent:
    @pytest.mark.asyncio
    async def test_high_confidence_dispatched(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        event = _event(session.session_id, Confidence.HIGH)
        await router.route_event(event)
        mock_channel.send_prompt.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_confidence_dispatched_as_ambiguous(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        # LOW confidence prompts are routed to the channel so the user can decide;
        # the channel labels them as ambiguous in the message text.
        event = _event(session.session_id, Confidence.LOW)
        await router.route_event(event)
        mock_channel.send_prompt.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_session_drops_event(
        self,
        router: PromptRouter,
        mock_channel: AsyncMock,
    ) -> None:
        event = _event("nonexistent-session-id")
        await router.route_event(event)
        mock_channel.send_prompt.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_machine_advances_to_awaiting_reply(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        event = _event(session.session_id)
        await router.route_event(event)
        sm = router._machines.get(event.prompt_id)
        assert sm is not None
        assert sm.status == PromptStatus.AWAITING_REPLY

    @pytest.mark.asyncio
    async def test_second_prompt_supersedes_first(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        e1 = _event(session.session_id, excerpt="Continue? [y/N]")
        e2 = _event(session.session_id, excerpt="Overwrite file? [y/N]")
        await router.route_event(e1)  # dispatched
        await router.route_event(e2)  # supersedes — different content, dispatched
        # Both prompts are dispatched (different content, no dedup)
        assert mock_channel.send_prompt.call_count == 2
        # Both have state machines registered
        assert e1.prompt_id in router._machines
        assert e2.prompt_id in router._machines


# ---------------------------------------------------------------------------
# Return path
# ---------------------------------------------------------------------------


class TestHandleReply:
    @pytest.mark.asyncio
    async def test_valid_reply_injected(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        event = _event(session.session_id)
        await router.route_event(event)

        # Add the adapter for this session
        router._adapter_map[session.session_id] = mock_adapter

        reply = _reply(event.prompt_id, session.session_id, value="y")
        await router.handle_reply(reply)

        mock_adapter.inject_reply.assert_called_once()
        sm = router._machines[event.prompt_id]
        assert sm.status == PromptStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_unknown_prompt_id_silently_dropped(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        reply = _reply("unknown-prompt-id", session.session_id)
        await router.handle_reply(reply)
        # Unknown prompts are silently dropped (no spam to channel)
        mock_channel.notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_disallowed_identity_rejected(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        event = _event(session.session_id)
        await router.route_event(event)
        router._adapter_map[session.session_id] = mock_adapter

        # Make channel reject this identity
        mock_channel.is_allowed = MagicMock(return_value=False)

        reply = _reply(event.prompt_id, session.session_id)
        await router.handle_reply(reply)
        mock_adapter.inject_reply.assert_not_called()


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


class TestInteractionEngineIntegration:
    """Tests for PromptRouter with interaction_engine set."""

    @pytest.mark.asyncio
    async def test_reply_uses_interaction_engine(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
    ) -> None:
        session = _session()
        session_manager.register(session)

        mock_engine = AsyncMock()
        mock_engine.handle_prompt_reply.return_value = MagicMock(
            success=True,
            escalated=False,
            feedback_message="Sent: y + Enter\nCLI advanced",
            injected_value="y",
        )

        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={},
            store=_mock_store(),
            interaction_engine=mock_engine,
        )

        event = _event(session.session_id)
        await router.route_event(event)
        reply = _reply(event.prompt_id, session.session_id, value="y")
        await router.handle_reply(reply)

        mock_engine.handle_prompt_reply.assert_called_once()
        sm = router._machines[event.prompt_id]
        assert sm.status == PromptStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_escalated_result_transitions_to_failed(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
    ) -> None:
        session = _session()
        session_manager.register(session)

        mock_engine = AsyncMock()
        mock_engine.handle_prompt_reply.return_value = MagicMock(
            success=False,
            escalated=True,
            feedback_message="CLI did not respond after retries. Please respond locally.",
            injected_value="y",
        )

        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={},
            store=_mock_store(),
            interaction_engine=mock_engine,
        )

        event = _event(session.session_id)
        await router.route_event(event)
        reply = _reply(event.prompt_id, session.session_id)
        await router.handle_reply(reply)

        sm = router._machines[event.prompt_id]
        assert sm.status == PromptStatus.FAILED

    @pytest.mark.asyncio
    async def test_feedback_message_sent_to_channel(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
    ) -> None:
        session = _session()
        session_manager.register(session)

        mock_engine = AsyncMock()
        mock_engine.handle_prompt_reply.return_value = MagicMock(
            success=True,
            escalated=False,
            feedback_message="Sent: y + Enter",
            injected_value="y",
        )

        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={},
            store=_mock_store(),
            interaction_engine=mock_engine,
        )

        event = _event(session.session_id)
        await router.route_event(event)
        reply = _reply(event.prompt_id, session.session_id, value="y")
        await router.handle_reply(reply)

        # edit_prompt_message should be called with the feedback
        mock_channel.edit_prompt_message.assert_called()
        call_args = mock_channel.edit_prompt_message.call_args
        assert "Sent: y + Enter" in call_args[0][1]


class TestChatModeHandler:
    """Tests for PromptRouter with chat_mode_handler set."""

    @pytest.mark.asyncio
    async def test_free_text_no_prompt_routes_to_chat(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
    ) -> None:
        session = _session()
        session_manager.register(session)

        chat_handler = AsyncMock()

        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={},
            store=_mock_store(),
            chat_mode_handler=chat_handler,
        )

        # Send a free-text reply with no active prompt
        from datetime import datetime

        reply = Reply(
            prompt_id="",
            session_id=session.session_id,
            value="check the logs",
            nonce="nonce-1",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )
        await router.handle_reply(reply)
        chat_handler.assert_called_once_with(reply)

    @pytest.mark.asyncio
    async def test_free_text_with_active_prompt_resolves_normally(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        session = _session()
        session_manager.register(session)

        chat_handler = AsyncMock()

        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={session.session_id: mock_adapter},
            store=_mock_store(),
            chat_mode_handler=chat_handler,
        )

        # Create an active prompt
        event = _event(session.session_id)
        await router.route_event(event)

        # Send a free-text reply (should resolve to the active prompt, not chat)
        from datetime import datetime

        reply = Reply(
            prompt_id="",
            session_id=session.session_id,
            value="y",
            nonce="nonce-2",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )
        await router.handle_reply(reply)

        # Chat handler should NOT be called — it went to the active prompt
        chat_handler.assert_not_called()
        mock_adapter.inject_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_chat_handler_drops_free_text(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        """Without chat_mode_handler, free-text with no prompt is silently dropped."""
        from datetime import datetime

        reply = Reply(
            prompt_id="",
            session_id=session.session_id,
            value="hello",
            nonce="nonce-3",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )
        await router.handle_reply(reply)
        # No error, just dropped
        mock_channel.notify.assert_not_called()


class TestExpireOverdue:
    @pytest.mark.asyncio
    async def test_overdue_prompt_expired(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        event = _event(session.session_id)
        await router.route_event(event)

        # Push TTL into the past
        from datetime import datetime, timedelta

        sm = router._machines[event.prompt_id]
        sm.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        await router.expire_overdue()
        assert sm.status == PromptStatus.EXPIRED


# ---------------------------------------------------------------------------
# Plan response handling
# ---------------------------------------------------------------------------


class TestPlanResponse:
    @pytest.mark.asyncio
    async def test_plan_execute_notifies_channel(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
    ) -> None:
        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={},
            store=_mock_store(),
        )
        s = _session()
        session_manager.register(s)
        await router.handle_plan_response(s.session_id, "execute")
        mock_channel.notify.assert_called_once()
        assert "accepted" in mock_channel.notify.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_plan_modify_sends_guidance(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
    ) -> None:
        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={},
            store=_mock_store(),
        )
        s = _session()
        session_manager.register(s)
        await router.handle_plan_response(s.session_id, "modify")
        mock_channel.notify.assert_called_once()
        assert "modifications" in mock_channel.notify.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_plan_cancel_injects_via_chat(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
    ) -> None:
        chat_handler = AsyncMock()
        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={},
            store=_mock_store(),
            chat_mode_handler=chat_handler,
        )
        s = _session()
        session_manager.register(s)
        await router.handle_plan_response(s.session_id, "cancel")
        chat_handler.assert_called_once()
        sent_reply = chat_handler.call_args[0][0]
        assert "cancel" in sent_reply.value.lower()

    @pytest.mark.asyncio
    async def test_plan_sentinel_prompt_id_routed(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
    ) -> None:
        """Reply with prompt_id='__plan__' is routed to handle_plan_response."""
        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={},
            store=_mock_store(),
        )
        s = _session()
        session_manager.register(s)
        from datetime import datetime

        reply = Reply(
            prompt_id="__plan__",
            session_id=s.session_id,
            value="execute",
            nonce="",
            channel_identity="telegram:12345",
            timestamp=datetime.now(UTC).isoformat(),
        )
        await router.handle_reply(reply)
        mock_channel.notify.assert_called_once()
        assert "accepted" in mock_channel.notify.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# Spam prevention — content dedup + failsafe
# ---------------------------------------------------------------------------


class TestSpamPrevention:
    """Tests for prompt deduplication and failsafe rate limiting in the router."""

    @pytest.mark.asyncio
    async def test_same_content_deduplicated(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        """Same excerpt content while first prompt is still active → suppressed."""
        e1 = _event(session.session_id, excerpt="Continue? [y/N]")
        e2 = _event(session.session_id, excerpt="Continue? [y/N]")
        await router.route_event(e1)
        await router.route_event(e2)
        # Only the first should be dispatched
        assert mock_channel.send_prompt.call_count == 1

    @pytest.mark.asyncio
    async def test_different_content_not_deduplicated(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        """Different excerpt content → both dispatched."""
        e1 = _event(session.session_id, excerpt="Continue? [y/N]")
        e2 = _event(session.session_id, excerpt="Overwrite? [y/N]")
        await router.route_event(e1)
        await router.route_event(e2)
        assert mock_channel.send_prompt.call_count == 2

    @pytest.mark.asyncio
    async def test_failsafe_pauses_after_max_dispatches(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
    ) -> None:
        """More than 5 dispatches in 60s window → failsafe pauses routing."""
        from atlasbridge.core.routing.router import _FAILSAFE_MAX_DISPATCHES

        for i in range(_FAILSAFE_MAX_DISPATCHES):
            e = _event(session.session_id, excerpt=f"Prompt {i}? [y/N]")
            await router.route_event(e)

        assert mock_channel.send_prompt.call_count == _FAILSAFE_MAX_DISPATCHES

        # One more should be blocked by failsafe
        extra = _event(session.session_id, excerpt="One more? [y/N]")
        await router.route_event(extra)
        assert mock_channel.send_prompt.call_count == _FAILSAFE_MAX_DISPATCHES  # unchanged

    @pytest.mark.asyncio
    async def test_failsafe_resets_after_reply(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        """Successful reply resets the failsafe counter."""
        s = _session()
        session_manager.register(s)

        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={s.session_id: mock_adapter},
            store=_mock_store(),
        )

        # Dispatch 3 events
        for i in range(3):
            e = _event(s.session_id, excerpt=f"Q{i}? [y/N]")
            await router.route_event(e)

        assert mock_channel.send_prompt.call_count == 3

        # Reply to last prompt — resets counter
        last_event = list(router._machines.values())[-1].event
        reply = _reply(last_event.prompt_id, s.session_id, value="y")
        await router.handle_reply(reply)

        # Counter should be reset — can dispatch more
        assert s.session_id not in router._session_dispatch_counts

    @pytest.mark.asyncio
    async def test_dedup_allows_after_resolution(
        self,
        session_manager: SessionManager,
        mock_channel: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        """After a prompt is resolved, same content can be dispatched again."""
        s = _session()
        session_manager.register(s)

        router = PromptRouter(
            session_manager=session_manager,
            channel=mock_channel,
            adapter_map={s.session_id: mock_adapter},
            store=_mock_store(),
        )

        # First event
        e1 = _event(s.session_id, excerpt="Continue? [y/N]")
        await router.route_event(e1)
        assert mock_channel.send_prompt.call_count == 1

        # Reply resolves it
        reply = _reply(e1.prompt_id, s.session_id, value="y")
        await router.handle_reply(reply)

        # Same content again — should dispatch (prompt was resolved)
        e2 = _event(s.session_id, excerpt="Continue? [y/N]")
        await router.route_event(e2)
        assert mock_channel.send_prompt.call_count == 2
