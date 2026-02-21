"""
AutopilotEngine — policy-driven autonomous prompt handling.

The engine intercepts every PromptEvent before it reaches the channel,
applies the configured policy, and either:

    - injects a reply automatically (auto_reply action)
    - forwards to the human operator (require_human action)
    - denies and notifies (deny action)
    - notifies only without waiting (notify_only action)

Kill switch (state machine)::

    RUNNING  →  PAUSED   (via /pause from Telegram/Slack or atlasbridge pause)
    PAUSED   →  RUNNING  (via /resume)
    RUNNING  →  STOPPED  (via /stop — triggers clean shutdown)
    PAUSED   →  STOPPED

When PAUSED, ALL prompts are escalated to the human regardless of policy.
When STOPPED, the engine exits its event loop.

Autonomy mode interaction:

    OFF   → engine passes every PromptEvent directly to route_fn (legacy behavior)
    ASSIST → engine evaluates policy but sends a *suggested* reply to the channel
             along with the prompt; human must confirm or override
    FULL   → engine auto-injects per policy; escalates no-match / LOW-confidence
             / require_human actions to the human
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from atlasbridge.core.autopilot.actions import (
    ActionResult,
    InjectFn,
    NotifyFn,
    RouteFn,
    execute_action,
)
from atlasbridge.core.autopilot.trace import DecisionTrace
from atlasbridge.core.policy.evaluator import evaluate
from atlasbridge.core.policy.model import AutonomyMode, Policy, PolicyDecision, PolicyRule
from atlasbridge.core.policy.model_v1 import PolicyV1

AnyPolicy = Policy | PolicyV1

logger = logging.getLogger(__name__)

STATE_FILENAME = "autopilot_state.json"
HISTORY_FILENAME = "autopilot_history.jsonl"


class AutopilotState(str, Enum):
    """Runtime state of the autopilot kill switch."""

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


_VALID_TRANSITIONS: dict[AutopilotState, set[AutopilotState]] = {
    AutopilotState.RUNNING: {AutopilotState.PAUSED, AutopilotState.STOPPED},
    AutopilotState.PAUSED: {AutopilotState.RUNNING, AutopilotState.STOPPED},
    AutopilotState.STOPPED: set(),
}


class AutopilotEngine:
    """
    Policy-driven autonomous prompt handler.

    Args:
        policy:       Loaded and validated Policy instance.
        trace_path:   Path to the decision trace JSONL file.
        state_path:   Path to the persistent state JSON (kill-switch state).
        inject_fn:    Coroutine: inject a reply string into the PTY.
        route_fn:     Coroutine: forward a PromptEvent to the human via channel.
        notify_fn:    Coroutine: send a one-way notification to the channel.
        history_path: Path to the state transition history JSONL file.
    """

    def __init__(
        self,
        policy: AnyPolicy,
        trace_path: Path,
        state_path: Path,
        inject_fn: InjectFn,
        route_fn: RouteFn,
        notify_fn: NotifyFn,
        history_path: Path | None = None,
    ) -> None:
        self.policy = policy
        self.trace = DecisionTrace(trace_path)
        self._state_path = state_path
        self._history_path = history_path or state_path.parent / HISTORY_FILENAME
        self._inject_fn = inject_fn
        self._route_fn = route_fn
        self._notify_fn = notify_fn
        self._state = self._load_state()
        self._lock = asyncio.Lock()
        # session_id → {rule_id → count}
        self._rule_reply_counts: dict[str, dict[str, int]] = {}

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> AutopilotState:
        """Load persisted state (defaults to RUNNING if file absent)."""
        if not self._state_path.exists():
            return AutopilotState.RUNNING
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return AutopilotState(data.get("state", AutopilotState.RUNNING.value))
        except (OSError, json.JSONDecodeError, ValueError):
            return AutopilotState.RUNNING

    def _save_state(self) -> None:
        """Persist current state to disk."""
        try:
            self._state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps({"state": self._state.value}),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("AutopilotEngine: cannot save state: %s", exc)

    # ------------------------------------------------------------------
    # Kill switch
    # ------------------------------------------------------------------

    @property
    def state(self) -> AutopilotState:
        return self._state

    def _transition(self, new_state: AutopilotState, triggered_by: str = "unknown") -> bool:
        """
        Attempt a state transition. Returns True if successful, False if invalid.
        """
        if new_state not in _VALID_TRANSITIONS.get(self._state, set()):
            logger.warning(
                "AutopilotEngine: invalid transition %s → %s",
                self._state.value,
                new_state.value,
            )
            return False
        old = self._state
        self._state = new_state
        self._save_state()
        self._append_history(old, new_state, triggered_by)
        logger.info("AutopilotEngine: %s → %s (by %s)", old.value, new_state.value, triggered_by)
        return True

    def _append_history(
        self,
        from_state: AutopilotState,
        to_state: AutopilotState,
        triggered_by: str,
    ) -> None:
        """Append one state transition entry to the history JSONL file."""
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "from_state": from_state.value,
            "to_state": to_state.value,
            "triggered_by": triggered_by,
        }
        try:
            self._history_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with self._history_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.error("AutopilotEngine: cannot write history: %s", exc)

    def pause(self, triggered_by: str = "unknown") -> bool:
        """Pause the engine — all prompts will be escalated to human."""
        return self._transition(AutopilotState.PAUSED, triggered_by=triggered_by)

    def resume(self, triggered_by: str = "unknown") -> bool:
        """Resume the engine — policy-driven auto-replies restart."""
        return self._transition(AutopilotState.RUNNING, triggered_by=triggered_by)

    def stop(self, triggered_by: str = "unknown") -> bool:
        """Stop the engine — triggers clean shutdown."""
        return self._transition(AutopilotState.STOPPED, triggered_by=triggered_by)

    # ------------------------------------------------------------------
    # Rate limit helpers
    # ------------------------------------------------------------------

    def _get_rule(self, rule_id: str | None) -> PolicyRule | None:
        """Return the rule with the given id, or None (works for v0 and v1 rules)."""
        if rule_id is None:
            return None
        return next((r for r in self.policy.rules if r.id == rule_id), None)  # type: ignore[return-value]

    def reset_session(self, session_id: str) -> None:
        """Clear per-rule reply counters for a finished session."""
        self._rule_reply_counts.pop(session_id, None)

    # ------------------------------------------------------------------
    # Policy hot-reload
    # ------------------------------------------------------------------

    def reload_policy(self, policy: AnyPolicy) -> None:
        """Replace the active policy at runtime (no restart required)."""
        old_hash = self.policy.content_hash()
        self.policy = policy
        new_hash = policy.content_hash()
        logger.info("AutopilotEngine: policy reloaded %s → %s", old_hash, new_hash)

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    async def handle_prompt(
        self,
        prompt_event: object,
        prompt_id: str,
        session_id: str,
        prompt_type: str,
        confidence: str,
        prompt_text: str,
        tool_id: str = "*",
        repo: str = "",
        session_tag: str = "",
    ) -> ActionResult:
        """
        Evaluate the policy against a PromptEvent and execute the resulting action.

        This is the main entry point called by the PromptRouter (or DaemonManager)
        whenever a new PromptEvent is detected.

        Args:
            prompt_event:  The raw PromptEvent object (forwarded to route_fn if required).
            prompt_id:     Unique ID of the PromptEvent.
            session_id:    Session the prompt belongs to.
            prompt_type:   PromptType string (e.g. "yes_no").
            confidence:    Confidence string ("high", "medium", "low").
            prompt_text:   Prompt excerpt (ANSI-stripped output).
            tool_id:       Adapter name (e.g. "claude_code").
            repo:          Working directory of the session.

        Returns:
            ActionResult describing the concrete action taken.
        """
        async with self._lock:
            autonomy_mode = self.policy.autonomy_mode

            # --- Kill switch: STOPPED ---
            if self._state == AutopilotState.STOPPED:
                logger.warning("AutopilotEngine: stopped — dropping prompt %s", prompt_id)
                return ActionResult(action_type="stopped", error="engine stopped")

            # --- Kill switch: PAUSED ---
            if self._state == AutopilotState.PAUSED:
                logger.info("AutopilotEngine: paused — escalating prompt %s to human", prompt_id)
                await self._route_fn(prompt_event)
                return ActionResult(action_type="require_human", routed_to_human=True)

            # --- Autonomy mode: OFF ---
            if autonomy_mode == AutonomyMode.OFF:
                await self._route_fn(prompt_event)
                return ActionResult(action_type="require_human", routed_to_human=True)

            # --- Evaluate policy ---
            decision: PolicyDecision = evaluate(
                policy=self.policy,
                prompt_text=prompt_text,
                prompt_type=prompt_type,
                confidence=confidence,
                prompt_id=prompt_id,
                session_id=session_id,
                tool_id=tool_id,
                repo=repo,
                session_tag=session_tag,
            )

            # Record decision to trace (always, regardless of action type)
            self.trace.record(decision)

            # --- Rate limit check ---
            # If the matched rule has max_auto_replies set, check the counter.
            # Exceeded limit → escalate to human instead of auto-replying.
            if decision.matched_rule_id is not None and decision.action_type == "auto_reply":
                rule = self._get_rule(decision.matched_rule_id)
                if rule is not None and rule.max_auto_replies is not None:
                    session_counts = self._rule_reply_counts.setdefault(session_id, {})
                    current = session_counts.get(decision.matched_rule_id, 0)
                    if current >= rule.max_auto_replies:
                        logger.info(
                            "AutopilotEngine: rate limit reached for rule=%s session=%s "
                            "(limit=%d) — escalating to human",
                            decision.matched_rule_id,
                            session_id,
                            rule.max_auto_replies,
                        )
                        await self._route_fn(prompt_event)
                        return ActionResult(action_type="require_human", routed_to_human=True)

            # --- Autonomy mode: ASSIST ---
            # Suggest the reply to the human; they confirm or override.
            if autonomy_mode == AutonomyMode.ASSIST:
                await self._route_fn(prompt_event)
                # Notification with the suggestion is sent by the channel adapter
                # (which reads action_type / action_value from the decision)
                logger.info(
                    "AutopilotEngine: assist mode — forwarded prompt %s with suggestion %r",
                    prompt_id,
                    decision.action_value,
                )
                return ActionResult(action_type="require_human", routed_to_human=True)

            # --- Autonomy mode: FULL ---
            result = await execute_action(
                decision=decision,
                prompt_event=prompt_event,
                inject_fn=self._inject_fn,
                route_fn=self._route_fn,
                notify_fn=self._notify_fn,
            )

            # Increment per-rule reply counter on successful auto_reply
            if result.injected and decision.matched_rule_id is not None:
                session_counts = self._rule_reply_counts.setdefault(session_id, {})
                session_counts[decision.matched_rule_id] = (
                    session_counts.get(decision.matched_rule_id, 0) + 1
                )

            return result
