"""
Anthropic Claude provider — direct Messages API via httpx.

Uses the Anthropic Messages API (https://docs.anthropic.com/en/docs/api-reference).
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

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_DEFAULT_MODEL = "claude-sonnet-4-20250514"


@ProviderRegistry.register("anthropic")
class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""

    provider_name = "anthropic"
    display_name = "Claude (Anthropic)"

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
            accumulated_text = ""
            tool_calls: list[ToolCall] = []
            current_tool: dict[str, Any] = {}
            usage: dict[str, int] = {}

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

                event_type = event.get("type", "")

                if event_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        current_tool = {
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "input_json": "",
                        }

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        accumulated_text += text
                        yield StreamChunk(text=text)
                    elif delta.get("type") == "input_json_delta":
                        if current_tool:
                            current_tool["input_json"] += delta.get("partial_json", "")

                elif event_type == "content_block_stop":
                    if current_tool:
                        try:
                            args = (
                                json.loads(current_tool["input_json"])
                                if current_tool["input_json"]
                                else {}
                            )
                        except json.JSONDecodeError:
                            args = {}
                        tc = ToolCall(
                            id=current_tool["id"],
                            name=current_tool["name"],
                            arguments=args,
                        )
                        tool_calls.append(tc)
                        current_tool = {}

                elif event_type == "message_delta":
                    u = event.get("usage", {})
                    if u:
                        usage.update(u)

                elif event_type == "message_stop":
                    pass

            yield StreamChunk(
                text="",
                tool_calls=tool_calls,
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
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
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
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": self._convert_messages(messages),
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [self._convert_tool(t) for t in tools]
        if stream:
            payload["stream"] = True
        return payload

    @staticmethod
    def _convert_messages(messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "tool":
                # Tool results are sent as user messages with tool_result content blocks
                content_blocks = []
                for tr in msg.tool_results:
                    content_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tr.tool_call_id,
                            "content": tr.content,
                            **({"is_error": True} if tr.is_error else {}),
                        }
                    )
                result.append({"role": "user", "content": content_blocks})
            elif msg.tool_calls:
                # Assistant message with tool use
                tc_blocks: list[dict[str, Any]] = []
                if msg.content:
                    tc_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    tc_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                result.append({"role": "assistant", "content": tc_blocks})
            else:
                result.append({"role": msg.role, "content": msg.content})
        return result

    @staticmethod
    def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> Message:
        content_blocks = data.get("content", [])
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )

        return Message(
            role="assistant",
            content="\n".join(text_parts),
            tool_calls=tool_calls,
            metadata={
                "model": data.get("model", ""),
                "usage": data.get("usage", {}),
                "stop_reason": data.get("stop_reason", ""),
            },
        )
