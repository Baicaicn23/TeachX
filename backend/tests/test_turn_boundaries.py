from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from teachx.providers.base import (
    BaseProvider,
    ContentDelta,
    LLMResult,
    ProviderEvent,
    StreamFinished,
    ToolCall,
)
from teachx.providers.openai_compat import OpenAICompatibleProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import (
    BaseTool,
    ToolContext,
    ToolPolicy,
    ToolRegistry,
    ToolResult,
)
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


class EchoTool(BaseTool):
    name = "echo"
    description = "Returns its tag."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=True, max_attempts=1, timeout_seconds=10.0)

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return ToolResult(content=f"echo:{kwargs.get('tag', '')}")


class LoopToolProvider(BaseProvider):
    """Requests a tool call every round and never produces a final answer."""

    name = "loop-tool-test"

    def __init__(self, *, with_content: bool = False) -> None:
        self.with_content = with_content

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        del messages, tools, max_output_tokens
        return LLMResult(content="")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        del messages, tools, max_output_tokens
        if self.with_content:
            yield ContentDelta("部分回答已经生成。")
        yield StreamFinished(
            LLMResult(
                tool_calls=[ToolCall(id="call-loop", name="echo", arguments={})],
                finish_reason="tool_calls",
            )
        )


class HangingStreamProvider(BaseProvider):
    """Streams two deltas quickly, then stalls longer than the turn timeout."""

    name = "hanging-stream-test"

    def __init__(self, hang_seconds: float = 5.0) -> None:
        self.hang_seconds = hang_seconds

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        del messages, tools, max_output_tokens
        return LLMResult(content="")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        del messages, tools, max_output_tokens
        yield ContentDelta("超时前的")
        yield ContentDelta("部分内容。")
        await asyncio.sleep(self.hang_seconds)
        yield ContentDelta("迟到的内容")
        yield StreamFinished(LLMResult(content="迟到的内容"))


async def _run(
    provider: BaseProvider,
    tool: BaseTool,
    *,
    max_rounds: int = 6,
    turn_timeout_seconds: float = 300.0,
    tmp_path: Path,
) -> list[dict[str, Any]]:
    database = Database(tmp_path / "turn-boundaries.db")
    await database.initialize()
    registry = ToolRegistry()
    registry.register(tool)
    runtime = AgentRuntime(
        provider=provider,
        tools=registry,
        repository=SessionRepository(database),
        max_rounds=max_rounds,
        turn_timeout_seconds=turn_timeout_seconds,
    )
    return [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="测试")
        )
    ]


def _terminal_error(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in reversed(events)
            if event["type"] == "error"
            and event.get("metadata", {}).get("turn_terminal")
        ),
        None,
    )


@pytest.mark.asyncio
async def test_max_rounds_without_content_fails_openly(tmp_path: Path) -> None:
    events = await _run(
        LoopToolProvider(), EchoTool(), max_rounds=2, tmp_path=tmp_path
    )

    done = events[-1]
    assert done["type"] == "done"
    assert done["metadata"]["status"] == "failed"
    assert done["metadata"]["assistant_message_id"] is None
    assert done["metadata"]["error_code"] == "max_rounds_exceeded"
    error = _terminal_error(events)
    assert error is not None
    assert error["metadata"]["error_code"] == "max_rounds_exceeded"
    assert error["metadata"]["retryable"] is True
    # 没有伪装成回答的罐头文本,也没有 result 事件。
    assert not [e for e in events if e["type"] == "result"]


@pytest.mark.asyncio
async def test_max_rounds_with_partial_content_saves_partial(tmp_path: Path) -> None:
    events = await _run(
        LoopToolProvider(with_content=True),
        EchoTool(),
        max_rounds=2,
        tmp_path=tmp_path,
    )

    done = events[-1]
    assert done["metadata"]["status"] == "failed"
    assert done["metadata"]["assistant_message_id"] is not None
    assert done["metadata"]["partial"] is True
    assert done["metadata"]["error_code"] == "max_rounds_exceeded"
    error = _terminal_error(events)
    assert error is not None
    assert error["metadata"]["retryable"] is True
    result_event = next(e for e in events if e["type"] == "result")
    assert "部分回答已经生成" in result_event["content"]


@pytest.mark.asyncio
async def test_turn_timeout_mid_stream_fails_with_partial(tmp_path: Path) -> None:
    events = await _run(
        HangingStreamProvider(hang_seconds=5.0),
        EchoTool(),
        turn_timeout_seconds=0.2,
        tmp_path=tmp_path,
    )

    done = events[-1]
    assert done["metadata"]["status"] == "failed"
    assert done["metadata"]["partial"] is True
    assert done["metadata"]["assistant_message_id"] is not None
    assert done["metadata"]["error_code"] == "turn_timeout"
    error = _terminal_error(events)
    assert error is not None
    assert error["metadata"]["error_code"] == "turn_timeout"
    assert error["metadata"]["retryable"] is True
    result_event = next(e for e in events if e["type"] == "result")
    assert "超时前的" in result_event["content"]


@pytest.mark.asyncio
async def test_turn_timeout_during_slow_tool_batch(tmp_path: Path) -> None:
    events = await _run(
        LoopToolProvider(),
        EchoTool(delay_seconds=2.0),
        turn_timeout_seconds=0.2,
        tmp_path=tmp_path,
    )

    error = _terminal_error(events)
    assert error is not None
    assert error["metadata"]["error_code"] == "turn_timeout"
    assert events[-1]["metadata"]["status"] == "failed"


@pytest.mark.asyncio
async def test_turn_timeout_disabled_lets_slow_turn_finish(tmp_path: Path) -> None:
    events = await _run(
        HangingStreamProvider(hang_seconds=0.3),
        EchoTool(),
        turn_timeout_seconds=0.0,
        max_rounds=1,
        tmp_path=tmp_path,
    )

    assert events[-1]["metadata"]["status"] == "completed"
    result_event = next(e for e in events if e["type"] == "result")
    assert "迟到的内容" in result_event["content"]


def test_stream_interruption_maps_to_unified_code() -> None:
    error = OpenAICompatibleProvider._translate_error(RuntimeError("boom"))

    assert error.code == "stream_interrupted"
    assert error.retryable is True
