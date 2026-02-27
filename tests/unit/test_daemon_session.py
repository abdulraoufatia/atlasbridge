"""
Unit tests for DaemonManager._run_adapter_session() session orchestration.

Tests the critical wiring between PTY output, PromptDetector, and PromptRouter
without any real PTY, network, or filesystem I/O.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlasbridge.core.daemon.manager import DaemonManager
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType
from atlasbridge.core.session.manager import SessionManager


def _minimal_config(tool: str = "claude", command: list[str] | None = None) -> dict:
    return {
        "tool": tool,
        "command": command or ["claude", "--no-browser"],
        "channels": {},
        "data_dir": "/tmp/atlasbridge-test-daemon",
    }


def _make_mock_adapter(chunks: list[bytes] | None = None) -> MagicMock:
    """
    Build a mock adapter with all async methods properly mocked.

    *chunks*: bytes to serve from read_stream; b"" (EOF) appended automatically.
    """
    adapter = MagicMock()
    adapter.snapshot_context.return_value = {"pid": 1, "alive": False}
    adapter.get_detector.return_value = None
    adapter.start_session = AsyncMock()
    adapter.terminate_session = AsyncMock()
    adapter.inject_reply = AsyncMock()

    # read_stream: serve chunks then EOF
    served = list(chunks or []) + [b""]
    it = iter(served)
    adapter.read_stream = AsyncMock(side_effect=lambda sid: it.__next__())
    adapter.await_input_state = AsyncMock(return_value=False)

    return adapter


# ---------------------------------------------------------------------------
# Noop cases
# ---------------------------------------------------------------------------


class TestRunAdapterSessionNoop:
    """Cases where _run_adapter_session exits immediately without starting a PTY."""

    @pytest.mark.asyncio
    async def test_no_tool_configured_returns_immediately(self) -> None:
        manager = DaemonManager({"channels": {}})
        manager._session_manager = SessionManager()
        manager._router = AsyncMock()
        await manager._run_adapter_session()
        assert len(manager._adapters) == 0

    @pytest.mark.asyncio
    async def test_no_command_configured_returns_immediately(self) -> None:
        manager = DaemonManager({"tool": "claude", "channels": {}})
        manager._session_manager = SessionManager()
        manager._router = AsyncMock()
        await manager._run_adapter_session()
        assert len(manager._adapters) == 0

    @pytest.mark.asyncio
    async def test_unknown_tool_falls_back_to_custom_adapter(self) -> None:
        """Unknown tools resolve to CustomCLIAdapter via fallback."""
        manager = DaemonManager({"tool": "nonexistent", "command": ["foo"], "channels": {}})
        manager._session_manager = SessionManager()
        manager._router = AsyncMock()
        mock_adapter = _make_mock_adapter()
        mock_cls = MagicMock(return_value=mock_adapter)
        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=mock_cls):
            await manager._run_adapter_session()
        mock_cls.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_session_manager_returns_immediately(self) -> None:
        manager = DaemonManager(_minimal_config())
        manager._session_manager = None
        manager._router = AsyncMock()
        mock_cls = MagicMock(return_value=_make_mock_adapter())
        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=mock_cls):
            await manager._run_adapter_session()
        assert len(manager._adapters) == 0


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestRunAdapterSessionLifecycle:
    """Integration-style tests with a fully mocked adapter."""

    @pytest.mark.asyncio
    async def test_session_registered_and_marked_ended_on_exit(self) -> None:
        """Session is registered at start and marked terminal when PTY exits."""
        manager = DaemonManager(_minimal_config())
        sm = SessionManager()
        manager._session_manager = sm
        manager._router = AsyncMock()

        mock_adapter = _make_mock_adapter()
        adapter_cls = MagicMock(return_value=mock_adapter)

        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=adapter_cls):
            await manager._run_adapter_session()

        sessions = list(sm.all_sessions())
        assert len(sessions) == 1
        assert sessions[0].is_terminal

    @pytest.mark.asyncio
    async def test_adapter_registered_in_adapter_map(self) -> None:
        """The adapter is added to manager._adapters keyed by a valid session UUID."""
        manager = DaemonManager(_minimal_config())
        manager._session_manager = SessionManager()
        manager._router = AsyncMock()

        mock_adapter = _make_mock_adapter()
        adapter_cls = MagicMock(return_value=mock_adapter)

        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=adapter_cls):
            await manager._run_adapter_session()

        assert len(manager._adapters) == 1
        session_id, adapter = list(manager._adapters.items())[0]
        assert adapter is mock_adapter
        uuid.UUID(session_id)  # must be a valid UUID

    @pytest.mark.asyncio
    async def test_shutdown_triggered_after_pty_exit(self) -> None:
        """When the PTY exits (EOF), stop() is called and shutdown_event is set."""
        manager = DaemonManager(_minimal_config())
        manager._session_manager = SessionManager()
        manager._router = AsyncMock()

        mock_adapter = _make_mock_adapter()
        adapter_cls = MagicMock(return_value=mock_adapter)

        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=adapter_cls):
            await manager._run_adapter_session()

        assert manager._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_session_marked_running_with_pid(self) -> None:
        """mark_running() is called with the PID returned by snapshot_context."""
        manager = DaemonManager(_minimal_config())
        sm = SessionManager()
        manager._session_manager = sm
        manager._router = AsyncMock()

        mock_adapter = _make_mock_adapter()
        mock_adapter.snapshot_context.return_value = {"pid": 4242, "alive": False}
        adapter_cls = MagicMock(return_value=mock_adapter)

        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=adapter_cls):
            await manager._run_adapter_session()

        sessions = list(sm.all_sessions())
        assert sessions[0].pid == 4242

    @pytest.mark.asyncio
    async def test_prompt_event_routed_for_yes_no_chunk(self) -> None:
        """Output matching a YES/NO pattern causes route_event to be called."""
        manager = DaemonManager(_minimal_config())
        sm = SessionManager()
        manager._session_manager = sm
        router = AsyncMock()
        manager._router = router

        mock_adapter = _make_mock_adapter(chunks=[b"Continue? [y/n] "])
        adapter_cls = MagicMock(return_value=mock_adapter)

        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=adapter_cls):
            await manager._run_adapter_session()

        router.route_event.assert_called()
        call_arg = router.route_event.call_args[0][0]
        assert isinstance(call_arg, PromptEvent)
        assert call_arg.prompt_type == PromptType.TYPE_YES_NO
        assert call_arg.confidence == Confidence.HIGH

    @pytest.mark.asyncio
    async def test_no_event_for_non_prompt_chunk(self) -> None:
        """Plain output that is not a prompt does not trigger route_event."""
        manager = DaemonManager(_minimal_config())
        manager._session_manager = SessionManager()
        router = AsyncMock()
        manager._router = router

        mock_adapter = _make_mock_adapter(chunks=[b"Compiling project...\n"])
        adapter_cls = MagicMock(return_value=mock_adapter)

        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=adapter_cls):
            await manager._run_adapter_session()

        router.route_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_terminate_session_called_on_exit(self) -> None:
        """adapter.terminate_session() is always called during cleanup."""
        manager = DaemonManager(_minimal_config())
        manager._session_manager = SessionManager()
        manager._router = AsyncMock()

        mock_adapter = _make_mock_adapter()
        adapter_cls = MagicMock(return_value=mock_adapter)

        with patch("atlasbridge.adapters.base.AdapterRegistry.get", return_value=adapter_cls):
            await manager._run_adapter_session()

        mock_adapter.terminate_session.assert_called_once()


# ---------------------------------------------------------------------------
# _run_loop task management
# ---------------------------------------------------------------------------


class TestRunLoop:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_tasks_and_returns(self) -> None:
        """Calling stop() triggers shutdown and _run_loop() returns cleanly."""
        manager = DaemonManager({"channels": {}})
        manager._running = True
        manager._channel = AsyncMock()
        manager._router = AsyncMock()

        # receive_replies blocks forever (simulates Telegram long-poll)
        async def _blocking_replies():
            await asyncio.sleep(9999)
            return
            yield  # make it an async generator

        manager._channel.receive_replies = _blocking_replies

        async def _shutdown_soon() -> None:
            await asyncio.sleep(0.05)
            await manager.stop()

        asyncio.create_task(_shutdown_soon())
        await manager._run_loop()
        assert manager._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_no_channel_skips_reply_consumer(self) -> None:
        """Without a channel, only the TTL sweeper is created."""
        manager = DaemonManager({"channels": {}})
        manager._running = True
        manager._channel = None
        manager._router = None

        # Shut down immediately
        await manager.stop()
        await manager._run_loop()
        # No error = pass (reply_consumer was not started)
