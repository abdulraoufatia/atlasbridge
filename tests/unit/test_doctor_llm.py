"""Unit tests for the LLM provider doctor check."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from atlasbridge.cli._doctor import _check_llm_provider


def _mock_config(name: str = "", api_key: str = "", model: str = "") -> MagicMock:
    """Build a mock AtlasBridgeConfig with the given chat provider settings."""
    cfg = MagicMock()
    cfg.chat.provider.name = name
    cfg.chat.provider.model = model
    if api_key:
        cfg.chat.provider.api_key.get_secret_value.return_value = api_key
    else:
        cfg.chat.provider.api_key = None
    return cfg


class TestCheckLlmProvider:
    def test_skip_when_no_config_file(self, tmp_path: Path) -> None:
        with patch(
            "atlasbridge.cli._doctor._config_path",
            return_value=tmp_path / "missing.toml",
        ):
            result = _check_llm_provider()
        assert result is None

    def test_skip_when_no_provider_configured(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.touch()
        with (
            patch("atlasbridge.cli._doctor._config_path", return_value=cfg),
            patch(
                "atlasbridge.core.config.load_config",
                return_value=_mock_config(),
            ),
        ):
            result = _check_llm_provider()
        assert result is None

    def test_warn_when_no_api_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.touch()
        with (
            patch("atlasbridge.cli._doctor._config_path", return_value=cfg),
            patch(
                "atlasbridge.core.config.load_config",
                return_value=_mock_config(name="anthropic"),
            ),
        ):
            result = _check_llm_provider()
        assert result is not None
        assert result["status"] == "warn"
        assert "no API key" in result["detail"]

    def test_pass_when_api_responds_200(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.touch()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with (
            patch("atlasbridge.cli._doctor._config_path", return_value=cfg),
            patch(
                "atlasbridge.core.config.load_config",
                return_value=_mock_config(name="anthropic", api_key="sk-test-key"),
            ),
            patch("httpx.post", return_value=mock_resp),
        ):
            result = _check_llm_provider()
        assert result is not None
        assert result["status"] == "pass"
        assert "API key valid" in result["detail"]

    def test_warn_when_api_returns_401(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.touch()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with (
            patch("atlasbridge.cli._doctor._config_path", return_value=cfg),
            patch(
                "atlasbridge.core.config.load_config",
                return_value=_mock_config(name="openai", api_key="sk-bad"),
            ),
            patch("httpx.post", return_value=mock_resp),
        ):
            result = _check_llm_provider()
        assert result is not None
        assert result["status"] == "warn"
        assert "401" in result["detail"]

    def test_warn_on_network_error(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.touch()
        import httpx

        with (
            patch("atlasbridge.cli._doctor._config_path", return_value=cfg),
            patch(
                "atlasbridge.core.config.load_config",
                return_value=_mock_config(name="anthropic", api_key="sk-test"),
            ),
            patch("httpx.post", side_effect=httpx.ConnectError("no network")),
        ):
            result = _check_llm_provider()
        assert result is not None
        assert result["status"] == "warn"
        assert "check failed" in result["detail"]

    def test_google_provider_path(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.touch()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with (
            patch("atlasbridge.cli._doctor._config_path", return_value=cfg),
            patch(
                "atlasbridge.core.config.load_config",
                return_value=_mock_config(name="google", api_key="AIza-test"),
            ),
            patch("httpx.post", return_value=mock_resp) as mock_post,
        ):
            result = _check_llm_provider()
        assert result is not None
        assert result["status"] == "pass"
        call_url = mock_post.call_args[0][0]
        assert "generativelanguage.googleapis.com" in call_url
