"""AtlasBridge exception hierarchy."""

from __future__ import annotations


class AtlasBridgeError(Exception):
    """Base exception for all AtlasBridge errors."""


class ConfigError(AtlasBridgeError):
    """Raised when the configuration is invalid or cannot be read."""


class ConfigNotFoundError(ConfigError):
    """Raised when the configuration file does not exist."""


class ChannelError(AtlasBridgeError):
    """Raised when a notification channel fails."""


class AdapterError(AtlasBridgeError):
    """Raised when a tool adapter fails."""


class SessionError(AtlasBridgeError):
    """Raised when session management fails."""


# Backwards-compat alias — remove in v1.0
AegisError = AtlasBridgeError
