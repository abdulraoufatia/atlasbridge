"""
Audit event writer.

Structured audit events written to the SQLite audit log.
All events use consistent field names for grep/jq searchability.

Event types:
  session_started        — new CLI session opened
  session_ended          — CLI session terminated
  prompt_detected        — PromptDetector fired
  prompt_routed          — sent to channel
  reply_received         — user tapped a button or replied
  response_injected      — bytes written to PTY stdin
  prompt_expired         — TTL elapsed, safe default applied
  prompt_canceled        — user or system canceled the prompt
  duplicate_callback     — idempotency guard: second callback rejected
  late_reply_rejected    — reply arrived after TTL expiry
  invalid_callback       — callback with unknown/mismatched prompt_id
  ambiguous_reply_held   — free-text with multiple active sessions
  telegram_polling_failed — Telegram API unreachable
  daemon_restarted       — daemon process restarted
  child_process_died     — child CLI process exited unexpectedly

Hash chain:
  Each event includes prev_hash (the SHA-256 of the previous event) and
  its own hash, forming an append-only chain. Truncation is detectable.
"""

from __future__ import annotations

import secrets
from typing import Any

from atlasbridge.core.store.database import Database


class AuditWriter:
    """
    Writes structured audit events to the database.

    Usage::

        writer = AuditWriter(db)
        writer.session_started("session-id", "claude", ["claude", "--no-browser"])
        writer.prompt_detected("session-id", "prompt-id", "yes_no", "high")
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def _write(
        self,
        event_type: str,
        payload: dict[str, Any],
        session_id: str = "",
        prompt_id: str = "",
    ) -> None:
        event_id = secrets.token_hex(12)
        self._db.append_audit_event(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            session_id=session_id,
            prompt_id=prompt_id,
        )

    def session_started(self, session_id: str, tool: str, command: list[str]) -> None:
        self._write(
            "session_started",
            {"tool": tool, "command": command},
            session_id=session_id,
        )

    def session_ended(
        self,
        session_id: str,
        exit_code: int | None,
        crashed: bool = False,
    ) -> None:
        self._write(
            "session_ended",
            {"exit_code": exit_code, "crashed": crashed},
            session_id=session_id,
        )

    def prompt_detected(
        self,
        session_id: str,
        prompt_id: str,
        prompt_type: str,
        confidence: str,
        excerpt: str = "",
        trigger: str = "pattern_match",
    ) -> None:
        self._write(
            "prompt_detected",
            {
                "prompt_type": prompt_type,
                "confidence": confidence,
                "excerpt_length": len(excerpt),
                "trigger": trigger,
            },
            session_id=session_id,
            prompt_id=prompt_id,
        )

    def prompt_routed(
        self,
        session_id: str,
        prompt_id: str,
        channel: str,
        message_id: str = "",
    ) -> None:
        self._write(
            "prompt_routed",
            {"channel": channel, "message_id": message_id},
            session_id=session_id,
            prompt_id=prompt_id,
        )

    def reply_received(
        self,
        session_id: str,
        prompt_id: str,
        channel_identity: str,
        value: str,
        nonce: str,
    ) -> None:
        self._write(
            "reply_received",
            {
                "channel_identity": channel_identity,
                "value_length": len(value),
                "nonce": nonce,
            },
            session_id=session_id,
            prompt_id=prompt_id,
        )

    def response_injected(
        self,
        session_id: str,
        prompt_id: str,
        prompt_type: str,
        value: str,
        latency_ms: float | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "prompt_type": prompt_type,
            "value_length": len(value),
        }
        if latency_ms is not None:
            payload["latency_ms"] = round(latency_ms, 1)
        self._write(
            "response_injected",
            payload,
            session_id=session_id,
            prompt_id=prompt_id,
        )

    def prompt_expired(self, session_id: str, prompt_id: str) -> None:
        self._write("prompt_expired", {}, session_id=session_id, prompt_id=prompt_id)

    def duplicate_callback(self, session_id: str, prompt_id: str, nonce: str) -> None:
        self._write(
            "duplicate_callback_ignored",
            {"nonce": nonce, "rows_affected": 0},
            session_id=session_id,
            prompt_id=prompt_id,
        )

    def late_reply_rejected(
        self, session_id: str, prompt_id: str, expired_at: str, reply_at: str
    ) -> None:
        self._write(
            "late_reply_rejected",
            {"expired_at": expired_at, "reply_arrived_at": reply_at},
            session_id=session_id,
            prompt_id=prompt_id,
        )

    def invalid_callback(
        self,
        attempted_prompt_id: str,
        reason: str,
        session_id: str = "",
    ) -> None:
        self._write(
            "invalid_callback",
            {"attempted_prompt_id": attempted_prompt_id, "reason": reason},
            session_id=session_id,
        )

    def telegram_polling_failed(self, error: str, backoff_seconds: float) -> None:
        self._write(
            "telegram_polling_failed",
            {"error": error, "backoff_seconds": backoff_seconds},
        )

    def daemon_restarted(self, prompts_reloaded: int) -> None:
        self._write(
            "daemon_restarted",
            {"prompts_reloaded": prompts_reloaded},
        )
