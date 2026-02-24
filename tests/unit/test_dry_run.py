"""Unit tests for dry-run mode across the pipeline."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from atlasbridge.core.audit.writer import AuditWriter
from atlasbridge.core.interaction.classifier import InteractionClass
from atlasbridge.core.interaction.engine import InteractionEngine
from atlasbridge.core.interaction.executor import InteractionExecutor
from atlasbridge.core.interaction.plan import build_plan
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType, Reply
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
# Executor dry-run
# ---------------------------------------------------------------------------


class TestExecutorDryRun:
    @pytest.mark.asyncio
    async def test_returns_success_without_injection(self):
        adapter = AsyncMock()
        detector = MagicMock()
        detector.last_output_time = time.monotonic()
        notify = AsyncMock()

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="s1",
            detector=detector,
            notify_fn=notify,
            dry_run=True,
        )

        plan = build_plan(InteractionClass.YES_NO)
        result = await executor.execute(plan, "y", "yes_no")

        assert result.success is True
        assert result.injected_value == "y"
        assert "[DRY RUN]" in result.feedback_message
        adapter.inject_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_password_redacted_in_dry_run(self):
        adapter = AsyncMock()
        detector = MagicMock()
        detector.last_output_time = time.monotonic()
        notify = AsyncMock()

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="s1",
            detector=detector,
            notify_fn=notify,
            dry_run=True,
        )

        plan = build_plan(InteractionClass.PASSWORD_INPUT)
        result = await executor.execute(plan, "my-secret", "free_text")

        assert "[REDACTED]" in result.injected_value
        assert "my-secret" not in result.feedback_message
        adapter.inject_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_input_dry_run(self):
        adapter = AsyncMock()
        adapter._supervisors = {}
        detector = MagicMock()
        detector.last_output_time = time.monotonic()
        notify = AsyncMock()

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="s1",
            detector=detector,
            notify_fn=notify,
            dry_run=True,
        )

        result = await executor.execute_chat_input("hello")

        assert result.success is True
        assert "[DRY RUN]" in result.feedback_message

    @pytest.mark.asyncio
    async def test_dry_run_false_still_injects(self):
        """Verify normal mode still injects (regression guard)."""
        adapter = AsyncMock()
        detector = MagicMock()
        detector.last_output_time = time.monotonic()
        notify = AsyncMock()

        executor = InteractionExecutor(
            adapter=adapter,
            session_id="s1",
            detector=detector,
            notify_fn=notify,
            dry_run=False,
        )

        plan = build_plan(InteractionClass.CHAT_INPUT)
        await executor.execute(plan, "y", "yes_no")

        adapter.inject_reply.assert_called_once()


# ---------------------------------------------------------------------------
# Engine dry-run
# ---------------------------------------------------------------------------


class TestEngineDryRun:
    @pytest.mark.asyncio
    async def test_engine_passes_dry_run_to_executor(self):
        adapter = AsyncMock()
        adapter.inject_reply = AsyncMock()
        detector = MagicMock()
        detector.last_output_time = time.monotonic()
        channel = AsyncMock()
        sm = SessionManager()

        engine = InteractionEngine(
            adapter=adapter,
            session_id="s1",
            detector=detector,
            channel=channel,
            session_manager=sm,
            dry_run=True,
        )

        event = _event(session_id="s1")
        reply = Reply(
            prompt_id=event.prompt_id,
            session_id="s1",
            value="y",
            nonce="n1",
            channel_identity="telegram:123",
            timestamp="",
        )

        result = await engine.handle_prompt_reply(event, reply)

        assert result.success is True
        assert "[DRY RUN]" in result.feedback_message
        adapter.inject_reply.assert_not_called()


# ---------------------------------------------------------------------------
# Router dry-run
# ---------------------------------------------------------------------------


class TestRouterDryRun:
    @pytest.mark.asyncio
    async def test_route_event_logs_without_channel(self):
        sm = SessionManager()
        session = Session(session_id="s1", tool="claude", command=["claude"])
        sm.register(session)

        channel = AsyncMock()

        router = PromptRouter(
            session_manager=sm,
            channel=channel,
            adapter_map={},
            store=MagicMock(),
            dry_run=True,
        )

        event = _event(session_id="s1")
        await router.route_event(event)

        # Channel.send_prompt NOT called
        channel.send_prompt.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_machine_transitions_to_routed(self):
        sm = SessionManager()
        session = Session(session_id="s1", tool="claude", command=["claude"])
        sm.register(session)

        router = PromptRouter(
            session_manager=sm,
            channel=None,
            adapter_map={},
            store=MagicMock(),
            dry_run=True,
        )

        event = _event(session_id="s1")
        await router.route_event(event)

        # State machine should exist and be in ROUTED state
        assert event.prompt_id in router._machines
        machine = router._machines[event.prompt_id]
        assert machine.status.value == "routed"


# ---------------------------------------------------------------------------
# Audit writer dry-run tagging
# ---------------------------------------------------------------------------


class TestAuditWriterDryRun:
    def test_dry_run_tags_payload(self, tmp_path):
        from atlasbridge.core.store.database import Database

        db = Database(tmp_path / "test.db")
        db.connect()

        writer = AuditWriter(db, dry_run=True)
        writer.session_started("s1", "claude", ["claude"])

        rows = db.get_recent_audit_events(limit=10)
        assert len(rows) >= 1
        import json

        payload = json.loads(rows[0]["payload"])
        assert payload["dry_run"] is True

        db.close()

    def test_normal_mode_no_tag(self, tmp_path):
        from atlasbridge.core.store.database import Database

        db = Database(tmp_path / "test.db")
        db.connect()

        writer = AuditWriter(db, dry_run=False)
        writer.session_started("s1", "claude", ["claude"])

        rows = db.get_recent_audit_events(limit=10)
        assert len(rows) >= 1
        import json

        payload = json.loads(rows[0]["payload"])
        assert "dry_run" not in payload

        db.close()
