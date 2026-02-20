"""Aegis constants: exit codes, enumerations, and defaults."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    ERROR = 1
    CONFIG_ERROR = 2
    ENV_ERROR = 3
    NETWORK_ERROR = 4
    PERMISSION_ERROR = 5
    SECURITY_VIOLATION = 6
    DEPENDENCY_MISSING = 7
    STATE_CORRUPTION = 8


class PromptType(StrEnum):
    YES_NO = "TYPE_YES_NO"
    CONFIRM_ENTER = "TYPE_CONFIRM_ENTER"
    MULTIPLE_CHOICE = "TYPE_MULTIPLE_CHOICE"
    FREE_TEXT = "TYPE_FREE_TEXT"
    UNKNOWN = "TYPE_UNKNOWN"


class PromptStatus(StrEnum):
    PENDING = "pending"
    TELEGRAM_SENT = "telegram_sent"
    AWAITING_RESPONSE = "awaiting_response"
    RESPONSE_RECEIVED = "response_received"
    INJECTING = "injecting"
    INJECTED = "injected"
    EXPIRED = "expired"
    AUTO_INJECTED = "auto_injected"
    POLICY_DENIED = "policy_denied"
    ABORTED_CRASH = "aborted_crash"
    ABORTED_SHUTDOWN = "aborted_shutdown"
    QUEUED = "queued"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CRASHED = "crashed"
    TERMINATED = "terminated"


class PolicyAction(StrEnum):
    ROUTE_TO_USER = "route_to_user"
    AUTO_INJECT = "auto_inject"
    DENY = "deny"


class SupervisorState(StrEnum):
    RUNNING = "running"
    PROMPT_DETECTED = "prompt_detected"
    AWAITING_RESPONSE = "awaiting_response"
    INJECTING = "injecting"
    DONE = "done"


# Filesystem layout
AEGIS_DIR_NAME = ".aegis"
CONFIG_FILENAME = "config.toml"
DB_FILENAME = "aegis.db"
AUDIT_FILENAME = "audit.log"
PID_FILENAME = "aegis.pid"
LOG_FILENAME = "aegis.log"
LAUNCHD_LABEL = "com.aegis-cli.aegis"

# Timeouts and limits
DEFAULT_PROMPT_TIMEOUT_SECONDS = 600  # 10 minutes
DEFAULT_REMINDER_SECONDS = 300  # 5 minutes into 10-minute window
DEFAULT_STUCK_TIMEOUT_SECONDS = 2.0  # seconds of no output before heuristic fires
DEFAULT_DETECTION_THRESHOLD = 0.65
DEFAULT_FREE_TEXT_MAX_CHARS = 200
DEFAULT_PROMPT_QUEUE_MAX = 10
DEFAULT_TELEGRAM_POLL_TIMEOUT = 30  # long-poll timeout
DEFAULT_TELEGRAM_MAX_RETRIES = 5

# Safe defaults per input type (injected on timeout / policy-deny)
SAFE_DEFAULTS: dict[PromptType, str] = {
    PromptType.YES_NO: "n",
    PromptType.CONFIRM_ENTER: "\n",
    PromptType.MULTIPLE_CHOICE: "1",
    PromptType.FREE_TEXT: "",
    PromptType.UNKNOWN: "n",
}

# Bytes injected into PTY stdin for each safe default action
INJECT_BYTES: dict[str, bytes] = {
    "y": b"y\r",
    "n": b"n\r",
    "\n": b"\r",
    "1": b"1\r",
    "2": b"2\r",
    "3": b"3\r",
    "4": b"4\r",
    "": b"\r",
}
