"""
ChatEngine — orchestrates the LLM conversation loop.

The engine manages:
  - Conversation history (bounded rolling window)
  - Sending user messages to the LLM provider
  - Streaming responses back to the channel (edit-in-place on Telegram)
  - Processing tool_use requests through the policy engine
  - Tool execution with policy governance
  - Audit logging for all decisions

Data flow::

    user message (from Telegram)
      -> ChatEngine.handle_message()
        -> provider.chat_stream(history, tools)
          -> [stream text to channel via edit-in-place]
          -> if tool_calls:
               for each tool_call:
                 policy_decision = evaluate(policy, ...)
                 if auto_reply: execute tool, add result
                 if require_human: escalate to channel, PAUSE
                 if deny: add denial to messages
               -> recurse: provider.chat_stream(history + tool_results)
          -> done: append final message to history
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from atlasbridge.providers.base import (
    Message,
    ToolCall,
    ToolDefinition,
    ToolResult,
)

if TYPE_CHECKING:
    from atlasbridge.channels.base import BaseChannel
    from atlasbridge.core.policy.model import Policy
    from atlasbridge.core.policy.model_v1 import PolicyV1
    from atlasbridge.core.session.manager import SessionManager
    from atlasbridge.providers.base import BaseProvider
    from atlasbridge.tools.executor import ToolExecutor
    from atlasbridge.tools.registry import ToolRegistry

logger = structlog.get_logger()

_MAX_TOOL_ROUNDS = 10  # Safety limit on consecutive tool-use rounds
_STREAM_EDIT_INTERVAL_S = 1.0  # Edit the channel message at most once per second


class ChatEngine:
    """Orchestrates a single chat session between a user and an LLM provider."""

    def __init__(
        self,
        provider: BaseProvider,
        channel: BaseChannel,
        session_id: str,
        session_manager: SessionManager,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        policy: Policy | PolicyV1 | None = None,
        system_prompt: str = "",
        max_history: int = 50,
    ) -> None:
        self._provider = provider
        self._channel = channel
        self._session_id = session_id
        self._sessions = session_manager
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._policy = policy
        self._system_prompt = system_prompt or self._default_system_prompt()
        self._max_history = max_history
        self._history: list[Message] = []
        self._pending_approval: dict[str, _PendingToolApproval] = {}

    async def handle_message(self, text: str, channel_identity: str = "") -> None:
        """Process a user message from the channel."""
        self._history.append(Message(role="user", content=text))
        self._trim_history()

        logger.info(
            "chat_message_received",
            session_id=self._session_id[:8],
            text_len=len(text),
        )

        await self._conversation_turn()

    async def handle_tool_approval(self, tool_call_id: str, approved: bool) -> None:
        """Handle human approval/denial of a pending tool call."""
        pending = self._pending_approval.pop(tool_call_id, None)
        if pending is None:
            return

        if approved:
            result = await self._execute_tool(pending.tool_call)
        else:
            result = ToolResult(
                tool_call_id=tool_call_id,
                content="Tool execution denied by human operator.",
                is_error=True,
            )

        # Add the tool result and continue the conversation
        self._history.append(Message(role="tool", tool_results=[result]))
        await self._conversation_turn()

    async def _conversation_turn(self) -> None:
        """Run one LLM turn: stream response, handle tool calls, recurse if needed."""
        tools = self._get_tool_definitions()

        for _round_num in range(_MAX_TOOL_ROUNDS):
            response = await self._stream_response(tools)

            if not response.tool_calls:
                # No tool calls — conversation turn complete
                self._history.append(response)
                self._trim_history()
                return

            # Process tool calls
            self._history.append(response)
            all_results: list[ToolResult] = []
            has_pending = False

            for tc in response.tool_calls:
                decision = await self._evaluate_tool_call(tc)

                if decision == "allow":
                    result = await self._execute_tool(tc)
                    all_results.append(result)
                elif decision == "deny":
                    all_results.append(
                        ToolResult(
                            tool_call_id=tc.id,
                            content=f"Tool '{tc.name}' denied by policy.",
                            is_error=True,
                        )
                    )
                elif decision == "escalate":
                    await self._escalate_tool_call(tc)
                    has_pending = True

            if has_pending:
                # Pause — waiting for human approval
                if all_results:
                    self._history.append(Message(role="tool", tool_results=all_results))
                return

            # All tools resolved — add results and recurse
            self._history.append(Message(role="tool", tool_results=all_results))
            self._trim_history()

        logger.warning(
            "chat_max_tool_rounds",
            session_id=self._session_id[:8],
            max_rounds=_MAX_TOOL_ROUNDS,
        )
        await self._channel.notify(
            "Reached maximum tool-use rounds. Conversation paused.",
            session_id=self._session_id,
        )

    async def _stream_response(self, tools: list[ToolDefinition] | None) -> Message:
        """Stream the LLM response to the channel, editing the message in-place."""
        # Send initial "thinking" indicator
        msg_id = await self._channel.send_output_editable(
            "...",
            session_id=self._session_id,
        )

        accumulated_text = ""
        final_tool_calls: list[ToolCall] = []
        last_edit_time = 0.0
        usage: dict[str, int] = {}

        async for chunk in self._provider.chat_stream(
            messages=self._history,
            tools=tools,
            system=self._system_prompt,
        ):
            if chunk.text:
                accumulated_text += chunk.text

                # Edit-in-place at most once per second for good UX
                now = time.monotonic()
                if msg_id and (now - last_edit_time) >= _STREAM_EDIT_INTERVAL_S:
                    try:
                        await self._channel.edit_prompt_message(
                            msg_id, accumulated_text, session_id=self._session_id
                        )
                        last_edit_time = now
                    except Exception:  # noqa: BLE001
                        pass  # Best-effort edit

            if chunk.is_final:
                final_tool_calls = chunk.tool_calls
                usage = chunk.usage

        # Final edit with complete text
        if msg_id and accumulated_text:
            try:
                await self._channel.edit_prompt_message(
                    msg_id, accumulated_text, session_id=self._session_id
                )
            except Exception:  # noqa: BLE001
                pass

        # If no text was streamed but we got tool calls, update the message
        if msg_id and not accumulated_text and final_tool_calls:
            tool_names = ", ".join(tc.name for tc in final_tool_calls)
            try:
                await self._channel.edit_prompt_message(
                    msg_id,
                    f"Using tools: {tool_names}",
                    session_id=self._session_id,
                )
            except Exception:  # noqa: BLE001
                pass

        return Message(
            role="assistant",
            content=accumulated_text,
            tool_calls=final_tool_calls,
            metadata={"usage": usage},
        )

    async def _evaluate_tool_call(self, tool_call: ToolCall) -> str:
        """Evaluate a tool call against the policy. Returns 'allow', 'deny', or 'escalate'."""
        if self._tool_executor is None:
            return "deny"

        if self._policy is None:
            # No policy loaded — escalate everything
            return "escalate"

        from atlasbridge.core.policy.evaluator import evaluate

        decision = evaluate(
            policy=self._policy,
            prompt_text=f"tool_use: {tool_call.name}({tool_call.arguments})",
            prompt_type="tool_use",
            confidence="high",
            prompt_id=tool_call.id,
            session_id=self._session_id,
            tool_id=self._provider.provider_name,
        )

        action_type = decision.action_type
        if action_type == "auto_reply":
            return "allow"
        elif action_type == "deny":
            return "deny"
        else:
            # require_human, notify_only, or no match → escalate
            return "escalate"

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool and return the result."""
        if self._tool_executor is None:
            return ToolResult(
                tool_call_id=tool_call.id,
                content="No tool executor available.",
                is_error=True,
            )

        try:
            result_text = await self._tool_executor.execute(tool_call.name, tool_call.arguments)
            return ToolResult(tool_call_id=tool_call.id, content=result_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tool_execution_error",
                tool=tool_call.name,
                error=str(exc),
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Tool error: {exc}",
                is_error=True,
            )

    async def _escalate_tool_call(self, tool_call: ToolCall) -> None:
        """Send a tool approval request to the channel."""
        self._pending_approval[tool_call.id] = _PendingToolApproval(
            tool_call=tool_call,
            created_at=time.monotonic(),
        )

        args_preview = str(tool_call.arguments)[:200]
        await self._channel.notify(
            f"LLM wants to use tool: {tool_call.name}\n"
            f"Arguments: {args_preview}\n\n"
            f"Reply 'yes' to approve or 'no' to deny.",
            session_id=self._session_id,
        )

    def _get_tool_definitions(self) -> list[ToolDefinition] | None:
        """Get tool definitions from the registry, if available."""
        if self._tool_registry is None:
            return None
        return self._tool_registry.to_definitions()

    def _trim_history(self) -> None:
        """Keep history within bounds."""
        if len(self._history) > self._max_history:
            # Keep system-level context by trimming from the start
            excess = len(self._history) - self._max_history
            self._history = self._history[excess:]

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "You are a helpful AI assistant accessed via AtlasBridge. "
            "You can use tools to help the user when available. "
            "Be concise and direct in your responses."
        )


class _PendingToolApproval:
    """Tracks a tool call awaiting human approval."""

    __slots__ = ("tool_call", "created_at")

    def __init__(self, tool_call: ToolCall, created_at: float) -> None:
        self.tool_call = tool_call
        self.created_at = created_at
