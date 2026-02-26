"""
AtlasBridge Policy DSL v0 — typed data model.

Design goals:
  - Strictly typed (Pydantic v2)
  - Versioned (policy_version field required)
  - Safe: no code execution, no templated shell
  - Deterministic: first-match-wins evaluation order
  - Explainable: every decision includes matched_rule_id + explanation
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AutonomyMode(str, Enum):
    """Operating mode for the autopilot engine."""

    OFF = "off"
    """Legacy behavior: all prompts routed to human via channel."""

    ASSIST = "assist"
    """Suggest replies; human can confirm or override within timeout."""

    FULL = "full"
    """Auto-inject per policy; escalate no-match / LOW-confidence / require_human."""


class PromptTypeFilter(str, Enum):
    """Subset of PromptType values used in policy match criteria."""

    YES_NO = "yes_no"
    CONFIRM_ENTER = "confirm_enter"
    MULTIPLE_CHOICE = "multiple_choice"
    FREE_TEXT = "free_text"
    TOOL_USE = "tool_use"
    ANY = "*"


class ConfidenceLevel(str, Enum):
    """Confidence levels, ordered LOW < MED < HIGH."""

    LOW = "low"
    MED = "medium"
    HIGH = "high"

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, ConfidenceLevel):
            return NotImplemented
        order = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MED: 1, ConfidenceLevel.HIGH: 2}
        return order[self] >= order[other]

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, ConfidenceLevel):
            return NotImplemented
        order = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MED: 1, ConfidenceLevel.HIGH: 2}
        return order[self] > order[other]

    def __le__(self, other: object) -> bool:
        if not isinstance(other, ConfidenceLevel):
            return NotImplemented
        order = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MED: 1, ConfidenceLevel.HIGH: 2}
        return order[self] <= order[other]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ConfidenceLevel):
            return NotImplemented
        order = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MED: 1, ConfidenceLevel.HIGH: 2}
        return order[self] < order[other]


# Map from detector Confidence strings to ConfidenceLevel
_CONFIDENCE_MAP: dict[str, ConfidenceLevel] = {
    "high": ConfidenceLevel.HIGH,
    "medium": ConfidenceLevel.MED,
    "med": ConfidenceLevel.MED,  # detector uses "medium" but guard both
    "low": ConfidenceLevel.LOW,
}


def confidence_from_str(s: str) -> ConfidenceLevel:
    """Convert detector Confidence string to ConfidenceLevel (case-insensitive)."""
    return _CONFIDENCE_MAP.get(s.lower(), ConfidenceLevel.LOW)


# ---------------------------------------------------------------------------
# Action models
# ---------------------------------------------------------------------------


class ReplyConstraints(BaseModel):
    """Optional constraints applied to an auto_reply action."""

    model_config = {"extra": "forbid"}

    max_length: int | None = Field(default=None, ge=1, le=4096)
    """Maximum character length of the reply value."""

    numeric_only: bool = False
    """If true, value must consist of digits only."""

    allowed_choices: list[str] | None = None
    """Allowlist of acceptable reply values. Auto_reply value must be in this list."""

    allow_free_text: bool = True
    """Whether arbitrary text is allowed (only relevant when allowed_choices is set)."""

    @model_validator(mode="after")
    def value_in_allowed_choices(self) -> ReplyConstraints:
        # Checked at rule level — here we just ensure the list is non-empty if given
        if self.allowed_choices is not None and len(self.allowed_choices) == 0:
            raise ValueError("allowed_choices must not be empty if specified")
        return self


class AutoReplyAction(BaseModel):
    """Inject a fixed reply into the PTY without human intervention."""

    model_config = {"extra": "forbid"}

    type: Literal["auto_reply"] = "auto_reply"
    value: str = Field(min_length=0, max_length=4096)
    """The literal string to inject into the tool's stdin."""

    constraints: ReplyConstraints | None = None

    @model_validator(mode="after")
    def value_satisfies_constraints(self) -> AutoReplyAction:
        if self.constraints is None:
            return self
        c = self.constraints
        if c.max_length is not None and len(self.value) > c.max_length:
            raise ValueError(
                f"auto_reply value length {len(self.value)} exceeds max_length={c.max_length}"
            )
        if c.numeric_only and not self.value.isdigit():
            raise ValueError(f"auto_reply value {self.value!r} is not numeric (numeric_only=true)")
        if c.allowed_choices is not None and self.value not in c.allowed_choices:
            raise ValueError(
                f"auto_reply value {self.value!r} not in allowed_choices={c.allowed_choices}"
            )
        return self


