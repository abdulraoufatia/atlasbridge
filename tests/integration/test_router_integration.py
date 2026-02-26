"""
Router integration test with real SQLite database.

Exercises the full forward + return path through the PromptRouter
with a real SQLite store (no mocks on the DB layer).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptStatus, PromptType, Reply
from atlasbridge.core.routing.router import PromptRouter
from atlasbridge.core.session.manager import SessionManager
from atlasbridge.core.session.models import Session
from atlasbridge.core.store.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    database.connect()
    yield database
    database.close()


@pytest.fixture
def session_manager() -> SessionManager:
    return SessionManager()


@pytest.fixture
def mock_channel() -> AsyncMock:
    channel = AsyncMock()
    channel.send_prompt.return_value = "msg-200"
    channel.is_allowed = MagicMock(return_value=True)
    channel.get_allowed_identities = MagicMock(return_value=["telegram:12345"])
    channel.channel_name = "telegram"
    return channel


@pytest.fixture
def mock_adapter() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def session(session_manager: SessionManager) -> Session:
    s = Session(session_id=str(uuid.uuid4()), tool="claude")
    session_manager.register(s)
    return s


@pytest.fixture
def router(
    session_manager: SessionManager,
    mock_channel: AsyncMock,
    db: Database,
) -> PromptRouter:
    return PromptRouter(
        session_manager=session_manager,
        channel=mock_channel,
        adapter_map={},
        store=db,
    )


def _event(session_id: str, excerpt: str = "Continue? [y/N]") -> PromptEvent:
    return PromptEvent.create(
        session_id=session_id,
        prompt_type=PromptType.TYPE_YES_NO,
        confidence=Confidence.HIGH,
        excerpt=excerpt,
    )


def _reply(prompt_id: str, session_id: str, value: str = "y") -> Reply:
    return Reply(
        prompt_id=prompt_id,
        session_id=session_id,
        value=value,
        nonce="test-nonce",
        channel_identity="telegram:12345",
        timestamp=datetime.now(UTC).isoformat(),
    )


class TestRouterWithRealSQLite:
    """Integration tests using real SQLite for the store."""

    @pytest.mark.asyncio
    async def test_full_forward_return_cycle(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        """Forward path → dispatch → return path → inject → resolve."""
        event = _event(session.session_id)
        await router.route_event(event)

        # Verify prompt is now AWAITING_REPLY
        sm = router._machines[event.prompt_id]
        assert sm.status == PromptStatus.AWAITING_REPLY

        # Inject adapter and send reply
        router._adapter_map[session.session_id] = mock_adapter
        reply = _reply(event.prompt_id, session.session_id, "y")
        await router.handle_reply(reply)

        # Verify full resolution
        assert sm.status == PromptStatus.RESOLVED
        mock_adapter.inject_reply.assert_called_once()
        assert sm.latency_ms is not None
        assert sm.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_second_prompt_supersedes_first(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
        mock_adapter: AsyncMock,
    ) -> None:
        """New prompts supersede old ones — both dispatched immediately."""
        e1 = _event(session.session_id, excerpt="Continue? [y/N]")
        e2 = _event(session.session_id, excerpt="Overwrite file? [y/N]")

        await router.route_event(e1)  # dispatched
        await router.route_event(e2)  # supersedes — also dispatched

        # Both dispatched (no queueing)
        assert mock_channel.send_prompt.call_count == 2
        sm1 = router._machines[e1.prompt_id]
        sm2 = router._machines[e2.prompt_id]
        assert sm1.status == PromptStatus.AWAITING_REPLY
        assert sm2.status == PromptStatus.AWAITING_REPLY

    @pytest.mark.asyncio
    async def test_db_session_survives_full_cycle(
        self,
        router: PromptRouter,
        session: Session,
        mock_channel: AsyncMock,
        mock_adapter: AsyncMock,
        db: Database,
    ) -> None:
        """Verify the DB layer works alongside the router for session ops."""
        # Save session to DB
        db.save_session(session.session_id, "claude", ["claude"], cwd="/tmp")

        event = _event(session.session_id)
        await router.route_event(event)

        router._adapter_map[session.session_id] = mock_adapter
        reply = _reply(event.prompt_id, session.session_id, "n")
        await router.handle_reply(reply)

        # DB should still have the session
        row = db.get_session(session.session_id)
        assert row is not None
        assert row["tool"] == "claude"
