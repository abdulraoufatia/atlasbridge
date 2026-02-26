"""Unit tests for RuntimeConfig environment tagging."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlasbridge.core.config import RuntimeConfig


class TestRuntimeConfig:
    def test_default_is_dev(self) -> None:
        cfg = RuntimeConfig()
        assert cfg.environment == "dev"

    def test_valid_environments(self) -> None:
        for env in ("dev", "staging", "production"):
            cfg = RuntimeConfig(environment=env)
            assert cfg.environment == env

    def test_invalid_environment_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid environment"):
            RuntimeConfig(environment="test")

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from atlasbridge.core.config import _apply_env_overrides

        data: dict = {}
        monkeypatch.setenv("ATLASBRIDGE_ENVIRONMENT", "production")
        _apply_env_overrides(data)
        assert data["runtime"]["environment"] == "production"

    def test_env_var_not_set_no_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from atlasbridge.core.config import _apply_env_overrides

        monkeypatch.delenv("ATLASBRIDGE_ENVIRONMENT", raising=False)
        data: dict = {}
        _apply_env_overrides(data)
        assert "runtime" not in data
