"""Tests for the Windows ConPTY adapter.

These tests mock pywinpty since they run on macOS/Linux CI.
They verify:
  - WindowsTTY.start() spawns via winpty.PTY
  - WindowsTTY.stop() shuts down cleanly
  - WindowsTTY.read_output() normalises CRLF → LF
  - WindowsTTY.inject_reply() writes to the ConPTY
  - get_tty_class() gates Windows behind --experimental
  - get_tty_class() returns correct class per platform
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlasbridge.os.tty.base import PTYConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pty_config():
    return PTYConfig(command=["cmd", "/c", "echo", "hello"])


@pytest.fixture()
def mock_winpty():
    """Provide a mock winpty module and patch sys.platform to win32."""
    mock_pty_instance = MagicMock()
    mock_pty_instance.isalive.return_value = True
    mock_pty_instance.pid = 12345
    mock_pty_instance.read.return_value = "hello\r\nworld\r\n"

    mock_winpty_mod = MagicMock()
    mock_winpty_mod.PTY.return_value = mock_pty_instance

    return mock_winpty_mod, mock_pty_instance


# ---------------------------------------------------------------------------
# get_tty_class tests
# ---------------------------------------------------------------------------


class TestGetTTYClass:
    def test_returns_macos_on_darwin(self):
        from atlasbridge.os.tty.windows import get_tty_class

        with patch("atlasbridge.os.tty.windows.sys") as mock_sys:
            mock_sys.platform = "darwin"
            cls = get_tty_class()
            assert cls.__name__ == "MacOSTTY"

    def test_returns_linux_on_linux(self):
        from atlasbridge.os.tty.windows import get_tty_class

        with patch("atlasbridge.os.tty.windows.sys") as mock_sys:
            mock_sys.platform = "linux"
            cls = get_tty_class()
            assert cls.__name__ == "LinuxTTY"

    def test_raises_on_windows_without_experimental(self):
        from atlasbridge.os.tty.windows import get_tty_class

        with patch("atlasbridge.os.tty.windows.sys") as mock_sys:
            mock_sys.platform = "win32"
            with pytest.raises(RuntimeError, match="experimental"):
                get_tty_class()

    def test_returns_windows_tty_with_experimental(self):
        from atlasbridge.os.tty.windows import WindowsTTY, get_tty_class

        with patch("atlasbridge.os.tty.windows.sys") as mock_sys:
            mock_sys.platform = "win32"
            cls = get_tty_class(experimental=True)
            assert cls is WindowsTTY

    def test_raises_on_unknown_platform(self):
        from atlasbridge.os.tty.windows import get_tty_class

        with patch("atlasbridge.os.tty.windows.sys") as mock_sys:
            mock_sys.platform = "freebsd"
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                get_tty_class()


# ---------------------------------------------------------------------------
# WindowsTTY construction
# ---------------------------------------------------------------------------


class TestWindowsTTYConstruction:
    def test_raises_on_non_windows(self, pty_config):
        """WindowsTTY.__init__ raises on non-win32 platforms."""
        from atlasbridge.os.tty.windows import WindowsTTY

        with pytest.raises(NotImplementedError, match="only valid on Windows"):
            WindowsTTY(pty_config, "sess-001")

    def test_constructs_on_win32(self, pty_config):
        """WindowsTTY can be constructed when sys.platform == 'win32'."""
        from atlasbridge.os.tty.windows import WindowsTTY

        with patch.object(sys, "platform", "win32"):
            tty = WindowsTTY(pty_config, "sess-001")
            assert tty.session_id == "sess-001"
            assert tty._proc is None
            assert tty._alive is False


# ---------------------------------------------------------------------------
# WindowsTTY.start()
# ---------------------------------------------------------------------------


class TestWindowsTTYStart:
    @pytest.mark.asyncio
    async def test_start_spawns_conpty(self, pty_config, mock_winpty):
        """start() creates a winpty.PTY and calls spawn()."""
        from atlasbridge.os.tty.windows import WindowsTTY

        mock_mod, mock_instance = mock_winpty

        with (
            patch.object(sys, "platform", "win32"),
            patch.dict(sys.modules, {"winpty": mock_mod}),
            patch("atlasbridge.os.tty.windows._get_windows_build", return_value=19041),
        ):
            tty = WindowsTTY(pty_config, "sess-001")
            await tty.start()

            mock_mod.PTY.assert_called_once_with(220, 50)
            mock_instance.spawn.assert_called_once()
            assert tty._alive is True

    @pytest.mark.asyncio
    async def test_start_raises_without_winpty(self, pty_config):
        """start() raises RuntimeError if pywinpty is not installed."""
        from atlasbridge.os.tty.windows import WindowsTTY

        with (
            patch.object(sys, "platform", "win32"),
            patch.dict(sys.modules, {"winpty": None}),
        ):
            tty = WindowsTTY(pty_config, "sess-001")
            with pytest.raises(RuntimeError, match="pywinpty is required"):
                await tty.start()

    @pytest.mark.asyncio
    async def test_start_rejects_old_windows_build(self, pty_config, mock_winpty):
        """start() raises RuntimeError on old Windows builds."""
        from atlasbridge.os.tty.windows import WindowsTTY

        mock_mod, _ = mock_winpty

        with (
            patch.object(sys, "platform", "win32"),
            patch.dict(sys.modules, {"winpty": mock_mod}),
            patch("atlasbridge.os.tty.windows._get_windows_build", return_value=15063),
        ):
            tty = WindowsTTY(pty_config, "sess-001")
            with pytest.raises(RuntimeError, match="build 17763"):
                await tty.start()


# ---------------------------------------------------------------------------
# WindowsTTY lifecycle
# ---------------------------------------------------------------------------


class TestWindowsTTYLifecycle:
    @pytest.mark.asyncio
    async def test_stop_clears_alive_flag(self, pty_config, mock_winpty):
        from atlasbridge.os.tty.windows import WindowsTTY

        mock_mod, mock_instance = mock_winpty

        with (
            patch.object(sys, "platform", "win32"),
            patch.dict(sys.modules, {"winpty": mock_mod}),
            patch("atlasbridge.os.tty.windows._get_windows_build", return_value=19041),
        ):
            tty = WindowsTTY(pty_config, "sess-001")
            await tty.start()
            assert tty.is_alive() is True

            await tty.stop(timeout_s=0.01)
            assert tty._alive is False

    def test_pid_returns_winpty_pid(self, pty_config, mock_winpty):
        from atlasbridge.os.tty.windows import WindowsTTY

        mock_mod, mock_instance = mock_winpty

        with patch.object(sys, "platform", "win32"):
            tty = WindowsTTY(pty_config, "sess-001")
            tty._proc = mock_instance
            tty._alive = True
            assert tty.pid() == 12345

    def test_pid_returns_negative_one_when_not_started(self, pty_config):
        from atlasbridge.os.tty.windows import WindowsTTY

        with patch.object(sys, "platform", "win32"):
            tty = WindowsTTY(pty_config, "sess-001")
            assert tty.pid() == -1


# ---------------------------------------------------------------------------
# WindowsTTY I/O
# ---------------------------------------------------------------------------


class TestWindowsTTYIO:
    def test_read_chunk_normalises_crlf(self, pty_config, mock_winpty):
        """_read_chunk() normalises \\r\\n → \\n."""
        from atlasbridge.os.tty.windows import WindowsTTY

        mock_mod, mock_instance = mock_winpty
        mock_instance.read.return_value = "line1\r\nline2\r\n"

        with patch.object(sys, "platform", "win32"):
            tty = WindowsTTY(pty_config, "sess-001")
            tty._proc = mock_instance
            tty._alive = True

            chunk = tty._read_chunk()
            assert chunk == b"line1\nline2\n"

    def test_read_chunk_raises_eof_on_empty(self, pty_config, mock_winpty):
        """_read_chunk() raises EOFError when winpty returns empty."""
        from atlasbridge.os.tty.windows import WindowsTTY

        mock_mod, mock_instance = mock_winpty
        mock_instance.read.return_value = ""

        with patch.object(sys, "platform", "win32"):
            tty = WindowsTTY(pty_config, "sess-001")
            tty._proc = mock_instance
            tty._alive = True

            with pytest.raises(EOFError):
                tty._read_chunk()

    @pytest.mark.asyncio
    async def test_inject_reply_writes_decoded_text(self, pty_config, mock_winpty):
        """inject_reply() decodes bytes to str for winpty."""
        from atlasbridge.os.tty.windows import WindowsTTY

        mock_mod, mock_instance = mock_winpty

        with patch.object(sys, "platform", "win32"):
            tty = WindowsTTY(pty_config, "sess-001")
            tty._proc = mock_instance

            await tty.inject_reply(b"y\r")
            mock_instance.write.assert_called_once_with("y\r")


# ---------------------------------------------------------------------------
# Windows build detection
# ---------------------------------------------------------------------------


class TestWindowsBuildDetection:
    def test_returns_zero_on_non_windows(self):
        from atlasbridge.os.tty.windows import _get_windows_build

        # On non-Windows, sys.getwindowsversion doesn't exist
        result = _get_windows_build()
        assert result == 0


# ---------------------------------------------------------------------------
# Safety: --experimental flag required
# ---------------------------------------------------------------------------


class TestExperimentalGate:
    def test_adapter_experimental_defaults_false(self):
        """ClaudeCodeAdapter.experimental defaults to False."""
        from atlasbridge.adapters.claude_code import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        assert adapter.experimental is False

    @pytest.mark.asyncio
    async def test_adapter_uses_experimental_for_tty_class(self):
        """start_session passes experimental flag to get_tty_class."""
        from atlasbridge.adapters.claude_code import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        adapter.experimental = True

        mock_tty_instance = MagicMock()
        mock_tty_instance.start = AsyncMock()
        mock_tty_cls = MagicMock(return_value=mock_tty_instance)

        with patch("atlasbridge.adapters.claude_code.get_tty_class") as mock_get:
            mock_get.return_value = mock_tty_cls

            try:
                await adapter.start_session("sess-001", ["claude"])
            except Exception:
                pass

            mock_get.assert_called_once_with(experimental=True)
