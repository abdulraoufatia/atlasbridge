"""
OpenAI GPT provider — direct Chat Completions API via httpx.

Uses the OpenAI Chat Completions API (https://platform.openai.com/docs/api-reference/chat).
No SDK dependency — raw httpx calls.

Supports:
  - Conversation with system prompt
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

_API_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4o"


@ProviderRegistry.register("openai")
class OpenAIProvider(BaseProvider):
    """OpenAI GPT API provider."""

    provider_name = "openai"
    display_name = "GPT (OpenAI)"

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
        payload = self._build_payload(messages, tools, system, max_tokens, stream=False)

        resp = await client.post(
            _API_URL,
            json=payload,
            headers=self._headers(),
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
        payload = self._build_payload(messages, tools, system, max_tokens, stream=True)

        async with client.stream(
            "POST",
            _API_URL,
            json=payload,
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            tool_calls_accum: dict[int, dict[str, Any]] = {}

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    break

                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                choices = event.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})

                # Text content
                text = delta.get("content", "")
                if text:
                    yield StreamChunk(text=text)

                # Tool calls (streamed incrementally)
                for tc_delta in delta.get("tool_calls", []):
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_accum:
                        tool_calls_accum[idx] = {
                            "id": tc_delta.get("id", ""),
                            "name": "",
                            "arguments": "",
                        }
                    fn = tc_delta.get("function", {})
                    if "name" in fn:
                        tool_calls_accum[idx]["name"] = fn["name"]
                    if "arguments" in fn:
                        tool_calls_accum[idx]["arguments"] += fn["arguments"]
                    if tc_delta.get("id"):
                        tool_calls_accum[idx]["id"] = tc_delta["id"]

            # Build final tool calls
            final_tool_calls: list[ToolCall] = []
            for _, tc_data in sorted(tool_calls_accum.items()):
                try:
                    args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                final_tool_calls.append(
                    ToolCall(id=tc_data["id"], name=tc_data["name"], arguments=args)
                )

            usage = event.get("usage", {}) if event else {}
            yield StreamChunk(
                text="",
                tool_calls=final_tool_calls,
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

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        system: str,
        max_tokens: int,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        converted = self._convert_messages(messages, system)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": converted,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [self._convert_tool(t) for t in tools]
        if stream:
            payload["stream"] = True
        return payload

    @staticmethod
    def _convert_messages(messages: list[Message], system: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if system:
            result.append({"role": "system", "content": system})
        for msg in messages:
            if msg.role == "tool":
                for tr in msg.tool_results:
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": tr.tool_call_id,
                            "content": tr.content,
                        }
                    )
            elif msg.tool_calls:
                entry: dict[str, Any] = {"role": "assistant"}
                if msg.content:
                    entry["content"] = msg.content
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                result.append(entry)
            else:
                result.append({"role": msg.role, "content": msg.content})
        return result

    @staticmethod
    def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> Message:
        choices = data.get("choices", [])
        if not choices:
            return Message(role="assistant", content="")

        choice = choices[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""
        tool_calls: list[ToolCall] = []

        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args)
            )

        return Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            metadata={
                "model": data.get("model", ""),
                "usage": data.get("usage", {}),
                "finish_reason": choice.get("finish_reason", ""),
            },
        )
