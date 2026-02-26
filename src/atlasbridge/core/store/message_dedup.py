"""
Channel message deduplication helper.

Uses the ``processed_messages`` table (added in migration v3→v4) with a
UNIQUE(channel, channel_identity, message_id) constraint.

An INSERT OR IGNORE is attempted; if rowcount == 0, the message was already
processed and the caller should skip it.  This prevents:
  - Duplicate handling of the same Telegram/Slack message on network retry.
  - Echo-loop injection from bot-delivered messages.
"""

from __future__ import annotations

import sqlite3

import structlog

logger = structlog.get_logger()


def mark_processed(
    channel: str,
    channel_identity: str,
    message_id: str,
    conn: sqlite3.Connection,
) -> bool:
    """Record a channel message as processed.

    Returns True if this is the first time the message is seen (new).
    Returns False if the message was already processed (duplicate — skip it).
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO processed_messages
            (channel, channel_identity, message_id, processed_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (channel, channel_identity, message_id),
    )
    conn.commit()
    new_row = conn.execute("SELECT changes()").fetchone()
    inserted = bool(new_row and new_row[0])
    if not inserted:
        logger.debug(
            "message_deduplicated",
            channel=channel,
            channel_identity=channel_identity,
            message_id=message_id,
        )
    return inserted
