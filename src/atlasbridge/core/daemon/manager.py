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
import logging
import os
import signal
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
        self._db = None
        self._channel = None
        self._session_manager = None
        self._router = None
        self._adapters: dict[str, Any] = {}
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._policy: Any = None  # Policy | PolicyV1, loaded in _init_autopilot

    async def start(self) -> None:
        """Start all subsystems and run until shutdown."""
        logger.info("AtlasBridge daemon starting")
        self._write_pid_file()

        try:
            await self._init_database()
            await self._reload_pending_prompts()
            await self._init_channel()
            await self._init_session_manager()
            await self._init_router()
            await self._init_autopilot()

            self._running = True
            self._setup_signal_handlers()

            logger.info("AtlasBridge daemon ready")
            await self._run_loop()

        finally:
            await self._cleanup()
            self._remove_pid_file()
            logger.info("AtlasBridge daemon stopped")

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
        logger.info("Database connected: %s", db_path)

    async def _reload_pending_prompts(self) -> None:
        """On restart, reload pending prompts from the database."""
        if self._db is None:
            return
        pending = self._db.list_pending_prompts()
        if pending:
            logger.info(
                "Daemon restarted with %d pending prompt(s) — will renotify",
                len(pending),
            )
        # TODO: renotify via channel after channel is initialised

    async def _init_channel(self) -> None:
        channel_config = self._config.get("channels", {})
        channels = []

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
            logger.warning("No channel configured — prompts will not be routed")
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

    async def _init_autopilot(self) -> None:
        """Load the policy for this session (from --policy file or built-in default)."""
        from atlasbridge.core.policy.parser import PolicyParseError, default_policy, load_policy

        policy_file = self._config.get("policy_file", "")
        if policy_file:
            try:
                self._policy = load_policy(policy_file)
                logger.info("Policy loaded from %s", policy_file)
            except PolicyParseError as exc:
                logger.error("Failed to load policy %s: %s — using safe default", policy_file, exc)
                self._policy = default_policy()
        else:
            self._policy = default_policy()

    async def _init_router(self) -> None:
        if self._session_manager is None or self._channel is None:
            return
        from atlasbridge.core.routing.router import PromptRouter

        self._router = PromptRouter(
            session_manager=self._session_manager,
            channel=self._channel,
            adapter_map=self._adapters,
            store=self._db,
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
            logger.info("No tool/command configured — running in channel-only mode")
            return

        from atlasbridge.adapters.base import AdapterRegistry
        from atlasbridge.core.session.models import Session

        try:
            adapter_cls = AdapterRegistry.get(tool)
        except KeyError as exc:
            logger.error("Cannot start adapter: %s", exc)
            return

        adapter = adapter_cls()
        session_id = str(uuid.uuid4())

        session = Session(session_id=session_id, tool=tool, command=list(command))
        if self._session_manager is None:
            logger.error("Session manager not initialised — cannot start session")
            return
        self._session_manager.register(session)
        self._adapters[session_id] = adapter

        logger.info("Starting %r session %s", tool, session_id[:8])
        await adapter.start_session(session_id=session_id, command=list(command))

        # Mark the session as running once the child PID is known
        ctx = adapter.snapshot_context(session_id)
        pid = ctx.get("pid", -1)
        if pid and pid > 0:
            self._session_manager.mark_running(session_id, pid)

        # Re-use the detector the adapter already created for this session.
        # This ensures inject_reply() → mark_injected() shares the same state
        # as our analyse() calls (echo suppression depends on this).
        detector = adapter._detectors.get(session_id)  # type: ignore[attr-defined]
        if detector is None:
            from atlasbridge.core.prompt.detector import PromptDetector

            detector = PromptDetector(session_id)

        event_q: asyncio.Queue[Any] = asyncio.Queue()
        eof_reached = asyncio.Event()

        async def _read_loop() -> None:
            try:
                while True:
                    chunk = await adapter.read_stream(session_id)
                    if not chunk:
                        break
                    tty_blocked = await adapter.await_input_state(session_id)
                    ev = detector.analyse(chunk, tty_blocked=tty_blocked)
                    if ev is not None and self._router is not None:
                        await event_q.put(ev)
            finally:
                eof_reached.set()

        async def _route_events() -> None:
            while not eof_reached.is_set() or not event_q.empty():
                try:
                    ev = await asyncio.wait_for(event_q.get(), timeout=0.2)
                    if self._router is not None:
                        await self._router.route_event(ev)
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
                if ev is not None and self._router is not None:
                    await self._router.route_event(ev)

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(_read_loop(), name="pty_read")
                tg.create_task(_route_events(), name="route_events")
                tg.create_task(_silence_watchdog(), name="silence_watchdog")
        except* asyncio.CancelledError:
            pass
        finally:
            logger.info("Session %s ended — requesting daemon shutdown", session_id[:8])
            self._session_manager.mark_ended(session_id)
            await adapter.terminate_session(session_id)
            await self.stop()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Run the reply consumer, TTL sweeper, and adapter session until shutdown."""
        tasks: list[asyncio.Task[Any]] = []
        if self._channel and self._router:
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
        assert self._router is not None
        async for reply in self._channel.receive_replies():
            try:
                await self._router.handle_reply(reply)
            except Exception as exc:  # noqa: BLE001
                logger.error("Reply handling error: %s", exc)

    async def _ttl_sweeper(self) -> None:
        """Periodically expire overdue prompts."""
        while self._running:
            await asyncio.sleep(10.0)
            if self._router:
                await self._router.expire_overdue()

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
