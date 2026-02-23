"""
StreamingManager — accumulates output and detects plans.

The StreamingManager sits alongside the OutputForwarder and watches
for plan blocks in the accumulated output.  When a plan is detected,
it presents it to the channel with Execute/Modify/Cancel buttons.

The accumulator is bounded at 8192 chars to prevent unbounded growth.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

from atlasbridge.core.interaction.plan_detector import DetectedPlan, detect_plan

if TYPE_CHECKING:
    from atlasbridge.channels.base import BaseChannel

logger = structlog.get_logger()

_MAX_ACCUMULATOR_CHARS = 8192


class PlanStatus(StrEnum):
    """Status of a detected plan."""

    PENDING = "pending"
    PRESENTED = "presented"
    RESOLVED = "resolved"


@dataclass
class PlanContext:
    """Context for a detected plan awaiting user response."""

    plan: DetectedPlan
    session_id: str
    plan_message_id: str = ""
    status: PlanStatus = PlanStatus.PENDING


class StreamingManager:
    """
    Accumulates output text and detects plans.

    Usage::

        mgr = StreamingManager(channel, session_id)
        # In the flush callback:
        plan = mgr.accumulate(text)
        if plan:
            ctx = await mgr.present_plan(plan)
    """

    def __init__(self, channel: BaseChannel, session_id: str) -> None:
        self._channel = channel
        self._session_id = session_id
        self._accumulator: str = ""
        self._active_plan: PlanContext | None = None

    def accumulate(self, text: str) -> DetectedPlan | None:
        """
        Accumulate output text and check for a plan.

        Returns a DetectedPlan if one is detected, None otherwise.
        After a detection, the accumulator is reset.
        """
        self._accumulator += text

        # Bound the accumulator
        if len(self._accumulator) > _MAX_ACCUMULATOR_CHARS:
            self._accumulator = self._accumulator[-_MAX_ACCUMULATOR_CHARS:]

        plan = detect_plan(self._accumulator)
        if plan is not None:
            self._accumulator = ""
            return plan

        return None

    async def present_plan(self, plan: DetectedPlan) -> PlanContext:
        """Send the detected plan to the channel with action buttons."""
        msg_id = await self._channel.send_plan(plan, session_id=self._session_id)
        ctx = PlanContext(
            plan=plan,
            session_id=self._session_id,
            plan_message_id=msg_id,
            status=PlanStatus.PRESENTED,
        )
        self._active_plan = ctx
        logger.info(
            "plan_presented",
            session_id=self._session_id[:8],
            steps=len(plan.steps),
            message_id=msg_id,
        )
        return ctx

    def resolve_plan(self, decision: str) -> None:
        """Mark the active plan as resolved."""
        if self._active_plan is not None:
            self._active_plan.status = PlanStatus.RESOLVED
            logger.debug(
                "plan_resolved",
                session_id=self._session_id[:8],
                decision=decision,
            )
            self._active_plan = None

    @property
    def active_plan(self) -> PlanContext | None:
        """Return the currently active plan context, or None."""
        return self._active_plan

    def reset(self) -> None:
        """Clear accumulator and active plan state."""
        self._accumulator = ""
        self._active_plan = None
