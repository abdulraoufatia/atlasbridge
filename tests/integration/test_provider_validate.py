"""Integration tests for provider key validation flow."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlasbridge.core.store.migrations import run_migrations
from atlasbridge.core.store.provider_config import (
    get_provider,
    list_providers,
    remove_key,
    store_key,
    validate_key,
)

_KEYCHAIN_RETRIEVE = "atlasbridge.core.store.provider_config._retrieve_from_keychain"


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    run_migrations(c, db_path)
    yield c
    c.close()


def _mock_http_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    return resp


def _mock_httpx_client(status_code: int) -> MagicMock:
    mock_resp = _mock_http_response(status_code)
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(return_value=mock_resp)
    return mock_client


class TestValidateKeyHappyPath:
    @pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
    def test_200_sets_validated(self, conn: sqlite3.Connection, provider: str) -> None:
        test_key = f"test-key-for-{provider}"
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key(provider, test_key, conn)

        with (
            patch(_KEYCHAIN_RETRIEVE, return_value=test_key),
            patch("httpx.Client", return_value=_mock_httpx_client(200)),
        ):
            result = validate_key(provider, conn)

        assert result["status"] == "validated"
        row = get_provider(provider, conn)
        assert row["status"] == "validated"
        assert row["validated_at"] is not None
        assert row["last_error"] is None


class TestValidateKeyErrorPath:
    @pytest.mark.parametrize("status_code", [401, 403, 429, 500])
    def test_non_200_sets_invalid(self, conn: sqlite3.Connection, status_code: int) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("openai", "sk-bad", conn)

        with (
            patch(_KEYCHAIN_RETRIEVE, return_value="sk-bad"),
            patch("httpx.Client", return_value=_mock_httpx_client(status_code)),
        ):
            result = validate_key("openai", conn)

        assert result["status"] == "invalid"
        row = get_provider("openai", conn)
        assert row["status"] == "invalid"

    def test_error_message_does_not_contain_key(self, conn: sqlite3.Connection) -> None:
        secret_key = "sk-secret-leak-check-9999"
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("openai", secret_key, conn)

        with (
            patch(_KEYCHAIN_RETRIEVE, return_value=secret_key),
            patch("httpx.Client", return_value=_mock_httpx_client(401)),
        ):
            result = validate_key("openai", conn)

        error_msg = result.get("error", "")
        assert secret_key not in error_msg

    def test_network_exception_sets_invalid(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("anthropic", "sk-ant-netfail", conn)

        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(side_effect=httpx.RequestError("connection refused"))

        with (
            patch(_KEYCHAIN_RETRIEVE, return_value="sk-ant-netfail"),
            patch("httpx.Client", return_value=mock_client),
        ):
            result = validate_key("anthropic", conn)

        assert result["status"] == "invalid"
        row = get_provider("anthropic", conn)
        assert row["status"] == "invalid"


class TestProviderKeyLifecycle:
    def test_store_validate_remove_cycle(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("gemini", "AIza-lifecycle", conn)

        assert get_provider("gemini", conn) is not None
        rows = list_providers(conn)
        assert any(r["provider"] == "gemini" for r in rows)
        # No key material in list
        for row in rows:
            for v in row.values():
                assert "AIza-lifecycle" not in str(v)

        with (
            patch(_KEYCHAIN_RETRIEVE, return_value="AIza-lifecycle"),
            patch("httpx.Client", return_value=_mock_httpx_client(200)),
        ):
            validate_key("gemini", conn)

        assert get_provider("gemini", conn)["status"] == "validated"

        with patch("atlasbridge.core.store.provider_config._delete_from_keychain"):
            remove_key("gemini", conn)

        assert get_provider("gemini", conn) is None
