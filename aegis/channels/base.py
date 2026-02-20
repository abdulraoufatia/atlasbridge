"""Aegis channel abstraction — base class for notification/response channels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aegis.store.models import PromptRecord


class BaseChannel(ABC):
    """
    Abstract channel that can send a prompt to a human and receive a response.

    Implementations: TelegramChannel (and future: Slack, email, etc.)
    """

    @abstractmethod
    async def send_prompt(self, prompt: PromptRecord) -> Any:
        """
        Send the prompt to the remote user and return channel-specific metadata
        (e.g., a Telegram message_id).
        """

    @abstractmethod
    async def send_message(self, text: str) -> None:
        """Send a plain informational message (no response expected)."""

    @abstractmethod
    async def send_timeout_notice(self, prompt: PromptRecord, injected: str) -> None:
        """Notify the user that a prompt timed out and was auto-answered."""

    @abstractmethod
    async def close(self) -> None:
        """Gracefully shut down the channel (cancel polling tasks, close sockets)."""
