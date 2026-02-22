"""AtlasBridge exception hierarchy."""

from __future__ import annotations

import warnings as _warnings


class AtlasBridgeError(Exception):
    """Base exception for all AtlasBridge errors."""


class ConfigError(AtlasBridgeError):
    """Raised when the configuration is invalid or cannot be read."""


class ConfigNotFoundError(ConfigError):
    """Raised when the configuration file does not exist."""


class ChannelError(AtlasBridgeError):
    """Raised when a notification channel fails."""


class ChannelUnavailableError(ChannelError):
    """Raised when a channel's circuit breaker is open."""


class AdapterError(AtlasBridgeError):
    """Raised when a tool adapter fails."""


class SessionError(AtlasBridgeError):
    """Raised when session management fails."""


# Backwards-compat alias — remove in v1.0


def __getattr__(name: str) -> type:  # noqa: N807
    if name == "AegisError":
        _warnings.warn(
            "AegisError is deprecated, use AtlasBridgeError instead. Will be removed in v1.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return AtlasBridgeError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
