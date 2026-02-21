"""
Session domain models.

A Session represents one invocation of a CLI tool under AtlasBridge supervision.
Sessions are identified by a UUID and are associated with exactly one
PTY supervisor and zero or more PromptEvents.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class SessionStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    AWAITING_REPLY = "awaiting_reply"  # Active prompt pending
    COMPLETED = "completed"
    CRASHED = "crashed"
    CANCELED = "canceled"


@dataclass
class Session:
    """Represents one CLI tool session managed by AtlasBridge."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool: str = ""  # Adapter name (e.g. "claude", "openai")
    command: list[str] = field(default_factory=list)
    cwd: str = ""
    pid: int = -1
    status: SessionStatus = SessionStatus.STARTING
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ended_at: str = ""
    exit_code: int | None = None

    # Metadata
    label: str = ""  # Optional human label (e.g. git branch name)
    channel_message_ids: dict[str, str] = field(default_factory=dict)
    active_prompt_id: str = ""  # prompt_id of current active prompt, or ""
    prompt_count: int = 0  # Total prompts seen this session
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_running(self, pid: int) -> None:
        self.pid = pid
        self.status = SessionStatus.RUNNING

    def mark_awaiting_reply(self, prompt_id: str) -> None:
        self.active_prompt_id = prompt_id
        self.status = SessionStatus.AWAITING_REPLY
        self.prompt_count += 1

    def mark_reply_received(self) -> None:
        self.active_prompt_id = ""
        self.status = SessionStatus.RUNNING

    def mark_ended(self, exit_code: int | None = None, crashed: bool = False) -> None:
        self.exit_code = exit_code
        self.ended_at = datetime.now(UTC).isoformat()
        self.status = SessionStatus.CRASHED if crashed else SessionStatus.COMPLETED

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            SessionStatus.COMPLETED,
            SessionStatus.CRASHED,
            SessionStatus.CANCELED,
        )

    @property
    def is_active(self) -> bool:
        return not self.is_terminal

    def short_id(self) -> str:
        """First 8 chars of session_id for display."""
        return self.session_id[:8]
