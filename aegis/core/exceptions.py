"""Aegis exception hierarchy."""

from __future__ import annotations


class AegisError(Exception):
    """Base exception for all Aegis errors."""

    exit_code: int = 1


class ConfigError(AegisError):
    """Configuration is missing, invalid, or cannot be written."""

    exit_code = 2


class ConfigNotFoundError(ConfigError):
    """Config file does not exist; setup has not been run."""


class EnvError(AegisError):
    """Environment problem: wrong Python version, missing dependency, etc."""

    exit_code = 3


class NetworkError(AegisError):
    """Network failure, e.g., Telegram API unreachable."""

    exit_code = 4


class PermissionError(AegisError):  # noqa: A001 — intentional shadow
    """File permissions problem."""

    exit_code = 5


class SecurityViolationError(AegisError):
    """Security policy violation: unauthorized user, blocked operation, etc."""

    exit_code = 6


class DependencyMissingError(AegisError):
    """Required tool or library is not installed."""

    exit_code = 7


class StateCorruptionError(AegisError):
    """Database, lock file, or audit log is corrupted."""

    exit_code = 8


class TelegramAuthError(SecurityViolationError):
    """Message received from a non-whitelisted Telegram user."""


class PromptQueueFullError(AegisError):
    """Prompt queue has reached its maximum depth."""


class DaemonNotRunningError(AegisError):
    """Aegis daemon is not running when it is required."""
