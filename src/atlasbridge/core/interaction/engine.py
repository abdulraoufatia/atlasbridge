"""
InteractionEngine — orchestrates classify → plan → execute → feedback.

The engine is constructed per-session and provides two entry points:

1. ``handle_prompt_reply(event, reply)`` — for structured prompt responses.
   Classifies the event, builds a plan, executes with retry/verification,
   and sends feedback to the channel.

2. ``handle_chat_input(reply)`` — for free-text with no active prompt.
   Builds a CHAT_INPUT plan and injects directly into stdin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from atlasbridge.core.interaction.classifier import InteractionClass, InteractionClassifier
from atlasbridge.core.interaction.executor import InjectionResult, InteractionExecutor
from atlasbridge.core.interaction.normalizer import detect_binary_menu, normalize_reply
from atlasbridge.core.interaction.plan import build_plan

if TYPE_CHECKING:
    from atlasbridge.adapters.base import BaseAdapter
    from atlasbridge.channels.base import BaseChannel
    from atlasbridge.core.conversation.session_binding import ConversationRegistry
    from atlasbridge.core.interaction.fuser import ClassificationFuser
    from atlasbridge.core.prompt.detector import PromptDetector
    from atlasbridge.core.prompt.models import PromptEvent, Reply
    from atlasbridge.core.session.manager import SessionManager

logger = structlog.get_logger()


class InteractionEngine:
    """
    Per-session orchestrator for the interaction pipeline.

    Ties together InteractionClassifier, InteractionPlan, and
    InteractionExecutor into a single entry point that the router
    can call.
    """

    def __init__(
        self,
        adapter: BaseAdapter,
        session_id: str,
        detector: PromptDetector,
        channel: BaseChannel,
        session_manager: SessionManager,
        fuser: ClassificationFuser | None = None,
        conversation_registry: ConversationRegistry | None = None,
        dry_run: bool = False,
    ) -> None:
        self._classifier = InteractionClassifier()
        self._fuser = fuser
        self._channel = channel
        self._session_id = session_id
        self._conversation_registry = conversation_registry
        self._dry_run = dry_run

        self._executor = InteractionExecutor(
            adapter=adapter,
            session_id=session_id,
            detector=detector,
            notify_fn=self._notify,
            dry_run=dry_run,
        )

    async def _notify(self, message: str) -> None:
        """Send a notification to the channel."""
        await self._channel.notify(message, session_id=self._session_id)

    async def handle_prompt_reply(
        self,
        event: PromptEvent,
        reply: Reply,
    ) -> InjectionResult:
        """
        Process a reply to a structured prompt.

        1. Classify the event's interaction type
        2. Build an execution plan
        3. Execute (inject + verify + retry)
        4. Return result (caller handles channel feedback)
        """
        log = logger.bind(
            session_id=self._session_id[:8],
            prompt_id=event.prompt_id,
        )

        if self._fuser is not None:
            fused = self._fuser.fuse(event)
            ic = fused.interaction_class
            if fused.disagreement:
                log.warning(
                    "classification_disagreement",
                    interaction_class=ic,
                    source=fused.source,
                )
        else:
            ic = self._classifier.classify(event)

        plan = build_plan(ic)

        # Normalize reply for binary semantic menus (e.g., "yes" → "1")
        injection_value = reply.value
        if ic == InteractionClass.NUMBERED_CHOICE:
            menu = detect_binary_menu(event.excerpt)
            if menu is not None:
                normalized = normalize_reply(menu, reply.value)
                if normalized is not None:
                    log.debug(
                        "reply_normalized",
                        original=reply.value,
                        normalized=normalized,
                        yes_option=menu.yes_option,
                        no_option=menu.no_option,
                    )
                    injection_value = normalized
                else:
                    # Ambiguous — ask user to pick a number
                    await self._notify(f"Please reply with {menu.yes_option} or {menu.no_option}.")
                    return InjectionResult(
                        success=False,
                        injected_value=reply.value,
                        feedback_message=(
                            f"Ambiguous reply. Send {menu.yes_option} or {menu.no_option}."
                        ),
                    )

        log.debug(
            "interaction_classified",
            interaction_class=ic,
            button_layout=plan.button_layout,
            max_retries=plan.max_retries,
        )

        result = await self._executor.execute(
            plan=plan,
            value=injection_value,
            prompt_type=event.prompt_type,
            event=event,
        )

        log.info(
            "interaction_executed",
            success=result.success,
            cli_advanced=result.cli_advanced,
            retries_used=result.retries_used,
            escalated=result.escalated,
        )

        return result

    async def handle_chat_input(self, reply: Reply) -> InjectionResult:
        """
        Process a free-text message when no prompt is active.

        Injects directly into the CLI's stdin as conversational input.
        """
        log = logger.bind(
            session_id=self._session_id[:8] if reply.session_id else "",
            channel_identity=reply.channel_identity,
        )

        result = await self._executor.execute_chat_input(reply.value)

        log.info(
            "chat_input_handled",
            success=result.success,
            value_length=len(reply.value),
        )

        return result
