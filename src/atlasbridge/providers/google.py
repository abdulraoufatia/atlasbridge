"""
Google Gemini provider — direct Generative Language API via httpx.

Uses the Google AI Generative Language API
(https://ai.google.dev/api/generate-content).
No SDK dependency — raw httpx calls.

Supports:
  - Conversation with system instruction
  - Streaming responses (SSE)
  - Tool use (function calling)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

from atlasbridge.providers.base import (
    BaseProvider,
    Message,
    ProviderRegistry,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)

logger = structlog.get_logger()

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-2.0-flash"


@ProviderRegistry.register("google")
class GoogleProvider(BaseProvider):
    """Google Gemini API provider."""

    provider_name = "google"
    display_name = "Gemini (Google)"

    def __init__(self, api_key: str, model: str = "") -> None:
        self._api_key = api_key
        self._model = model or _DEFAULT_MODEL
        self._client: Any = None

    async def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system: str = "",
        max_tokens: int = 4096,
    ) -> Message:
        client = await self._ensure_client()
        url = f"{_API_BASE}/{self._model}:generateContent"
        payload = self._build_payload(messages, tools, system, max_tokens)

        resp = await client.post(
            url,
            json=payload,
            params={"key": self._api_key},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return self._parse_response(data)

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system: str = "",
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        client = await self._ensure_client()
        url = f"{_API_BASE}/{self._model}:streamGenerateContent"
        payload = self._build_payload(messages, tools, system, max_tokens)

        async with client.stream(
            "POST",
            url,
            json=payload,
            params={"key": self._api_key, "alt": "sse"},
            headers={"Content-Type": "application/json"},
        ) as resp:
            resp.raise_for_status()
            all_tool_calls: list[ToolCall] = []
            usage: dict[str, int] = {}

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:]

                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                candidates = event.get("candidates", [])
                if not candidates:
                    # Check for usage metadata
                    um = event.get("usageMetadata", {})
                    if um:
                        usage = {
                            "prompt_tokens": um.get("promptTokenCount", 0),
                            "completion_tokens": um.get("candidatesTokenCount", 0),
                        }
                    continue

                content = candidates[0].get("content", {})
                for part in content.get("parts", []):
                    if "text" in part:
                        yield StreamChunk(text=part["text"])
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        all_tool_calls.append(
                            ToolCall(
                                id=fc.get("name", ""),  # Gemini uses name as ID
                                name=fc.get("name", ""),
                                arguments=fc.get("args", {}),
                            )
                        )

            yield StreamChunk(
                text="",
                tool_calls=all_tool_calls,
                is_final=True,
                usage=usage,
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        system: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contents": self._convert_messages(messages),
            "generationConfig": {
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = [{"functionDeclarations": [self._convert_tool(t) for t in tools]}]
        return payload

    @staticmethod
    def _convert_messages(messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "tool":
                parts = []
                for tr in msg.tool_results:
                    parts.append(
                        {
                            "functionResponse": {
                                "name": tr.tool_call_id,  # Gemini uses tool name as ID
                                "response": {"content": tr.content},
                            }
                        }
                    )
                result.append({"role": "user", "parts": parts})
            elif msg.tool_calls:
                parts: list[dict[str, Any]] = []
                if msg.content:
                    parts.append({"text": msg.content})
                for tc in msg.tool_calls:
                    parts.append(
                        {
                            "functionCall": {
                                "name": tc.name,
                                "args": tc.arguments,
                            }
                        }
                    )
                result.append({"role": "model", "parts": parts})
            else:
                role = "model" if msg.role == "assistant" else "user"
                result.append({"role": role, "parts": [{"text": msg.content}]})
        return result

    @staticmethod
    def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> Message:
        candidates = data.get("candidates", [])
        if not candidates:
            return Message(role="assistant", content="")

        content = candidates[0].get("content", {})
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for part in content.get("parts", []):
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(
                    ToolCall(
                        id=fc.get("name", ""),
                        name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                    )
                )

        usage_meta = data.get("usageMetadata", {})
        return Message(
            role="assistant",
            content="\n".join(text_parts),
            tool_calls=tool_calls,
            metadata={
                "model": data.get("modelVersion", ""),
                "usage": {
                    "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                    "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                },
            },
        )
