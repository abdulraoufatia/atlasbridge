"""Gate decision message formatter — phone-friendly, channel-agnostic.

Converts GateDecision objects into short, actionable user-facing messages
suitable for Telegram and Slack. No channel imports — pure core module.
"""

from __future__ import annotations

from atlasbridge.core.gate.engine import AcceptType, GateDecision, GateRejectReason

# Accept confirmation messages — one line, under 30 chars.
_ACCEPT_MESSAGES: dict[AcceptType, str] = {
    AcceptType.REPLY: "\u2713 Sent to session.",
    AcceptType.CHAT_TURN: "\u2713 Message sent.",
    AcceptType.INTERRUPT: "\u2713 Interrupt sent to session.",
}

# Reject headline messages — short, phone-readable.
_REJECT_HEADLINES: dict[GateRejectReason, str] = {
    GateRejectReason.REJECT_BUSY_STREAMING: ("\u23f3 Agent is working. Message not sent."),
    GateRejectReason.REJECT_BUSY_RUNNING: ("\u23f3 Agent is busy. Message not sent."),
    GateRejectReason.REJECT_NO_ACTIVE_SESSION: ("No active session. Message not sent."),
    GateRejectReason.REJECT_NOT_AWAITING_INPUT: (
        "Agent is not waiting for input. Message not sent."
    ),
    GateRejectReason.REJECT_TTL_EXPIRED: ("This prompt has expired. Message not sent."),
    GateRejectReason.REJECT_POLICY_DENY: ("Policy does not allow this action. Message not sent."),
    GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED: ("You are not authorized for this session."),
    GateRejectReason.REJECT_INVALID_CHOICE: ("Invalid response. Message not sent."),
    GateRejectReason.REJECT_RATE_LIMITED: ("Too many messages. Please wait a moment."),
    GateRejectReason.REJECT_UNSAFE_INPUT_TYPE: (
        "This prompt requires local input (not via channel)."
    ),
}

# Next-action copy — brief, actionable.
_REJECT_NEXT_ACTIONS: dict[GateRejectReason, str] = {
    GateRejectReason.REJECT_BUSY_STREAMING: (
        "Wait for the current operation to finish, then try again."
    ),
    GateRejectReason.REJECT_BUSY_RUNNING: ("Wait for the agent to finish or request input."),
    GateRejectReason.REJECT_NO_ACTIVE_SESSION: ("Start a session first: atlasbridge run claude"),
    GateRejectReason.REJECT_NOT_AWAITING_INPUT: ("Wait for a prompt to appear."),
    GateRejectReason.REJECT_TTL_EXPIRED: ("A new prompt will appear if the agent needs input."),
    GateRejectReason.REJECT_POLICY_DENY: (
        "Check your policy configuration or contact the operator."
    ),
    GateRejectReason.REJECT_IDENTITY_NOT_ALLOWLISTED: ("Contact the session operator."),
    GateRejectReason.REJECT_INVALID_CHOICE: (
        "Reply with one of the valid options shown in the prompt."
    ),
    GateRejectReason.REJECT_RATE_LIMITED: ("Try again in a few seconds."),
    GateRejectReason.REJECT_UNSAFE_INPUT_TYPE: ("Enter this value directly in the terminal."),
}


def format_gate_decision(decision: GateDecision) -> str:
    """Format a gate decision as a user-facing message.

    Returns a short, phone-friendly string suitable for sending
    to any channel (Telegram, Slack, etc.). No secrets, no jargon.

    Accept messages: single line with checkmark.
    Reject messages: headline + next action on separate lines.
    """
    if decision.action == "accept":
        if decision.accept_type is not None:
            return _ACCEPT_MESSAGES.get(decision.accept_type, _ACCEPT_MESSAGES[AcceptType.REPLY])
        return _ACCEPT_MESSAGES[AcceptType.REPLY]

    if decision.reason_code is None:
        return "Message not sent."

    headline = _REJECT_HEADLINES.get(decision.reason_code, "Message not sent.")
    next_action = _REJECT_NEXT_ACTIONS.get(decision.reason_code, "")
    if next_action:
        return f"{headline}\n{next_action}"
    return headline
