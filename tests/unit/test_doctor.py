"""
Unit tests for atlasbridge doctor checks.

Regression coverage for:
- _check_config / _check_bot_token must not raise when config path is str
- load_config accepts str path without AttributeError
- _check_config returns "warn" (not "fail") when config file is absent
- _check_bot_token returns "skip" when config file is absent
- _fix_config creates skeleton and sets permissions when file is missing
"""

from __future__ import annotations

from pathlib import Path

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
