"""
Unit tests for atlasbridge doctor checks.

Regression coverage for:
- _check_config / _check_bot_token must not raise when config path is str
- load_config accepts str path without AttributeError
- _check_config returns "warn" (not "fail") when config file is absent
- _check_bot_token returns "skip" (channels removed)
- _fix_config creates skeleton and sets permissions when file is missing
"""

from __future__ import annotations

from pathlib import Path

import pytest

MINIMAL_TOML = """\
config_version = 1

[prompts]
timeout_seconds = 300
"""


# ---------------------------------------------------------------------------
# load_config accepts str path (regression: 'str' has no attribute 'exists')
# ---------------------------------------------------------------------------


class TestLoadConfigAcceptsStrPath:
    def test_load_config_with_str_path_does_not_raise(self, tmp_path: Path) -> None:
        """Passing a str path to load_config must not raise AttributeError."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        from atlasbridge.core.config import load_config

        result = load_config(str(cfg))  # <-- was crashing before the fix
        assert result.config_version == 1

    def test_load_config_with_path_object(self, tmp_path: Path) -> None:
        """Passing a Path object to load_config continues to work."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        from atlasbridge.core.config import load_config

        result = load_config(cfg)
        assert result.config_version == 1

    def test_load_config_missing_file_raises_config_not_found(self, tmp_path: Path) -> None:
        """Missing file raises ConfigNotFoundError (not AttributeError)."""
        from atlasbridge.core.config import load_config
        from atlasbridge.core.exceptions import ConfigNotFoundError

        with pytest.raises(ConfigNotFoundError):
            load_config(tmp_path / "nonexistent.toml")

    def test_load_config_missing_str_path_raises_config_not_found(self, tmp_path: Path) -> None:
        """Missing file passed as str raises ConfigNotFoundError (not AttributeError)."""
        from atlasbridge.core.config import load_config
        from atlasbridge.core.exceptions import ConfigNotFoundError

        with pytest.raises(ConfigNotFoundError):
            load_config(str(tmp_path / "nonexistent.toml"))


# ---------------------------------------------------------------------------
# _check_config / _check_bot_token behaviour
# ---------------------------------------------------------------------------


class TestDoctorChecks:
    def test_check_config_warn_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_check_config returns status='warn' (not 'fail') when config is absent."""
        missing = tmp_path / "config.toml"
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(missing))
        from atlasbridge.cli._doctor import _check_config

        result = _check_config()
        assert result["status"] == "warn"
        assert "not found" in result["detail"]

    def test_check_config_pass_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_check_config returns status='pass' for a valid config file."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))
        from atlasbridge.cli._doctor import _check_config

        result = _check_config()
        assert result["status"] == "pass"

    def test_check_config_fail_on_invalid_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_check_config returns status='fail' for a malformed config file."""
        cfg = tmp_path / "config.toml"
        cfg.write_text("this is not valid toml ::::")
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))
        from atlasbridge.cli._doctor import _check_config

        result = _check_config()
        assert result["status"] == "fail"
        assert result["detail"]  # must have a non-empty message

    def test_check_bot_token_skip_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_check_bot_token returns status='skip' when config file is absent."""
        missing = tmp_path / "config.toml"
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(missing))
        from atlasbridge.cli._doctor import _check_bot_token

        result = _check_bot_token()
        assert result["status"] == "skip"

    def test_check_bot_token_always_skip(self) -> None:
        """_check_bot_token always returns skip since channels were removed."""
        from atlasbridge.cli._doctor import _check_bot_token

        result = _check_bot_token()
        assert result["status"] == "skip"

    def test_check_bot_token_never_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_check_bot_token must not propagate any exception — always returns a dict."""
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(tmp_path / "nope.toml"))
        from atlasbridge.cli._doctor import _check_bot_token

        result = _check_bot_token()
        assert isinstance(result, dict)
        assert "status" in result
        assert "detail" in result


# ---------------------------------------------------------------------------
# --fix: config skeleton creation
# ---------------------------------------------------------------------------


