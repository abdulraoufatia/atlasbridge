"""Unit tests for keyring-first API key storage in setup."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from atlasbridge.cli._doctor import _check_plaintext_tokens


class TestSetupKeyringFlag:
    def test_setup_cmd_accepts_no_keyring_flag(self) -> None:
        """--no-keyring flag is accepted by the setup command."""
        from atlasbridge.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["setup", "--help"])
        assert result.exit_code == 0
        assert "--no-keyring" in result.output


class TestCheckPlaintextTokens:
    def test_skip_when_keyring_not_available(self) -> None:
        with patch(
            "atlasbridge.core.keyring_store.is_keyring_available",
            return_value=False,
        ):
            result = _check_plaintext_tokens()
        assert result is None

    def test_skip_when_no_config(self, tmp_path) -> None:
        with (
            patch(
                "atlasbridge.core.keyring_store.is_keyring_available",
                return_value=True,
            ),
            patch(
                "atlasbridge.cli._doctor._config_path",
                return_value=tmp_path / "missing.toml",
            ),
        ):
            result = _check_plaintext_tokens()
        assert result is None

    def test_pass_when_no_plaintext_tokens(self, tmp_path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text("config_version = 1\n\n[prompts]\ntimeout_seconds = 300\n")
        with (
            patch(
                "atlasbridge.core.keyring_store.is_keyring_available",
                return_value=True,
            ),
            patch("atlasbridge.cli._doctor._config_path", return_value=cfg),
        ):
            result = _check_plaintext_tokens()
        # No token fields to check → pass or None
        assert result is None or result["status"] == "pass"

    def test_warn_on_plaintext_chat_api_key(self, tmp_path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            "config_version = 1\n\n"
            "[chat.provider]\n"
            'name = "anthropic"\n'
            'api_key = "sk-plaintext-key"\n'
        )
        with (
            patch(
                "atlasbridge.core.keyring_store.is_keyring_available",
                return_value=True,
            ),
            patch("atlasbridge.cli._doctor._config_path", return_value=cfg),
        ):
            result = _check_plaintext_tokens()
        assert result is not None
        assert result["status"] == "warn"
        assert "chat.provider.api_key" in result["detail"]
