"""
BaseProvider — abstract interface for LLM API providers.

A provider is responsible for:
  1. Sending conversation messages to an LLM API
  2. Receiving responses (including streaming chunks)
  3. Parsing tool_use requests from the LLM response
  4. Sending tool results back to the LLM

Providers are stateless across sessions — conversation history is managed
by the ChatEngine, not the provider.

Provider registry:
  Use @ProviderRegistry.register("name") to register a provider class.
  Retrieve with: ProviderRegistry.get("name")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

PROVIDER_API_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ToolDefinition:
    """Tool schema passed to the LLM API."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    """An LLM-requested tool invocation."""

    id: str  # provider-assigned call ID
    name: str  # tool name (e.g. "read_file", "run_command")
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """The result of executing a tool."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "user" | "assistant" | "system" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """A chunk of a streaming response."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    is_final: bool = False
    usage: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider ABC
# ---------------------------------------------------------------------------


class BaseProvider(ABC):
    """Abstract LLM API provider."""

    #: Short identifier (e.g. "anthropic", "openai", "google")
    provider_name: str = ""

    #: Human-readable name shown in UI
    display_name: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system: str = "",
        max_tokens: int = 4096,
    ) -> Message:
        """Send a conversation and get a complete response."""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system: str = "",
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        """Send a conversation and stream the response."""

    @abstractmethod
    async def close(self) -> None:
        """Close the HTTP client."""

    def healthcheck(self) -> dict[str, Any]:
        """Return health status for this provider."""
        return {"status": "ok", "provider": self.provider_name}


# ---------------------------------------------------------------------------
# Provider registry (same metaclass pattern as AdapterRegistry)
# ---------------------------------------------------------------------------


class _ProviderRegistryMeta(type):
    _registry: dict[str, type[BaseProvider]] = {}


class ProviderRegistry(metaclass=_ProviderRegistryMeta):
    """Global registry of available LLM providers."""

    @classmethod
    def register(cls, name: str) -> Any:
        """Decorator: @ProviderRegistry.register("anthropic")"""

        def decorator(provider_cls: type[BaseProvider]) -> type[BaseProvider]:
            cls._registry[name] = provider_cls
            return provider_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseProvider]:
        if name not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys())) or "(none)"
            raise KeyError(f"Unknown provider: {name!r}. Available: {available}")
        return cls._registry[name]

    @classmethod
    def list_all(cls) -> dict[str, type[BaseProvider]]:
        return dict(cls._registry)
