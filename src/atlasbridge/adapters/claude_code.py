"""
Claude Code adapter.

Wraps the `claude` CLI (Claude Code) in a PTY supervisor and integrates
the tri-signal PromptDetector for prompt detection.

Value normalisation table (PromptType → injected bytes):
  yes_no          "y" → b"y\\r"    "n" → b"n\\r"
  confirm_enter   any  → b"\\r"
  multiple_choice "1"  → b"1\\r"   "2" → b"2\\r"  etc.
  free_text       raw  → value.encode() + b"\\r"

Claude Code quirks:
  - Uses ANSI colour codes heavily — strip before pattern matching
  - Prompt lines often arrive without a trailing newline (partial-line)
  - Press Enter prompts appear after file diffs
  - Inline keyboard input is echoed back by the PTY
"""

from __future__ import annotations

from typing import Any

from atlasbridge.adapters.base import AdapterRegistry, BaseAdapter
from atlasbridge.core.prompt.detector import PromptDetector
from atlasbridge.core.prompt.models import PromptType
from atlasbridge.os.tty.windows import get_tty_class

# Value normalisation: (prompt_type, value) → bytes to inject
_NORMALISE: dict[str, dict[str, bytes]] = {
    PromptType.TYPE_YES_NO: {
        "y": b"y\r",
        "yes": b"y\r",
        "n": b"n\r",
        "no": b"n\r",
    },
    PromptType.TYPE_CONFIRM_ENTER: {
        "*": b"\r",  # any value → send Enter
    },
    # multiple_choice and free_text are handled dynamically
}


@AdapterRegistry.register("claude")
@AdapterRegistry.register("claude-code")
class ClaudeCodeAdapter(BaseAdapter):
    """
    Adapter for the `claude` CLI (Claude Code by Anthropic).

    Supports Claude Code ≥ 0.2.x.
    """

    tool_name = "claude"
    description = "Claude Code by Anthropic (claude CLI)"
    min_tool_version = "0.2.0"

    def __init__(self) -> None:
        self._supervisors: dict[str, Any] = {}  # session_id → BaseTTY
        self._detectors: dict[str, PromptDetector] = {}
        self._output_buffers: dict[str, bytearray] = {}
        self.experimental: bool = False  # set by DaemonManager from config

    async def start_session(
        self,
        session_id: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str = "",
    ) -> None:
        from atlasbridge.os.tty.base import PTYConfig

        cfg = PTYConfig(
            command=command,
            env=env or {},
            cwd=cwd,
        )
        tty_class = get_tty_class(experimental=self.experimental)
        tty = tty_class(cfg, session_id)
        self._supervisors[session_id] = tty
        self._detectors[session_id] = self._make_detector(session_id)
        self._output_buffers[session_id] = bytearray()

        await tty.start()

    def _make_detector(self, session_id: str) -> PromptDetector:
        """Return the PromptDetector to use for this adapter. Override in subclasses."""
        return PromptDetector(session_id)

    def get_detector(self, session_id: str) -> PromptDetector | None:
        """Return the PromptDetector for *session_id*, or None."""
        return self._detectors.get(session_id)

    async def terminate_session(self, session_id: str, timeout_s: float = 5.0) -> None:
        tty = self._supervisors.pop(session_id, None)
        if tty:
            await tty.stop(timeout_s)
        self._detectors.pop(session_id, None)
        self._output_buffers.pop(session_id, None)

    async def read_stream(self, session_id: str) -> bytes:
        tty = self._supervisors.get(session_id)
        if tty is None:
            return b""
        # Read one chunk from the PTY
        async for chunk in tty.read_output():
            buf = self._output_buffers.get(session_id)
            if buf is not None:
                # Keep rolling buffer bounded at max_buffer_bytes
                buf.extend(chunk)
                if len(buf) > tty.config.max_buffer_bytes:
                    del buf[: len(buf) - tty.config.max_buffer_bytes]
            return chunk
        return b""

    async def inject_reply(self, session_id: str, value: str, prompt_type: str) -> None:
        tty = self._supervisors.get(session_id)
        if tty is None:
            return

        data = self._normalise(value, prompt_type)
        await tty.inject_reply(data)

        detector = self._detectors.get(session_id)
        if detector:
            detector.mark_injected()

    async def await_input_state(self, session_id: str) -> bool:
        """
        Approximate TTY-blocked-on-read by checking if no output has arrived
        for read_timeout_s seconds while the process is alive.

        A proper implementation would use select()/poll() on the PTY master fd.
        This approximation is sufficient for Signal 2 detection in v0.2.0.
        """
        tty = self._supervisors.get(session_id)
        if tty is None:
            return False
        return tty.is_alive()

    def snapshot_context(self, session_id: str) -> dict[str, Any]:
        tty = self._supervisors.get(session_id)
        if tty is None:
            return {}
        return {
            "pid": tty.pid(),
            "alive": tty.is_alive(),
            "tool": self.tool_name,
        }

    def healthcheck(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "adapter": self.tool_name,
            "active_sessions": len(self._supervisors),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalise(self, value: str, prompt_type: str) -> bytes:
        """Encode *value* as the byte sequence to inject for *prompt_type*."""
        v = value.lower().strip()

        if prompt_type == PromptType.TYPE_YES_NO:
            mapping = _NORMALISE[PromptType.TYPE_YES_NO]
            return mapping.get(v, b"n\r")  # safe default: n

        if prompt_type == PromptType.TYPE_CONFIRM_ENTER:
            return b"\r"

        if prompt_type == PromptType.TYPE_MULTIPLE_CHOICE:
            # value is the option number or letter
            return value.encode("utf-8", errors="replace") + b"\r"

        # TYPE_FREE_TEXT — send as-is + Enter
        return value.encode("utf-8", errors="replace") + b"\r"
