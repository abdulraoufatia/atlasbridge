"""Telegram bot token verification via the getMe API endpoint."""

from __future__ import annotations


def verify_telegram_token(token: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Call Telegram getMe to verify a bot token works.

    Returns ``(True, "Bot: @username")`` on success, or
    ``(False, "reason")`` on any failure.

    Uses httpx synchronously — safe for CLI and doctor contexts.
    """
    try:
        import httpx
    except ImportError:
        return False, "httpx is not installed"

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        resp = httpx.get(url, timeout=timeout)
        data = resp.json()
        if data.get("ok"):
            username = data.get("result", {}).get("username", "unknown")
            return True, f"Bot: @{username}"
        description = data.get("description", "Unknown error")
        return False, description
    except httpx.TimeoutException:
        return False, "Request timed out"
    except httpx.ConnectError:
        return False, "Could not connect to Telegram API"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
