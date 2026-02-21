"""Optional keyring integration for secure token storage.

When the ``[keyring]`` extra is installed (``pip install atlasbridge[keyring]``),
tokens can be stored in the OS keychain (macOS Keychain / Linux Secret Service)
instead of the config file.  A ``keyring:atlasbridge:<key>`` placeholder is
written to ``config.toml`` in place of the real token.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

SERVICE_NAME = "atlasbridge"
KEYRING_PREFIX = "keyring:"


def is_keyring_available() -> bool:
    """Return True if a usable keyring backend is available."""
    try:
        import keyring

        backend = keyring.get_keyring()
        name = type(backend).__name__.lower()
        # Reject non-functional backends
        return "fail" not in name and "null" not in name
    except Exception:  # noqa: BLE001
        return False


def store_token(key: str, token: str) -> str:
    """Store *token* in OS keychain under *key*, return placeholder string."""
    import keyring

    keyring.set_password(SERVICE_NAME, key, token)
    return f"{KEYRING_PREFIX}{SERVICE_NAME}:{key}"


def retrieve_token(placeholder: str) -> str | None:
    """Resolve a ``keyring:service:key`` placeholder to the actual token.

    Returns ``None`` if keyring is unavailable or the key is not found.
    """
    if not placeholder.startswith(KEYRING_PREFIX):
        return None

    try:
        import keyring

        rest = placeholder[len(KEYRING_PREFIX) :]
        service, key = rest.split(":", 1)
        return keyring.get_password(service, key)
    except Exception:  # noqa: BLE001
        logger.warning("keyring_retrieve_failed", placeholder=placeholder)
        return None


def is_keyring_placeholder(value: str) -> bool:
    """Return True if *value* is a ``keyring:*`` placeholder."""
    return isinstance(value, str) and value.startswith(KEYRING_PREFIX)


def delete_token(key: str) -> None:
    """Remove a token from the keychain (best-effort)."""
    try:
        import keyring

        keyring.delete_password(SERVICE_NAME, key)
    except Exception:  # noqa: BLE001
        pass
