"""Unit tests for config migration system."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from atlasbridge.core.config import load_config, save_config
from atlasbridge.core.config_migrate import (
    CURRENT_CONFIG_VERSION,
    detect_version,
    upgrade_config,
)
from atlasbridge.core.exceptions import ConfigError

MINIMAL_TOML_V0 = """
[prompts]
timeout_seconds = 300
"""

MINIMAL_TOML_V1 = """
config_version = 1

[prompts]
timeout_seconds = 300
"""


class TestDetectVersion:
    def test_missing_version_defaults_to_zero(self):
        assert detect_version({"prompts": {}}) == 0

    def test_explicit_version_returned(self):
        assert detect_version({"config_version": 1}) == 1

    def test_future_version(self):
        assert detect_version({"config_version": 99}) == 99

    def test_empty_dict(self):
        assert detect_version({}) == 0


class TestUpgradeConfig:
    def test_v0_to_v1_adds_version(self):
        data = {"prompts": {"timeout_seconds": 300}}
        result = upgrade_config(data, from_version=0, to_version=1)
        assert result["config_version"] == 1

    def test_same_version_noop(self):
        data = {"config_version": 1, "prompts": {"timeout_seconds": 300}}
        result = upgrade_config(data, from_version=1, to_version=1)
        assert result is data  # same object, no copy

    def test_downgrade_rejected(self):
        with pytest.raises(ConfigError, match="[Dd]owngrade"):
            upgrade_config({"config_version": 1}, from_version=1, to_version=0)

    def test_unknown_migration_path(self):
        with pytest.raises(ConfigError, match="[Nn]o migration path"):
            upgrade_config({}, from_version=99, to_version=100)

    def test_idempotent(self):
        data = {"prompts": {"timeout_seconds": 300}}
        first = upgrade_config(data, 0, 1)
        second = upgrade_config(first, 1, 1)
        assert first["config_version"] == 1
        assert second is first


class TestAutoMigration:
    def test_load_config_auto_migrates_v0(self, tmp_path: Path):
        """load_config auto-migrates a v0 config and persists the new version."""
        p = tmp_path / "config.toml"
        p.write_text(MINIMAL_TOML_V0)

        cfg = load_config(p)
        assert cfg.config_version == 1

        # Verify persistence
        with open(p, "rb") as f:
            data = tomllib.load(f)
        assert data["config_version"] == 1

    def test_load_config_v1_no_rewrite(self, tmp_path: Path):
        """v1 config should not trigger a rewrite."""
        p = tmp_path / "config.toml"
        p.write_text(MINIMAL_TOML_V1)
        mtime_before = p.stat().st_mtime_ns

        load_config(p)

        # File should not have been rewritten
        mtime_after = p.stat().st_mtime_ns
        assert mtime_before == mtime_after

    def test_save_config_stamps_version(self, tmp_path: Path):
        """save_config always stamps config_version."""
        data = {
            "prompts": {
                "timeout_seconds": 300,
            }
        }
        path = save_config(data, tmp_path / "config.toml")

        with open(path, "rb") as f:
            saved = tomllib.load(f)
        assert saved["config_version"] == CURRENT_CONFIG_VERSION


class TestConstant:
    def test_current_version_is_one(self):
        assert CURRENT_CONFIG_VERSION == 1
