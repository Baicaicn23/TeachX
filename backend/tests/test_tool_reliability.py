from __future__ import annotations

import asyncio
import sqlite3
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
    KnowledgeSearchTool,
    ToolContext,
    ToolError,
    ToolExecutionDefaults,
    ToolPolicy,
    ToolRegistry,
    ToolResult,
    ToolTransientError,
)
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


class FlakyTool(BaseTool):
    name = "flaky"
    description = "Fails a configurable number of times before succeeding."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=True, max_attempts=None, timeout_seconds=1.0)

    def __init__(self, failures: int = 1) -> None:
        self.failures = failures
        self.calls = 0

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context, kwargs
        self.calls += 1
        if self.calls <= self.failures:
            raise ToolTransientError("temporary failure")
        return ToolResult(content="recovered", metadata={"source": "test"})


class PermanentFailureTool(BaseTool):
    name = "permanent"
    description = "Always fails with a permanent validation error."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=True, max_attempts=None, timeout_seconds=1.0)

    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context, kwargs
        self.calls += 1
        raise ToolError("invalid input")


class SlowTool(BaseTool):
    name = "slow"
    description = "Sleeps longer than its configured timeout."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=True, max_attempts=2, timeout_seconds=0.01)

    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context, kwargs
        self.calls += 1
        await asyncio.sleep(0.05)
        return ToolResult(content="too late")


class FlakyKnowledgeService:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        del args, kwargs
        self.calls += 1
        if self.calls == 1:
            raise sqlite3.OperationalError("database is locked")
        return []


class ToolCallingProvider(BaseProvider):
    name = "tool-test"

    def __init__(self) -> None:
        self.calls = 0

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
        self.calls += 1
        if self.calls == 1:
            yield StreamFinished(
                LLMResult(
                    tool_calls=[
                        ToolCall(id="call-1", name="flaky", arguments={}),
                    ],
                    finish_reason="tool_calls",
                )
            )
            return
        yield ContentDelta("工具调用完成")
        yield StreamFinished(LLMResult(content="工具调用完成"))


def _registry(*tools: BaseTool) -> ToolRegistry:
    registry = ToolRegistry(
        ToolExecutionDefaults(
            max_attempts=3,
            timeout_seconds=1.0,
            retry_base_delay_seconds=0,
            retry_max_delay_seconds=0,
        )
    )
    for tool in tools:
        registry.register(tool)
    return registry


@pytest.mark.asyncio
async def test_transient_tool_failure_is_retried_then_succeeds() -> None:
    tool = FlakyTool(failures=1)
    result = await _registry(tool).execute("flaky", {})

    assert result.success is True
    assert result.content == "recovered"
    assert result.metadata is not None
    assert result.metadata["source"] == "test"
    assert result.metadata["attempt_count"] == 2
    assert result.metadata["retry_count"] == 1
    assert result.metadata["read_only"] is True
    assert tool.calls == 2


@pytest.mark.asyncio
async def test_permanent_tool_failure_is_not_retried() -> None:
    tool = PermanentFailureTool()
    result = await _registry(tool).execute("permanent", {})

    assert result.success is False
    assert result.metadata is not None
    assert result.metadata["error_code"] == "tool_error"
    assert result.metadata["retryable"] is False
    assert result.metadata["attempt_count"] == 1
    assert result.metadata["retry_count"] == 0
    assert tool.calls == 1


@pytest.mark.asyncio
async def test_retry_exhaustion_returns_observable_failure_metadata() -> None:
    tool = FlakyTool(failures=99)
    result = await _registry(tool).execute("flaky", {})

    assert result.success is False
    assert result.metadata is not None
    assert result.metadata["error_code"] == "tool_transient_error"
    assert result.metadata["retryable"] is True
    assert result.metadata["attempt_count"] == 3
    assert result.metadata["retry_count"] == 2
    assert result.metadata["retry_delays_ms"] == [0.0, 0.0]
    assert tool.calls == 3


@pytest.mark.asyncio
async def test_tool_timeout_is_retryable_and_reported() -> None:
    tool = SlowTool()
    result = await _registry(tool).execute("slow", {})

    assert result.success is False
    assert result.metadata is not None
    assert result.metadata["error_code"] == "tool_timeout"
    assert result.metadata["timed_out"] is True
    assert result.metadata["retryable"] is True
    assert result.metadata["attempt_count"] == 2
    assert tool.calls == 2


@pytest.mark.asyncio
async def test_knowledge_search_retries_transient_database_lock() -> None:
    service = FlakyKnowledgeService()
    registry = _registry(KnowledgeSearchTool(service))  # type: ignore[arg-type]

    result = await registry.execute("knowledge_search", {"query": "测试"})

    assert result.success is True
    assert result.metadata is not None
    assert result.metadata["attempt_count"] == 2
    assert service.calls == 2


@pytest.mark.asyncio
async def test_unknown_tool_has_stable_failure_metadata() -> None:
    result = await _registry().execute("missing", {})

    assert result.success is False
    assert result.metadata == {
        "attempt_count": 0,
        "retry_count": 0,
        "error_code": "unknown_tool",
        "retryable": False,
        "duration_ms": 0.0,
    }


@pytest.mark.asyncio
async def test_runtime_exposes_tool_attempt_metadata(tmp_path: Path) -> None:
    database = Database(tmp_path / "tool-reliability.db")
    await database.initialize()
    runtime = AgentRuntime(
        provider=ToolCallingProvider(),
        tools=_registry(FlakyTool(failures=1)),
        repository=SessionRepository(database),
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="调用工具")
        )
    ]

    tool_result = next(event for event in events if event["type"] == "tool_result")
    assert tool_result["metadata"]["attempt_count"] == 2
    assert tool_result["metadata"]["retry_count"] == 1
    assert events[-1]["metadata"]["status"] == "completed"
