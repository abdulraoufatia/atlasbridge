"""
InteractionExecutor — handles injection, advance verification, retry, and escalation.

The executor delegates actual PTY injection to the adapter's existing
``inject_reply()`` method, which normalises values and appends ``\\r``.
It then optionally verifies that the CLI produced new output (advance
verification) and retries or escalates if the CLI appears stalled.

For chat mode (no active prompt), the executor injects directly into
the PTY supervisor's stdin.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from atlasbridge.core.interaction.plan import InteractionPlan
from atlasbridge.core.prompt.detector import ECHO_SUPPRESS_MS

if TYPE_CHECKING:
    from atlasbridge.adapters.base import BaseAdapter
    from atlasbridge.core.prompt.detector import PromptDetector
    from atlasbridge.core.prompt.models import PromptEvent

logger = structlog.get_logger()

# Polling interval for advance check (seconds)
_POLL_INTERVAL_S = 0.2


@dataclass
class InjectionResult:
    """Outcome of an injection attempt."""

    success: bool
    injected_value: str  # Redacted for password prompts
    cli_advanced: bool | None = None  # True/False/None (not checked)
    retries_used: int = 0
    escalated: bool = False
    feedback_message: str = ""  # Human-readable feedback for the channel


class InteractionExecutor:
    """
    Executes an InteractionPlan by injecting into the adapter and
    verifying advancement.

    Dependencies are injected at construction time for testability.
    """

    def __init__(
        self,
        adapter: BaseAdapter,
        session_id: str,
        detector: PromptDetector,
        notify_fn: Callable[[str], Awaitable[None]],
        dry_run: bool = False,
    ) -> None:
        self._adapter = adapter
        self._session_id = session_id
        self._detector = detector
        self._notify_fn = notify_fn
        self._dry_run = dry_run

    async def execute(
        self,
        plan: InteractionPlan,
        value: str,
        prompt_type: str,
        event: PromptEvent | None = None,
    ) -> InjectionResult:
        """
        Execute an interaction plan.

        1. Inject the value into the PTY (via adapter.inject_reply)
        2. Optionally verify that the CLI advanced (new output appeared)
        3. Retry if the CLI stalled and retries are allowed
        4. Escalate if retries are exhausted

        Args:
            plan:        The InteractionPlan dictating behaviour.
            value:       The reply value to inject.
            prompt_type: The PromptType string for adapter normalisation.
            event:       The original PromptEvent (for logging context).
        """
        display_value = "[REDACTED]" if plan.suppress_value else value
        retries_used = 0

        log = logger.bind(
            session_id=self._session_id[:8],
            interaction_class=plan.interaction_class,
            suppress_value=plan.suppress_value,
        )

        if self._dry_run:
            log.info(
                "dry_run_skip_injection",
                would_inject=display_value,
                prompt_type=prompt_type,
            )
            return InjectionResult(
                success=True,
                injected_value=display_value,
                cli_advanced=None,
                feedback_message=f"[DRY RUN] Would inject: {display_value}",
            )

        for attempt in range(1 + plan.max_retries):
            pre_inject_time = self._detector.last_output_time

            try:
                await self._adapter.inject_reply(
                    session_id=self._session_id,
                    value=value,
                    prompt_type=prompt_type,
                )
            except Exception as exc:  # noqa: BLE001
                log.error("injection_failed", attempt=attempt + 1, error=str(exc))
                return InjectionResult(
                    success=False,
                    injected_value=display_value,
                    feedback_message=f"Injection failed: {exc}",
                )

            # Build immediate feedback message
            feedback = plan.display_template.format(value=display_value)

            if not plan.verify_advance:
                log.info("injection_ok_no_verify", attempt=attempt + 1)
                return InjectionResult(
                    success=True,
                    injected_value=display_value,
                    cli_advanced=None,
                    retries_used=retries_used,
                    feedback_message=feedback,
                )

            # Verify that the CLI produced new output
            advanced = await self._check_advance(plan, pre_inject_time)

            if advanced:
                full_feedback = f"{feedback}\n{plan.feedback_on_advance}"
                log.info("injection_advanced", attempt=attempt + 1)
                return InjectionResult(
                    success=True,
                    injected_value=display_value,
                    cli_advanced=True,
                    retries_used=retries_used,
                    feedback_message=full_feedback.strip(),
                )

            # CLI did not advance
            if attempt < plan.max_retries:
                retries_used += 1
                stall_msg = plan.feedback_on_stall.format(value=display_value)
                log.warning("injection_stalled_retrying", attempt=attempt + 1)
                await self._notify_fn(stall_msg)
                await asyncio.sleep(plan.retry_delay_s)
            else:
                # Retries exhausted
                if plan.escalate_on_exhaustion:
                    escalation_msg = plan.escalation_template.format(
                        value=display_value,
                        retries=retries_used,
                    )
                    log.warning("injection_escalating", attempts=attempt + 1)
                    await self._notify_fn(escalation_msg)
                    return InjectionResult(
                        success=False,
                        injected_value=display_value,
                        cli_advanced=False,
                        retries_used=retries_used,
                        escalated=True,
                        feedback_message=escalation_msg,
                    )
                else:
                    stall_msg = plan.feedback_on_stall.format(value=display_value)
                    return InjectionResult(
                        success=True,  # Best effort — we injected, CLI didn't advance
                        injected_value=display_value,
                        cli_advanced=False,
                        retries_used=retries_used,
                        feedback_message=f"{feedback}\n{stall_msg}".strip(),
                    )

        # Should not reach here, but guard
        return InjectionResult(
            success=False,
            injected_value=display_value,
            feedback_message="Unexpected: injection loop completed without result",
        )

    async def execute_chat_input(self, value: str) -> InjectionResult:
        """
        Direct stdin injection for chat mode (no active prompt).

        Writes value + \\r to the PTY supervisor and triggers echo
        suppression. No advance verification.
        """
        log = logger.bind(session_id=self._session_id[:8])

        if self._dry_run:
            log.info("dry_run_skip_chat_input", value_length=len(value))
            return InjectionResult(
                success=True,
                injected_value=value,
                cli_advanced=None,
                feedback_message=f"[DRY RUN] Would send chat: {value!r}",
            )

        try:
            # Access the adapter's TTY supervisor for direct injection.
            # For chat input there is no prompt_type, so we bypass _normalise()
            # and write raw bytes + CR directly.
            supervisors = getattr(self._adapter, "_supervisors", {})
            tty = supervisors.get(self._session_id)
            if tty is None:
                return InjectionResult(
                    success=False,
                    injected_value=value,
                    feedback_message="No active PTY session for chat input",
                )

            data = value.encode("utf-8", errors="replace") + b"\r"
            await tty.inject_reply(data)
            self._detector.mark_injected()

            feedback = f'Sent: "{value}"'
            log.info("chat_input_injected", value_length=len(value))
            return InjectionResult(
                success=True,
                injected_value=value,
                cli_advanced=None,
                feedback_message=feedback,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("chat_input_failed", error=str(exc))
            return InjectionResult(
                success=False,
                injected_value=value,
                feedback_message=f"Chat input failed: {exc}",
            )

    async def _check_advance(self, plan: InteractionPlan, pre_inject_time: float) -> bool:
        """
        Wait up to advance_timeout_s for new output after injection.

        Returns True if detector.last_output_time moved past
        pre_inject_time + echo suppression window.
        """
        echo_window_s = ECHO_SUPPRESS_MS / 1000.0
        deadline = time.monotonic() + plan.advance_timeout_s

        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL_S)
            if self._detector.last_output_time > pre_inject_time + echo_window_s:
                return True

        return False
