"""Aegis data models: dataclasses for SQLite-backed entities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s)


@dataclass
class Session:
    id: str
    tool: str
    cwd: str
    started_at: str = field(default_factory=_now_iso)
    pid: int | None = None
    status: str = "active"
    ended_at: str | None = None
    exit_code: int | None = None
    prompt_count: int = 0

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "cwd": self.cwd,
            "started_at": self.started_at,
            "pid": self.pid,
            "status": self.status,
            "ended_at": self.ended_at,
            "exit_code": self.exit_code,
            "prompt_count": self.prompt_count,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Session":
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})

    @property
    def started_dt(self) -> datetime:
        return datetime.fromisoformat(self.started_at)

    @property
    def ended_dt(self) -> datetime | None:
        return _dt(self.ended_at)


@dataclass
class PromptRecord:
    id: str
    session_id: str
    input_type: str
    excerpt: str
    confidence: float
    nonce: str
    expires_at: str
    created_at: str = field(default_factory=_now_iso)
    choices_json: str = "[]"
    status: str = "pending"
    safe_default: str = "n"
    telegram_msg_id: int | None = None
    nonce_used: bool = False
    decided_at: str | None = None
    decided_by: str | None = None
    response_normalized: str | None = None
    detection_method: str = "text_pattern"

    @property
    def choices(self) -> list[str]:
        return json.loads(self.choices_json)

    @choices.setter
    def choices(self, value: list[str]) -> None:
        self.choices_json = json.dumps(value)

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "input_type": self.input_type,
            "excerpt": self.excerpt,
            "confidence": self.confidence,
            "nonce": self.nonce,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "choices_json": self.choices_json,
            "status": self.status,
            "safe_default": self.safe_default,
            "telegram_msg_id": self.telegram_msg_id,
            "nonce_used": int(self.nonce_used),
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "response_normalized": self.response_normalized,
            "detection_method": self.detection_method,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PromptRecord":
        d = dict(row)
        d["nonce_used"] = bool(d.get("nonce_used", 0))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > datetime.fromisoformat(self.expires_at)

    @property
    def short_id(self) -> str:
        return self.id[:6]

    @property
    def ttl_remaining_seconds(self) -> float:
        exp = datetime.fromisoformat(self.expires_at)
        now = datetime.now(timezone.utc)
        return max(0.0, (exp - now).total_seconds())


@dataclass
class AuditEvent:
    id: str
    event_type: str
    ts: str = field(default_factory=_now_iso)
    seq: int = 0
    session_id: str | None = None
    prompt_id: str | None = None
    data_json: str = "{}"
    prev_hash: str = "genesis"
    hash: str = ""

    @property
    def data(self) -> dict[str, Any]:
        return json.loads(self.data_json)

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "ts": self.ts,
            "seq": self.seq,
            "session_id": self.session_id,
            "prompt_id": self.prompt_id,
            "data_json": self.data_json,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }
