# AtlasBridge Tool Adapter Abstraction Design

**Version:** 0.1.0
**Status:** Design
**Last updated:** 2026-02-20

---

## Overview

AtlasBridge must work with multiple AI CLI tools (Claude Code, OpenAI CLI, and future tools). The tool adapter abstraction provides a vendor-neutral interface for:
1. Launching the tool in a controlled environment
2. Intercepting tool call events from the tool's output stream
3. Injecting approval decisions back into the tool's input

---

## Design Goals

- **Vendor neutral**: Adding a new tool requires only a new adapter implementation
- **Protocol agnostic**: Different tools emit tool calls in different formats — the adapter handles parsing
- **Fail-safe**: If the adapter can't parse an event, it defaults to `require_approval`
- **Transparent**: From the user's perspective, `atlasbridge run claude` behaves exactly like `claude`

---

## Base Adapter Interface

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
from atlasbridge.core.events import ToolCallEvent, ToolCallResult

class ToolAdapter(ABC):
    """
    Abstract base class for all tool adapters.

    A tool adapter is responsible for:
    1. Launching the wrapped tool process
    2. Parsing tool call events from the tool's output stream
    3. Injecting approval decisions (allow/deny) back to the tool
    4. Relaying non-tool output to the user's terminal
    5. Handling process lifecycle (start, stop, crash)
    """

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """The canonical name of the tool (e.g., 'claude', 'openai')."""
        ...

    @property
    @abstractmethod
    def supported_versions(self) -> list[str]:
        """Semver ranges of supported tool versions (empty = all versions)."""
        ...

    @abstractmethod
    async def launch(
        self,
        args: list[str],
        env: dict[str, str],
        session_id: str,
    ) -> None:
        """
        Launch the tool process.

        Args:
            args: Command-line arguments to pass to the tool
            env: Environment variables for the tool's process
            session_id: AtlasBridge session ID for this invocation
        """
        ...

    @abstractmethod
    async def tool_call_events(self) -> AsyncIterator[ToolCallEvent]:
        """
        Async generator that yields tool call events as the tool emits them.

        Each yielded event represents one tool call that needs policy evaluation.
        The generator suspends the tool's execution while each event is processed.
        """
        ...

    @abstractmethod
    async def allow_tool_call(self, event: ToolCallEvent) -> None:
        """
        Signal to the tool that the tool call is approved and should proceed.
        """
        ...

    @abstractmethod
    async def deny_tool_call(self, event: ToolCallEvent, reason: str) -> None:
        """
        Signal to the tool that the tool call is denied.
        The tool receives an error response and may retry or stop.
        """
        ...

    @abstractmethod
    async def wait(self) -> int:
        """
        Wait for the tool process to exit. Returns the exit code.
        """
        ...

    @abstractmethod
    async def terminate(self, force: bool = False) -> None:
        """
        Terminate the tool process (SIGTERM, or SIGKILL if force=True).
        """
        ...

    # Optional hooks (default: no-op)

    async def on_start(self) -> None:
        """Called after the tool process has started."""
        pass

    async def on_stop(self, exit_code: int) -> None:
        """Called after the tool process has exited."""
        pass

    async def on_crash(self, exit_code: int) -> None:
        """Called if the tool process exits unexpectedly."""
        pass
```

---

## Event Model

```python
from dataclasses import dataclass, field
from typing import Any
import uuid

@dataclass
class ToolCallEvent:
    """Represents a single tool call intercepted from an AI agent."""

    # Unique ID for this event
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Session context
    session_id: str = ""

    # Tool information
    tool_name: str = ""          # e.g., "read_file", "bash", "write_file"
    arguments: dict[str, Any] = field(default_factory=dict)

    # Raw event data (for adapter-specific handling)
    raw: str = ""

    # Adapter that created this event
    adapter: str = ""            # e.g., "claude", "openai", "generic"

    # Computed fields (populated by interceptor)
    normalized_args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResult:
    """Result of executing an approved tool call."""

    event_id: str
    success: bool
    output: str = ""
    error: str = ""
