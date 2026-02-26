"""
Tool registry — defines available tools for LLM chat mode.

Each tool has a name, description, JSON Schema parameters, risk level,
and an async executor function.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from atlasbridge.providers.base import ToolDefinition

# Type alias for tool executor functions
ToolExecutorFn = Callable[[dict[str, Any]], Awaitable[str]]


@dataclass
class Tool:
    """A registered tool that the LLM can invoke."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    risk_level: str = "moderate"  # safe | moderate | dangerous
    executor: ToolExecutorFn | None = None


class ToolRegistry:
    """Registry of available tools for LLM chat mode."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Return a tool by name, or None if not found."""
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def to_definitions(self) -> list[ToolDefinition]:
        """Convert all tools to ToolDefinition objects for the LLM API."""
        return [
            ToolDefinition(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
            )
            for t in self._tools.values()
        ]


def get_default_registry() -> ToolRegistry:
    """Create a ToolRegistry with all built-in tools registered."""
    from atlasbridge.tools.builtins import get_builtin_tools

    registry = ToolRegistry()
    for tool in get_builtin_tools():
        registry.register(tool)
    return registry
