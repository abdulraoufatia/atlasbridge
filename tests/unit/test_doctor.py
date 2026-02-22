"""
Unit tests for atlasbridge doctor checks.

Regression coverage for:
- _check_config / _check_bot_token must not raise when config path is str
- load_config accepts str path without AttributeError
- _check_config returns "warn" (not "fail") when config file is absent
- _check_bot_token returns "skip" when config file is absent
- _fix_config creates skeleton and sets permissions when file is missing
- _check_telegram_reachability pass/warn/skip
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

MINIMAL_TOML = """\
[telegram]
bot_token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
allowed_users = [12345678]
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
        assert result.telegram is not None

    def test_load_config_with_path_object(self, tmp_path: Path) -> None:
        """Passing a Path object to load_config continues to work."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        from atlasbridge.core.config import load_config

        result = load_config(cfg)
        assert result.telegram is not None

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

    def test_check_bot_token_pass_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_check_bot_token returns status='pass' for a valid token."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))
        from atlasbridge.cli._doctor import _check_bot_token

        result = _check_bot_token()
        assert result["status"] == "pass"
        assert "..." in result["detail"]  # masked token

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
        assert "[telegram]" in content

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
# _check_telegram_reachability
# ---------------------------------------------------------------------------


class TestCheckTelegramReachability:
    def test_check_telegram_reachability_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns pass when verify_telegram_token succeeds."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        with patch(
            "atlasbridge.channels.telegram.verify.verify_telegram_token",
            return_value=(True, "Bot: @testbot"),
        ):
            from atlasbridge.cli._doctor import _check_telegram_reachability

            result = _check_telegram_reachability()

        assert result is not None
        assert result["status"] == "pass"
        assert "Bot: @testbot" in result["detail"]

    def test_check_telegram_reachability_warn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns warn when verify_telegram_token fails."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        with patch(
            "atlasbridge.channels.telegram.verify.verify_telegram_token",
            return_value=(False, "Unauthorized"),
        ):
            from atlasbridge.cli._doctor import _check_telegram_reachability

            result = _check_telegram_reachability()

        assert result is not None
        assert result["status"] == "warn"
        assert "Unauthorized" in result["detail"]

    def test_check_telegram_reachability_skip_no_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns None (skip) when no Telegram is configured."""
        missing = tmp_path / "config.toml"
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(missing))

        from atlasbridge.cli._doctor import _check_telegram_reachability

        result = _check_telegram_reachability()
        assert result is None


# ---------------------------------------------------------------------------
# --fix: database creation and migration
# ---------------------------------------------------------------------------


