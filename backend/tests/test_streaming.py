from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx2
import pytest
from openai import (
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from teachx.providers.base import ContentDelta, StreamFinished
from teachx.providers.mock import MockProvider
from teachx.providers.openai_compat import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_mock_provider_streams_multiple_content_deltas() -> None:
    provider = MockProvider()
    events = [
        event
        async for event in provider.stream(
            [{"role": "user", "content": "解释 Agent Loop"}],
            [],
        )
    ]

    deltas = [event.content for event in events if isinstance(event, ContentDelta)]
    finished = next(event for event in events if isinstance(event, StreamFinished))

    assert len(deltas) > 1
    assert "".join(deltas) == finished.result.content


@pytest.mark.asyncio
async def test_openai_stream_assembles_streamed_tool_arguments() -> None:
    provider = OpenAICompatibleProvider(
        model="test-model",
        api_key="test-key",
        base_url="http://example.invalid/v1",
        temperature=0,
        max_output_tokens=55,
    )
    provider.client = _FakeOpenAIClient()  # type: ignore[assignment]

    events = [
        event
        async for event in provider.stream(
            [{"role": "user", "content": "计算 2 + 3"}],
            [
                {
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "description": "calculate",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        )
    ]

    deltas = [event.content for event in events if isinstance(event, ContentDelta)]
    finished = next(event for event in events if isinstance(event, StreamFinished))

    assert deltas == ["我先", "计算。"]
    assert finished.result.content == "我先计算。"
    assert len(finished.result.tool_calls) == 1
    assert finished.result.tool_calls[0].name == "calculator"
    assert finished.result.tool_calls[0].arguments == {"expression": "2 + 3"}
    assert finished.result.finish_reason == "tool_calls"
    assert finished.result.usage is not None
    assert finished.result.usage.prompt_tokens == 11
    assert finished.result.usage.completion_tokens == 4
    assert finished.result.usage.total_tokens == 15


def test_openai_error_mapping_is_stable() -> None:
    provider = OpenAICompatibleProvider(
        model="test-model",
        api_key="test-key",
        base_url="http://example.invalid/v1",
        temperature=0,
    )
    request = httpx2.Request(
        "POST",
        "http://example.invalid/v1/chat/completions",
    )
    response_429 = httpx2.Response(429, request=request)
    response_500 = httpx2.Response(500, request=request)
    response_400 = httpx2.Response(400, request=request)

    timeout = provider._translate_error(APITimeoutError(request=request))
    limited = provider._translate_error(
        RateLimitError("limited", response=response_429, body=None)
    )
    server = provider._translate_error(
        InternalServerError("server", response=response_500, body=None)
    )
    bad_request = provider._translate_error(
        APIStatusError("bad request", response=response_400, body=None)
    )

    assert (timeout.code, timeout.retryable) == ("provider_timeout", True)
    assert (limited.code, limited.retryable, limited.status_code) == (
        "rate_limited",
        True,
        429,
    )
    assert (server.code, server.retryable, server.status_code) == (
        "provider_server_error",
        True,
        500,
    )
    assert (bad_request.code, bad_request.retryable, bad_request.status_code) == (
        "provider_http_error",
        False,
        400,
    )


@pytest.mark.asyncio
async def test_openai_stream_retries_when_usage_options_are_unsupported() -> None:
    provider = OpenAICompatibleProvider(
        model="test-model",
        api_key="test-key",
        base_url="http://example.invalid/v1",
        temperature=0,
    )
    client = _UnsupportedStreamOptionsClient()
    provider.client = client  # type: ignore[assignment]

    events = [
        event
        async for event in provider.stream(
            [{"role": "user", "content": "你好"}],
            [],
        )
    ]

    finished = next(event for event in events if isinstance(event, StreamFinished))
    assert client.chat.completions.attempts == 2
    assert finished.result.content == "兼容回答"
    assert finished.result.usage is not None
    assert finished.result.usage.estimated is True


class _FakeFunction:
    def __init__(self, name: str | None = None, arguments: str | None = None) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCallDelta:
    def __init__(
        self,
        index: int,
        *,
        call_id: str | None = None,
        name: str | None = None,
        arguments: str | None = None,
    ) -> None:
        self.index = index
        self.id = call_id
        self.function = _FakeFunction(name, arguments)


class _FakeDelta:
    def __init__(
        self,
        *,
        content: str | None = None,
        tool_calls: list[_FakeToolCallDelta] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeChoice:
    def __init__(self, delta: _FakeDelta, finish_reason: str | None = None) -> None:
        self.delta = delta
        self.finish_reason = finish_reason


class _FakeChunk:
    def __init__(
        self,
        delta: _FakeDelta | None,
        finish_reason: str | None = None,
        *,
        usage: _FakeUsage | None = None,
    ) -> None:
        self.choices = [_FakeChoice(delta, finish_reason)] if delta is not None else []
        self.usage = usage


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 4
    total_tokens = 15
    prompt_tokens_details = None
    completion_tokens_details = None


class _FakeStream:
    def __init__(self, chunks: list[_FakeChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> AsyncIterator[_FakeChunk]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[_FakeChunk]:
        for chunk in self._chunks:
            yield chunk


class _FakeCompletions:
    async def create(self, **kwargs: Any) -> _FakeStream:
        assert kwargs["stream"] is True
        assert kwargs["max_tokens"] == 55
        assert kwargs["stream_options"] == {"include_usage": True}
        return _FakeStream(
            [
                _FakeChunk(_FakeDelta(content="我先")),
                _FakeChunk(
                    _FakeDelta(
                        tool_calls=[
                            _FakeToolCallDelta(
                                0,
                                call_id="call-1",
                                name="calculator",
                                arguments='{"expression":',
                            )
                        ]
                    )
                ),
                _FakeChunk(_FakeDelta(content="计算。")),
                _FakeChunk(
                    _FakeDelta(
                        tool_calls=[
                            _FakeToolCallDelta(0, arguments='"2 + 3"}'),
                        ]
                    ),
                    finish_reason="tool_calls",
                ),
                _FakeChunk(None, usage=_FakeUsage()),
            ]
        )


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


class _UnsupportedStreamOptionsCompletions:
    def __init__(self) -> None:
        self.attempts = 0

    async def create(self, **kwargs: Any) -> _FakeStream:
        self.attempts += 1
        if self.attempts == 1:
            request = httpx2.Request(
                "POST",
                "http://example.invalid/v1/chat/completions",
            )
            response = httpx2.Response(400, request=request)
            raise BadRequestError(
                "stream_options is unsupported",
                response=response,
                body=None,
            )
        assert "stream_options" not in kwargs
        return _FakeStream([_FakeChunk(_FakeDelta(content="兼容回答"))])


class _UnsupportedStreamOptionsChat:
    def __init__(self) -> None:
        self.completions = _UnsupportedStreamOptionsCompletions()


class _UnsupportedStreamOptionsClient:
    def __init__(self) -> None:
        self.chat = _UnsupportedStreamOptionsChat()