```

---

## Adapter Registry

The adapter registry maps tool names to adapter classes:

```python
class AdapterRegistry:
    _registry: dict[str, type[ToolAdapter]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a tool adapter."""
        def decorator(adapter_class: type[ToolAdapter]) -> type[ToolAdapter]:
            cls._registry[name] = adapter_class
            return adapter_class
        return decorator

    @classmethod
    def get(cls, tool_name: str) -> type[ToolAdapter]:
        if tool_name in cls._registry:
            return cls._registry[tool_name]
        # Fall back to generic PTY adapter for unknown tools
        return GenericPTYAdapter

    @classmethod
    def list_supported(cls) -> list[str]:
        return list(cls._registry.keys())
```

---

## Claude Code Adapter

The Claude Code adapter handles Claude CLI's specific tool call protocol.

```python
@AdapterRegistry.register("claude")
class ClaudeAdapter(ToolAdapter):
    """
    Adapter for Claude Code (claude CLI).

    Claude Code emits tool calls as structured JSON events in its
    output stream when using --output-format stream-json or in
    hook-based interception mode.
    """

    tool_name = "claude"
    supported_versions = [">=1.0.0"]

    # Tool call event pattern in Claude's output stream
    # Claude Code emits tool_use blocks in its structured output
    TOOL_CALL_PATTERN = re.compile(
        r'\{"type":"tool_use","id":"[^"]+","name":"[^"]+","input":\{.*?\}\}',
        re.DOTALL
    )

    async def launch(self, args: list[str], env: dict[str, str], session_id: str) -> None:
        # Launch claude in PTY with stream output
        self._pty = await PTYProcess.spawn(
            ["claude", "--output-format", "stream-json", *args],
            env=self._sanitize_env(env),
        )

    async def tool_call_events(self) -> AsyncIterator[ToolCallEvent]:
        buffer = ""
        async for chunk in self._pty.read_stream():
            buffer += chunk
            # Relay non-tool-call output to user terminal
            while event_match := self.TOOL_CALL_PATTERN.search(buffer):
                # Output everything before this tool call
                pre_output = buffer[:event_match.start()]
                if pre_output:
                    await self._relay_to_terminal(pre_output)

                # Yield the tool call event
                raw_event = event_match.group(0)
                event = self._parse_tool_call(raw_event, session_id)

                # Suspend relay — yield the event
                yield event

                # Remove processed event from buffer
                buffer = buffer[event_match.end():]

        # Flush any remaining output
        if buffer:
            await self._relay_to_terminal(buffer)

    def _parse_tool_call(self, raw: str, session_id: str) -> ToolCallEvent:
        data = json.loads(raw)
        return ToolCallEvent(
            session_id=session_id,
            tool_name=data["name"],
            arguments=data["input"],
            raw=raw,
            adapter="claude",
        )

    async def allow_tool_call(self, event: ToolCallEvent) -> None:
        # Claude handles execution after receiving the allow signal
        # In stream-json mode, no injection needed — proceed is implicit
        # In hook mode, write allow response to Claude's hook pipe
        pass

    async def deny_tool_call(self, event: ToolCallEvent, reason: str) -> None:
        # Write a tool_result block indicating error
        error_response = json.dumps({
            "type": "tool_result",
            "tool_use_id": event.raw_id,
            "is_error": True,
            "content": f"Operation blocked by AtlasBridge: {reason}",
        })
        await self._pty.write(error_response + "\n")
```

---

## Generic PTY Adapter

For tools not explicitly supported, the generic PTY adapter wraps the tool transparently without intercepting tool calls. This provides PTY wrapping (terminal compatibility) without policy enforcement:

```python
class GenericPTYAdapter(ToolAdapter):
    """
    Generic PTY adapter for unsupported tools.

    Wraps the tool in a PTY for terminal compatibility.
    Does NOT intercept tool calls (no interception protocol known).
    All operations pass through directly.

    Warning: No policy enforcement for unsupported tools.
    """

    tool_name = "generic"
    supported_versions = []

    async def tool_call_events(self) -> AsyncIterator[ToolCallEvent]:
        # Generic adapter yields no tool call events
        # All I/O is relayed directly
        return
        yield  # makes this an async generator

    async def allow_tool_call(self, event: ToolCallEvent) -> None:
        pass  # Not called for generic adapter

    async def deny_tool_call(self, event: ToolCallEvent, reason: str) -> None:
        pass  # Not called for generic adapter
```

---

## Supported Tools (Phase Roadmap)

| Tool | Adapter | Phase | Interception Method |
|------|---------|-------|---------------------|
| Claude Code (`claude`) | `ClaudeAdapter` | Phase 2 | Stream JSON + hooks |
| OpenAI CLI (`openai`) | `OpenAIAdapter` | Phase 2 | Stream JSON output |
| Generic (any) | `GenericPTYAdapter` | Phase 2 | PTY only (no interception) |
| Custom Python agents | `PythonAgentAdapter` | Phase 3 | Function call hooks |
| WhatsApp integration | N/A (channel) | Phase 3 | Channel, not adapter |

---

## Adapter Detection

`atlasbridge run <tool>` auto-detects the correct adapter:

```python
def detect_adapter(tool_name: str) -> type[ToolAdapter]:
    # 1. Check if tool is registered
    adapter_class = AdapterRegistry.get(tool_name)

    # 2. Warn if falling back to generic
    if adapter_class is GenericPTYAdapter:
        logger.warning(
            "No specific adapter found for %s — using generic PTY adapter. "
            "Tool calls will NOT be intercepted.",
            tool_name,
        )

    return adapter_class
```

---

## Adding a New Adapter

To add support for a new AI tool:

1. Create `atlasbridge/bridge/adapters/<tool_name>.py`
2. Subclass `ToolAdapter`
3. Decorate with `@AdapterRegistry.register("<tool_name>")`
4. Implement all abstract methods
5. Add tests in `tests/unit/bridge/test_<tool_name>_adapter.py`
6. Document tool call event format in the adapter's docstring

The new adapter is immediately available as `atlasbridge run <tool_name>` with no changes to the core codebase.

---

## Adapter Versioning

Adapters declare `supported_versions` to handle breaking changes in upstream tools:

```python
@property
def supported_versions(self) -> list[str]:
    return [">=1.0.0,<2.0.0"]   # semver constraint
```

At `atlasbridge run` time, the adapter checks the tool's version and warns if the version is outside the supported range. The tool still runs but a compatibility warning is shown.
