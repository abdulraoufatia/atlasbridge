"""
AtlasBridge built-in adapters.

Importing this package (or any of its sub-modules) automatically registers
all built-in adapters in the global AdapterRegistry via their
@AdapterRegistry.register() decorators.

Third-party adapters can register themselves the same way — just import
atlasbridge.adapters.base and apply @AdapterRegistry.register("my-tool").
"""

# Side-effect imports: running each module executes the @AdapterRegistry.register()
# decorator at module scope, which populates AdapterRegistry._registry.
from atlasbridge.adapters import claude_code, gemini_cli, openai_cli  # noqa: F401

# Re-export the registry and base class for convenience.
from atlasbridge.adapters.base import AdapterRegistry, BaseAdapter

__all__ = ["AdapterRegistry", "BaseAdapter"]
