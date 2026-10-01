from collections.abc import AsyncIterator
from typing import Any

import pytest

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
    def __init__(self, delta: _FakeDelta, finish_reason: str | None = None) -> None:
        self.choices = [_FakeChoice(delta, finish_reason)]


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
            ]
        )


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()
