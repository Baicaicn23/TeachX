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


class ReadTrackerTool(BaseTool):
    """Read-only tool that records peak concurrency and completion order."""

    name = "read_tracker"
    description = "Records overlap while pretending to do read-only work."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=True, max_attempts=1, timeout_seconds=5.0)

    def __init__(self, shared: dict[str, Any] | None = None) -> None:
        self.active = 0
        self.peak = 0
        self.completion_order: list[str] = []
        self.started_with_side_active: list[int] = []
        self.shared = shared if shared is not None else {}

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.shared["read_active"] = self.shared.get("read_active", 0) + 1
        self.started_with_side_active.append(self.shared.get("side_active", 0))
        tag = str(kwargs.get("tag", ""))
        delay = float(kwargs.get("delay", 0.02))
        await asyncio.sleep(delay)
        self.active -= 1
        self.shared["read_active"] -= 1
        self.completion_order.append(tag)
        return ToolResult(content=f"read-{tag}")


class SideTrackerTool(BaseTool):
    """Side-effect tool that records whether read tools were active alongside it."""

    name = "side_tracker"
    description = "Records overlap while pretending to perform a side effect."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=False, max_attempts=1, timeout_seconds=5.0)

    def __init__(self, shared: dict[str, Any] | None = None) -> None:
        self.active = 0
        self.peak = 0
        self.started_with_read_active: list[int] = []
        self.shared = shared if shared is not None else {}

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context, kwargs
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.shared["side_active"] = self.shared.get("side_active", 0) + 1
        self.started_with_read_active.append(self.shared.get("read_active", 0))
        await asyncio.sleep(0.03)
        self.active -= 1
        self.shared["side_active"] -= 1
        return ToolResult(content="side-done")


class MultiCallProvider(BaseProvider):
    """Emits a configured list of tool calls in round one, then answers."""

    name = "multi-call-test"

    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls
        self.round = 0
        self.second_round_messages: list[dict[str, Any]] = []

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
        del tools, max_output_tokens
        self.round += 1
        if self.round == 1:
            yield StreamFinished(
                LLMResult(
                    tool_calls=[
                        ToolCall(id=f"call-{index}", name=name, arguments=arguments)
                        for index, (name, arguments) in enumerate(self.calls, start=1)
                    ],
                    finish_reason="tool_calls",
                )
            )
            return
        self.second_round_messages = list(messages)
        yield ContentDelta("完成")
        yield StreamFinished(LLMResult(content="完成"))


def _registry(*tools: BaseTool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


async def _run_turn(
    provider: MultiCallProvider,
    registry: ToolRegistry,
    *,
    max_tool_concurrency: int,
    tmp_path: Path,
) -> list[dict[str, Any]]:
    database = Database(tmp_path / "tool-concurrency.db")
    await database.initialize()
    runtime = AgentRuntime(
        provider=provider,
        tools=registry,
        repository=SessionRepository(database),
        max_tool_concurrency=max_tool_concurrency,
    )
    return [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="并发调用工具")
        )
    ]


def _result_call_ids(events: list[dict[str, Any]]) -> list[str]:
    return [
        event["metadata"]["call_id"] for event in events if event["type"] == "tool_result"
    ]


@pytest.mark.asyncio
async def test_consecutive_read_only_calls_run_concurrently(tmp_path: Path) -> None:
    read = ReadTrackerTool()
    provider = MultiCallProvider(
        [
            ("read_tracker", {"tag": "a", "delay": 0.05}),
            ("read_tracker", {"tag": "b", "delay": 0.05}),
        ]
    )
    events = await _run_turn(
        provider, _registry(read), max_tool_concurrency=2, tmp_path=tmp_path
    )

    assert read.peak == 2
    assert events[-1]["metadata"]["status"] == "completed"
    # 一批的 tool_call 事件先全部发出,再按顺序发 tool_result。
    event_types = [event["type"] for event in events]
    first_result_index = event_types.index("tool_result")
    call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(call_events) == 2
    assert events.index(call_events[1]) < first_result_index


