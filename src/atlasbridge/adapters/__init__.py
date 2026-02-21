"""
AtlasBridge built-in adapters.

Importing this package (or any of its sub-modules) automatically registers
all built-in adapters in the global AdapterRegistry via their
@AdapterRegistry.register() decorators.

Third-party adapters can register themselves the same way — just import
atlasbridge.adapters.base and apply @AdapterRegistry.register("my-tool").
"""

import structlog as _structlog

_logger = _structlog.get_logger()

# Side-effect imports: running each module executes the @AdapterRegistry.register()
# decorator at module scope, which populates AdapterRegistry._registry.
# Each import is wrapped so a broken adapter doesn't prevent the rest from loading.
_BUILTIN_ADAPTERS = (
    "atlasbridge.adapters.claude_code",
    "atlasbridge.adapters.openai_cli",
    "atlasbridge.adapters.gemini_cli",
)

for _mod_name in _BUILTIN_ADAPTERS:
    try:
        __import__(_mod_name)
    except Exception as _exc:  # noqa: BLE001
        _logger.warning("adapter_load_failed", module=_mod_name, error=str(_exc))

# Re-export the registry and base class for convenience.
from atlasbridge.adapters.base import AdapterRegistry, BaseAdapter  # noqa: E402

__all__ = ["AdapterRegistry", "BaseAdapter"]
