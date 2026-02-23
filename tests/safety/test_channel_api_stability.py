"""Safety guard: BaseChannel ABC surface must not drift."""

from __future__ import annotations

import inspect
import re

from atlasbridge.channels.base import (
    CHANNEL_API_VERSION,
    BaseChannel,
    ChannelCircuitBreaker,
)

# Frozen abstract method set for v0.9.0
FROZEN_ABSTRACT_METHODS = frozenset(
    {
        "start",
        "close",
        "send_prompt",
        "notify",
        "send_output",
        "edit_prompt_message",
        "receive_replies",
        "is_allowed",
    }
)

# Frozen optional (non-abstract) methods with defaults
FROZEN_OPTIONAL_METHODS = frozenset(
    {
        "healthcheck",
        "send_agent_message",
        "send_output_editable",
        "send_plan",
        "guarded_send",
    }
)

# Known concrete channel implementations
KNOWN_CHANNEL_CLASSES: list[tuple[str, str]] = [
    ("atlasbridge.channels.telegram.channel", "TelegramChannel"),
    ("atlasbridge.channels.slack.channel", "SlackChannel"),
    ("atlasbridge.channels.multi", "MultiChannel"),
]


def _get_abstract_methods(cls: type) -> set[str]:
    return {
        name
        for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)
        if getattr(getattr(cls, name), "__isabstractmethod__", False)
    }


def test_channel_api_version_semver():
    """CHANNEL_API_VERSION must be a valid semver string."""
    assert re.match(r"^\d+\.\d+\.\d+$", CHANNEL_API_VERSION), (
        f"CHANNEL_API_VERSION is not valid semver: {CHANNEL_API_VERSION!r}"
    )


def test_abstract_methods_frozen():
    """BaseChannel must have exactly the frozen set of abstract methods."""
    actual = _get_abstract_methods(BaseChannel)
    assert actual == FROZEN_ABSTRACT_METHODS, (
        f"BaseChannel abstract methods changed. "
        f"Expected: {sorted(FROZEN_ABSTRACT_METHODS)}, "
        f"Got: {sorted(actual)}. "
        f"Added: {sorted(actual - FROZEN_ABSTRACT_METHODS)}, "
        f"Removed: {sorted(FROZEN_ABSTRACT_METHODS - actual)}"
    )


def test_optional_methods_exist():
    """BaseChannel must have all frozen optional methods with defaults."""
    for method_name in FROZEN_OPTIONAL_METHODS:
        method = getattr(BaseChannel, method_name, None)
        assert method is not None, f"Optional method '{method_name}' missing from BaseChannel"
        assert not getattr(method, "__isabstractmethod__", False), (
            f"'{method_name}' was optional but is now abstract — this breaks existing channels"
        )


def test_circuit_breaker_exists():
    """ChannelCircuitBreaker must exist with expected interface."""
    cb = ChannelCircuitBreaker()
    assert hasattr(cb, "threshold")
    assert hasattr(cb, "recovery_seconds")
    assert hasattr(cb, "is_open")
    assert callable(getattr(cb, "record_success", None))
    assert callable(getattr(cb, "record_failure", None))
    assert callable(getattr(cb, "reset", None))


def test_circuit_breaker_defaults():
    """ChannelCircuitBreaker default parameters must not drift."""
    cb = ChannelCircuitBreaker()
    assert cb.threshold == 3, f"Circuit breaker threshold changed: {cb.threshold}"
    assert cb.recovery_seconds == 30.0, (
        f"Circuit breaker recovery_seconds changed: {cb.recovery_seconds}"
    )


def test_send_prompt_signature():
    """send_prompt() must accept (self, event) and return str."""
    sig = inspect.signature(BaseChannel.send_prompt)
    params = list(sig.parameters.keys())
    assert params == ["self", "event"], f"send_prompt signature changed: {params}"


def test_notify_signature():
    """notify() signature must not change."""
    sig = inspect.signature(BaseChannel.notify)
    params = list(sig.parameters.keys())
    assert params == ["self", "message", "session_id"], f"notify signature changed: {params}"


def test_all_channels_have_required_class_attrs():
    """Every known channel must define channel_name and display_name."""
    import importlib

    for module_path, class_name in KNOWN_CHANNEL_CLASSES:
        mod = importlib.import_module(module_path)
        channel_cls = getattr(mod, class_name)
        assert channel_cls.channel_name, f"{class_name}.channel_name is empty"
        assert channel_cls.display_name, f"{class_name}.display_name is empty"
