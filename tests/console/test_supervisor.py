"""Unit tests for ProcessSupervisor."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlasbridge.console.supervisor import (
    ProcessInfo,
    ProcessSupervisor,
    _pid_alive,
    _port_listening,
)

# ---------------------------------------------------------------------------
# ProcessInfo dataclass
# ---------------------------------------------------------------------------


class TestProcessInfo:
    def test_defaults(self):
        info = ProcessInfo(name="daemon")
        assert info.name == "daemon"
        assert info.pid is None
        assert info.running is False
        assert info.started_at is None
        assert info.tool == ""
        assert info.port is None

    def test_uptime_when_not_running(self):
        info = ProcessInfo(name="daemon", running=False)
        assert info.uptime_seconds == 0.0
        assert info.uptime_display == "0s"

    def test_uptime_when_running(self):
        started = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        info = ProcessInfo(name="daemon", running=True, started_at=started)
        assert info.uptime_seconds > 0
        # Display should be hours format for such a long uptime
        assert "h" in info.uptime_display

    def test_uptime_display_minutes(self):
        from datetime import timedelta

        started = datetime.now(UTC) - timedelta(minutes=5, seconds=32)
        info = ProcessInfo(name="dashboard", running=True, started_at=started)
        display = info.uptime_display
        assert "m" in display

    def test_uptime_display_seconds(self):
        from datetime import timedelta

        started = datetime.now(UTC) - timedelta(seconds=45)
        info = ProcessInfo(name="agent", running=True, started_at=started)
        display = info.uptime_display
        assert "s" in display

    def test_agent_with_tool(self):
        info = ProcessInfo(name="agent", pid=1234, running=True, tool="claude")
        assert info.tool == "claude"

    def test_dashboard_with_port(self):
        info = ProcessInfo(name="dashboard", pid=5678, running=True, port=8787)
        assert info.port == 8787


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_pid_alive_returns_true_for_current_process(self):
        import os

        assert _pid_alive(os.getpid()) is True

    def test_pid_alive_returns_false_for_invalid_pid(self):
        assert _pid_alive(999999999) is False

    def test_port_listening_closed_port(self):
        # Pick a likely-unused port
        assert _port_listening(19999) is False


# ---------------------------------------------------------------------------
# ProcessSupervisor — daemon
# ---------------------------------------------------------------------------


class TestDaemonLifecycle:
    def test_daemon_status_when_not_running(self):
        supervisor = ProcessSupervisor()
        with (
            patch("atlasbridge.console.supervisor._pid_alive", return_value=False),
            patch("atlasbridge.cli._daemon._read_pid", return_value=None),
        ):
            status = supervisor.daemon_status()
            assert status.name == "daemon"
            assert status.running is False

    def test_daemon_status_when_running(self):
        supervisor = ProcessSupervisor()
        with (
            patch("atlasbridge.cli._daemon._read_pid", return_value=1234),
            patch("atlasbridge.console.supervisor._pid_alive", return_value=True),
        ):
            status = supervisor.daemon_status()
            assert status.name == "daemon"
            assert status.running is True
            assert status.pid == 1234

    @pytest.mark.asyncio
    async def test_start_daemon_success(self):
        supervisor = ProcessSupervisor()
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("atlasbridge.cli._daemon._read_pid", return_value=9999),
            patch("atlasbridge.console.supervisor._pid_alive", return_value=True),
        ):
            result = await supervisor.start_daemon()
            assert result.name == "daemon"
            assert result.running is True

    @pytest.mark.asyncio
    async def test_stop_daemon_success(self):
        supervisor = ProcessSupervisor()
        with (
            patch("atlasbridge.cli._daemon._read_pid", return_value=1234),
            patch("atlasbridge.cli._daemon._pid_alive", return_value=False),
            patch("os.kill"),
        ):
            # Daemon is not alive after SIGTERM
            result = await supervisor.stop_daemon()
            assert result is False  # _pid_alive says not alive at check time


# ---------------------------------------------------------------------------
# ProcessSupervisor — dashboard
# ---------------------------------------------------------------------------


class TestDashboardLifecycle:
    def test_dashboard_status_not_running(self):
        supervisor = ProcessSupervisor()
        with patch("atlasbridge.console.supervisor._port_listening", return_value=False):
            status = supervisor.dashboard_status(8787)
            assert status.name == "dashboard"
            assert status.running is False
            assert status.port == 8787

    @pytest.mark.asyncio
    async def test_start_dashboard_success(self):
        supervisor = ProcessSupervisor()
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 5555

        with (
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc),
            patch("atlasbridge.console.supervisor._port_listening", return_value=True),
        ):
            result = await supervisor.start_dashboard(port=8787)
            assert result.name == "dashboard"
            assert result.running is True
            assert result.port == 8787

    @pytest.mark.asyncio
    async def test_stop_dashboard_success(self):
        supervisor = ProcessSupervisor()
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock(return_value=0)
        supervisor._dashboard_proc = mock_proc

        result = await supervisor.stop_dashboard()
        assert result is True
        mock_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_dashboard_when_not_running(self):
        supervisor = ProcessSupervisor()
        result = await supervisor.stop_dashboard()
        assert result is False


# ---------------------------------------------------------------------------
# ProcessSupervisor — agent
# ---------------------------------------------------------------------------


class TestAgentLifecycle:
    def test_agent_status_not_running(self):
        supervisor = ProcessSupervisor()
        status = supervisor.agent_status()
        assert status.name == "agent"
        assert status.running is False

    @pytest.mark.asyncio
    async def test_start_agent_success(self):
        supervisor = ProcessSupervisor()
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 7777

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc
        ):
            result = await supervisor.start_agent(tool="claude")
            assert result.name == "agent"
            assert result.running is True
            assert result.tool == "claude"

    @pytest.mark.asyncio
    async def test_stop_agent_success(self):
        supervisor = ProcessSupervisor()
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock(return_value=0)
        supervisor._agent_proc = mock_proc

        result = await supervisor.stop_agent()
        assert result is True
        mock_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_agent_when_not_running(self):
        supervisor = ProcessSupervisor()
        result = await supervisor.stop_agent()
        assert result is False

    @pytest.mark.asyncio
    async def test_start_agent_with_custom_tool(self):
        supervisor = ProcessSupervisor()
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 8888

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc
        ):
            result = await supervisor.start_agent(tool="openai")
            assert result.tool == "openai"


# ---------------------------------------------------------------------------
# ProcessSupervisor — lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_shutdown_all(self):
        supervisor = ProcessSupervisor()

        # Set up mock agent and dashboard processes
        mock_agent = MagicMock()
        mock_agent.returncode = None
        mock_agent.terminate = MagicMock()
        mock_agent.wait = AsyncMock(return_value=0)
        supervisor._agent_proc = mock_agent

        mock_dash = MagicMock()
        mock_dash.returncode = None
        mock_dash.terminate = MagicMock()
        mock_dash.wait = AsyncMock(return_value=0)
        supervisor._dashboard_proc = mock_dash

        with patch.object(supervisor, "stop_daemon", new_callable=AsyncMock) as mock_stop_daemon:
            await supervisor.shutdown_all()
            mock_agent.terminate.assert_called_once()
            mock_dash.terminate.assert_called_once()
            mock_stop_daemon.assert_called_once()

    def test_all_status_returns_list(self):
        supervisor = ProcessSupervisor()
        with (
            patch("atlasbridge.cli._daemon._read_pid", return_value=None),
            patch("atlasbridge.console.supervisor._port_listening", return_value=False),
        ):
            statuses = supervisor.all_status()
            assert len(statuses) == 3
            assert statuses[0].name == "daemon"
            assert statuses[1].name == "dashboard"
            assert statuses[2].name == "agent"
