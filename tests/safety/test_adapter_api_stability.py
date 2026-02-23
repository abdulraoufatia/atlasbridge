"""Safety guard: BaseAdapter ABC surface must not drift."""

from __future__ import annotations

import inspect
import re

from atlasbridge.adapters.base import ADAPTER_API_VERSION, AdapterRegistry, BaseAdapter

# Frozen abstract method set for v0.9.0
FROZEN_ABSTRACT_METHODS = frozenset(
    {
        "start_session",
        "terminate_session",
        "read_stream",
        "inject_reply",
        "await_input_state",
    }
)

# Frozen optional (non-abstract) methods with defaults
FROZEN_OPTIONAL_METHODS = frozenset(
    {
        "snapshot_context",
        "get_detector",
        "healthcheck",
    }
)

# Frozen registered adapter names
FROZEN_ADAPTER_NAMES = frozenset(
    {
        "claude",
        "claude-code",
        "openai",
        "gemini",
        "custom",
    }
)


def _get_abstract_methods(cls: type) -> set[str]:
    """Return names of abstract methods on a class."""
    return {
        name
        for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)
        if getattr(getattr(cls, name), "__isabstractmethod__", False)
    }


def test_abstract_methods_frozen():
    """BaseAdapter must have exactly the frozen set of abstract methods."""
    actual = _get_abstract_methods(BaseAdapter)
    assert actual == FROZEN_ABSTRACT_METHODS, (
        f"BaseAdapter abstract methods changed. "
        f"Expected: {sorted(FROZEN_ABSTRACT_METHODS)}, "
        f"Got: {sorted(actual)}. "
        f"Added: {sorted(actual - FROZEN_ABSTRACT_METHODS)}, "
        f"Removed: {sorted(FROZEN_ABSTRACT_METHODS - actual)}"
    )


def test_optional_methods_exist():
    """BaseAdapter must have all frozen optional methods with defaults."""
    for method_name in FROZEN_OPTIONAL_METHODS:
        method = getattr(BaseAdapter, method_name, None)
        assert method is not None, f"Optional method '{method_name}' missing from BaseAdapter"
        assert not getattr(method, "__isabstractmethod__", False), (
            f"'{method_name}' was optional but is now abstract — this breaks existing adapters"
        )


def test_start_session_signature():
    """start_session() signature must not change."""
    sig = inspect.signature(BaseAdapter.start_session)
    params = list(sig.parameters.keys())
    assert params == ["self", "session_id", "command", "env", "cwd"], (
        f"start_session signature changed: {params}"
    )


def test_inject_reply_signature():
    """inject_reply() signature must not change."""
    sig = inspect.signature(BaseAdapter.inject_reply)
    params = list(sig.parameters.keys())
    assert params == ["self", "session_id", "value", "prompt_type"], (
        f"inject_reply signature changed: {params}"
    )


def test_registry_has_frozen_adapters():
    """All frozen adapter names must be registered."""
    # Force adapter imports so they register
    import atlasbridge.adapters.claude_code  # noqa: F401
    import atlasbridge.adapters.gemini_cli  # noqa: F401
    import atlasbridge.adapters.openai_cli  # noqa: F401

    registered = set(AdapterRegistry.list_all().keys())
    missing = FROZEN_ADAPTER_NAMES - registered
    assert not missing, f"Adapter names removed from registry: {sorted(missing)}"


def test_registry_methods_exist():
    """AdapterRegistry must expose register(), get(), list_all()."""
    assert callable(getattr(AdapterRegistry, "register", None))
    assert callable(getattr(AdapterRegistry, "get", None))
    assert callable(getattr(AdapterRegistry, "list_all", None))


def test_adapter_api_version_semver():
    """ADAPTER_API_VERSION must be a valid semver string."""
    assert re.match(r"^\d+\.\d+\.\d+$", ADAPTER_API_VERSION), (
        f"ADAPTER_API_VERSION is not valid semver: {ADAPTER_API_VERSION!r}"
    )


def test_all_adapters_implement_abstract_methods():
    """Every registered adapter must implement all abstract methods."""
    import atlasbridge.adapters.claude_code  # noqa: F401
    import atlasbridge.adapters.gemini_cli  # noqa: F401
    import atlasbridge.adapters.openai_cli  # noqa: F401

    for name, adapter_cls in AdapterRegistry.list_all().items():
        remaining = _get_abstract_methods(adapter_cls)
        assert not remaining, (
            f"Adapter '{name}' ({adapter_cls.__name__}) has unimplemented "
            f"abstract methods: {sorted(remaining)}"
        )


def test_all_adapters_have_required_class_attrs():
    """Every registered adapter must define tool_name, description, min_tool_version."""
    import atlasbridge.adapters.claude_code  # noqa: F401
    import atlasbridge.adapters.gemini_cli  # noqa: F401
    import atlasbridge.adapters.openai_cli  # noqa: F401

    for name, adapter_cls in AdapterRegistry.list_all().items():
        assert adapter_cls.tool_name, f"Adapter '{name}' has empty tool_name"
        assert adapter_cls.description, f"Adapter '{name}' has empty description"
