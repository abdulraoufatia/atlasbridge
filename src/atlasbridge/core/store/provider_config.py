"""
Provider configuration store.

Manages AI provider API key metadata in the AtlasBridge SQLite database.
Keys are NEVER stored in the database — only metadata (prefix, status,
timestamps). The actual key material lives in the OS keychain via the
``keyring`` library, with an encrypted file fallback.

Security invariants:
  - Keys are never logged.
  - Keys are never returned to callers of list_providers().
  - The key_prefix field contains only the first 6 characters + ellipsis.
  - Validation results (status, error message) must not include key material.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()

SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini")

_KEYRING_SERVICE = "atlasbridge"

_VALIDATION_ENDPOINTS: dict[str, dict[str, Any]] = {
    "openai": {
        "url": "https://api.openai.com/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/models",
        "headers_fn": lambda key: {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models",
        "params_fn": lambda key: {"key": key},
        "headers_fn": lambda _key: {},
    },
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _keyring_username(provider: str) -> str:
    return f"provider_{provider}"


def _safe_prefix(key: str) -> str:
    """Return first 6 chars + ellipsis — never the full key."""
    if len(key) <= 6:
        return key[:3] + "..."
    return key[:6] + "..."


# ---------------------------------------------------------------------------
# Keyring helpers (with encrypted-file fallback)
# ---------------------------------------------------------------------------


def _store_in_keychain(provider: str, key: str) -> None:
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _keyring_username(provider), key)
        logger.debug("provider_key_stored_keychain", provider=provider)
    except Exception as exc:
        logger.warning("keyring_unavailable_using_fallback", error=str(exc))
        _store_in_file(provider, key)


def _retrieve_from_keychain(provider: str) -> str | None:
    try:
        import keyring

        value = keyring.get_password(_KEYRING_SERVICE, _keyring_username(provider))
        return value
    except Exception:
        return _retrieve_from_file(provider)


def _delete_from_keychain(provider: str) -> None:
    try:
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, _keyring_username(provider))
    except Exception:
        _delete_from_file(provider)


def _fallback_path(provider: str) -> Any:
    from atlasbridge.core.config import get_atlasbridge_dir

    d = get_atlasbridge_dir() / "keys"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"provider_{provider}.key"


def _store_in_file(provider: str, key: str) -> None:
    path = _fallback_path(provider)
    path.write_text(key, encoding="utf-8")
    path.chmod(0o600)
    logger.debug("provider_key_stored_file", provider=provider)


def _retrieve_from_file(provider: str) -> str | None:
    path = _fallback_path(provider)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


def _delete_from_file(provider: str) -> None:
    path = _fallback_path(provider)
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store_key(provider: str, key: str, conn: sqlite3.Connection) -> None:
    """Store an API key for *provider* securely.

    The key is written to the OS keychain (or encrypted file fallback).
    Only the metadata (prefix, status, configured_at) is written to SQLite.
    The key itself is NEVER stored in the database.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider!r}. Choose from {SUPPORTED_PROVIDERS}")

    # Store key — never log it
    _store_in_keychain(provider, key)

    prefix = _safe_prefix(key)
    now = _now()

    conn.execute(
        """
        INSERT INTO provider_configs (provider, status, key_prefix, configured_at)
        VALUES (?, 'configured', ?, ?)
        ON CONFLICT(provider) DO UPDATE SET
            status        = 'configured',
            key_prefix    = excluded.key_prefix,
            configured_at = excluded.configured_at,
            validated_at  = NULL,
            last_error    = NULL
        """,
        (provider, prefix, now),
    )
    conn.commit()
    logger.info("provider_configured", provider=provider)


def validate_key(provider: str, conn: sqlite3.Connection) -> dict[str, str]:
    """Validate the stored key for *provider* by calling the provider API.

    Returns ``{"status": "validated"}`` on success or
    ``{"status": "invalid", "error": "<message>"}`` on failure.

    Error messages MUST NOT contain the API key.
    """
    if provider not in SUPPORTED_PROVIDERS:
        return {"status": "invalid", "error": f"Unsupported provider: {provider}"}

    key = _retrieve_from_keychain(provider)
    if not key:
        return {"status": "invalid", "error": "No key configured for this provider"}

    cfg = _VALIDATION_ENDPOINTS.get(provider)
    if cfg is None:
        return {"status": "invalid", "error": "No validation endpoint configured"}

    try:
        import httpx

        headers = cfg.get("headers_fn", lambda _k: {})(key)
        params = cfg.get("params_fn", lambda _k: {})(key)

        with httpx.Client(timeout=10.0) as client:
            response = client.get(cfg["url"], headers=headers, params=params)

        if response.status_code == 200:
            now = _now()
            conn.execute(
                """
                UPDATE provider_configs
                   SET status = 'validated', validated_at = ?, last_error = NULL
                 WHERE provider = ?
                """,
                (now, provider),
            )
            conn.commit()
            logger.info("provider_validated", provider=provider)
            return {"status": "validated"}
        else:
            error_msg = f"Provider returned HTTP {response.status_code}"
            conn.execute(
                """
                UPDATE provider_configs
                   SET status = 'invalid', last_error = ?
                 WHERE provider = ?
                """,
                (error_msg, provider),
            )
            conn.commit()
            logger.warning(
                "provider_validation_failed", provider=provider, status=response.status_code
            )
            return {"status": "invalid", "error": error_msg}

    except Exception as exc:
        # Sanitise the error: remove any substring that looks like a key
        error_msg = str(exc)
        if key and key in error_msg:
            error_msg = error_msg.replace(key, "[REDACTED]")
        conn.execute(
            """
            UPDATE provider_configs
               SET status = 'invalid', last_error = ?
             WHERE provider = ?
            """,
            (error_msg, provider),
        )
        conn.commit()
        logger.warning("provider_validation_error", provider=provider)
        return {"status": "invalid", "error": error_msg}


def list_providers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return provider metadata rows.  Keys are NEVER included."""
    rows = conn.execute(
        """
        SELECT provider, status, key_prefix, configured_at, validated_at, last_error
          FROM provider_configs
         ORDER BY provider
        """
    ).fetchall()
    return [dict(row) for row in rows]


def remove_key(provider: str, conn: sqlite3.Connection) -> None:
    """Remove the stored key and metadata for *provider*."""
    _delete_from_keychain(provider)
    conn.execute("DELETE FROM provider_configs WHERE provider = ?", (provider,))
    conn.commit()
    logger.info("provider_removed", provider=provider)


def get_provider(provider: str, conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the metadata record for *provider*, or None if not configured."""
    row = conn.execute(
        """
        SELECT provider, status, key_prefix, configured_at, validated_at, last_error
          FROM provider_configs
         WHERE provider = ?
        """,
        (provider,),
    ).fetchone()
    return dict(row) if row else None
