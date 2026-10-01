from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from teachx.providers.base import (
    BaseProvider,
    ContentDelta,
    LLMResult,
    ProviderEvent,
    StreamFinished,
    ToolCall,
)


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI 及兼容 Chat Completions 接口的适配器。"""

    name = "openai"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None,
        temperature: float,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.client = AsyncOpenAI(
            api_key=api_key or "missing-api-key",
            base_url=base_url,
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResult:
        response = await self.client.chat.completions.create(
            **self._request_kwargs(messages, tools)
        )
        choice = response.choices[0]
        message = choice.message
        return LLMResult(
            content=message.content or "",
            tool_calls=self._parse_tool_calls(message.tool_calls or []),
            finish_reason=choice.finish_reason or "stop",
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[ProviderEvent]:
        """消费供应商 SSE 流，并在结束时还原完整文本和工具调用。"""

        stream = await self.client.chat.completions.create(
            **self._request_kwargs(messages, tools),
            stream=True,
        )
        content_parts: list[str] = []
        tool_buffers: dict[int, dict[str, str]] = {}
        finish_reason = "stop"

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            text = delta.content
            if isinstance(text, str) and text:
                content_parts.append(text)
                yield ContentDelta(text)

            for tool_delta in delta.tool_calls or []:
                index = tool_delta.index
                buffer = tool_buffers.setdefault(
                    index,
                    {"id": "", "name": "", "arguments": ""},
                )
                if tool_delta.id:
                    buffer["id"] = tool_delta.id
                function = tool_delta.function
                if function and function.name:
                    buffer["name"] = function.name
                if function and function.arguments:
                    buffer["arguments"] += function.arguments

            if choice.finish_reason:
                finish_reason = choice.finish_reason

        tool_calls: list[ToolCall] = []
        for index in sorted(tool_buffers):
            buffer = tool_buffers[index]
            if not buffer["name"]:
                continue
            tool_calls.append(
                ToolCall(
                    id=buffer["id"] or f"tool-call-{index}",
                    name=buffer["name"],
                    arguments=self._parse_arguments(buffer["arguments"]),
                )
            )

        yield StreamFinished(
            LLMResult(
                content="".join(content_parts),
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
        )

    def _request_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return kwargs

    @staticmethod
    def _parse_tool_calls(calls: list[Any]) -> list[ToolCall]:
        parsed: list[ToolCall] = []
        for call in calls:
            parsed.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=OpenAICompatibleProvider._parse_arguments(call.function.arguments),
                )
            )
        return parsed

    @staticmethod
    def _parse_arguments(raw_arguments: str | None) -> dict[str, Any]:
        try:
            value = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return {"raw": raw_arguments or ""}
        return value if isinstance(value, dict) else {"value": value}