class RequireHumanAction(BaseModel):
    """Route the prompt to the human via Telegram/Slack and await reply."""

    model_config = {"extra": "forbid"}

    type: Literal["require_human"] = "require_human"
    message: str | None = None
    """Optional extra context sent alongside the escalation message."""


class DenyAction(BaseModel):
    """Reject the prompt and pause the session — no injection, no escalation."""

    model_config = {"extra": "forbid"}

    type: Literal["deny"] = "deny"
    reason: str | None = None
    """Human-readable reason for the denial (sent to channel as notification)."""


class NotifyOnlyAction(BaseModel):
    """Send a notification to the channel but do NOT inject a reply and do NOT wait."""

    model_config = {"extra": "forbid"}

    type: Literal["notify_only"] = "notify_only"
    message: str | None = None
    """Optional custom notification text. Defaults to the prompt excerpt."""


PolicyAction = Annotated[
    AutoReplyAction | RequireHumanAction | DenyAction | NotifyOnlyAction,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Match criteria
# ---------------------------------------------------------------------------


class MatchCriteria(BaseModel):
    """Conditions that must ALL be true for a rule to match."""

    model_config = {"extra": "forbid"}

    tool_id: str = "*"
    """Exact tool name (e.g. "claude_code") or "*" wildcard. Default: "*"."""

    repo: str | None = None
    """Prefix match on session cwd. "/home/user" matches "/home/user/project"."""

    prompt_type: list[PromptTypeFilter] | None = None
    """List of prompt types that trigger this rule. Omit = match any type."""

    tool_name: str | None = None
    """Match on the tool being invoked (chat mode only). Supports regex if contains_is_regex=true."""

    contains: str | None = None
    """Substring or regex pattern to match against the prompt excerpt."""

    contains_is_regex: bool = False
    """If true, `contains` is treated as a Python regex (with safety limits)."""

    min_confidence: ConfidenceLevel = ConfidenceLevel.LOW
    """Minimum confidence level. event.confidence >= min_confidence required."""

    @field_validator("contains")
    @classmethod
    def validate_contains_not_empty_match(cls, v: str | None) -> str | None:
        if v is not None and v == "":
            raise ValueError("contains must not be empty string")
        return v

    @model_validator(mode="after")
    def validate_regex(self) -> MatchCriteria:
        if self.contains_is_regex and self.contains:
            import re

            if len(self.contains) > 200:
                raise ValueError(f"contains regex too long ({len(self.contains)} chars, max 200)")
            try:
                compiled = re.compile(self.contains, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"Invalid regex in contains: {exc}") from exc
            # Reject patterns that match empty string (too broad)
            if compiled.match(""):
                raise ValueError(
                    f"Regex {self.contains!r} matches empty string — too broad; "
                    "use a more specific pattern"
                )
        return self


# ---------------------------------------------------------------------------
# Rule + policy
# ---------------------------------------------------------------------------


class PolicyRule(BaseModel):
    """A single policy rule: match criteria + action."""

    model_config = {"extra": "forbid"}

    id: str = Field(pattern=r"^[A-Za-z0-9][\w\-]{0,63}$")
    """Unique rule identifier. Used in decision trace and explain output."""

    description: str = ""
    """Human-readable description of what this rule does."""

    match: MatchCriteria
    action: PolicyAction

    max_auto_replies: int | None = Field(default=None, ge=1)
    """Max times this rule may auto-reply per session. None = unlimited."""


class PolicyDefaults(BaseModel):
    """Fallback actions when no rule matches or confidence is too low."""

    model_config = {"extra": "forbid"}

    no_match: Literal["require_human", "deny"] = "require_human"
    """Action when no rule matches. Default: require_human (safe)."""

    low_confidence: Literal["require_human", "deny"] = "require_human"
    """Action when event confidence is LOW and no rule explicitly covers it."""


class Policy(BaseModel):
    """
    Root policy document — AtlasBridge Policy DSL v0.

    Evaluation semantics: FIRST-MATCH-WINS.
    Rules are evaluated in list order; the first rule whose ALL match criteria
    are satisfied wins. If no rule matches, ``defaults.no_match`` applies.
    """

    model_config = {"extra": "forbid"}

    policy_version: str
    """Must be "0". Future versions will increment this field."""

    name: str = "default"
    """Human-readable policy name (used in logs and explain output)."""

    autonomy_mode: AutonomyMode = AutonomyMode.ASSIST
    """Default autonomy mode. Can be overridden by runtime config."""

    rules: list[PolicyRule] = Field(default_factory=list)
    """Ordered rule list — evaluated top-to-bottom, first match wins."""

    defaults: PolicyDefaults = Field(default_factory=PolicyDefaults)

    @field_validator("policy_version")
    @classmethod
    def check_version(cls, v: str) -> str:
        if v != "0":
            raise ValueError(
                f"Unsupported policy_version {v!r}. Only version '0' is supported by this runtime."
            )
        return v

    @model_validator(mode="after")
    def unique_rule_ids(self) -> Policy:
        ids = [r.id for r in self.rules]
        seen: set[str] = set()
        for rid in ids:
            if rid in seen:
                raise ValueError(f"Duplicate rule id {rid!r} — rule ids must be unique")
            seen.add(rid)
        return self

    def content_hash(self) -> str:
        """Stable SHA-256 hash of this policy's content (first 16 hex chars)."""
        serialized = self.model_dump_json()
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Decision output
# ---------------------------------------------------------------------------


class PolicyDecision:
    """
    The output of policy evaluation for a single PromptEvent.

    Every decision is:
    - Idempotent: same (policy_hash, prompt_id, session_id) → same decision
    - Auditable: serializes to JSONL for the decision trace
    - Explainable: explanation field describes why this rule matched
    """

    __slots__ = (
        "idempotency_key",
        "prompt_id",
        "session_id",
        "policy_hash",
        "matched_rule_id",
        "action",
        "action_type",
        "action_value",
        "explanation",
        "confidence",
        "prompt_type",
        "autonomy_mode",
        "timestamp",
        "risk_score",
        "risk_category",
        "risk_factors",
    )

    def __init__(
        self,
        *,
        prompt_id: str,
        session_id: str,
        policy_hash: str,
        matched_rule_id: str | None,
        action: PolicyAction,
        explanation: str,
        confidence: str,
        prompt_type: str,
        autonomy_mode: str,
        risk_score: int | None = None,
        risk_category: str | None = None,
        risk_factors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.prompt_id = prompt_id
        self.session_id = session_id
        self.policy_hash = policy_hash
        self.matched_rule_id = matched_rule_id
        self.action = action
        self.action_type = action.type
        self.action_value = getattr(action, "value", "")
        self.explanation = explanation
        self.confidence = confidence
        self.prompt_type = prompt_type
        self.autonomy_mode = autonomy_mode
        self.timestamp = datetime.now(UTC).isoformat()
        self.risk_score = risk_score
        self.risk_category = risk_category
        self.risk_factors = risk_factors or []

        # Idempotency key: SHA-256(policy_hash + prompt_id + session_id)[:16]
        raw = f"{policy_hash}:{prompt_id}:{session_id}"
        self.idempotency_key = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp,
            "idempotency_key": self.idempotency_key,
            "prompt_id": self.prompt_id,
            "session_id": self.session_id,
            "policy_hash": self.policy_hash,
            "matched_rule_id": self.matched_rule_id,
            "action_type": self.action_type,
            "action_value": self.action_value,
            "confidence": self.confidence,
            "prompt_type": self.prompt_type,
            "autonomy_mode": self.autonomy_mode,
            "explanation": self.explanation,
        }
        if self.risk_score is not None:
            d["risk_score"] = self.risk_score
            d["risk_category"] = self.risk_category
            d["risk_factors"] = self.risk_factors
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def __repr__(self) -> str:
        return (
            f"PolicyDecision("
            f"rule={self.matched_rule_id!r}, "
            f"action={self.action_type!r}, "
            f"key={self.idempotency_key!r})"
        )
