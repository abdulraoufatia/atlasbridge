"""
BaseAdapter — abstract interface that every tool adapter must implement.

An adapter is responsible for:
  1. Launching a CLI tool inside a PTY supervisor
  2. Streaming output to the PromptDetector
  3. Injecting replies back into the CLI's stdin
  4. Normalising reply values to the format the CLI expects

Adapter registry:
  Use @AdapterRegistry.register("name") to register an adapter class.
  Retrieve with: AdapterRegistry.get("name")

Naming convention: <ToolName>Adapter (e.g. ClaudeCodeAdapter, OpenAIAdapter)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

ADAPTER_API_VERSION = "1.0.0"


class BaseAdapter(ABC):
    """
    Abstract CLI tool adapter.

    Each adapter knows how to:
    - Launch the specific CLI tool in a PTY
    - Detect prompts in its output stream
    - Inject the correct byte sequence for each PromptType

    Adapters must be stateless across sessions — session state lives in
    the Session model, not the adapter.
    """

    #: Short identifier used in config files and CLI output (e.g. "claude")
    tool_name: str = ""

    #: Human-readable description shown in `atlasbridge adapter list`
    description: str = ""

    #: Minimum supported version of the wrapped tool (semver string or "")
    min_tool_version: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def start_session(
        self,
        session_id: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str = "",
    ) -> None:
        """
        Launch the CLI tool and open the PTY session.

        Args:
            session_id: Unique session identifier.
            command:     argv to exec (e.g. ["claude", "--no-browser"]).
            env:         Additional environment variables to inject.
            cwd:         Working directory for the child process.
        """

    @abstractmethod
    async def terminate_session(self, session_id: str, timeout_s: float = 5.0) -> None:
        """Terminate the CLI tool process gracefully, then forcibly."""

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    @abstractmethod
    async def read_stream(self, session_id: str) -> bytes:
        """
        Return the next chunk of raw PTY output bytes.

        Blocks until data is available or the process exits.
        Returns b"" on EOF.
        """

    @abstractmethod
    async def inject_reply(self, session_id: str, value: str, prompt_type: str) -> None:
        """
        Inject *value* into the CLI's stdin.

        Args:
            session_id:  Target session.
            value:       Normalised reply string (e.g. "y", "2", "my text").
            prompt_type: PromptType string (e.g. "yes_no") for value encoding.
        """

    # ------------------------------------------------------------------
    # Prompt detection helpers
    # ------------------------------------------------------------------

    @abstractmethod
    async def await_input_state(self, session_id: str) -> bool:
        """
        Return True if the OS-level TTY is blocked on read (Signal 2).

        This is the TTY-blocked-on-read heuristic. Implementation varies
        by platform (ioctl/select on POSIX, ConPTY state on Windows).
        """

    # ------------------------------------------------------------------
    # Context snapshotting (optional)
    # ------------------------------------------------------------------

    def snapshot_context(self, session_id: str) -> dict[str, Any]:
        """
        Return a dict of contextual information about the current session.

        Used to enrich prompt events with adapter-specific metadata.
        Default implementation returns an empty dict.
        """
        return {}

    # ------------------------------------------------------------------
    # Detector access
    # ------------------------------------------------------------------

    def get_detector(self, session_id: str) -> Any:
        """
        Return the PromptDetector for *session_id*, or None if not tracked.

        The DaemonManager calls this to share the same detector instance
        that inject_reply() uses for echo suppression.  Adapters that
        maintain a per-session detector dict should override this.

        Returns:
            PromptDetector instance, or None.
        """
        return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def healthcheck(self) -> dict[str, Any]:
        """
        Return health status for this adapter.

        Called by `atlasbridge doctor`. Default returns {"status": "ok"}.
        """
        return {"status": "ok", "adapter": self.tool_name}


class _AdapterRegistryMeta(type):
    """Metaclass that maintains the adapter registry."""

    _registry: dict[str, type[BaseAdapter]] = {}


class AdapterRegistry(metaclass=_AdapterRegistryMeta):
    """Global registry of available CLI adapters."""

    @classmethod
    def register(cls, name: str) -> Any:
        """Decorator: @AdapterRegistry.register("claude")"""

        def decorator(adapter_cls: type[BaseAdapter]) -> type[BaseAdapter]:
            cls._registry[name] = adapter_cls
            return adapter_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseAdapter]:
        if name not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys())) or "(none)"
            raise KeyError(f"Unknown adapter: {name!r}. Available: {available}")
        return cls._registry[name]

    @classmethod
    def list_all(cls) -> dict[str, type[BaseAdapter]]:
        return dict(cls._registry)
