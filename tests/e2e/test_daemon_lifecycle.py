"""
End-to-end test for daemon lifecycle.

Tests the DaemonManager startup → subsystem init → shutdown cycle
without requiring a real Telegram bot or PTY process.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from atlasbridge.core.daemon.manager import DaemonManager


@pytest.fixture
def config(tmp_path: Path) -> dict:
    """Minimal config that avoids needing real channels or tools."""
    return {
        "data_dir": str(tmp_path / "data"),
    }


class TestDaemonLifecycle:
    """End-to-end daemon startup and shutdown."""

    @pytest.mark.asyncio
    async def test_daemon_starts_and_stops_cleanly(self, config: dict) -> None:
        """Daemon should start, create DB, write PID file, and stop on signal."""
        manager = DaemonManager(config)

        # Start the daemon in a background task and immediately signal shutdown
        async def start_then_stop() -> None:
            # Give the daemon a moment to initialise, then stop
            await asyncio.sleep(0.1)
            await manager.stop()

        task = asyncio.create_task(manager.start())
        stop_task = asyncio.create_task(start_then_stop())

        await asyncio.wait_for(
            asyncio.gather(task, stop_task, return_exceptions=True),
            timeout=5.0,
        )

        # PID file should be cleaned up after stop
        pid_file = Path(config["data_dir"]) / "atlasbridge.pid"
        assert not pid_file.exists()

        # Database file should have been created
        db_file = Path(config["data_dir"]) / "atlasbridge.db"
        assert db_file.exists()

    @pytest.mark.asyncio
    async def test_daemon_creates_data_dir(self, config: dict) -> None:
        """Daemon should create its data directory if it doesn't exist."""
        data_dir = Path(config["data_dir"])
        assert not data_dir.exists()

        manager = DaemonManager(config)

        async def stop_quickly() -> None:
            await asyncio.sleep(0.05)
            await manager.stop()

        task = asyncio.create_task(manager.start())
        stop_task = asyncio.create_task(stop_quickly())

        await asyncio.wait_for(
            asyncio.gather(task, stop_task, return_exceptions=True),
            timeout=5.0,
        )

        assert data_dir.exists()

    @pytest.mark.asyncio
    async def test_daemon_no_channel_still_starts(self, config: dict) -> None:
        """Daemon should start even without any channel configured."""
        manager = DaemonManager(config)

        async def stop_quickly() -> None:
            await asyncio.sleep(0.05)
            await manager.stop()

        task = asyncio.create_task(manager.start())
        stop_task = asyncio.create_task(stop_quickly())

        # Should not raise
        results = await asyncio.wait_for(
            asyncio.gather(task, stop_task, return_exceptions=True),
            timeout=5.0,
        )
        # No exceptions should propagate
        for r in results:
            if isinstance(r, Exception):
                raise r
