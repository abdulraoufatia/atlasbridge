"""
Telegram message templates and inline keyboard builders for each prompt type.

All user-visible text lives here so it can be reviewed and localised
independently of the bot logic.
"""

from __future__ import annotations

import textwrap

from aegis.core.constants import PromptType
from aegis.store.models import PromptRecord

# ---------------------------------------------------------------------------
# Keyboard builder
# ---------------------------------------------------------------------------

# Telegram inline keyboard button format
_Btn = dict[str, str]
_Row = list[_Btn]
_Keyboard = dict[str, list[_Row]]


def _btn(text: str, data: str) -> _Btn:
    return {"text": text, "callback_data": data}


def _keyboard(*rows: _Row) -> _Keyboard:
    return {"inline_keyboard": list(rows)}


# ---------------------------------------------------------------------------
# Message formatters
# ---------------------------------------------------------------------------


def format_prompt(prompt: PromptRecord, tool: str = "Claude Code") -> tuple[str, _Keyboard | None]:
    """
    Return (message_text, inline_keyboard) for the given prompt type.

    The caller is responsible for sending via the Telegram API.
    """
    dispatch = {
        PromptType.YES_NO: _format_yes_no,
        PromptType.CONFIRM_ENTER: _format_confirm_enter,
        PromptType.MULTIPLE_CHOICE: _format_multiple_choice,
        PromptType.FREE_TEXT: _format_free_text,
        PromptType.UNKNOWN: _format_unknown,
    }
    fn = dispatch.get(PromptType(prompt.input_type), _format_unknown)
    return fn(prompt, tool)


def _header(prompt: PromptRecord, tool: str, label: str) -> str:
    ttl = int(prompt.ttl_remaining_seconds)
    mins, secs = divmod(ttl, 60)
    ttl_str = f"{mins}m {secs}s" if mins else f"{secs}s"
    excerpt = textwrap.shorten(prompt.excerpt, width=200, placeholder="…")
    return (
        f"🤖 *{tool}* is waiting for your input\n"
        f"_{label}_\n\n"
        f"```\n{excerpt}\n```\n\n"
        f"⏳ Expires in *{ttl_str}* — default: *{prompt.safe_default}*"
    )


def _format_yes_no(prompt: PromptRecord, tool: str) -> tuple[str, _Keyboard]:
    text = _header(prompt, tool, "Yes / No question")
    kb = _keyboard(
        [
            _btn("✅  Yes", f"ans:{prompt.id}:{prompt.nonce}:y"),
            _btn("❌  No", f"ans:{prompt.id}:{prompt.nonce}:n"),
        ],
        [_btn("⏩  Use default (n)", f"ans:{prompt.id}:{prompt.nonce}:default")],
    )
    return text, kb


def _format_confirm_enter(prompt: PromptRecord, tool: str) -> tuple[str, _Keyboard]:
    text = _header(prompt, tool, "Press Enter to continue")
    kb = _keyboard(
        [_btn("↩️  Press Enter", f"ans:{prompt.id}:{prompt.nonce}:enter")],
        [_btn("⏩  Use default (↩)", f"ans:{prompt.id}:{prompt.nonce}:default")],
    )
    return text, kb


def _format_multiple_choice(prompt: PromptRecord, tool: str) -> tuple[str, _Keyboard]:
    choices = prompt.choices  # list[str]
    text = _header(prompt, tool, "Multiple choice")

    rows: list[_Row] = []
    for i, choice in enumerate(choices, start=1):
        label = textwrap.shorten(choice, width=30, placeholder="…")
        rows.append([_btn(f"{i}. {label}", f"ans:{prompt.id}:{prompt.nonce}:{i}")])
    rows.append([_btn("⏩  Use default (1)", f"ans:{prompt.id}:{prompt.nonce}:default")])

    return text, _keyboard(*rows)


def _format_free_text(prompt: PromptRecord, tool: str) -> tuple[str, _Keyboard]:
    text = (
        _header(prompt, tool, "Free-text input")
        + "\n\n📝 *Reply to this message* with your text response."
        + f"\n_(max {200} characters)_"
    )
    kb = _keyboard([_btn("⏩  Use default (empty)", f"ans:{prompt.id}:{prompt.nonce}:default")])
    return text, kb


def _format_unknown(prompt: PromptRecord, tool: str) -> tuple[str, _Keyboard]:
    text = (
        _header(prompt, tool, "Unknown prompt type")
        + "\n\n⚠️ Aegis could not classify this prompt. "
        + "Reply with your response or use the default."
    )
    kb = _keyboard(
        [
            _btn("✅  Yes / Enter", f"ans:{prompt.id}:{prompt.nonce}:y"),
            _btn("❌  No / Skip", f"ans:{prompt.id}:{prompt.nonce}:n"),
        ],
        [_btn("⏩  Use default", f"ans:{prompt.id}:{prompt.nonce}:default")],
    )
    return text, kb


# ---------------------------------------------------------------------------
# Notification templates (no keyboard)
# ---------------------------------------------------------------------------


def format_timeout_notice(prompt: PromptRecord, injected: str, tool: str = "Claude Code") -> str:
    excerpt = textwrap.shorten(prompt.excerpt, width=120, placeholder="…")
    return f"⏰ *{tool}* prompt timed out\n\n```\n{excerpt}\n```\n\nAuto-injected: *{injected!r}*"


def format_session_started(session_id: str, tool: str, cwd: str) -> str:
    return f"▶️ *Aegis session started*\n\nTool: `{tool}`\nCWD: `{cwd}`\nSession: `{session_id[:8]}`"


def format_session_ended(session_id: str, tool: str, exit_code: int | None) -> str:
    status = "✅ exited 0" if exit_code == 0 else f"⚠️ exited {exit_code}"
    return (
        f"⏹ *Aegis session ended*\n\nTool: `{tool}`\nSession: `{session_id[:8]}`\nStatus: {status}"
    )


def format_error_notice(message: str) -> str:
    return f"🚨 *Aegis error*\n\n`{message}`"


def format_response_accepted(prompt: PromptRecord, response: str) -> str:
    return (
        f"✅ *Response recorded*\n\n"
        f"Prompt `{prompt.short_id}` → `{response!r}`\n"
        f"Injecting into {prompt.input_type}…"
    )


def format_already_decided(prompt: PromptRecord) -> str:
    return f"⚠️ Prompt `{prompt.short_id}` was already answered (status: {prompt.status})."


def format_expired(prompt: PromptRecord) -> str:
    return f"⏰ Prompt `{prompt.short_id}` has expired. Default was injected."


# ---------------------------------------------------------------------------
# Callback data parsing
# ---------------------------------------------------------------------------


def parse_callback_data(data: str) -> tuple[str, str, str] | None:
    """
    Parse ``ans:<prompt_id>:<nonce>:<value>`` callback data.

    Returns ``(prompt_id, nonce, value)`` or ``None`` if malformed.
    """
    parts = data.split(":", 3)
    if len(parts) != 4 or parts[0] != "ans":
        return None
    _, prompt_id, nonce, value = parts
    if not prompt_id or not nonce or not value:
        return None
    return prompt_id, nonce, value