class TestFixDatabase:
    def test_fix_database_creates_new_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_database creates a new database when none exists."""
        monkeypatch.setenv("ATLASBRIDGE_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_database

        db_path = tmp_path / "atlasbridge.db"
        assert not db_path.exists()

        _fix_database(Console(quiet=True))

        assert db_path.exists()

        # Verify schema was applied
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        from atlasbridge.core.store.migrations import LATEST_SCHEMA_VERSION, get_user_version

        assert get_user_version(conn) == LATEST_SCHEMA_VERSION
        conn.close()

    def test_fix_database_runs_migration_on_old_schema(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_database runs pending migrations on an existing database with old schema."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)

        import sqlite3

        db_path = tmp_path / "atlasbridge.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA user_version = 0")
        conn.close()

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_database

        _fix_database(Console(quiet=True))

        conn = sqlite3.connect(str(db_path))
        from atlasbridge.core.store.migrations import LATEST_SCHEMA_VERSION, get_user_version

        assert get_user_version(conn) == LATEST_SCHEMA_VERSION
        conn.close()

    def test_fix_database_noop_on_current_schema(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_database is a no-op when database is already at latest schema."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)

        import sqlite3

        from atlasbridge.core.store.migrations import LATEST_SCHEMA_VERSION

        db_path = tmp_path / "atlasbridge.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION}")
        conn.close()

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_database

        _fix_database(Console(quiet=True))

        # File was opened but no schema changes should have occurred
        conn = sqlite3.connect(str(db_path))
        from atlasbridge.core.store.migrations import get_user_version

        assert get_user_version(conn) == LATEST_SCHEMA_VERSION
        conn.close()


# ---------------------------------------------------------------------------
# --fix: stale PID cleanup
# ---------------------------------------------------------------------------


class TestFixStalePid:
    def test_fix_stale_pid_removes_stale_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_stale_pid removes PID file when process is not alive."""
        monkeypatch.setattr("atlasbridge.core.constants._default_data_dir", lambda: tmp_path)

        pid_file = tmp_path / "atlasbridge.pid"
        pid_file.write_text("99999999")  # Likely not a real PID

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_stale_pid

        _fix_stale_pid(Console(quiet=True))

        assert not pid_file.exists()

    def test_fix_stale_pid_keeps_live_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_stale_pid does not remove PID file when process is alive."""
        import os

        monkeypatch.setattr("atlasbridge.core.constants._default_data_dir", lambda: tmp_path)

        pid_file = tmp_path / "atlasbridge.pid"
        pid_file.write_text(str(os.getpid()))  # Current process — definitely alive

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_stale_pid

        _fix_stale_pid(Console(quiet=True))

        assert pid_file.exists()  # Should NOT have been removed

    def test_fix_stale_pid_noop_when_no_pid_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_stale_pid is a no-op when no PID file exists."""
        monkeypatch.setattr("atlasbridge.core.constants._default_data_dir", lambda: tmp_path)

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_stale_pid

        _fix_stale_pid(Console(quiet=True))
        # No exception, no side effects

    def test_fix_stale_pid_removes_invalid_pid_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_stale_pid removes PID file with non-numeric content."""
        monkeypatch.setattr("atlasbridge.core.constants._default_data_dir", lambda: tmp_path)

        pid_file = tmp_path / "atlasbridge.pid"
        pid_file.write_text("not-a-pid")

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_stale_pid

        _fix_stale_pid(Console(quiet=True))

        assert not pid_file.exists()


# ---------------------------------------------------------------------------
# --fix: file permissions
# ---------------------------------------------------------------------------


class TestFixPermissions:
    def test_fix_permissions_repairs_config_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_permissions sets config.toml to 0600 when too open."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        cfg.chmod(0o644)  # Too open
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_permissions

        _fix_permissions(Console(quiet=True))

        assert cfg.stat().st_mode & 0o777 == 0o600

    def test_fix_permissions_repairs_config_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_permissions sets config directory to 0700 when too open."""
        cfg_dir = tmp_path / "atlasbridge"
        cfg_dir.mkdir(mode=0o755)
        cfg = cfg_dir / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        cfg.chmod(0o600)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_permissions

        _fix_permissions(Console(quiet=True))

        assert cfg_dir.stat().st_mode & 0o777 == 0o700

    def test_fix_permissions_noop_when_correct(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_permissions is a no-op when permissions are already correct."""
        cfg_dir = tmp_path / "atlasbridge"
        cfg_dir.mkdir(mode=0o700)
        cfg = cfg_dir / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        cfg.chmod(0o600)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_permissions

        _fix_permissions(Console(quiet=True))

        assert cfg.stat().st_mode & 0o777 == 0o600
        assert cfg_dir.stat().st_mode & 0o777 == 0o700


# ---------------------------------------------------------------------------
# New check functions
# ---------------------------------------------------------------------------


class TestCheckStalePid:
    def test_check_stale_pid_returns_none_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("atlasbridge.core.constants._default_data_dir", lambda: tmp_path)
        from atlasbridge.cli._doctor import _check_stale_pid

        assert _check_stale_pid() is None

    def test_check_stale_pid_warns_when_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("atlasbridge.core.constants._default_data_dir", lambda: tmp_path)
        (tmp_path / "atlasbridge.pid").write_text("99999999")

        from atlasbridge.cli._doctor import _check_stale_pid

        result = _check_stale_pid()
        assert result is not None
        assert result["status"] == "warn"
        assert "stale" in result["detail"]

    def test_check_stale_pid_pass_when_alive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setattr("atlasbridge.core.constants._default_data_dir", lambda: tmp_path)
        (tmp_path / "atlasbridge.pid").write_text(str(os.getpid()))

        from atlasbridge.cli._doctor import _check_stale_pid

        result = _check_stale_pid()
        assert result is not None
        assert result["status"] == "pass"


class TestCheckPermissions:
    def test_check_permissions_pass_when_correct(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_dir = tmp_path / "atlasbridge"
        cfg_dir.mkdir(mode=0o700)
        cfg = cfg_dir / "config.toml"
        cfg.write_text(MINIMAL_TOML)
        cfg.chmod(0o600)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from atlasbridge.cli._doctor import _check_permissions

        result = _check_permissions()
        assert result is not None
        assert result["status"] == "pass"

    def test_check_permissions_warn_when_too_open(
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

    def test_check_permissions_none_when_no_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(tmp_path / "nope.toml"))

        from atlasbridge.cli._doctor import _check_permissions

        assert _check_permissions() is None


# ---------------------------------------------------------------------------
# --fix idempotency
# ---------------------------------------------------------------------------


class TestFixIdempotency:
    def test_fix_is_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Running all fix functions twice produces no additional changes."""
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(tmp_path / "config.toml"))
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)
        monkeypatch.setattr("atlasbridge.core.constants._default_data_dir", lambda: tmp_path)

        from rich.console import Console

        from atlasbridge.cli._doctor import (
            _fix_config,
            _fix_database,
            _fix_permissions,
            _fix_stale_pid,
        )

        console = Console(quiet=True)

        # First run — creates config and database
        _fix_config(console)
        _fix_database(console)
        _fix_stale_pid(console)
        _fix_permissions(console)

        cfg = tmp_path / "config.toml"
        db = tmp_path / "atlasbridge.db"
        assert cfg.exists()
        assert db.exists()

        cfg_content = cfg.read_text()
        cfg_mtime = cfg.stat().st_mtime

        # Second run — should be a no-op
        _fix_config(console)
        _fix_database(console)
        _fix_stale_pid(console)
        _fix_permissions(console)

        assert cfg.read_text() == cfg_content
        assert cfg.stat().st_mtime == cfg_mtime


# ---------------------------------------------------------------------------
# --fix safety: never deletes user data
# ---------------------------------------------------------------------------


class TestFixSafety:
    def test_fix_never_deletes_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_config never deletes or overwrites an existing config file."""
        cfg = tmp_path / "config.toml"
        cfg.write_text("# My precious config\n" + MINIMAL_TOML)
        monkeypatch.setenv("ATLASBRIDGE_CONFIG", str(cfg))

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_config

        _fix_config(Console(quiet=True))

        content = cfg.read_text()
        assert "My precious config" in content

    def test_fix_never_deletes_database(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_fix_database never deletes or overwrites an existing database."""
        monkeypatch.setattr("atlasbridge.core.config.atlasbridge_dir", lambda: tmp_path)

        import sqlite3

        db_path = tmp_path / "atlasbridge.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE user_data (id TEXT)")
        conn.execute("INSERT INTO user_data VALUES ('important')")
        conn.commit()
        conn.close()

        from rich.console import Console

        from atlasbridge.cli._doctor import _fix_database

        _fix_database(Console(quiet=True))

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT * FROM user_data").fetchall()
        conn.close()
        assert rows == [("important",)]
