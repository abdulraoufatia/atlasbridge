"""Unit tests for aegis.core.config — AegisConfig loading and validation."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

import pytest

from aegis.core.config import AegisConfig, load_config, save_config
from aegis.core.exceptions import ConfigError, ConfigNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(content)
    return p


MINIMAL_TOML = """
[telegram]
bot_token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
allowed_users = [12345678]
"""


# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_minimal_valid(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, MINIMAL_TOML)
        cfg = load_config(p)
        assert cfg.telegram.allowed_users == [12345678]

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigNotFoundError):
            load_config(tmp_path / "nonexistent.toml")

    def test_invalid_toml_raises(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, "this is not valid toml %%% [[[")
        with pytest.raises(ConfigError):
            load_config(p)

    def test_invalid_token_format_raises(self, tmp_path: Path) -> None:
        bad = """
[telegram]
bot_token = "notavalidtoken"
allowed_users = [12345678]
"""
        p = _write_config(tmp_path, bad)
        with pytest.raises(ConfigError):
            load_config(p)

    def test_auto_approve_rejected(self, tmp_path: Path) -> None:
        bad = MINIMAL_TOML + '\n[prompts]\nyes_no_safe_default = "y"\n'
        p = _write_config(tmp_path, bad)
        with pytest.raises(ConfigError, match="[Aa]uto-approv"):
            load_config(p)

    def test_timeout_bounds(self, tmp_path: Path) -> None:
        bad = MINIMAL_TOML + "\n[prompts]\ntimeout_seconds = 10\n"
        p = _write_config(tmp_path, bad)
        with pytest.raises(ConfigError):
            load_config(p)

    def test_env_override_token(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "AEGIS_TELEGRAM_BOT_TOKEN",
            "987654321:ZYXWVUTSRQPONMLKJIHGFEDCBAzyxwvutsrqpo",
        )
        p = _write_config(tmp_path, MINIMAL_TOML)
        cfg = load_config(p)
        assert cfg.telegram.bot_token.get_secret_value().startswith("987654321:")

    def test_env_override_users(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AEGIS_TELEGRAM_ALLOWED_USERS", "111,222,333")
        p = _write_config(tmp_path, MINIMAL_TOML)
        cfg = load_config(p)
        assert cfg.telegram.allowed_users == [111, 222, 333]


# ---------------------------------------------------------------------------
# Save config
# ---------------------------------------------------------------------------


class TestSaveConfig:
    def test_saves_and_loads(self, tmp_path: Path) -> None:
        data = {
            "telegram": {
                "bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
                "allowed_users": [42],
            }
        }
        path = save_config(data, tmp_path / "config.toml")
        cfg = load_config(path)
        assert cfg.telegram.allowed_users == [42]

    def test_secure_permissions(self, tmp_path: Path) -> None:
        data = {
            "telegram": {
                "bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
                "allowed_users": [1],
            }
        }
        path = save_config(data, tmp_path / "config.toml")
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"Expected 0600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# db_path / audit_path derivation
# ---------------------------------------------------------------------------


class TestPaths:
    def test_default_db_path(self, tmp_path: Path) -> None:
        p = _write_config(tmp_path, MINIMAL_TOML)
        cfg = load_config(p)
        assert cfg.db_path.name == "aegis.db"

    def test_custom_db_path(self, tmp_path: Path) -> None:
        toml = MINIMAL_TOML + f'\n[database]\npath = "{tmp_path}/custom.db"\n'
        p = _write_config(tmp_path, toml)
        cfg = load_config(p)
        assert cfg.db_path == tmp_path / "custom.db"
