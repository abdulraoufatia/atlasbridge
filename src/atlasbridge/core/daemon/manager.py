"""
Daemon manager.

The DaemonManager orchestrates all top-level AtlasBridge components for one
daemon process lifetime:
  - Loads configuration
  - Connects to the database
  - Starts the notification channel
  - Manages sessions and the prompt router
  - Runs the reply consumer loop
  - Handles graceful shutdown on SIGTERM/SIGINT

The daemon is a long-running asyncio process started by `atlasbridge start`
and managed by launchd (macOS) or systemd (Linux).

PID file: <data_dir>/atlasbridge.pid
"""

from __future__ import annotations

import asyncio
import os
import signal
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from atlasbridge.adapters.base import BaseAdapter
    from atlasbridge.channels.base import BaseChannel
    from atlasbridge.core.policy.model import Policy
    from atlasbridge.core.policy.model_v1 import PolicyV1
    from atlasbridge.core.routing.intent import IntentRouter
    from atlasbridge.core.routing.router import PromptRouter
    from atlasbridge.core.session.manager import SessionManager
    from atlasbridge.core.store.database import Database

logger = structlog.get_logger()

_DEFAULT_DATA_DIR = Path.home() / ".atlasbridge"


class DaemonManager:
    """
    Top-level orchestrator for the AtlasBridge daemon.

    Lifecycle::

        manager = DaemonManager(config)
        await manager.start()    # blocks until shutdown signal
        await manager.stop()
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._data_dir = Path(config.get("data_dir", str(_DEFAULT_DATA_DIR)))
        self._dry_run: bool = config.get("dry_run", False)
        self._db: Database | None = None
        self._channel: BaseChannel | None = None
        self._session_manager: SessionManager | None = None
        self._router: PromptRouter | None = None
        self._adapters: dict[str, BaseAdapter] = {}
        self._running: bool = False
        self._shutdown_event: asyncio.Event = asyncio.Event()
        self._policy: Policy | PolicyV1 | None = None
        self._intent_router: IntentRouter | None = None
        self._conversation_registry: Any = None  # ConversationRegistry
        self._autopilot_trace: Any = None  # DecisionTrace | None
        self._transcript_writers: dict[str, Any] = {}  # session_id → TranscriptWriter

    async def start(self) -> None:
        """Start all subsystems and run until shutdown."""
        logger.info(
            "daemon_starting",
            pid=os.getpid(),
            data_dir=str(self._data_dir),
            dry_run=self._dry_run,
        )
        self._write_pid_file()

        try:
            await self._init_database()
            await self._reload_pending_prompts()
            await self._init_channel()
            await self._renotify_pending()
            await self._init_session_manager()
            self._init_conversation_registry()
            await self._init_router()
            await self._init_autopilot()
            self._init_intent_router()

            self._running = True
            self._setup_signal_handlers()

            logger.info("daemon_ready")
            await self._run_loop()

        finally:
            await self._cleanup()
            self._remove_pid_file()
            logger.info("daemon_stopped")

    async def stop(self) -> None:
        """Request graceful shutdown."""
        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def _init_database(self) -> None:
        from atlasbridge.core.store.database import Database

        db_path = self._data_dir / "atlasbridge.db"
        self._db = Database(db_path)
        self._db.connect()
        logger.info("database_connected", path=str(db_path))

    async def _reload_pending_prompts(self) -> None:
        """On restart, reload pending prompts from the database."""
        if self._db is None:
            return
        pending = self._db.list_pending_prompts()
        if pending:
            logger.info("daemon_restarted_with_pending", count=len(pending))
            self._pending_renotify = pending  # saved for _renotify_pending()

    async def _renotify_pending(self) -> None:
        """Re-send pending prompts to the channel after restart.

        Called after channel initialisation so that humans see any prompts
        that were awaiting reply when the previous daemon instance died.
        """
        pending = getattr(self, "_pending_renotify", [])
        if not pending or self._channel is None or self._dry_run:
            return

        count = 0
        for row in pending:
            try:
                await self._channel.notify(
                    f"⚠ Pending prompt (restart recovery): {row['excerpt'][:120]}",
                    session_id=row["session_id"],
                )
                count += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("renotify_failed", prompt_id=row["id"], error=str(exc))

        if count:
            logger.info("renotify_complete", sent=count, total=len(pending))
        self._pending_renotify = []

    async def _init_channel(self) -> None:
        if self._dry_run:
            logger.info("dry_run_channel_suppressed")
            return

        # Notification channels (Telegram/Slack) have been removed.
        # Prompts that would have been escalated are now logged only.
        logger.info("channel_init_skipped_channels_removed")

    async def _init_session_manager(self) -> None:
        from atlasbridge.core.session.manager import SessionManager

        self._session_manager = SessionManager()

    def _init_conversation_registry(self) -> None:
        """Create the conversation registry for thread→session binding."""
        from atlasbridge.core.conversation.session_binding import ConversationRegistry

        self._conversation_registry = ConversationRegistry()
        logger.info("conversation_registry_initialized")

    async def _init_autopilot(self) -> None:
        """Load the policy for this session (from --policy file or built-in default)."""
        from atlasbridge.core.autopilot.trace import DecisionTrace
        from atlasbridge.core.policy.parser import PolicyParseError, default_policy, load_policy

        policy_file = self._config.get("policy_file", "")
        if policy_file:
            try:
                self._policy = load_policy(policy_file)
                logger.info("policy_loaded", path=policy_file)
            except PolicyParseError as exc:
                logger.error("policy_load_failed", path=policy_file, error=str(exc))
                self._policy = default_policy()
        else:
            self._policy = default_policy()

        trace_path = self._data_dir / "autopilot_decisions.jsonl"
        self._autopilot_trace = DecisionTrace(trace_path)

    def _init_intent_router(self) -> None:
        """Wrap the PromptRouter with intent classification and autopilot execution."""
        if self._router is None or self._policy is None:
            return

        # In "off" mode, skip autopilot entirely — all prompts go to the human channel.
        autonomy_mode = self._config.get("autonomy_mode", "assist")
        if autonomy_mode == "off":
            logger.info("autonomy_mode_off_skipping_intent_router")
            return

        from atlasbridge.core.routing.intent import IntentRouter, PolicyRouteClassifier

        classifier = PolicyRouteClassifier(policy=self._policy)

        async def _autopilot_handler(event: Any, result: Any) -> None:
            """Auto-inject the reply value for prompts matched by an auto_reply rule."""
            if result.action_type != "auto_reply":
                # require_human or unknown — fall through to channel
                if self._router is not None:
                    await self._router.route_event(event)
                return

            # Delegate injection to router (router.py is in ALLOWED_INJECTION_MODULES)
            if self._router is not None:
                await self._router.inject_autopilot_reply(event, result.action_value)
                logger.info(
                    "autopilot_auto_replied",
                    rule=result.matched_rule_id,
                    value=repr(result.action_value[:20]),
                    session_id=event.session_id[:8],
                )
                # Record to decision trace for audit/explain
                if self._autopilot_trace is not None and self._policy is not None:
                    try:
                        from atlasbridge.core.policy.evaluator import evaluate

                        pt = (
                            event.prompt_type.value
                            if hasattr(event.prompt_type, "value")
                            else str(event.prompt_type)
                        )
                        conf_str = (
                            event.confidence.value
                            if hasattr(event.confidence, "value")
                            else str(event.confidence)
                        )
                        decision = evaluate(
                            policy=self._policy,
                            prompt_text=event.excerpt,
                            prompt_type=pt,
                            confidence=conf_str,
                            prompt_id=event.prompt_id,
                            session_id=event.session_id,
                            tool_id=event.tool or self._config.get("tool", ""),
                            repo=event.cwd or "",
                        )
                        self._autopilot_trace.record(decision)
                    except Exception as trace_exc:
                        logger.warning("autopilot_trace_failed", error=str(trace_exc))

        async def _deny_handler(event: Any, result: Any) -> None:
            """Log and notify on deny — do NOT inject."""
            logger.warning(
                "autopilot_prompt_denied",
                rule=result.matched_rule_id,
                session_id=event.session_id[:8],
            )
            if self._channel is not None:
                try:
                    msg = (
                        f"Prompt denied by policy rule "
                        f"'{result.matched_rule_id}': "
                        f"{result.explanation or ''}"
                    )
                    await self._channel.notify(msg, session_id=event.session_id)
                except Exception:
                    pass

        self._intent_router = IntentRouter(
            prompt_router=self._router,
            classifier=classifier,
            autopilot_handler=_autopilot_handler,
            deny_handler=_deny_handler,
        )
        logger.info("intent_router_initialized")

    async def _init_router(self) -> None:
        if self._session_manager is None:
            return
        # Router is needed even without a channel — the dashboard Chat page
        # serves as a standalone relay when no Telegram/Slack is configured.
        from atlasbridge.core.routing.router import PromptRouter

        self._router = PromptRouter(
            session_manager=self._session_manager,
            channel=self._channel,
            adapter_map=self._adapters,
            store=self._db,
            conversation_registry=self._conversation_registry,
            dry_run=self._dry_run,
        )

    # ------------------------------------------------------------------
    # Adapter session
    # ------------------------------------------------------------------

    async def _run_adapter_session(self) -> None:
        """
        Launch the adapter/PTY for the configured tool, run until the child
        process exits, then trigger daemon shutdown.

        This is the critical wiring between the PTY supervisor and the
        PromptRouter:

            PTY output bytes
              → PromptDetector.analyse()
                → PromptEvent
                  → PromptRouter.route_event()
                    → Channel (Telegram / Slack)
                      → Reply
                        → PromptRouter.handle_reply()
                          → adapter.inject_reply()
                            → PTY stdin
        """
        tool = self._config.get("tool", "")
        command = self._config.get("command", [])
        if not tool or not command:
            logger.info("channel_only_mode")
            return

        from atlasbridge.adapters.base import AdapterRegistry
        from atlasbridge.core.session.models import Session

        try:
            adapter_cls = AdapterRegistry.get(tool)
        except KeyError as exc:
            logger.error("adapter_not_found", tool=tool, error=str(exc))
            return

        adapter = adapter_cls()
        adapter.experimental = self._config.get("experimental", False)  # type: ignore[attr-defined]
        session_id = str(uuid.uuid4())

        session = Session(session_id=session_id, tool=tool, command=list(command))
        if self._session_manager is None:
            logger.error("session_manager_not_initialized")
            return
        self._session_manager.register(session)
        self._adapters[session_id] = adapter

        logger.info("session_starting", tool=tool, session_id=session_id[:8])

        # Persist session to DB so the dashboard can see it
        if self._db is not None:
            cwd = self._config.get("cwd", "") or ""
            label = self._config.get("session_label", "") or ""
            self._db.save_session(session_id, tool, list(command), cwd=cwd, label=label)

        await adapter.start_session(session_id=session_id, command=list(command))

        # Mark the session as running once the child PID is known
        ctx = adapter.snapshot_context(session_id)
        pid = ctx.get("pid", -1)
        if pid and pid > 0:
            self._session_manager.mark_running(session_id, pid)
            if self._db is not None:
                import os as _os

                self._db.update_session(session_id, status="running", pid=pid or _os.getpid())

        # Re-use the detector the adapter already created for this session.
        # This ensures inject_reply() → mark_injected() shares the same state
        # as our analyse() calls (echo suppression depends on this).
        detector = adapter.get_detector(session_id)
        if detector is None:
            from atlasbridge.core.prompt.detector import PromptDetector

            detector = PromptDetector(session_id)

        event_q: asyncio.Queue[Any] = asyncio.Queue()
        eof_reached = asyncio.Event()

        # Use intent router when available, fall back to prompt router
        router = self._intent_router or self._router

        # Wire InteractionEngine and OutputForwarder for Conversation UX v2
        output_forwarder = None
        if self._channel is not None and self._session_manager is not None:
            from atlasbridge.core.interaction.classifier import InteractionClassifier
            from atlasbridge.core.interaction.engine import InteractionEngine
            from atlasbridge.core.interaction.fuser import ClassificationFuser
            from atlasbridge.core.interaction.ml_classifier import NullMLClassifier
            from atlasbridge.core.interaction.output_forwarder import OutputForwarder
            from atlasbridge.core.interaction.output_router import OutputRouter

            # Classification fuser: deterministic + NullML (ML slot ready)
            fuser = ClassificationFuser(InteractionClassifier(), NullMLClassifier())

            interaction_engine = InteractionEngine(
                adapter=adapter,
                session_id=session_id,
                detector=detector,
                channel=self._channel,
                session_manager=self._session_manager,
                fuser=fuser,
                conversation_registry=self._conversation_registry,
                dry_run=self._dry_run,
            )

            # Output router classifies agent prose vs CLI output
            output_router = OutputRouter()

            # Build StreamingConfig from raw config dict (if present)
            streaming_config = None
            if self._config.get("streaming"):
                from atlasbridge.core.config import StreamingConfig

                try:
                    streaming_config = StreamingConfig.model_validate(self._config["streaming"])
                except Exception:  # noqa: BLE001
                    pass  # Fall back to module-level constants

            # StreamingManager for plan detection in output
            from atlasbridge.core.interaction.streaming import StreamingManager

            streaming_manager = StreamingManager(self._channel, session_id)

            output_forwarder = OutputForwarder(
                self._channel,
                session_id,
                output_router=output_router,
                streaming_config=streaming_config,
                conversation_registry=self._conversation_registry,
                streaming_manager=streaming_manager,
            )

            # Inject into the PromptRouter (works for both PromptRouter and IntentRouter)
            prompt_router = self._router
            if prompt_router is not None:
                prompt_router._interaction_engine = interaction_engine
                prompt_router._chat_mode_handler = interaction_engine.handle_chat_input

            logger.info(
                "interaction_engine_wired",
                session_id=session_id[:8],
                fuser="enabled",
                output_router="enabled",
            )

        # Transcript writer — persists output for dashboard live transcript
        transcript_writer = None
        if self._db is not None:
            from atlasbridge.core.store.transcript import TranscriptWriter

            transcript_writer = TranscriptWriter(self._db, session_id)
            self._transcript_writers[session_id] = transcript_writer

        async def _read_loop() -> None:
            try:
                while True:
                    chunk = await adapter.read_stream(session_id)
                    if not chunk:
                        break
                    tty_blocked = await adapter.await_input_state(session_id)
                    ev = detector.analyse(chunk, tty_blocked=tty_blocked)
                    if ev is not None and router is not None:
                        await event_q.put(ev)
                    # Feed output to forwarder for Chat Mode
                    if output_forwarder is not None:
                        output_forwarder.feed(chunk)
                    # Feed output to transcript writer for dashboard
                    if transcript_writer is not None:
                        transcript_writer.feed(chunk)
            finally:
                eof_reached.set()

        async def _route_events() -> None:
            while not eof_reached.is_set() or not event_q.empty():
                try:
                    ev = await asyncio.wait_for(event_q.get(), timeout=0.2)
                    if router is not None:
                        await router.route_event(ev)
                except TimeoutError:
                    continue

        async def _silence_watchdog() -> None:
            interval = 1.0
            while not eof_reached.is_set():
                await asyncio.sleep(interval)
                try:
                    running = await adapter.await_input_state(session_id)
                except Exception:  # noqa: BLE001
                    running = False
                ev = detector.check_silence(process_running=running)
                if ev is not None and router is not None:
                    await router.route_event(ev)

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(_read_loop(), name="pty_read")
                tg.create_task(_route_events(), name="route_events")
                tg.create_task(_silence_watchdog(), name="silence_watchdog")
                if output_forwarder is not None:
                    tg.create_task(output_forwarder.flush_loop(), name="output_forwarder")
                if transcript_writer is not None:
                    tg.create_task(transcript_writer.flush_loop(), name="transcript_writer")
        except* asyncio.CancelledError:
            pass
        finally:
            logger.info("session_ended", session_id=session_id[:8])
            self._session_manager.mark_ended(session_id)
            if self._db is not None:
                self._db.update_session(session_id, status="completed")

            # Clean up transcript writer
            self._transcript_writers.pop(session_id, None)

            # Unbind conversation threads for this session
            if self._conversation_registry is not None:
                self._conversation_registry.unbind(session_id)

            # Session lifecycle: notify channel of session end
            if self._channel is not None and not self._dry_run:
                try:
                    await self._channel.notify(
                        f"Session ended: {tool} ({session_id[:8]})",
                        session_id=session_id,
                    )
                except Exception:  # noqa: BLE001
                    pass  # Best-effort; channel may already be closed

            await adapter.terminate_session(session_id)
            await self.stop()

    # ------------------------------------------------------------------
    # Chat session (direct LLM API mode)
    # ------------------------------------------------------------------

    async def _run_chat_session(self) -> None:
        """
        Run a chat session: users talk to an LLM via the channel,
        with tool use governed by the policy engine.

        Data flow::

            user message (Telegram/Slack)
              -> ChatEngine.handle_message()
                -> LLM provider (streaming)
                  -> tool_calls -> policy -> execute/escalate/deny
                -> response -> channel
        """
        chat_cfg = self._config.get("chat", {})
        provider_name = chat_cfg.get("provider_name", "")
        api_key = chat_cfg.get("api_key", "")

        if not provider_name or not api_key:
            logger.error("chat_session_missing_provider")
            return

        if self._channel is None:
            logger.error("chat_session_no_channel")
            return

        # Import and create provider (import triggers auto-registration)
        import atlasbridge.providers  # noqa: F401
        from atlasbridge.providers.base import ProviderRegistry

        try:
            provider_cls = ProviderRegistry.get(provider_name)
        except KeyError as exc:
            logger.error("chat_provider_not_found", error=str(exc))
            return

        model = chat_cfg.get("model", "")
        provider = provider_cls(api_key=api_key, model=model)  # type: ignore[call-arg]

        # Create session
        from atlasbridge.core.session.models import Session

        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            tool=f"chat:{provider_name}",
            command=["chat"],
        )
        if self._session_manager is not None:
            self._session_manager.register(session)

        # Set up tool registry + executor (if tools enabled)
        tool_registry = None
        tool_executor = None
        if chat_cfg.get("tools_enabled", True):
            from atlasbridge.tools.executor import ToolExecutor
            from atlasbridge.tools.registry import get_default_registry

            tool_registry = get_default_registry()
            tool_executor = ToolExecutor(tool_registry)

        # Create ChatEngine
        from atlasbridge.core.chat.engine import ChatEngine

        engine = ChatEngine(
            provider=provider,
            channel=self._channel,
            session_id=session_id,
            session_manager=self._session_manager,  # type: ignore[arg-type]
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            policy=self._policy,
            system_prompt=chat_cfg.get("system_prompt", ""),
            max_history=chat_cfg.get("max_history", 50),
        )

        logger.info(
            "chat_session_started",
            session_id=session_id[:8],
            provider=provider_name,
            model=model or "(default)",
            tools=chat_cfg.get("tools_enabled", True),
        )

        # Consume channel messages and forward to ChatEngine
        try:
            async for reply in self._channel.receive_replies():
                text = reply.value
                if not text or not text.strip():
                    continue
                try:
                    await engine.handle_message(text)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "chat_message_error",
                        session_id=session_id[:8],
                        error=str(exc),
                    )
                    try:
                        await self._channel.notify(
                            f"Error: {exc}",
                            session_id=session_id,
                        )
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            await provider.close()
            if self._session_manager is not None:
                self._session_manager.mark_ended(session_id)
            logger.info("chat_session_ended", session_id=session_id[:8])

    async def _run_agent_session(self) -> None:
        """
        Run an Expert Agent session: users interact with a governance-specialised
        LLM agent through the channel, with SoR persistence and policy gating.
        """
        chat_cfg = self._config.get("chat", {})
        provider_name = chat_cfg.get("provider_name", "")
        api_key = chat_cfg.get("api_key", "")

        if not provider_name or not api_key:
            logger.error("agent_session_missing_provider")
            return

        if self._channel is None:
            logger.error("agent_session_no_channel")
            return

        import atlasbridge.providers  # noqa: F401
        from atlasbridge.providers.base import ProviderRegistry

        try:
            provider_cls = ProviderRegistry.get(provider_name)
        except KeyError as exc:
            logger.error("agent_provider_not_found", error=str(exc))
            return

        model = chat_cfg.get("model", "")
        provider = provider_cls(api_key=api_key, model=model)  # type: ignore[call-arg]

        # Create or reuse session (pre-created by --background path)
        from atlasbridge.core.session.models import Session

        pre_session_id = self._config.get("session_id", "")
        session_id = pre_session_id if pre_session_id else str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            tool=f"agent:{provider_name}",
            command=["agent"],
        )
        if self._session_manager is not None:
            self._session_manager.register(session)

        # Persist session (skip save if pre-created, just update status)
        if self._db is not None:
            if pre_session_id:
                self._db.update_session(session_id, status="running")
            else:
                self._db.save_session(
                    session_id,
                    f"agent:{provider_name}",
                    ["agent"],
                    label="Expert Agent",
                )
                self._db.update_session(session_id, status="running")

        # Set up agent tools
        from atlasbridge.core.agent.tools import get_agent_registry, set_agent_context
        from atlasbridge.tools.executor import ToolExecutor

        set_agent_context(self._db, self._config)
        tool_registry = get_agent_registry()
        tool_executor = ToolExecutor(tool_registry)

        # Build system prompt
        from atlasbridge.core.agent.models import AgentProfile
        from atlasbridge.core.agent.prompt import build_system_prompt

        profile = AgentProfile(
            name="atlasbridge_expert",
            version="1.0.0",
            description="AtlasBridge Expert Agent — governance operations specialist",
            capabilities=[t.name for t in tool_registry.list_all()],
            risk_tier="moderate",
            max_autonomy="assist",
        )
        system_prompt = build_system_prompt(profile, self._config)

        # Create SoR writer
        from atlasbridge.core.agent.sor import SystemOfRecordWriter

        assert self._db is not None, "Database must be initialised for agent mode"
        sor = SystemOfRecordWriter(db=self._db, session_id=session_id, trace_id=trace_id)

        # Create ExpertAgentEngine
        from atlasbridge.core.agent.engine import ExpertAgentEngine

        engine = ExpertAgentEngine(
            provider=provider,
            channel=self._channel,
            session_id=session_id,
            session_manager=self._session_manager,  # type: ignore[arg-type]
            sor=sor,
            db=self._db,
            tool_registry=tool_registry,
            tool_executor=tool_executor,
            policy=self._policy,
            system_prompt=system_prompt,
            max_history=chat_cfg.get("max_history", 50),
            profile=profile,
        )

        logger.info(
            "agent_session_started",
            session_id=session_id[:8],
            trace_id=trace_id[:8],
            provider=provider_name,
            model=model or "(default)",
        )

        # Consume channel messages
        try:
            async for reply in self._channel.receive_replies():
                text = reply.value
                if not text or not text.strip():
                    continue

                # Handle approval/denial commands
                lower = text.strip().lower()
                if lower == "approve" and engine.state.value == "gate":
                    plan_id = engine._state_machine.active_plan_id
                    if plan_id:
                        await engine.handle_approval(plan_id, approved=True)
                        continue
                elif lower == "deny" and engine.state.value == "gate":
                    plan_id = engine._state_machine.active_plan_id
                    if plan_id:
                        await engine.handle_approval(plan_id, approved=False)
                        continue

                try:
                    await engine.handle_message(text)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "agent_message_error",
                        session_id=session_id[:8],
                        error=str(exc),
                    )
                    try:
                        await self._channel.notify(f"Error: {exc}", session_id=session_id)
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            await provider.close()
            if self._session_manager is not None:
                self._session_manager.mark_ended(session_id)
            if self._db is not None:
                self._db.update_session(session_id, status="completed")
            logger.info("agent_session_ended", session_id=session_id[:8])

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Run the reply consumer, TTL sweeper, and adapter/chat/agent session until shutdown."""
        tasks: list[asyncio.Task[Any]] = []
        router = self._intent_router or self._router

        mode = self._config.get("mode", "")
        is_chat_mode = mode == "chat"
        is_agent_mode = mode == "agent"

        if is_agent_mode:
            tasks.append(asyncio.create_task(self._run_agent_session(), name="agent_session"))
        elif is_chat_mode:
            # Chat mode: ChatEngine consumes replies directly
            tasks.append(asyncio.create_task(self._run_chat_session(), name="chat_session"))
        else:
            # Adapter (PTY) mode: reply consumer + adapter session
            if self._channel and router:
                tasks.append(asyncio.create_task(self._reply_consumer(), name="reply_consumer"))
            elif not self._channel and router:
                # Channelless mode — poll DB for dashboard-originated replies
                tasks.append(asyncio.create_task(self._db_reply_poller(), name="db_reply_poller"))
            # Operator directives — always active (dashboard free-text input)
            directive_task = self._db_directive_poller()
            tasks.append(asyncio.create_task(directive_task, name="db_directive_poller"))
            if self._config.get("tool") and self._config.get("command"):
                tasks.append(
                    asyncio.create_task(self._run_adapter_session(), name="adapter_session")
                )

        tasks.append(asyncio.create_task(self._ttl_sweeper(), name="ttl_sweeper"))

        await self._shutdown_event.wait()

        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _reply_consumer(self) -> None:
        """Consume replies from the channel and hand them to the router."""
        assert self._channel is not None
        router = self._intent_router or self._router
        assert router is not None
        async for reply in self._channel.receive_replies():
            try:
                await router.handle_reply(reply)
            except Exception as exc:  # noqa: BLE001
                logger.error("reply_handling_error", error=str(exc))

    async def _db_reply_poller(self) -> None:
        """Poll DB for dashboard-originated replies (channelless mode).

        When no channel is configured, the dashboard Chat page is the relay.
        Users reply via ``POST /api/chat/reply`` → ``atlasbridge sessions reply``
        which atomically sets ``status = 'reply_received'`` in the DB.
        This loop detects those rows and injects them into the PTY.
        """
        router = self._intent_router or self._router
        assert router is not None
        while self._running:
            await asyncio.sleep(0.5)
            if self._db is None:
                continue
            try:
                rows = self._db.list_reply_received()
                for row in rows:
                    sid = row["session_id"]
                    ok = await router.inject_dashboard_reply(
                        prompt_id=row["id"],
                        session_id=sid,
                        value=row["response_normalized"],
                    )
                    if ok:
                        tw = self._transcript_writers.get(sid)
                        if tw is not None:
                            tw.record_input(row["response_normalized"], row["id"])
                        self._db.update_prompt_status(row["id"], "resolved")
            except Exception as exc:  # noqa: BLE001
                logger.error("db_reply_poller_error", error=str(exc))

    async def _db_directive_poller(self) -> None:
        """Poll DB for operator directives (free-text input from dashboard).

        The dashboard Chat page sends messages via
        ``POST /api/sessions/:id/message`` → ``atlasbridge sessions message``
        which inserts a row into operator_directives with status='pending'.
        This loop detects those rows and injects them into the PTY.
        """
        while self._running:
            await asyncio.sleep(0.5)
            if self._db is None:
                continue
            try:
                rows = self._db.list_pending_directives()
                for row in rows:
                    sid = row["session_id"]
                    content = row["content"]
                    directive_id = row["id"]

                    adapter = self._adapters.get(sid)
                    if adapter is None:
                        # No adapter — session not managed by this daemon.
                        # Mark processed to avoid infinite retry loop.
                        self._db.mark_directive_processed(directive_id)
                        logger.warning(
                            "directive_skipped_no_adapter",
                            directive_id=directive_id,
                            session_id=sid[:8],
                        )
                        continue

                    try:
                        await adapter.inject_reply(
                            session_id=sid,
                            value=content,
                            prompt_type="free_text",
                        )
                        tw = self._transcript_writers.get(sid)
                        if tw is not None:
                            tw.record_input(content, role="operator")
                        self._db.mark_directive_processed(directive_id)
                        logger.info(
                            "operator_directive_injected",
                            session_id=sid[:8],
                            directive_id=directive_id,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "directive_inject_failed",
                            directive_id=directive_id,
                            error=str(exc),
                        )
            except Exception as exc:  # noqa: BLE001
                logger.error("db_directive_poller_error", error=str(exc))

    async def _ttl_sweeper(self) -> None:
        """Periodically expire overdue prompts."""
        while self._running:
            await asyncio.sleep(10.0)
            router = self._intent_router or self._router
            if router:
                await router.expire_overdue()

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _setup_signal_handlers(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

    # ------------------------------------------------------------------
    # PID file
    # ------------------------------------------------------------------

    def _write_pid_file(self) -> None:
        pid_file = self._data_dir / "atlasbridge.pid"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

    def _remove_pid_file(self) -> None:
        pid_file = self._data_dir / "atlasbridge.pid"
        pid_file.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def _cleanup(self) -> None:
        self._running = False
        if self._channel:
            await self._channel.close()
        if self._db:
            self._db.close()
