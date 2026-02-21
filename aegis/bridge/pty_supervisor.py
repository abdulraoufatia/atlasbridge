"""
Aegis PTY supervisor — wraps a CLI tool in a pseudo-terminal.

The supervisor owns the event loop for one ``aegis run`` session:

  ┌──────────────────────────────────────────────────────────────────┐
  │  asyncio event loop                                              │
  │                                                                  │
  │  ┌─────────────┐   output   ┌──────────┐   prompt   ┌────────┐  │
  │  │ PTY reader  │──────────▶│ Detector │──────────▶│ Engine │  │
  │  └─────────────┘            └──────────┘            └───┬────┘  │
  │        ▲                                                 │       │
  │        │ inject                                  route   │       │
  │  ┌─────┴──────┐             ┌──────────────┐            │       │
  │  │ PTY writer │◀────────────│ Telegram bot │◀───────────┘       │
  │  └────────────┘  response   └──────────────┘                    │
  └──────────────────────────────────────────────────────────────────┘

Terminal fidelity
-----------------
The supervisor puts the host terminal into raw mode so all keystrokes
(arrows, Ctrl-C, etc.) are forwarded byte-for-byte to the child PTY.
Output from the child is forwarded to the host terminal unchanged so
colours, progress bars, and readline editing all work.

Prompt detection
----------------
A sliding window of recent output (``_output_buffer``) is fed to the
PromptDetector after each read chunk.  A separate asyncio.Task watches
for stdin stall: if the child produces no output for
``stuck_timeout_seconds`` the heuristic fires.

Response injection
------------------
When a response arrives via the Telegram queue the supervisor pauses
stdin forwarding, injects the response bytes into the PTY master, then
resumes forwarding.
"""

from __future__ import annotations

import asyncio
import logging
import os
import select
import signal
import sys
import termios
import tty
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import ptyprocess  # type: ignore[import]

from aegis.audit.writer import AuditWriter
from aegis.channels.telegram.bot import TelegramBot
from aegis.core.config import AegisConfig
from aegis.core.constants import (
    INJECT_BYTES,
    PromptStatus,
    SessionStatus,
    SupervisorState,
)
from aegis.policy.detector import PromptDetector
from aegis.policy.engine import PolicyAction, PolicyEngine
from aegis.store.database import Database
from aegis.store.models import PromptRecord, Session

log = logging.getLogger(__name__)

# Rolling output buffer size (bytes)
_BUFFER_SIZE = 4096
# PTY read chunk size
_READ_CHUNK = 1024
# Interval for the stall watchdog
_WATCHDOG_INTERVAL = 0.25


