"""
ExpertAgentEngine — orchestrates the Expert Agent state machine.

State flow per turn:
  READY → INTAKE → PLAN → [GATE →] EXECUTE → SYNTHESISE → RESPOND → READY

The engine drives the AgentStateMachine and persists all operations
to the System of Record via SystemOfRecordWriter.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from atlasbridge.core.agent.state import AgentState, AgentStateMachine
from atlasbridge.providers.base import Message, ToolCall, ToolResult

if TYPE_CHECKING:
    from atlasbridge.channels.base import BaseChannel
    from atlasbridge.core.agent.models import AgentProfile
    from atlasbridge.core.agent.sor import SystemOfRecordWriter
    from atlasbridge.core.policy.model import Policy
    from atlasbridge.core.policy.model_v1 import PolicyV1
    from atlasbridge.core.session.manager import SessionManager
    from atlasbridge.core.store.database import Database
    from atlasbridge.providers.base import BaseProvider
    from atlasbridge.tools.executor import ToolExecutor
    from atlasbridge.tools.registry import ToolRegistry

logger = structlog.get_logger()

_MAX_TOOL_ROUNDS = 10
_STREAM_EDIT_INTERVAL_S = 1.0
_DANGEROUS_RISK_LEVELS = frozenset({"dangerous"})


class ExpertAgentEngine:
    """Orchestrates a single Expert Agent session with SoR persistence."""

    def __init__(
        self,
        provider: BaseProvider,
        channel: BaseChannel,
        session_id: str,
        session_manager: SessionManager,
        sor: SystemOfRecordWriter,
        db: Database,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        policy: Policy | PolicyV1 | None = None,
        system_prompt: str = "",
        max_history: int = 50,
        profile: AgentProfile | None = None,
    ) -> None:
        self._provider = provider
        self._channel = channel
        self._session_id = session_id
        self._sessions = session_manager
        self._sor = sor
        self._db = db
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._policy = policy
        self._system_prompt = system_prompt
        self._max_history = max_history
        self._profile = profile
        self._history: list[Message] = []
        self._state_machine = AgentStateMachine(
            session_id=session_id,
            trace_id=sor.trace_id,
        )
        # Initialise to READY
        self._state_machine.transition(AgentState.READY, "engine_init")

    @property
    def state(self) -> AgentState:
        return self._state_machine.state

    def get_state(self) -> dict[str, object]:
        return self._state_machine.to_dict()

    async def handle_message(self, text: str) -> None:
        """Process a user message — drives the full state machine cycle."""
        if not self._state_machine.can_accept_input:
            logger.warning(
                "agent_message_rejected",
                state=str(self._state_machine.state),
                session_id=self._session_id[:8],
            )
            await self._channel.notify(
                f"Cannot accept input in state {self._state_machine.state}. "
                f"Current state requires resolution first.",
                session_id=self._session_id,
            )
            return

        # -- INTAKE ---------------------------------------------------------
        self._state_machine.transition(AgentState.INTAKE, "user_message")
        turn_id = self._sor.record_turn(role="user", content=text, state="intake")
        self._state_machine.active_turn_id = turn_id

        self._history.append(Message(role="user", content=text))
        self._trim_history()

        logger.info(
            "agent_intake",
            session_id=self._session_id[:8],
            turn_id=turn_id[:8],
            text_len=len(text),
        )

        # -- PLAN -----------------------------------------------------------
        self._state_machine.transition(AgentState.PLAN, "generating_plan")
        tools = self._get_tool_definitions()

        response = await self._stream_response(tools)

        if not response.tool_calls:
            # No tools needed — direct answer
            self._history.append(response)
            self._sor.update_turn(turn_id, state="respond")

            # Record assistant turn
            self._sor.record_turn(role="assistant", content=response.content, state="respond")
            self._sor.record_outcome(
                turn_id=turn_id,
                status="success",
                summary=response.content[:500],
            )

            self._state_machine.transition(AgentState.RESPOND, "direct_answer")
            self._state_machine.transition(AgentState.READY, "turn_complete")
            self._state_machine.active_turn_id = ""
            return

        # Tools requested — build plan
        plan_steps = [
            {"tool": tc.name, "arguments_preview": str(tc.arguments)[:200]}
            for tc in response.tool_calls
        ]
        risk_level = self._assess_plan_risk(response.tool_calls)

        plan_id = self._sor.record_plan(
            turn_id=turn_id,
            description=response.content or "Tool execution plan",
            steps=plan_steps,
            risk_level=risk_level,
        )
        self._state_machine.active_plan_id = plan_id

        # -- GATE (if needed) -----------------------------------------------
        needs_gate = risk_level == "high" or self._has_dangerous_tools(response.tool_calls)

        if needs_gate:
            self._state_machine.transition(AgentState.GATE, "dangerous_tools_detected")
            self._sor.record_decision(
                turn_id=turn_id,
                decision_type="plan_gate",
                action="escalate",
                plan_id=plan_id,
                risk_score=self._risk_score(risk_level),
                explanation=f"Plan requires approval: risk={risk_level}",
            )

            # Notify user of pending approval
            step_summary = "\n".join(f"  {i + 1}. {s['tool']}" for i, s in enumerate(plan_steps))
            await self._channel.notify(
                f"Plan requires approval (risk: {risk_level}):\n{step_summary}\n\n"
                f"Plan ID: {plan_id[:8]}\n"
                f"Reply 'approve' or 'deny'.",
                session_id=self._session_id,
            )
            # Store response for later execution
            self._history.append(response)
            return

        # -- EXECUTE (auto-approved) ----------------------------------------
        self._sor.record_decision(
            turn_id=turn_id,
            decision_type="auto_approve",
            action="allow",
            plan_id=plan_id,
            risk_score=self._risk_score(risk_level),
            explanation=f"Auto-approved: risk={risk_level}",
        )
        self._sor.resolve_plan(plan_id, status="approved", resolved_by="policy")

        self._history.append(response)
        await self._execute_tools(turn_id, plan_id, response.tool_calls)

    async def handle_approval(self, plan_id: str, approved: bool) -> None:
        """Handle human approval/denial of a gated plan."""
        if not self._state_machine.is_gated:
            logger.warning("agent_approval_not_gated", state=str(self._state_machine.state))
            return

        turn_id = self._state_machine.active_turn_id

        if approved:
            self._sor.resolve_plan(plan_id, status="approved", resolved_by="human")
            self._sor.record_decision(
                turn_id=turn_id,
                decision_type="plan_gate",
                action="allow",
                plan_id=plan_id,
                explanation="Approved by human operator",
            )

            # Re-extract tool calls from the last assistant message
            tool_calls = self._extract_pending_tool_calls()
            if tool_calls:
                await self._execute_tools(turn_id, plan_id, tool_calls)
            else:
                self._state_machine.transition(AgentState.RESPOND, "no_tools_after_approve")
                await self._channel.notify(
                    "Plan approved but no tools to execute.",
                    session_id=self._session_id,
                )
                self._state_machine.transition(AgentState.READY, "turn_complete")
        else:
            self._sor.resolve_plan(plan_id, status="denied", resolved_by="human")
            self._sor.record_decision(
                turn_id=turn_id,
                decision_type="plan_gate",
                action="deny",
                plan_id=plan_id,
                explanation="Denied by human operator",
            )
            self._sor.record_outcome(
                turn_id=turn_id,
                status="denied",
                summary="Plan denied by human operator",
            )

            self._state_machine.transition(AgentState.RESPOND, "plan_denied")
            await self._channel.notify(
                f"Plan {plan_id[:8]} denied. Ready for next input.",
                session_id=self._session_id,
            )
            self._state_machine.transition(AgentState.READY, "turn_complete")
            self._state_machine.active_turn_id = ""
            self._state_machine.active_plan_id = ""

    async def _execute_tools(self, turn_id: str, plan_id: str, tool_calls: list[ToolCall]) -> None:
        """Execute tool calls and drive through EXECUTE → SYNTHESISE → RESPOND."""
        self._state_machine.transition(AgentState.EXECUTE, "executing_tools")
        self._sor.resolve_plan(plan_id, status="executing", resolved_by="policy")

        total_start = time.monotonic()
        all_results: list[ToolResult] = []
        tool_run_count = 0

        for _round in range(_MAX_TOOL_ROUNDS):
            round_results: list[ToolResult] = []

            for tc in tool_calls:
                start = time.monotonic()
                result = await self._execute_single_tool(tc)
                duration_ms = (time.monotonic() - start) * 1000

                self._sor.record_tool_run(
                    turn_id=turn_id,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    result=result.content[:5000],
                    is_error=result.is_error,
                    duration_ms=duration_ms,
                    plan_id=plan_id,
                )
                round_results.append(result)
                tool_run_count += 1

            all_results.extend(round_results)
            self._history.append(Message(role="tool", tool_results=round_results))

            # Get next LLM response (may include more tool calls)
            tools = self._get_tool_definitions()
            response = await self._stream_response(tools)
            self._history.append(response)

            if not response.tool_calls:
                break
            tool_calls = response.tool_calls

        total_duration_ms = (time.monotonic() - total_start) * 1000

        # -- SYNTHESISE -----------------------------------------------------
        self._state_machine.transition(AgentState.SYNTHESISE, "aggregating_results")
        self._sor.resolve_plan(plan_id, status="completed", resolved_by="policy")

        # Get the final response content
        final_content = ""
        for msg in reversed(self._history):
            if msg.role == "assistant" and msg.content:
                final_content = msg.content
                break

        self._sor.record_turn(role="assistant", content=final_content, state="respond")
        self._sor.record_outcome(
            turn_id=turn_id,
            status="success",
            summary=final_content[:500],
            tool_runs_count=tool_run_count,
            total_duration_ms=total_duration_ms,
        )

        # -- RESPOND --------------------------------------------------------
        self._state_machine.transition(AgentState.RESPOND, "delivering_response")
        self._state_machine.transition(AgentState.READY, "turn_complete")
        self._state_machine.active_turn_id = ""
        self._state_machine.active_plan_id = ""

        logger.info(
            "agent_turn_complete",
            session_id=self._session_id[:8],
            turn_id=turn_id[:8],
            tool_runs=tool_run_count,
            duration_ms=round(total_duration_ms),
        )

    async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call."""
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
            logger.warning("agent_tool_error", tool=tool_call.name, error=str(exc))
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"Tool error: {exc}",
                is_error=True,
            )

    async def _stream_response(self, tools: list | None) -> Message:
        """Stream the LLM response to the channel, editing in-place."""

        msg_id = await self._channel.send_output_editable("...", session_id=self._session_id)

        accumulated_text = ""
        final_tool_calls: list[ToolCall] = []
        last_edit_time = 0.0
        usage: dict[str, int] = {}

        async for chunk in self._provider.chat_stream(  # type: ignore[attr-defined]
            messages=self._history,
            tools=tools,
            system=self._system_prompt,
        ):
            if chunk.text:
                accumulated_text += chunk.text
                now = time.monotonic()
                if msg_id and (now - last_edit_time) >= _STREAM_EDIT_INTERVAL_S:
                    try:
                        await self._channel.edit_prompt_message(
                            msg_id, accumulated_text, session_id=self._session_id
                        )
                        last_edit_time = now
                    except Exception:  # noqa: BLE001
                        pass
            if chunk.is_final:
                final_tool_calls = chunk.tool_calls
                usage = chunk.usage

        if msg_id and accumulated_text:
            try:
                await self._channel.edit_prompt_message(
                    msg_id, accumulated_text, session_id=self._session_id
                )
            except Exception:  # noqa: BLE001
                pass

        if msg_id and not accumulated_text and final_tool_calls:
            tool_names = ", ".join(tc.name for tc in final_tool_calls)
            try:
                await self._channel.edit_prompt_message(
                    msg_id, f"Using tools: {tool_names}", session_id=self._session_id
                )
            except Exception:  # noqa: BLE001
                pass

        return Message(
            role="assistant",
            content=accumulated_text,
            tool_calls=final_tool_calls,
            metadata={"usage": usage},
        )

    def _get_tool_definitions(self) -> list | None:
        if self._tool_registry is None:
            return None
        return self._tool_registry.to_definitions()

    def _trim_history(self) -> None:
        if len(self._history) > self._max_history:
            excess = len(self._history) - self._max_history
            self._history = self._history[excess:]

    def _assess_plan_risk(self, tool_calls: list[ToolCall]) -> str:
        """Assess the risk level of a set of tool calls."""
        if self._tool_registry is None:
            return "low"
        for tc in tool_calls:
            tool = self._tool_registry.get(tc.name)
            if tool and tool.risk_level in _DANGEROUS_RISK_LEVELS:
                return "high"
        has_moderate = any(
            (t := self._tool_registry.get(tc.name)) and t.risk_level == "moderate"
            for tc in tool_calls
        )
        return "medium" if has_moderate else "low"

    def _has_dangerous_tools(self, tool_calls: list[ToolCall]) -> bool:
        if self._tool_registry is None:
            return False
        return any(
            (t := self._tool_registry.get(tc.name)) and t.risk_level in _DANGEROUS_RISK_LEVELS
            for tc in tool_calls
        )

    def _extract_pending_tool_calls(self) -> list[ToolCall]:
        """Extract tool calls from the last assistant message in history."""
        for msg in reversed(self._history):
            if msg.role == "assistant" and msg.tool_calls:
                return msg.tool_calls
        return []

    @staticmethod
    def _risk_score(level: str) -> int:
        return {"low": 10, "medium": 40, "high": 80}.get(level, 0)
