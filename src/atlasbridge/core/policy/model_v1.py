"""
AtlasBridge Policy DSL v1 — typed data model.

v1 is a backward-compatible extension of v0:
  - All v0 fields and semantics are preserved
  - New: compound OR logic (``any_of``)
  - New: NOT logic (``none_of``)
  - New: ``session_tag`` — scope a rule to a named session
  - New: ``max_confidence`` — upper bound on confidence (e.g. LOW-only rules)
  - New: ``extends`` — inherit rules from a base policy file

Design notes:
  - ``PolicyV1`` is a standalone class (not a subclass of Policy) so v0 is frozen
  - ``MatchCriteriaV1`` is self-referential; call ``MatchCriteriaV1.model_rebuild()``
    after the class definition to resolve the forward reference
  - ``any_of`` and flat criteria are mutually exclusive on the same block
  - ``none_of`` can coexist with flat criteria or ``any_of``
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field, field_validator, model_validator

from atlasbridge.core.policy.model import (
    AutonomyMode,
    ConfidenceLevel,
    PolicyAction,
    PolicyDefaults,
    PromptTypeFilter,
)

# ---------------------------------------------------------------------------
# v1 validation constants
# ---------------------------------------------------------------------------

_VALID_SESSION_STATES: frozenset[str] = frozenset(
    {"idle", "running", "streaming", "awaiting_input", "stopped"}
)

_VALID_INPUT_TYPES: frozenset[str] = frozenset(
    {"yes_no", "confirm_enter", "multiple_choice", "free_text", "password_input"}
)

# ---------------------------------------------------------------------------
# v1 Match criteria
# ---------------------------------------------------------------------------


class MatchCriteriaV1(BaseModel):
    """
    v1 match criteria — flat AND + compound OR/NOT + session_tag + max_confidence.

    Flat AND fields (same semantics as v0 MatchCriteria):
      tool_id, repo, prompt_type, contains, contains_is_regex, min_confidence

    v1 additions:
      max_confidence: upper bound on confidence
      session_tag:    exact-match filter on session label
      any_of:         OR block — match if ANY sub-criteria block passes
      none_of:        NOT block — fail if ANY sub-criteria block passes

    Constraint: ``any_of`` and flat criteria are mutually exclusive on the same
    block (because ``any_of`` IS the match condition; combining it with flat
    criteria would be ambiguous). ``none_of`` has no such restriction.
    """

    model_config = {"extra": "forbid"}

    # ---- v0 flat AND fields (identical semantics) ----
    tool_id: str = "*"
    """Exact tool name or "*" wildcard. Default: "*"."""

    repo: str | None = None
    """Prefix match on session cwd."""

    prompt_type: list[PromptTypeFilter] | None = None
    """Prompt types that trigger this rule. Omit = match any."""

    contains: str | None = None
    """Substring or regex pattern to match against the prompt excerpt."""

    contains_is_regex: bool = False
    """If true, ``contains`` is treated as a Python regex."""

    min_confidence: ConfidenceLevel = ConfidenceLevel.LOW
    """Minimum confidence. event.confidence >= min_confidence required."""

    # ---- v1 additions ----
    max_confidence: ConfidenceLevel | None = None
    """Upper bound on confidence. event.confidence <= max_confidence required."""

    session_tag: str | None = None
    """Match only if the session label equals this string exactly."""

    session_state: list[str] | None = None
    """Match only when session is in one of these conversation states."""

    channel_message: bool | None = None
    """If true, rule only matches messages originating from a channel (not local)."""

    deny_input_types: list[str] | None = None
    """Match when the prompt type is in this list (used for deny rules via channel)."""

    environment: str | None = None
    """Match only when runtime environment equals this string (dev/staging/production)."""

    any_of: list[MatchCriteriaV1] | None = None
    """OR logic: rule matches if ANY sub-criteria block matches."""

    none_of: list[MatchCriteriaV1] | None = None
    """NOT logic: rule fails if ANY sub-criteria block matches."""

    @field_validator("contains")
    @classmethod
    def validate_contains_not_empty(cls, v: str | None) -> str | None:
        if v is not None and v == "":
            raise ValueError("contains must not be empty string")
        return v

    @field_validator("session_state")
    @classmethod
    def validate_session_state_values(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for state in v:
                if state not in _VALID_SESSION_STATES:
                    raise ValueError(
                        f"Unknown session_state {state!r}. "
                        f"Valid values: {sorted(_VALID_SESSION_STATES)}"
                    )
        return v

    @field_validator("deny_input_types")
    @classmethod
    def validate_deny_input_types_values(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for input_type in v:
                if input_type not in _VALID_INPUT_TYPES:
                    raise ValueError(
                        f"Unknown deny_input_type {input_type!r}. "
                        f"Valid values: {sorted(_VALID_INPUT_TYPES)}"
                    )
        return v

    @model_validator(mode="after")
    def validate_regex(self) -> MatchCriteriaV1:
        if self.contains_is_regex and self.contains:
            import re

            if len(self.contains) > 200:
                raise ValueError(f"contains regex too long ({len(self.contains)} chars, max 200)")
            try:
                compiled = re.compile(self.contains, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"Invalid regex in contains: {exc}") from exc
            if compiled.match(""):
                raise ValueError(
                    f"Regex {self.contains!r} matches empty string — too broad; "
                    "use a more specific pattern"
                )
        return self

    @model_validator(mode="after")
    def any_of_and_flat_mutually_exclusive(self) -> MatchCriteriaV1:
        """any_of replaces flat AND criteria — they cannot coexist on the same block."""
        has_flat = any(
            [
                self.tool_id != "*",
                self.repo is not None,
                self.prompt_type is not None,
                self.contains is not None,
                self.session_tag is not None,
                self.max_confidence is not None,
                self.min_confidence != ConfidenceLevel.LOW,
                self.session_state is not None,
                self.channel_message is not None,
                self.deny_input_types is not None,
            ]
        )
        if self.any_of is not None and has_flat:
            raise ValueError(
                "any_of and flat match criteria are mutually exclusive on the same block; "
                "put each set of conditions in a separate any_of sub-block"
            )
        return self


# Pydantic v2 requires model_rebuild() to resolve self-referential annotations
MatchCriteriaV1.model_rebuild()


# ---------------------------------------------------------------------------
# v1 Rule
# ---------------------------------------------------------------------------


class PolicyRuleV1(BaseModel):
    """A single v1 policy rule: v1 match criteria + action."""

    model_config = {"extra": "forbid"}

    id: str = Field(pattern=r"^[A-Za-z0-9][\w\-]{0,63}$")
    """Unique rule identifier."""

    description: str = ""
    """Human-readable description of what this rule does."""

    match: MatchCriteriaV1
    action: PolicyAction

    max_auto_replies: int | None = Field(default=None, ge=1)
    """Max times this rule may auto-reply per session. None = unlimited."""


# ---------------------------------------------------------------------------
# v1 Policy
# ---------------------------------------------------------------------------


class PolicyV1(BaseModel):
    """
    Root policy document — AtlasBridge Policy DSL v1.

    v1 extends v0 with compound conditions, session_tag, max_confidence,
    and policy inheritance (``extends``).

    Evaluation semantics: FIRST-MATCH-WINS (same as v0).
    """

    model_config = {"extra": "forbid"}

    policy_version: str
    """Must be "1"."""

    name: str = "default"
    """Human-readable policy name."""

    autonomy_mode: AutonomyMode = AutonomyMode.ASSIST
    """Default autonomy mode."""

    rules: list[PolicyRuleV1] = Field(default_factory=list)
    """Ordered rule list — evaluated top-to-bottom, first match wins."""

    defaults: PolicyDefaults = Field(default_factory=PolicyDefaults)

    extends: str | None = None
    """
    Path to a base policy file (v1 only). Child rules are evaluated first;
    base rules are appended. Cycle detection is enforced at parse time.
    This field is resolved at load time; the resulting PolicyV1 object
    contains the merged rule list.
    """

    @field_validator("policy_version")
    @classmethod
    def check_version(cls, v: str) -> str:
        if v != "1":
            raise ValueError(
                f"Expected policy_version '1' for PolicyV1, got {v!r}. "
                "Use policy_version: '0' for a v0 policy."
            )
        return v

    @model_validator(mode="after")
    def unique_rule_ids(self) -> PolicyV1:
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
