"""
LLM Providers — direct API integration for chat mode.

Providers talk to LLM APIs (Anthropic, OpenAI, Google) via httpx.
Each provider normalises its API's response format into a unified
Message/ToolCall/StreamChunk model.

Auto-imports all built-in providers on first access so that
ProviderRegistry.get("anthropic") works without explicit imports.
"""

# Auto-register built-in providers
from atlasbridge.providers import anthropic as _anthropic  # noqa: F401
from atlasbridge.providers import google as _google  # noqa: F401
from atlasbridge.providers import openai as _openai  # noqa: F401
from atlasbridge.providers.base import BaseProvider, ProviderRegistry  # noqa: F401
