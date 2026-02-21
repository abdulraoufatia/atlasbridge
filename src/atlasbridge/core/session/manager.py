"""
Session manager.

The SessionManager maintains the registry of active and recent sessions.
It is the single source of truth for session state in memory.
Persistent state is written to the SQLite store by the daemon.

Invariants:
  - Session IDs are globally unique UUIDs.
  - At most one active prompt per session at a time.
  - Sessions are never deleted from the in-memory registry during a
    daemon run — they are marked terminal and retained for audit queries.
"""

from __future__ import annotations

from collections.abc import Iterator

import structlog

from atlasbridge.core.session.models import Session, SessionStatus

logger = structlog.get_logger()


class SessionNotFoundError(Exception):
    """Raised when a session_id is not in the registry."""


class SessionManager:
    """
    In-memory session registry.

    Thread-safe for single-threaded asyncio use. All public methods are
    synchronous (no I/O) and must be called from the event loop thread.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, session: Session) -> None:
        """Add a new session to the registry."""
        if session.session_id in self._sessions:
            raise ValueError(f"Session {session.session_id!r} already registered")
        self._sessions[session.session_id] = session
        logger.info("session_registered", session_id=session.short_id(), tool=session.tool)

    def get(self, session_id: str) -> Session:
        """Return the session; raise SessionNotFoundError if not found."""
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFoundError(f"Session not found: {session_id!r}") from None

    def get_or_none(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all_sessions(self) -> Iterator[Session]:
        yield from self._sessions.values()

    def active_sessions(self) -> list[Session]:
        return [s for s in self._sessions.values() if s.is_active]

    def sessions_with_pending_prompt(self) -> list[Session]:
        return [s for s in self._sessions.values() if s.status == SessionStatus.AWAITING_REPLY]

    def count_active(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_active)

    # ------------------------------------------------------------------
    # State transitions (delegate to Session methods)
    # ------------------------------------------------------------------

    def mark_running(self, session_id: str, pid: int) -> None:
        session = self.get(session_id)
        session.mark_running(pid)
        logger.info("session_running", session_id=session.short_id(), pid=pid)

    def mark_awaiting_reply(self, session_id: str, prompt_id: str) -> None:
        session = self.get(session_id)
        session.mark_awaiting_reply(prompt_id)

    def mark_reply_received(self, session_id: str) -> None:
        session = self.get(session_id)
        session.mark_reply_received()

    def mark_ended(
        self,
        session_id: str,
        exit_code: int | None = None,
        crashed: bool = False,
    ) -> None:
        session = self.get(session_id)
        session.mark_ended(exit_code=exit_code, crashed=crashed)
        status_str = "crashed" if crashed else "completed"
        logger.info(
            "session_ended",
            session_id=session.short_id(),
            status=status_str,
            exit_code=exit_code,
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def prune_terminal(self, keep_last: int = 50) -> int:
        """
        Remove terminal sessions beyond the last *keep_last*.

        Returns the number of sessions pruned.
        """
        terminal = [s for s in self._sessions.values() if s.is_terminal]
        terminal.sort(key=lambda s: s.ended_at or s.started_at)
        to_prune = terminal[:-keep_last] if len(terminal) > keep_last else []
        for s in to_prune:
            del self._sessions[s.session_id]
        return len(to_prune)
