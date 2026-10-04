from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from teachx.providers.base import (
    BaseProvider,
    ContentDelta,
    LLMResult,
    LLMUsage,
    ProviderError,
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
        max_output_tokens: int = 1024,
        include_stream_usage: bool = True,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.include_stream_usage = include_stream_usage
        self.client = AsyncOpenAI(
            api_key=api_key or "missing-api-key",
            base_url=base_url,
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        started_at = time.perf_counter()
        try:
            response = await self.client.chat.completions.create(
                **self._request_kwargs(
                    messages,
                    tools,
                    max_output_tokens=max_output_tokens,
                )
            )
        except Exception as exc:
            raise self._translate_error(exc) from exc
        duration_seconds = time.perf_counter() - started_at
        choice = response.choices[0]
        message = choice.message
        content = message.content or ""
        return LLMResult(
            content=content,
            tool_calls=self._parse_tool_calls(message.tool_calls or []),
            finish_reason=choice.finish_reason or "stop",
            usage=self._usage_from_openai(
                getattr(response, "usage", None),
                messages,
                content,
                duration_seconds=duration_seconds,
                ttft_seconds=None,
            ),
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """消费供应商 SSE 流，并在结束时还原完整文本和工具调用。"""

        content_parts: list[str] = []
        tool_buffers: dict[int, dict[str, str]] = {}
        finish_reason = "stop"
        reported_usage: Any = None
        started_at = time.perf_counter()
        first_content_at: float | None = None

        try:
            request_kwargs = self._request_kwargs(
                messages,
                tools,
                max_output_tokens=max_output_tokens,
            )
            try:
                stream = await self.client.chat.completions.create(
                    **request_kwargs,
                    stream=True,
                    **(
                        {"stream_options": {"include_usage": True}}
                        if self.include_stream_usage
                        else {}
                    ),
                )
            except BadRequestError as exc:
                if (
                    not self.include_stream_usage
                    or "stream_options" not in str(exc).lower()
                ):
                    raise
                stream = await self.client.chat.completions.create(
                    **request_kwargs,
                    stream=True,
                )

            async for chunk in stream:
                if getattr(chunk, "usage", None) is not None:
                    reported_usage = chunk.usage
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                text = delta.content
                if isinstance(text, str) and text:
                    if first_content_at is None:
                        first_content_at = time.perf_counter()
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
        except Exception as exc:
            raise self._translate_error(exc) from exc

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

        content = "".join(content_parts)
        finished_at = time.perf_counter()
        yield StreamFinished(
            LLMResult(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=self._usage_from_openai(
                    reported_usage,
                    messages,
                    content,
                    duration_seconds=finished_at - started_at,
                    ttft_seconds=(
                        first_content_at - started_at
                        if first_content_at is not None
                        else None
                    ),
                ),
            )
        )

    def _request_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_output_tokens or self.max_output_tokens,
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

    @classmethod
    def _usage_from_openai(
        cls,
        usage: Any,
        messages: list[dict[str, Any]],
        completion: str,
        *,
        duration_seconds: float | None,
        ttft_seconds: float | None,
    ) -> LLMUsage:
        if usage is None:
            return cls._estimate_usage(
                messages,
                completion,
                duration_seconds=duration_seconds,
                ttft_seconds=ttft_seconds,
            )
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        completion_details = getattr(usage, "completion_tokens_details", None)
        cached_tokens = getattr(prompt_details, "cached_tokens", None)
        reasoning_tokens = getattr(completion_details, "reasoning_tokens", None)
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or prompt_tokens + completion_tokens,
            cached_tokens=(
                int(cached_tokens) if cached_tokens is not None else None
            ),
            reasoning_tokens=(
                int(reasoning_tokens) if reasoning_tokens is not None else None
            ),
            estimated=False,
            duration_seconds=duration_seconds,
            ttft_seconds=ttft_seconds,
        )

    @staticmethod
    def _estimate_usage(
        messages: list[dict[str, Any]],
        completion: str,
        *,
        duration_seconds: float | None,
        ttft_seconds: float | None,
    ) -> LLMUsage:
        prompt_chars = sum(len(str(item.get("content") or "")) for item in messages)
        prompt_tokens = max(1, prompt_chars // 4)
        completion_tokens = max(1, len(completion) // 4) if completion else 0
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated=True,
            duration_seconds=duration_seconds,
            ttft_seconds=ttft_seconds,
        )

    @staticmethod
    def _translate_error(exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, APITimeoutError):
            return ProviderError("模型请求超时，请稍后重试", code="provider_timeout")
        if isinstance(exc, RateLimitError):
            return ProviderError(
                "模型平台触发限流，请稍后重试",
                code="rate_limited",
                status_code=429,
            )
        if isinstance(exc, APIConnectionError):
            return ProviderError(
                "无法连接模型平台，请检查网络后重试",
                code="provider_connection_error",
            )
        if isinstance(exc, InternalServerError):
            return ProviderError(
                "模型平台暂时不可用，请稍后重试",
                code="provider_server_error",
                status_code=500,
            )
        if isinstance(exc, APIStatusError):
            status_code = int(getattr(exc, "status_code", 0) or 0)
            retryable = status_code == 429 or status_code >= 500
            return ProviderError(
                f"模型平台返回 {status_code or '错误状态'}",
                code="provider_http_error",
                retryable=retryable,
                status_code=status_code or None,
            )
        return ProviderError(
            "模型流式响应中断，请重试",
            code="stream_interrupted",
        )
