"""ChannelMessageGate — pure, deterministic accept/reject for channel messages.

Every incoming channel message is evaluated immediately. No queueing.
The gate reads a frozen context snapshot and returns a frozen decision.

Evaluation order (10-step sequence):
  1. Identity check
  2. Session existence
  3. Session state (STREAMING → reject, RUNNING → reject unless interrupt policy)
  4. AWAITING_INPUT path: prompt binding → TTL → unsafe type → policy → validation
  5. IDLE path: chat turns policy check
  6. Default deny
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from atlasbridge.core.conversation.session_binding import ConversationState
from atlasbridge.core.interaction.classifier import InteractionClass


class AcceptType(StrEnum):
    """Type of accepted channel message."""

    REPLY = "reply"  # AWAITING_INPUT prompt reply
    CHAT_TURN = "chat_turn"  # IDLE free text
    INTERRUPT = "interrupt"  # RUNNING with interrupt policy


class GateRejectReason(StrEnum):
    """Machine-readable reason codes for gate rejections."""

    REJECT_BUSY_STREAMING = "reject_busy_streaming"
    REJECT_BUSY_RUNNING = "reject_busy_running"
    REJECT_NO_ACTIVE_SESSION = "reject_no_active_session"
    REJECT_NOT_AWAITING_INPUT = "reject_not_awaiting_input"
    REJECT_TTL_EXPIRED = "reject_ttl_expired"
    REJECT_POLICY_DENY = "reject_policy_deny"
    REJECT_IDENTITY_NOT_ALLOWLISTED = "reject_identity_not_allowlisted"
    REJECT_INVALID_CHOICE = "reject_invalid_choice"
    REJECT_RATE_LIMITED = "reject_rate_limited"
    REJECT_UNSAFE_INPUT_TYPE = "reject_unsafe_input_type"


# Human-friendly messages for each rejection reason.
_REASON_MESSAGES: dict[GateRejectReason, str] = {
    GateRejectReason.REJECT_BUSY_STREAMING: (
        "The agent is currently producing output. "
        "Please wait until it finishes before sending a message."
    ),
    GateRejectReason.REJECT_BUSY_RUNNING: (
        "The agent is executing a command. Please wait for it to finish or prompt for input."
    ),
    GateRejectReason.REJECT_NO_ACTIVE_SESSION: (
        "No active session found. Start a session with `atlasbridge run <tool>` first."
    ),
    GateRejectReason.REJECT_NOT_AWAITING_INPUT: (
        "The agent is not waiting for input right now. "
        "Your message cannot be delivered at this time."
    ),
    GateRejectReason.REJECT_TTL_EXPIRED: (
        "This prompt has expired. The agent may have moved on. Check session status."
    ),
    GateRejectReason.REJECT_POLICY_DENY: (
        "Your policy does not allow this action. "
        "Check your policy rules or switch to a more permissive mode."
    ),
    GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED: (
        "Your identity is not on the allowlist. "
        "Only authorized users can send messages to this session."
    ),
    GateRejectReason.REJECT_INVALID_CHOICE: (
        "Invalid choice. Please select a valid option from the list."
    ),
    GateRejectReason.REJECT_RATE_LIMITED: (
        "Too many messages. Please wait a moment before sending another message."
    ),
    GateRejectReason.REJECT_UNSAFE_INPUT_TYPE: (
        "This prompt requires sensitive input (password/token). "
        "Enter it directly in the terminal, not via the channel."
    ),
}

# Next-action hints for each rejection reason.
_NEXT_ACTION_HINTS: dict[GateRejectReason, str] = {
    GateRejectReason.REJECT_BUSY_STREAMING: "Wait for the agent to finish.",
    GateRejectReason.REJECT_BUSY_RUNNING: "Wait for a prompt to appear.",
    GateRejectReason.REJECT_NO_ACTIVE_SESSION: "Run `atlasbridge run <tool>`.",
    GateRejectReason.REJECT_NOT_AWAITING_INPUT: "Wait for the next prompt.",
    GateRejectReason.REJECT_TTL_EXPIRED: "Check `atlasbridge status`.",
    GateRejectReason.REJECT_POLICY_DENY: "Review your policy file.",
    GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED: "Contact the session owner.",
    GateRejectReason.REJECT_INVALID_CHOICE: "Send a valid option number.",
    GateRejectReason.REJECT_RATE_LIMITED: "Wait and try again.",
    GateRejectReason.REJECT_UNSAFE_INPUT_TYPE: "Enter the value in the terminal.",
}


@dataclass(frozen=True)
class GateContext:
    """Immutable snapshot of all inputs needed for gate evaluation."""

    session_id: str | None
    conversation_state: ConversationState | None
    active_prompt_id: str | None
    interaction_class: InteractionClass | None
    prompt_expires_at: str | None  # ISO 8601 timestamp
    channel_user_id: str
    channel_name: str  # "telegram" | "slack"
    message_body: str
    message_hash: str  # SHA-256 of message body
    identity_allowlist: frozenset[str]
    allow_chat_turns: bool = False
    allow_interrupts: bool = False
    valid_choices: tuple[str, ...] = ()  # for multiple_choice validation
    timestamp: str = ""  # evaluation time (ISO 8601)


@dataclass(frozen=True)
class GateDecision:
    """Deterministic output of the gate evaluation."""

    action: Literal["accept", "reject"]
    reason_code: GateRejectReason | None = None
    reason_message: str = ""
    next_action_hint: str = ""
    injection_payload: str | None = None
    accept_type: AcceptType | None = None


def _reject(reason: GateRejectReason) -> GateDecision:
    """Build a reject decision with standard messages."""
    return GateDecision(
        action="reject",
        reason_code=reason,
        reason_message=_REASON_MESSAGES.get(reason, "Message rejected."),
        next_action_hint=_NEXT_ACTION_HINTS.get(reason, ""),
    )


def _accept(payload: str, accept_type: AcceptType = AcceptType.REPLY) -> GateDecision:
    """Build an accept decision with the sanitized payload."""
    return GateDecision(
        action="accept",
        injection_payload=payload,
        accept_type=accept_type,
    )


def _is_expired(expires_at: str | None, now: str) -> bool:
    """Check if a prompt TTL has expired."""
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at)
        current = datetime.fromisoformat(now) if now else datetime.now(UTC)
        return current >= exp
    except (ValueError, TypeError):
        return False


def evaluate_gate(ctx: GateContext) -> GateDecision:
    """Pure, deterministic gate evaluation. No side effects.

    Evaluation order:
      1. Identity check
      2. Session existence
      3. Session state (STREAMING, RUNNING, STOPPED)
      4. AWAITING_INPUT: prompt binding → TTL → unsafe type → validation
      5. IDLE: chat turns check
      6. Default deny
    """
    # 1. Identity check
    if ctx.channel_user_id not in ctx.identity_allowlist:
        return _reject(GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED)

    # 2. Session existence
    if ctx.session_id is None or ctx.conversation_state is None:
        return _reject(GateRejectReason.REJECT_NO_ACTIVE_SESSION)

    # 3. Session state checks
    if ctx.conversation_state == ConversationState.STREAMING:
        return _reject(GateRejectReason.REJECT_BUSY_STREAMING)

    if ctx.conversation_state == ConversationState.RUNNING:
        if not ctx.allow_interrupts:
            return _reject(GateRejectReason.REJECT_BUSY_RUNNING)
        # Interrupt allowed by policy — accept
        return _accept(ctx.message_body, AcceptType.INTERRUPT)

    if ctx.conversation_state == ConversationState.STOPPED:
        return _reject(GateRejectReason.REJECT_NO_ACTIVE_SESSION)

    # 4. AWAITING_INPUT path
    if ctx.conversation_state == ConversationState.AWAITING_INPUT:
        # 4a. Prompt binding
        if ctx.active_prompt_id is None:
            return _reject(GateRejectReason.REJECT_NOT_AWAITING_INPUT)

        # 4b. TTL check
        if _is_expired(ctx.prompt_expires_at, ctx.timestamp):
            return _reject(GateRejectReason.REJECT_TTL_EXPIRED)

        # 4c. Unsafe input type (password/credential prompts)
        if ctx.interaction_class == InteractionClass.PASSWORD_INPUT:
            return _reject(GateRejectReason.REJECT_UNSAFE_INPUT_TYPE)

        # 4d. Choice validation is handled post-gate by the interaction
        # engine's normalizer, which maps natural language synonyms
        # (yes, allow, trust, etc.) to the correct option number.
        # The gate no longer rejects free-text replies here.

        # Accept
        return _accept(ctx.message_body)

    # 5. IDLE path — chat turns
    if ctx.conversation_state == ConversationState.IDLE:
        if not ctx.allow_chat_turns:
            return _reject(GateRejectReason.REJECT_POLICY_DENY)
        return _accept(ctx.message_body, AcceptType.CHAT_TURN)

    # 6. Default deny — unrecognized state
    return _reject(GateRejectReason.REJECT_POLICY_DENY)
