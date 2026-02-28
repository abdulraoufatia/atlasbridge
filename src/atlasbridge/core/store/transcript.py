"""
Batched transcript writer for live session output.

Captures PTY output and injected input, persists to the transcript_chunks
table for dashboard live transcript display.
"""

from __future__ import annotations

import asyncio

import structlog

from atlasbridge.core.prompt.sanitize import is_meaningful, strip_ansi
from atlasbridge.core.security.redactor import redact

from .database import Database

logger = structlog.get_logger()

_MAX_BUFFER_BYTES = 16_384  # 16 KB internal buffer cap
_MAX_CHUNK_CHARS = 8_000  # 8 KB per persisted chunk


class TranscriptWriter:
    """Batched writer that persists PTY output for dashboard live transcript."""

    def __init__(
        self,
        db: Database,
        session_id: str,
        flush_interval: float = 2.0,
    ) -> None:
        self._db = db
        self._session_id = session_id
        self._flush_interval = flush_interval
        self._buffer: list[str] = []
        self._buffer_chars = 0
        self._seq = 0
        self._lock = asyncio.Lock()

    def feed(self, raw: bytes) -> None:
        """Accept raw PTY bytes, sanitize, and buffer for batch write."""
        try:
            text = strip_ansi(raw.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            return
        if not text or not is_meaningful(text):
            return
        text = redact(text)
        self._buffer.append(text)
        self._buffer_chars += len(text)
        # Cap internal buffer
        if self._buffer_chars > _MAX_BUFFER_BYTES:
            self._compact_buffer()

    def record_input(self, text: str, prompt_id: str = "", role: str = "user") -> None:
        """Record input into the transcript (written immediately).

        Args:
            text: The input text.
            prompt_id: Optional prompt ID this input is replying to.
            role: Transcript role — ``"user"`` for prompt replies,
                  ``"operator"`` for operator directives.
        """
        self._seq += 1
        try:
            self._db.save_transcript_chunk(
                session_id=self._session_id,
                role=role,
                content=redact(text)[:_MAX_CHUNK_CHARS],
                seq=self._seq,
                prompt_id=prompt_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("transcript_record_input_error", error=str(exc))

    async def flush_loop(self) -> None:
        """Background loop: flush buffer to DB every flush_interval seconds."""
        try:
            while True:
                await asyncio.sleep(self._flush_interval)
                await self._flush()
        except asyncio.CancelledError:
            await self._flush()
            raise

    async def _flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            merged = "".join(self._buffer)
            self._buffer.clear()
            self._buffer_chars = 0

        if len(merged) > _MAX_CHUNK_CHARS:
            merged = merged[:_MAX_CHUNK_CHARS] + "\n...(truncated)"

        self._seq += 1
        try:
            self._db.save_transcript_chunk(
                session_id=self._session_id,
                role="agent",
                content=merged,
                seq=self._seq,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("transcript_flush_error", error=str(exc))

    def _compact_buffer(self) -> None:
        """Drop oldest entries to stay within buffer cap."""
        while self._buffer_chars > _MAX_BUFFER_BYTES and self._buffer:
            dropped = self._buffer.pop(0)
            self._buffer_chars -= len(dropped)
