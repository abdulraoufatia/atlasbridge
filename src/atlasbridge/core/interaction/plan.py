"""
InteractionPlan — execution strategy for a classified interaction.

Maps each InteractionClass to a concrete set of parameters that
control injection, retry, verification, and operator feedback.
"""

from __future__ import annotations

from dataclasses import dataclass

from atlasbridge.core.interaction.classifier import InteractionClass


@dataclass(frozen=True)
class InteractionPlan:
    """Immutable execution strategy for one interaction."""

    interaction_class: InteractionClass

    # Injection
    append_cr: bool = True  # Append \\r (Enter key) after value
    suppress_value: bool = False  # True for PASSWORD_INPUT — redact in logs/feedback

    # Retry
    max_retries: int = 1  # How many times to re-inject if CLI doesn't advance
    retry_delay_s: float = 2.0  # Seconds to wait before retry
    escalate_on_exhaustion: bool = True  # Escalate to human when retries exhausted

    # Verification
    verify_advance: bool = True  # Check if CLI produced new output after injection
    advance_timeout_s: float = 5.0  # How long to wait for CLI to advance

    # Display
    display_template: str = ""  # e.g. "Sent: {value} + Enter"
    feedback_on_advance: str = ""  # e.g. "CLI advanced"
    feedback_on_stall: str = ""  # e.g. "CLI did not respond..."
    escalation_template: str = (
        "Injection did not advance the CLI after {retries} retries. "
        "Please try running this step locally."
    )

    # Channel rendering hint
    button_layout: str = ""  # "yes_no" | "numbered" | "confirm_enter" | "none"


def build_plan(interaction_class: InteractionClass) -> InteractionPlan:
    """
    Build an InteractionPlan for the given InteractionClass.

    Pure function — same class always produces the same plan.
    """
    match interaction_class:
        case InteractionClass.YES_NO:
            return InteractionPlan(
                interaction_class=interaction_class,
                append_cr=True,
                max_retries=1,
                verify_advance=True,
                advance_timeout_s=3.0,
                display_template="Sent: {value} + Enter",
                feedback_on_advance="CLI advanced",
                feedback_on_stall='CLI did not respond to "{value}", retrying...',
                escalation_template=(
                    'CLI did not respond to "{value}" after retries. Please respond locally.'
                ),
                button_layout="yes_no",
            )

        case InteractionClass.CONFIRM_ENTER:
            return InteractionPlan(
                interaction_class=interaction_class,
                append_cr=True,
                max_retries=1,
                verify_advance=True,
                advance_timeout_s=3.0,
                display_template="Sent: Enter",
                feedback_on_advance="CLI advanced",
                feedback_on_stall="CLI did not advance after Enter, retrying...",
                escalation_template=(
                    "CLI did not advance after pressing Enter. Please continue locally."
                ),
                button_layout="confirm_enter",
            )

        case InteractionClass.NUMBERED_CHOICE:
            return InteractionPlan(
                interaction_class=interaction_class,
                append_cr=True,
                max_retries=1,
                verify_advance=True,
                advance_timeout_s=5.0,
                display_template="Sent: option {value} + Enter",
                feedback_on_advance="Option {value} accepted",
                feedback_on_stall='CLI did not accept option "{value}", retrying...',
                escalation_template=(
                    'CLI did not accept option "{value}" after retries. Please select locally.'
                ),
                button_layout="numbered",
            )

        case InteractionClass.FREE_TEXT:
            return InteractionPlan(
                interaction_class=interaction_class,
                append_cr=True,
                max_retries=0,
                verify_advance=True,
                advance_timeout_s=5.0,
                display_template='Sent: "{value}" + Enter',
                feedback_on_advance="CLI accepted input",
                feedback_on_stall="CLI may still be processing...",
                escalation_template=(
                    "CLI did not accept input after injection. Please enter text locally."
                ),
                button_layout="none",
            )

        case InteractionClass.PASSWORD_INPUT:
            return InteractionPlan(
                interaction_class=interaction_class,
                append_cr=True,
                suppress_value=True,
                max_retries=0,
                verify_advance=True,
                advance_timeout_s=5.0,
                display_template="Sent: [REDACTED] + Enter",
                feedback_on_advance="CLI accepted credential",
                feedback_on_stall="CLI did not advance after credential input",
                escalation_template=(
                    "CLI did not accept credential after injection. Please enter locally."
                ),
                button_layout="none",
            )

        case InteractionClass.FOLDER_TRUST:
            return InteractionPlan(
                interaction_class=interaction_class,
                append_cr=True,
                max_retries=1,
                verify_advance=True,
                advance_timeout_s=3.0,
                escalate_on_exhaustion=True,
                display_template="Trust: {value} + Enter",
                feedback_on_advance="Folder trust accepted",
                feedback_on_stall='CLI did not respond to trust "{value}", retrying...',
                escalation_template=(
                    "Folder trust prompt did not advance. Please respond locally."
                ),
                button_layout="trust_folder",
            )

        case InteractionClass.RAW_TERMINAL:
            return InteractionPlan(
                interaction_class=interaction_class,
                append_cr=False,
                max_retries=0,
                verify_advance=False,
                advance_timeout_s=0.0,
                escalate_on_exhaustion=True,
                display_template="This prompt could not be handled remotely.",
                feedback_on_advance="",
                feedback_on_stall="",
                escalation_template=(
                    "This prompt could not be handled remotely. Please respond locally."
                ),
                button_layout="none",
            )

        case InteractionClass.CHAT_INPUT:
            return InteractionPlan(
                interaction_class=interaction_class,
                append_cr=True,
                max_retries=0,
                verify_advance=False,
                advance_timeout_s=0.0,
                escalate_on_exhaustion=False,
                display_template='Sent: "{value}"',
                feedback_on_advance="",
                feedback_on_stall="",
                button_layout="none",
            )

        case _:
            return InteractionPlan(
                interaction_class=interaction_class,
                display_template="Sent: {value} + Enter",
                button_layout="none",
            )