class PTYSupervisor:
    """
    Launch ``command`` inside a PTY and supervise it until it exits.

    Usage::

        sup = PTYSupervisor(command=["claude"], config=cfg, db=db, ...)
        await sup.run()
    """

    def __init__(
        self,
        command: list[str],
        config: AegisConfig,
        db: Database,
        audit: AuditWriter,
        bot: TelegramBot,
        session_id: str | None = None,
    ) -> None:
        self._command = command
        self._config = config
        self._db = db
        self._audit = audit
        self._bot = bot
        self._session_id = session_id or str(uuid.uuid4())

        self._detector = PromptDetector(threshold=config.adapters.claude.detection_threshold)
        self._engine = PolicyEngine(free_text_enabled=config.prompts.free_text_enabled)

        # asyncio.Queue: telegram bot puts (prompt_id, normalized_value) here
        self._response_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        self._state = SupervisorState.RUNNING
        self._proc: ptyprocess.PtyProcess | None = None
        self._output_buffer = bytearray()
        self._last_output_time: float = 0.0
        self._current_prompt_id: str | None = None
        self._injecting = False

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self) -> int:
        """
        Run the supervised command to completion.
        Returns the child's exit code (or 1 on error).
        """
        cwd = os.getcwd()
        session = Session(
            id=self._session_id,
            tool=self._command[0],
            cwd=cwd,
            pid=None,
        )
        self._db.save_session(session)
        self._audit.write_event(
            event_id=str(uuid.uuid4()),
            event_type="session_started",
            session_id=self._session_id,
            data={"command": self._command, "cwd": cwd},
        )

        # Wire the Telegram bot to our response queue
        self._bot._response_queue = self._response_queue

        exit_code = 1
        old_term_settings = None
        try:
            # Launch child in PTY
            cols, rows = _get_terminal_size()
            self._proc = ptyprocess.PtyProcess.spawn(
                self._command,
                dimensions=(rows, cols),
            )
            self._db.update_session(self._session_id, pid=self._proc.pid)
            self._last_output_time = asyncio.get_event_loop().time()

            log.info(
                "Spawned %s pid=%d in PTY (%dx%d)",
                self._command,
                self._proc.pid,
                cols,
                rows,
            )

            # Put host terminal into raw mode so control sequences pass through
            if sys.stdin.isatty():
                old_term_settings = termios.tcgetattr(sys.stdin.fileno())
                tty.setraw(sys.stdin.fileno())

            await self._bot.notify_session_started(self._session_id, cwd)

            # Run the three concurrent loops
            try:
                exit_code = await asyncio.wait_for(
                    self._event_loop(),
                    timeout=None,  # runs until child exits
                )
            except asyncio.CancelledError:
                log.info("Supervisor cancelled — sending SIGTERM to child")
                try:
                    self._proc.kill(signal.SIGTERM)
                except Exception:
                    pass
                exit_code = 130

        except Exception as exc:
            log.exception("PTY supervisor error: %s", exc)
            exit_code = 1
        finally:
            # Restore terminal
            if old_term_settings is not None:
                try:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_term_settings)
                except Exception:
                    pass

            self._db.update_session(
                self._session_id,
                status=SessionStatus.COMPLETED if exit_code == 0 else SessionStatus.CRASHED,
                ended_at=datetime.now(UTC).isoformat(),
                exit_code=exit_code,
            )
            self._audit.write_event(
                event_id=str(uuid.uuid4()),
                event_type="session_ended",
                session_id=self._session_id,
                data={"exit_code": exit_code},
            )
            await self._bot.notify_session_ended(self._session_id, exit_code)
            log.info("Session %s ended (exit=%d)", self._session_id[:8], exit_code)

        return exit_code

    # ------------------------------------------------------------------
    # Concurrent event loop
    # ------------------------------------------------------------------

    async def _event_loop(self) -> int:
        """Run PTY reader, stdin relay, stall watchdog, and response consumer."""
        tasks = [
            asyncio.create_task(self._pty_reader(), name="pty-reader"),
            asyncio.create_task(self._stdin_relay(), name="stdin-relay"),
            asyncio.create_task(self._stall_watchdog(), name="stall-watchdog"),
            asyncio.create_task(self._response_consumer(), name="response-consumer"),
        ]

        # Wait for child to exit (detected in pty_reader) or any task to fail
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        # Retrieve exit code
        if self._proc:
            try:
                return self._proc.wait()
            except Exception:
                pass
        return 0

    # ------------------------------------------------------------------
    # PTY reader
    # ------------------------------------------------------------------

    async def _pty_reader(self) -> None:
        """Read child output, forward to stdout, feed the detector."""
        loop = asyncio.get_event_loop()
        assert self._proc is not None
        fd = self._proc.fd

        while True:
            # Non-blocking select so we yield control to other tasks
            readable, _, _ = await loop.run_in_executor(
                None, lambda: select.select([fd], [], [], 0.05)
            )
            if not readable:
                await asyncio.sleep(0)
                continue

            try:
                chunk = os.read(fd, _READ_CHUNK)
            except OSError:
                # Child closed the PTY — it has exited
                break

            if not chunk:
                break

            # Forward to the real terminal
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()

            # Update output buffer and timestamp
            self._output_buffer.extend(chunk)
            if len(self._output_buffer) > _BUFFER_SIZE:
                del self._output_buffer[: len(self._output_buffer) - _BUFFER_SIZE]
            self._last_output_time = loop.time()

            # Run detector if we're not mid-injection and not already waiting
            if self._state == SupervisorState.RUNNING and not self._injecting:
                text = self._output_buffer.decode("utf-8", errors="replace")
                result = self._detector.detect(text)
                if result.detected and result.is_confident:
                    await self._handle_detection(result)

    # ------------------------------------------------------------------
    # Stdin relay
    # ------------------------------------------------------------------

    async def _stdin_relay(self) -> None:
        """Forward host stdin → child PTY (pass-through while not injecting)."""
        loop = asyncio.get_event_loop()
        assert self._proc is not None
        fd_in = sys.stdin.fileno()
        fd_pty = self._proc.fd

        while True:
            if self._injecting:
                await asyncio.sleep(0.05)
                continue

            readable, _, _ = await loop.run_in_executor(
                None, lambda: select.select([fd_in], [], [], 0.05)
            )
            if not readable:
                await asyncio.sleep(0)
                continue

            try:
                data = os.read(fd_in, _READ_CHUNK)
            except OSError:
                break
            if not data:
                break

            try:
                os.write(fd_pty, data)
            except OSError:
                break

    # ------------------------------------------------------------------
    # Stall watchdog
    # ------------------------------------------------------------------

    async def _stall_watchdog(self) -> None:
        """
        Detect when the child has stopped producing output (possible prompt).
        Fires the blocking heuristic after stuck_timeout_seconds.
        """
        stuck_timeout = self._config.prompts.stuck_timeout_seconds
        loop = asyncio.get_event_loop()

        while True:
            await asyncio.sleep(_WATCHDOG_INTERVAL)

            if self._state != SupervisorState.RUNNING or self._injecting:
                continue

            elapsed = loop.time() - self._last_output_time
            if elapsed < stuck_timeout:
                continue

            # Has the buffer end look like a prompt?
            text = self._output_buffer.decode("utf-8", errors="replace")
            # Only fire if buffer is non-empty and ends with a prompt-like line
            stripped = text.rstrip()
            if not stripped:
                continue

            # Already detected via patterns? Skip heuristic
            pattern_result = self._detector.detect(stripped[-512:])
            if pattern_result.detected:
                continue

            # Fire blocking heuristic
            result = self._detector.detect_blocking(stripped[-512:])
            log.debug("Stall heuristic fired after %.1fs (conf=%.2f)", elapsed, result.confidence)
            await self._handle_detection(result)

    # ------------------------------------------------------------------
    # Response consumer
    # ------------------------------------------------------------------

    async def _response_consumer(self) -> None:
        """
        Wait for a response from Telegram and inject it into the PTY.
        """
        while True:
            prompt_id, normalized = await self._response_queue.get()

            # Validate this is the prompt we're waiting for
            if self._current_prompt_id and prompt_id != self._current_prompt_id:
                log.warning(
                    "Received response for stale prompt %s (current=%s)",
                    prompt_id[:8],
                    str(self._current_prompt_id)[:8],
                )
                self._response_queue.task_done()
                continue

            await self._inject_response(prompt_id, normalized)
            self._response_queue.task_done()

    # ------------------------------------------------------------------
    # Prompt handling
    # ------------------------------------------------------------------

    async def _handle_detection(self, result: Any) -> None:
        if self._state != SupervisorState.RUNNING:
            return  # Already processing a prompt

        self._state = SupervisorState.PROMPT_DETECTED
        log.info(
            "Prompt detected: type=%s conf=%.2f method=%s",
            result.prompt_type,
            result.confidence,
            result.method,
        )

        # Policy decision
        decision = self._engine.evaluate(result)

        if decision.action == PolicyAction.AUTO_INJECT:
            inject_val = decision.inject_value or ""
            await self._inject_auto(inject_val, reason=decision.reason)
            return

        # ROUTE_TO_USER: create DB record and send to Telegram
        self._state = SupervisorState.AWAITING_RESPONSE
        prompt = await self._create_prompt_record(result)
        self._current_prompt_id = prompt.id
        self._db.save_prompt(prompt)

        self._audit.write_event(
            event_id=str(uuid.uuid4()),
            event_type="prompt_created",
            session_id=self._session_id,
            prompt_id=prompt.id,
            data={
                "type": prompt.input_type,
                "confidence": result.confidence,
                "method": result.method,
            },
        )

        msg_id = await self._bot.send_prompt(prompt)
        if msg_id:
            self._db.update_prompt(
                prompt.id, status=PromptStatus.TELEGRAM_SENT, telegram_msg_id=msg_id
            )

        # Start timeout task
        asyncio.create_task(
            self._prompt_timeout(prompt),
            name=f"prompt-timeout-{prompt.id[:8]}",
        )

    async def _create_prompt_record(self, result: Any) -> PromptRecord:
        import secrets

        timeout = self._config.prompts.timeout_seconds
        expires_at = (datetime.now(UTC) + timedelta(seconds=timeout)).isoformat()

        from aegis.core.constants import SAFE_DEFAULTS

        safe_default = SAFE_DEFAULTS.get(result.prompt_type, "n")
        pr = PromptRecord(
            id=str(uuid.uuid4()),
            session_id=self._session_id,
            input_type=result.prompt_type,
            excerpt=result.excerpt,
            confidence=result.confidence,
            nonce=secrets.token_hex(16),
            expires_at=expires_at,
            safe_default=safe_default,
            detection_method=result.method,
        )
        pr.choices = result.choices
        return pr

    async def _prompt_timeout(self, prompt: PromptRecord) -> None:
        """Wait for the prompt TTL; inject safe default if still pending."""
        await asyncio.sleep(prompt.ttl_remaining_seconds + 0.5)

        # Check if already answered
        current = self._db.get_prompt(prompt.id)
        if current and current.status not in (
            PromptStatus.RESPONSE_RECEIVED,
            PromptStatus.INJECTED,
            PromptStatus.AUTO_INJECTED,
        ):
            log.info("Prompt %s timed out — injecting safe default", prompt.short_id)
            self._db.update_prompt(prompt.id, status=PromptStatus.EXPIRED)
            await self._bot.send_timeout_notice(prompt, prompt.safe_default)
            await self._inject_response(prompt.id, prompt.safe_default, timed_out=True)

    async def _inject_response(
        self, prompt_id: str, normalized: str, timed_out: bool = False
    ) -> None:
        assert self._proc is not None
        self._injecting = True
        self._state = SupervisorState.INJECTING

        inject_bytes = INJECT_BYTES.get(normalized, normalized.encode() + b"\r")

        try:
            os.write(self._proc.fd, inject_bytes)
            log.info(
                "Injected %r for prompt %s",
                inject_bytes,
                str(prompt_id)[:8],
            )
            status = PromptStatus.AUTO_INJECTED if timed_out else PromptStatus.INJECTED
            self._db.update_prompt(
                prompt_id,
                status=status,
                decided_at=datetime.now(UTC).isoformat(),
            )
            self._audit.write_event(
                event_id=str(uuid.uuid4()),
                event_type="response_injected",
                session_id=self._session_id,
                prompt_id=prompt_id,
                data={"value": normalized, "timed_out": timed_out},
            )
        except OSError as exc:
            log.error("Injection failed: %s", exc)
        finally:
            self._injecting = False
            self._current_prompt_id = None
            self._state = SupervisorState.RUNNING
            # Clear the output buffer so old prompt text doesn't re-trigger
            self._output_buffer.clear()
            self._last_output_time = asyncio.get_event_loop().time()

    async def _inject_auto(self, value: str, reason: str) -> None:
        """Auto-inject without routing to Telegram (policy-driven)."""
        inject_bytes = INJECT_BYTES.get(value, value.encode() + b"\r")
        self._injecting = True
        try:
            assert self._proc is not None
            os.write(self._proc.fd, inject_bytes)
            log.info("Auto-injected %r (%s)", value, reason)
            self._audit.write_event(
                event_id=str(uuid.uuid4()),
                event_type="auto_injected",
                session_id=self._session_id,
                data={"value": value, "reason": reason},
            )
        except OSError as exc:
            log.error("Auto-injection failed: %s", exc)
        finally:
            self._injecting = False
            self._state = SupervisorState.RUNNING
            self._output_buffer.clear()
            self._last_output_time = asyncio.get_event_loop().time()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_terminal_size() -> tuple[int, int]:
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except OSError:
        return 80, 24
