"""
Tool executor — runs tools by name with argument dispatch.

The executor looks up tools in the registry and calls their executor function.
Policy governance happens in the ChatEngine before reaching here.
"""

from __future__ import annotations

from typing import Any

import structlog

from atlasbridge.tools.registry import ToolRegistry

logger = structlog.get_logger()


class ToolExecutor:
    """Executes tools by looking them up in the registry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return its string result."""
        tool = self._registry.get(tool_name)
        if tool is None:
            return f"Error: Unknown tool '{tool_name}'"
        if tool.executor is None:
            return f"Error: Tool '{tool_name}' has no executor."

        logger.info(
            "tool_executing",
            tool=tool_name,
            risk=tool.risk_level,
        )

        result = await tool.executor(arguments)

        logger.info(
            "tool_executed",
            tool=tool_name,
            result_len=len(result),
        )
        return result
