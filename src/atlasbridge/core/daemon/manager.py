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

    async def start(self) -> None:
        """Start all subsystems and run until shutdown."""
        logger.info("daemon_starting", pid=os.getpid(), data_dir=str(self._data_dir))
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
        if not pending or self._channel is None:
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
        channel_config = self._config.get("channels", {})
        channels: list[Any] = []

        telegram_cfg = channel_config.get("telegram", {})
        if telegram_cfg:
            from atlasbridge.channels.telegram.channel import TelegramChannel

            channels.append(
                TelegramChannel(
                    bot_token=telegram_cfg["bot_token"],
                    allowed_user_ids=telegram_cfg.get("allowed_user_ids", []),
                )
            )

        slack_cfg = channel_config.get("slack", {})
        if slack_cfg:
            from atlasbridge.channels.slack.channel import SlackChannel

            channels.append(
                SlackChannel(
                    bot_token=slack_cfg["bot_token"],
                    app_token=slack_cfg["app_token"],
                    allowed_user_ids=slack_cfg.get("allowed_user_ids", []),
                )
            )

        if not channels:
            logger.warning("no_channel_configured")
            return

        if len(channels) == 1:
            self._channel = channels[0]
        else:
            from atlasbridge.channels.multi import MultiChannel

            self._channel = MultiChannel(channels)

        await self._channel.start()

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

    def _init_intent_router(self) -> None:
        """Wrap the PromptRouter with intent classification."""
        if self._router is None or self._policy is None:
            return

        from atlasbridge.core.routing.intent import IntentRouter, PolicyRouteClassifier

        classifier = PolicyRouteClassifier(policy=self._policy)
        self._intent_router = IntentRouter(
            prompt_router=self._router,
            classifier=classifier,
            # Handlers are None in Feature 1 — all intents fall through to channel.
            # Wired in Feature 2: autopilot_handler, deny_handler.
        )
        logger.info("intent_router_initialized")

    async def _init_router(self) -> None:
        if self._session_manager is None or self._channel is None:
            return
        from atlasbridge.core.routing.router import PromptRouter

        self._router = PromptRouter(
            session_manager=self._session_manager,
            channel=self._channel,
            adapter_map=self._adapters,
            store=self._db,
            conversation_registry=self._conversation_registry,
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

        # Session lifecycle: notify channel of session start
        if self._channel is not None:
            await self._channel.notify(
                f"Session started: {tool} ({session_id[:8]})",
                session_id=session_id,
            )

        await adapter.start_session(session_id=session_id, command=list(command))

        # Mark the session as running once the child PID is known
        ctx = adapter.snapshot_context(session_id)
        pid = ctx.get("pid", -1)
        if pid and pid > 0:
            self._session_manager.mark_running(session_id, pid)

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
        except* asyncio.CancelledError:
            pass
        finally:
            logger.info("session_ended", session_id=session_id[:8])
            self._session_manager.mark_ended(session_id)

            # Unbind conversation threads for this session
            if self._conversation_registry is not None:
                self._conversation_registry.unbind(session_id)

            # Session lifecycle: notify channel of session end
            if self._channel is not None:
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
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Run the reply consumer, TTL sweeper, and adapter session until shutdown."""
        tasks: list[asyncio.Task[Any]] = []
        router = self._intent_router or self._router
        if self._channel and router:
            tasks.append(asyncio.create_task(self._reply_consumer(), name="reply_consumer"))
        tasks.append(asyncio.create_task(self._ttl_sweeper(), name="ttl_sweeper"))
        if self._config.get("tool") and self._config.get("command"):
            tasks.append(asyncio.create_task(self._run_adapter_session(), name="adapter_session"))

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
