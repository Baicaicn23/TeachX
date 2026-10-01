from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from teachx.providers.base import LLMResult, ToolCall


class OpenAICompatibleProvider:
    """Provider adapter for OpenAI and compatible Chat Completions APIs."""

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
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"raw": call.function.arguments}
            tool_calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=arguments,
                )
            )
        return LLMResult(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=response.choices[0].finish_reason or "stop",
        )