@pytest.mark.asyncio
async def test_results_keep_model_call_order_despite_completion_order(
    tmp_path: Path,
) -> None:
    read = ReadTrackerTool()
    provider = MultiCallProvider(
        [
            ("read_tracker", {"tag": "slow", "delay": 0.09}),
            ("read_tracker", {"tag": "fast", "delay": 0.01}),
        ]
    )
    events = await _run_turn(
        provider, _registry(read), max_tool_concurrency=2, tmp_path=tmp_path
    )

    # fast 实际先完成,证明 gather 需要保序。
    assert read.completion_order == ["fast", "slow"]
    assert _result_call_ids(events) == ["call-1", "call-2"]


@pytest.mark.asyncio
async def test_side_effect_calls_run_serially(tmp_path: Path) -> None:
    shared: dict[str, Any] = {}
    side = SideTrackerTool(shared)
    provider = MultiCallProvider(
        [
            ("side_tracker", {}),
            ("side_tracker", {}),
        ]
    )
    events = await _run_turn(
        provider, _registry(side), max_tool_concurrency=4, tmp_path=tmp_path
    )

    assert side.peak == 1
    assert _result_call_ids(events) == ["call-1", "call-2"]


@pytest.mark.asyncio
async def test_mixed_calls_keep_side_effects_isolated_and_ordered(
    tmp_path: Path,
) -> None:
    shared: dict[str, Any] = {}
    read = ReadTrackerTool(shared)
    side = SideTrackerTool(shared)
    provider = MultiCallProvider(
        [
            ("read_tracker", {"tag": "a", "delay": 0.05}),
            ("read_tracker", {"tag": "b", "delay": 0.05}),
            ("side_tracker", {}),
            ("read_tracker", {"tag": "c", "delay": 0.01}),
        ]
    )
    events = await _run_turn(
        provider, _registry(read, side), max_tool_concurrency=4, tmp_path=tmp_path
    )

    # 前两个只读工具并发;副作用工具与任何只读工具都不重叠。
    assert read.peak == 2
    assert side.peak == 1
    assert side.started_with_read_active == [0]
    assert all(active == 0 for active in read.started_with_side_active)
    assert _result_call_ids(events) == ["call-1", "call-2", "call-3", "call-4"]
    # 发给模型的 tool 消息保持模型调用顺序。
    tool_messages = [
        item for item in provider.second_round_messages if item.get("role") == "tool"
    ]
    assert [m["tool_call_id"] for m in tool_messages] == [
        "call-1",
        "call-2",
        "call-3",
        "call-4",
    ]


@pytest.mark.asyncio
async def test_max_concurrency_bounds_parallelism(tmp_path: Path) -> None:
    read = ReadTrackerTool()
    provider = MultiCallProvider(
        [
            ("read_tracker", {"tag": "a", "delay": 0.04}),
            ("read_tracker", {"tag": "b", "delay": 0.04}),
            ("read_tracker", {"tag": "c", "delay": 0.04}),
        ]
    )
    await _run_turn(
        provider, _registry(read), max_tool_concurrency=2, tmp_path=tmp_path
    )

    assert read.peak == 2


@pytest.mark.asyncio
async def test_concurrency_of_one_runs_everything_serially(tmp_path: Path) -> None:
    read = ReadTrackerTool()
    provider = MultiCallProvider(
        [
            ("read_tracker", {"tag": "a", "delay": 0.03}),
            ("read_tracker", {"tag": "b", "delay": 0.03}),
        ]
    )
    events = await _run_turn(
        provider, _registry(read), max_tool_concurrency=1, tmp_path=tmp_path
    )

    assert read.peak == 1
    assert _result_call_ids(events) == ["call-1", "call-2"]


def test_registry_reports_read_only_flag() -> None:
    registry = _registry(ReadTrackerTool(), SideTrackerTool())

    assert registry.is_read_only("read_tracker") is True
    assert registry.is_read_only("side_tracker") is False
    assert registry.is_read_only("missing") is False