class TestFixConfig:
    def test_fix_config_creates_skeleton(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_config creates a skeleton config.toml when file is absent."""
        cfg = tmp_path / "config.toml"
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_config

        _fix_config(Console(quiet=True))

        assert cfg.exists()
        content = cfg.read_text()
        assert "config_version" in content

    def test_fix_config_creates_parent_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_config creates intermediate directories as needed."""
        cfg = tmp_path / "deep" / "nested" / "config.toml"
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_config

        _fix_config(Console(quiet=True))

        assert cfg.exists()

    def test_fix_config_noop_when_file_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_config does not overwrite an existing config file."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))
        original = cfg.read_text()

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_config

        _fix_config(Console(quiet=True))

        assert cfg.read_text() == original


# ---------------------------------------------------------------------------
# --fix: database auto-initialization
# ---------------------------------------------------------------------------


class TestFixDatabase:
    def test_fix_database_creates_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_fix_database creates a new database when none exists."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_database

        _fix_database(Console(quiet=True))
        db_path = tmp_path / "atlasbridge.db"
        assert db_path.exists()

    def test_fix_database_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Running _fix_database twice produces no error."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_database

        console = Console(quiet=True)
        _fix_database(console)
        _fix_database(console)  # second run — no error
        assert (tmp_path / "atlasbridge.db").exists()

    def test_fix_database_never_deletes_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_database never removes an existing database file."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        db_path = tmp_path / "atlasbridge.db"
        db_path.write_bytes(b"existing data")

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_database

        _fix_database(Console(quiet=True))
        # File must still exist (may have been modified by migration, but not deleted)
        assert db_path.exists()
        assert db_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# --fix: stale PID cleanup
# ---------------------------------------------------------------------------


class TestFixStalePid:
    def test_fix_stale_pid_removes_dead_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_stale_pid removes PID file when the process is dead."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        pid_path = tmp_path / "daemon.pid"
        pid_path.write_text("999999999")  # very unlikely to be alive

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_stale_pid

        _fix_stale_pid(Console(quiet=True))
        assert not pid_path.exists()

    def test_fix_stale_pid_noop_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_stale_pid does nothing when no PID file exists."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_stale_pid

        _fix_stale_pid(Console(quiet=True))  # no error

    def test_fix_stale_pid_removes_malformed_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_stale_pid removes PID files with non-numeric content."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        pid_path = tmp_path / "daemon.pid"
        pid_path.write_text("not-a-pid")

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_stale_pid

        _fix_stale_pid(Console(quiet=True))
        assert not pid_path.exists()

    def test_fix_stale_pid_keeps_alive_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_stale_pid does not remove PID file for a running process."""
        import os

        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        pid_path = tmp_path / "daemon.pid"
        pid_path.write_text(str(os.getpid()))  # current process is alive

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_stale_pid

        _fix_stale_pid(Console(quiet=True))
        assert pid_path.exists()


# ---------------------------------------------------------------------------
# --fix: file permissions
# ---------------------------------------------------------------------------


class TestFixPermissions:
    def test_fix_permissions_repairs_open_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_permissions tightens world-readable config."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        cfg.chmod(0o644)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_permissions

        _fix_permissions(Console(quiet=True))

        import stat

        mode = stat.S_IMODE(cfg.stat().st_mode)
        assert mode & 0o077 == 0, f"Config still has group/other bits: {oct(mode)}"

    def test_fix_permissions_noop_when_correct(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_permissions is a no-op when permissions are already correct."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        cfg.chmod(0o600)
        tmp_path.chmod(0o700)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_permissions

        _fix_permissions(Console(quiet=True))  # no error, no change

        import stat

        assert stat.S_IMODE(cfg.stat().st_mode) == 0o600

    def test_fix_permissions_noop_when_no_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_permissions does nothing when config file does not exist."""
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(tmp_path / "absent.toml"))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_permissions

        _fix_permissions(Console(quiet=True))  # no error


# ---------------------------------------------------------------------------
# Check functions for new diagnostics
# ---------------------------------------------------------------------------


class TestCheckStalePid:
    def test_check_stale_pid_none_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        from atlasbridge.cli._doctor import _check_stale_pid

        assert _check_stale_pid() is None

    def test_check_stale_pid_warn_when_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        pid_path = tmp_path / "daemon.pid"
        pid_path.write_text("999999999")
        from atlasbridge.cli._doctor import _check_stale_pid

        result = _check_stale_pid()
        assert result is not None
        assert result["status"] == "warn"

    def test_check_stale_pid_pass_when_alive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        pid_path = tmp_path / "daemon.pid"
        pid_path.write_text(str(os.getpid()))
        from atlasbridge.cli._doctor import _check_stale_pid

        result = _check_stale_pid()
        assert result is not None
        assert result["status"] == "pass"


class TestCheckPermissions:
    def test_check_permissions_none_when_no_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(tmp_path / "absent.toml"))
        from atlasbridge.cli._doctor import _check_permissions

        assert _check_permissions() is None

    def test_check_permissions_pass_when_correct(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        cfg.chmod(0o600)
        tmp_path.chmod(0o700)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))
        from atlasbridge.cli._doctor import _check_permissions

        result = _check_permissions()
        assert result is not None
        assert result["status"] == "pass"

    def test_check_permissions_warn_when_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        cfg.chmod(0o644)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))
        from atlasbridge.cli._doctor import _check_permissions

        result = _check_permissions()
        assert result is not None
        assert result["status"] == "warn"


# ---------------------------------------------------------------------------
# --fix: idempotency (all fixes)
# ---------------------------------------------------------------------------


class TestFixIdempotency:
    def test_all_fixes_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Running all --fix actions twice produces no errors or extra changes."""
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(tmp_path / "config.toml"))
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)

        from rich.console import Console

        from atlasbridge.cli._doctor import (
            _fix_config,
            _fix_database,
            _fix_permissions,
            _fix_stale_pid,
        )

        console = Console(quiet=True)

        # First run
        _fix_config(console)
        _fix_database(console)
        _fix_stale_pid(console)
        _fix_permissions(console)

        # Capture state after first run
        cfg_content = (tmp_path / "config.toml").read_text()

        # Second run
        _fix_config(console)
        _fix_database(console)
        _fix_stale_pid(console)
        _fix_permissions(console)

        # Config unchanged
        assert (tmp_path / "config.toml").read_text() == cfg_content


# ---------------------------------------------------------------------------
# --fix: safety invariant — never deletes user data
# ---------------------------------------------------------------------------


class TestFixSafety:
    def test_fix_never_deletes_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No --fix action may delete an existing config file."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)

        from rich.console import Console

        from atlasbridge.cli._doctor import (
            _fix_config,
            _fix_database,
            _fix_permissions,
            _fix_stale_pid,
        )

        console = Console(quiet=True)
        _fix_config(console)
        _fix_database(console)
        _fix_stale_pid(console)
        _fix_permissions(console)

        assert cfg.exists()
        assert cfg.read_text() == MINIMAL_TOML
