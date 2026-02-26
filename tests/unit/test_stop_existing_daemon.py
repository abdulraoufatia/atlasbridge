"""Unit tests for _stop_existing_daemon in _run.py."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from atlasbridge.cli._run import _stop_existing_daemon

# The function imports _read_pid and _pid_alive from atlasbridge.cli._daemon
# at call time, so we patch them at the source module.
_DAEMON = "atlasbridge.cli._daemon"


class TestStopExistingDaemon:
    def test_noop_when_no_pid_file(self) -> None:
        with patch(f"{_DAEMON}._read_pid", return_value=None):
            _stop_existing_daemon()  # should return silently

    def test_noop_when_pid_not_alive(self) -> None:
        with (
            patch(f"{_DAEMON}._read_pid", return_value=9999),
            patch(f"{_DAEMON}._pid_alive", return_value=False),
        ):
            _stop_existing_daemon()  # should return silently

    def test_does_not_kill_self(self) -> None:
        own_pid = os.getpid()
        with (
            patch(f"{_DAEMON}._read_pid", return_value=own_pid),
            patch(f"{_DAEMON}._pid_alive", return_value=True),
            patch("os.kill") as mock_kill,
        ):
            _stop_existing_daemon()
            mock_kill.assert_not_called()

    def test_sends_sigterm_to_running_daemon(self) -> None:
        import signal

        fake_pid = 99999
        kill_mock = MagicMock()
        # First call (initial check): alive. Second call (after SIGTERM): dead.
        alive_calls = [True, False]

        with (
            patch(f"{_DAEMON}._read_pid", return_value=fake_pid),
            patch(f"{_DAEMON}._pid_alive", side_effect=alive_calls),
            patch("os.kill", kill_mock),
            patch("time.sleep"),
            patch("atlasbridge.cli._run.console"),
        ):
            _stop_existing_daemon()
            kill_mock.assert_called_once_with(fake_pid, signal.SIGTERM)

    def test_handles_permission_error_gracefully(self) -> None:
        with (
            patch(f"{_DAEMON}._read_pid", return_value=99999),
            patch(f"{_DAEMON}._pid_alive", return_value=True),
            patch("os.kill", side_effect=PermissionError),
        ):
            _stop_existing_daemon()  # should not raise
