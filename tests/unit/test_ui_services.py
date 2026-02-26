"""Unit tests for UI service layer — verifies delegation and error isolation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlasbridge.ui.services import (
    ConfigService,
    DaemonService,
    DoctorService,
    LogsService,
    SessionService,
)
from atlasbridge.ui.state import ConfigStatus, DaemonStatus

# ---------------------------------------------------------------------------
# ConfigService
# ---------------------------------------------------------------------------


class TestConfigService:
    def test_load_state_never_raises(self) -> None:
        state = ConfigService.load_state()
        assert state is not None

    def test_load_state_not_found_when_config_missing(self, tmp_path: Path) -> None:
        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=tmp_path):
            state = ConfigService.load_state()
        assert state.config_status == ConfigStatus.NOT_FOUND

    def test_is_configured_returns_bool(self) -> None:
        result = ConfigService.is_configured()
        assert isinstance(result, bool)

    def test_is_configured_false_when_no_config_file(self, tmp_path: Path) -> None:
        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=tmp_path):
            result = ConfigService.is_configured()
        assert result is False

    def test_is_configured_true_when_config_file_exists(self, tmp_path: Path) -> None:
        (tmp_path / "config.toml").write_text("[telegram]\nbot_token='x'\n")
        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=tmp_path):
            result = ConfigService.is_configured()
        assert result is True

    def test_save_delegates_to_save_config(self) -> None:
        fake_path = Path("/tmp/atlasbridge/config.toml")
        with patch("atlasbridge.core.config.save_config", return_value=fake_path) as mock_save:
            result = ConfigService.save({"telegram": {"bot_token": "tok", "allowed_users": [1]}})
        mock_save.assert_called_once()
        assert result == str(fake_path)

    def test_save_returns_string_path(self) -> None:
        with patch("atlasbridge.core.config.save_config", return_value=Path("/x/y.toml")):
            result = ConfigService.save({"telegram": {}})
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# DoctorService
# ---------------------------------------------------------------------------


class TestDoctorService:
    def test_run_checks_returns_list(self) -> None:
        checks = DoctorService.run_checks()
        assert isinstance(checks, list)

    def test_run_checks_items_have_status_and_name(self) -> None:
        checks = DoctorService.run_checks()
        for c in checks:
            assert isinstance(c, dict)
            assert "status" in c
            assert "name" in c

    def test_run_checks_never_raises(self) -> None:
        try:
            DoctorService.run_checks()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"DoctorService.run_checks() raised: {exc}")

    def test_run_checks_filters_none(self) -> None:
        mock_check = {"status": "pass", "name": "python"}
        with (
            patch("atlasbridge.cli._doctor._check_python_version", return_value=mock_check),
            patch("atlasbridge.cli._doctor._check_platform", return_value=None),
            patch("atlasbridge.cli._doctor._check_ptyprocess", return_value=mock_check),
            patch("atlasbridge.cli._doctor._check_config", return_value=None),
            patch("atlasbridge.cli._doctor._check_bot_token", return_value=mock_check),
        ):
            result = DoctorService.run_checks()
        assert None not in result
        assert all(isinstance(c, dict) for c in result)


# ---------------------------------------------------------------------------
# DaemonService
# ---------------------------------------------------------------------------


class TestDaemonService:
    def test_get_status_returns_daemon_status(self) -> None:
        status = DaemonService.get_status()
        assert isinstance(status, DaemonStatus)

    def test_get_status_never_raises(self) -> None:
        try:
            DaemonService.get_status()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"DaemonService.get_status() raised: {exc}")

    def test_get_status_stopped_when_no_pid(self) -> None:
        with patch("atlasbridge.cli._daemon._read_pid", return_value=None):
            status = DaemonService.get_status()
        assert status == DaemonStatus.STOPPED

    def test_get_status_running_when_pid_alive(self) -> None:
        with (
            patch("atlasbridge.cli._daemon._read_pid", return_value=12345),
            patch("atlasbridge.cli._daemon._pid_alive", return_value=True),
        ):
            status = DaemonService.get_status()
        assert status == DaemonStatus.RUNNING

    def test_get_status_stopped_when_pid_dead(self) -> None:
        with (
            patch("atlasbridge.cli._daemon._read_pid", return_value=99999),
            patch("atlasbridge.cli._daemon._pid_alive", return_value=False),
        ):
            status = DaemonService.get_status()
        assert status == DaemonStatus.STOPPED

    def test_get_pid_returns_none_when_no_pid(self) -> None:
        with patch("atlasbridge.cli._daemon._read_pid", return_value=None):
            pid = DaemonService.get_pid()
        assert pid is None

    def test_get_pid_returns_int(self) -> None:
        with patch("atlasbridge.cli._daemon._read_pid", return_value=42):
            pid = DaemonService.get_pid()
        assert pid == 42

    def test_get_status_unknown_on_exception(self) -> None:
        with patch("atlasbridge.cli._daemon._read_pid", side_effect=RuntimeError("oops")):
            status = DaemonService.get_status()
        assert status == DaemonStatus.UNKNOWN


# ---------------------------------------------------------------------------
# SessionService
# ---------------------------------------------------------------------------


class TestSessionService:
    def test_list_sessions_returns_list(self) -> None:
        result = SessionService.list_sessions()
        assert isinstance(result, list)

    def test_list_sessions_never_raises(self) -> None:
        try:
            SessionService.list_sessions()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"SessionService.list_sessions() raised: {exc}")

    def test_list_sessions_empty_when_no_db(self, tmp_path: Path) -> None:
        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=tmp_path):
            result = SessionService.list_sessions()
        assert result == []

    def test_list_sessions_delegates_to_db(self, tmp_path: Path) -> None:
        fake_rows = [
            {"session_id": "abc", "tool": "claude", "status": "active", "created_at": "2025"}
        ]
        mock_db = MagicMock()
        mock_db.list_sessions.return_value = fake_rows

        # Create a fake DB file so the path.exists() check passes
        (tmp_path / "atlasbridge.db").touch()
        with (
            patch("atlasbridge.core.config.atlasbridge_dir", return_value=tmp_path),
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            result = SessionService.list_sessions(limit=10)

        mock_db.connect.assert_called_once()
        mock_db.list_sessions.assert_called_once_with(limit=10)
        mock_db.close.assert_called_once()
        assert result == fake_rows


# ---------------------------------------------------------------------------
# LogsService
# ---------------------------------------------------------------------------


class TestLogsService:
    def test_read_recent_returns_list(self) -> None:
        result = LogsService.read_recent()
        assert isinstance(result, list)

    def test_read_recent_never_raises(self) -> None:
        try:
            LogsService.read_recent()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"LogsService.read_recent() raised: {exc}")

    def test_read_recent_empty_when_no_log(self, tmp_path: Path) -> None:
        with patch("atlasbridge.core.config.atlasbridge_dir", return_value=tmp_path):
            result = LogsService.read_recent(50)
        assert result == []

    def test_read_recent_delegates_to_database(self, tmp_path: Path) -> None:
        fake_row = MagicMock()
        fake_row.__iter__ = lambda s: iter([("ts", "2025-01-01"), ("event_type", "session_start")])
        mock_db = MagicMock()
        mock_db.get_recent_audit_events.return_value = [fake_row]

        (tmp_path / "atlasbridge.db").touch()
        with (
            patch("atlasbridge.core.config.atlasbridge_dir", return_value=tmp_path),
            patch("atlasbridge.core.store.database.Database", return_value=mock_db),
        ):
            LogsService.read_recent(limit=25)

        mock_db.connect.assert_called_once()
        mock_db.get_recent_audit_events.assert_called_once_with(limit=25)
        mock_db.close.assert_called_once()
