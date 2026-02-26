"""Unit tests for atlasbridge.core.store.provider_config."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlasbridge.core.store.migrations import run_migrations
from atlasbridge.core.store.provider_config import (
    _safe_prefix,
    get_provider,
    list_providers,
    remove_key,
    store_key,
    validate_key,
)


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    run_migrations(c, db_path)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# _safe_prefix
# ---------------------------------------------------------------------------


class TestSafePrefix:
    def test_short_key_ends_with_dots(self) -> None:
        prefix = _safe_prefix("sk-abc")
        assert prefix.endswith("...")
        assert len(prefix) <= 9

    def test_long_key_truncated(self) -> None:
        key = "sk-ant-api03-longkeyhere"
        prefix = _safe_prefix(key)
        # 6 chars + "..." = 9 chars max
        assert len(prefix) <= 9
        assert prefix.endswith("...")

    def test_prefix_does_not_include_full_key(self) -> None:
        key = "sk-reallyverylongapikey12345"
        prefix = _safe_prefix(key)
        assert key not in prefix
        assert len(prefix) < len(key)


# ---------------------------------------------------------------------------
# store_key — metadata only in DB, key in keychain
# ---------------------------------------------------------------------------


class TestStoreKey:
    def test_store_writes_metadata_not_key(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain") as mock_kc:
            store_key("openai", "sk-test-key-1234", conn)
            mock_kc.assert_called_once()

        row = get_provider("openai", conn)
        assert row is not None
        # Key must NOT be stored in DB
        raw = conn.execute("SELECT * FROM provider_configs WHERE provider = 'openai'").fetchone()
        raw_dict = dict(raw)
        assert "sk-test-key-1234" not in str(raw_dict)

    def test_store_records_prefix(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("anthropic", "sk-ant-key-9876", conn)

        row = get_provider("anthropic", conn)
        assert row is not None
        assert row["key_prefix"] is not None
        assert "sk-ant" in row["key_prefix"]
        assert "9876" not in row["key_prefix"]  # no full key in prefix

    def test_store_sets_status_configured(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("gemini", "AIza-testkey-xyz", conn)

        row = get_provider("gemini", conn)
        assert row["status"] == "configured"

    def test_key_not_in_logger_output(self, conn: sqlite3.Connection) -> None:
        """Verify key material does not appear in structured log output."""
        secret_key = "sk-super-secret-key-should-never-appear"
        log_events: list[dict] = []

        import structlog

        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            with structlog.testing.capture_logs() as captured:
                store_key("openai", secret_key, conn)
            log_events = captured

        for event in log_events:
            for v in event.values():
                assert secret_key not in str(v), f"Secret key found in log event: {event}"


# ---------------------------------------------------------------------------
# list_providers — no key material
# ---------------------------------------------------------------------------


class TestListProviders:
    def test_empty_initially(self, conn: sqlite3.Connection) -> None:
        assert list_providers(conn) == []

    def test_no_key_material_in_response(self, conn: sqlite3.Connection) -> None:
        secret_key = "sk-ant-very-secret-key-abc123"
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("anthropic", secret_key, conn)

        rows = list_providers(conn)
        assert len(rows) == 1
        for row in rows:
            for v in row.values():
                assert secret_key not in str(v), "Secret key found in list_providers response"

    def test_lists_multiple_providers(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("openai", "sk-1111", conn)
            store_key("gemini", "AIza-2222", conn)

        rows = list_providers(conn)
        providers = {r["provider"] for r in rows}
        assert "openai" in providers
        assert "gemini" in providers


# ---------------------------------------------------------------------------
# validate_key
# ---------------------------------------------------------------------------


def _mock_httpx_client(status_code: int) -> MagicMock:
    """Create a mock httpx.Client context manager that returns given status."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(return_value=mock_resp)
    return mock_client


class TestValidateKey:
    def test_validate_success_updates_status(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("openai", "sk-valid-key", conn)

        mock_client = _mock_httpx_client(200)
        with patch("atlasbridge.core.store.provider_config._retrieve_from_keychain", return_value="sk-valid-key"):
            with patch("httpx.Client", return_value=mock_client):
                result = validate_key("openai", conn)

        assert result["status"] == "validated"
        row = get_provider("openai", conn)
        assert row["status"] == "validated"
        assert row["validated_at"] is not None

    def test_validate_failure_sets_invalid(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("openai", "sk-bad-key", conn)

        mock_client = _mock_httpx_client(401)
        with patch("atlasbridge.core.store.provider_config._retrieve_from_keychain", return_value="sk-bad-key"):
            with patch("httpx.Client", return_value=mock_client):
                result = validate_key("openai", conn)

        assert result["status"] == "invalid"
        row = get_provider("openai", conn)
        assert row["status"] == "invalid"

    def test_validate_error_does_not_leak_key(self, conn: sqlite3.Connection) -> None:
        secret_key = "sk-super-secret-must-not-leak"
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("openai", secret_key, conn)

        mock_client = _mock_httpx_client(401)
        with patch("atlasbridge.core.store.provider_config._retrieve_from_keychain", return_value=secret_key):
            with patch("httpx.Client", return_value=mock_client):
                result = validate_key("openai", conn)

        # Error message must not contain the key
        error_msg = result.get("error", "")
        assert secret_key not in error_msg

        # last_error in DB must not contain the key
        row = get_provider("openai", conn)
        assert row["last_error"] is None or secret_key not in row["last_error"]


# ---------------------------------------------------------------------------
# remove_key
# ---------------------------------------------------------------------------


class TestRemoveKey:
    def test_remove_deletes_from_db(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("openai", "sk-to-remove", conn)

        assert get_provider("openai", conn) is not None

        with patch("atlasbridge.core.store.provider_config._delete_from_keychain"):
            remove_key("openai", conn)

        assert get_provider("openai", conn) is None

    def test_remove_calls_keychain_delete(self, conn: sqlite3.Connection) -> None:
        with patch("atlasbridge.core.store.provider_config._store_in_keychain"):
            store_key("gemini", "AIza-key", conn)

        with patch("atlasbridge.core.store.provider_config._delete_from_keychain") as mock_del:
            remove_key("gemini", conn)
            mock_del.assert_called_once_with("gemini")
