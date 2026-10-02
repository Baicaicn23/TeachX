from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiosqlite
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
from teachx.runtime.tool_executions import (
    ToolExecutionStore,
    compute_idempotency_key,
)
from teachx.runtime.tools import (
    BaseTool,
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


class SideEffectTool(BaseTool):
    name = "side_effect"
    description = "Pretends to perform a side effect and counts executions."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=False, max_attempts=1, timeout_seconds=1.0)

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.calls = 0
        self.delay_seconds = delay_seconds

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context, kwargs
        self.calls += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return ToolResult(
            content="effect-done",
            metadata={"sources": [{"id": "s-1"}], "side_effect": True},
        )


class PermanentFailureTool(BaseTool):
    name = "permanent"
    description = "Always fails with a permanent validation error."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=False, max_attempts=1, timeout_seconds=1.0)

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


class TransientFailureTool(BaseTool):
    name = "transient"
    description = "Always fails with a retryable transient error."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=False, max_attempts=2, timeout_seconds=1.0)

    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context, kwargs
        self.calls += 1
        raise ToolTransientError("temporary outage")


class DoubleCallProvider(BaseProvider):
    name = "double-call-test"

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
                        ToolCall(id="call-1", name="side_effect", arguments={}),
                        ToolCall(id="call-1", name="side_effect", arguments={}),
                    ],
                    finish_reason="tool_calls",
                )
            )
            return
        yield ContentDelta("工具调用完成")
        yield StreamFinished(LLMResult(content="工具调用完成"))


def _database(tmp_path: Path, name: str = "idempotency.db") -> Database:
    return Database(tmp_path / name)


def _registry(tool: BaseTool, database: Database) -> ToolRegistry:
    registry = ToolRegistry(
        ToolExecutionDefaults(
            max_attempts=3,
            timeout_seconds=1.0,
            retry_base_delay_seconds=0,
            retry_max_delay_seconds=0,
        ),
        execution_store=ToolExecutionStore(database),
    )
    registry.register(tool)
    return registry


def _context(
    user_id: str = "user-1",
    turn_id: str = "turn-1",
    session_id: str = "session-1",
) -> ToolContext:
    return ToolContext(session_id=session_id, user_id=user_id, turn_id=turn_id)


def _key(context: ToolContext, call_id: str = "call-1") -> str:
    return compute_idempotency_key(
        user_id=context.user_id,
        session_id=context.session_id,
        turn_id=context.turn_id,
        call_id=call_id,
        tool_name="side_effect",
        arguments={},
    )


@pytest.mark.asyncio
async def test_first_execution_runs_tool_and_records(tmp_path: Path) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = SideEffectTool()
    registry = _registry(tool, database)

    result = await registry.execute(
        "side_effect",
        {},
        context=_context(),
        call_id="call-1",
    )

    assert result.success is True
    assert result.content == "effect-done"
    assert result.metadata is not None
    assert result.metadata["deduplicated"] is False
    assert result.metadata["replayed"] is False
    assert result.metadata["execution_status"] == "completed"
    assert result.metadata["idempotency_key_hash"]
    assert tool.calls == 1

    store = ToolExecutionStore(database)
    record = await store.get(_key(_context()))
    assert record is not None
    assert record.status == "completed"
    assert record.tool_name == "side_effect"
    assert record.attempt_count == 1
    assert record.result_metadata.get("side_effect") is True


@pytest.mark.asyncio
async def test_duplicate_call_replays_result_without_reexecuting(tmp_path: Path) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = SideEffectTool()
    registry = _registry(tool, database)

    first = await registry.execute("side_effect", {}, context=_context(), call_id="call-1")
    second = await registry.execute("side_effect", {}, context=_context(), call_id="call-1")

    assert tool.calls == 1
    assert second.success is True
    assert second.content == first.content
    assert second.metadata is not None
    assert second.metadata["deduplicated"] is True
    assert second.metadata["replayed"] is True
    assert second.metadata["execution_status"] == "completed"
    assert second.metadata["sources"] == [{"id": "s-1"}]


@pytest.mark.asyncio
async def test_permanent_failure_is_replayed_without_reexecuting(tmp_path: Path) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = PermanentFailureTool()
    registry = _registry(tool, database)

    first = await registry.execute("permanent", {}, context=_context(), call_id="call-1")
    second = await registry.execute("permanent", {}, context=_context(), call_id="call-1")

    assert tool.calls == 1
    assert first.success is False
    assert first.metadata is not None
    assert first.metadata["replayed"] is False
    assert second.success is False
    assert second.metadata is not None
    assert second.metadata["replayed"] is True
    assert second.metadata["deduplicated"] is True
    assert second.metadata["execution_status"] == "failed"
    assert second.metadata["error_code"] == "tool_error"
    assert second.metadata["retryable"] is False


@pytest.mark.asyncio
async def test_same_arguments_in_different_turn_or_call_are_not_deduplicated(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = SideEffectTool()
    registry = _registry(tool, database)

    await registry.execute("side_effect", {}, context=_context(), call_id="call-1")
    await registry.execute("side_effect", {}, context=_context(turn_id="turn-2"), call_id="call-1")
    await registry.execute("side_effect", {}, context=_context(), call_id="call-2")

    assert tool.calls == 3


@pytest.mark.asyncio
async def test_different_users_do_not_share_execution_records(tmp_path: Path) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = SideEffectTool()
    registry = _registry(tool, database)

    await registry.execute(
        "side_effect", {}, context=_context(user_id="user-1"), call_id="call-1"
    )
    await registry.execute(
        "side_effect", {}, context=_context(user_id="user-2"), call_id="call-1"
    )

    assert tool.calls == 2

    store = ToolExecutionStore(database)
    first = await store.get(_key(_context(user_id="user-1")))
    second = await store.get(_key(_context(user_id="user-2")))
    assert first is not None and second is not None
    assert first.idempotency_key != second.idempotency_key


@pytest.mark.asyncio
async def test_concurrent_duplicate_calls_execute_only_once(tmp_path: Path) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = SideEffectTool(delay_seconds=0.05)
    registry = _registry(tool, database)

    results = await asyncio.gather(
        registry.execute("side_effect", {}, context=_context(), call_id="call-1"),
        registry.execute("side_effect", {}, context=_context(), call_id="call-1"),
    )

    assert tool.calls == 1
    assert all(result.success for result in results)
    replayed_flags = sorted(result.metadata["replayed"] for result in results)
    assert replayed_flags == [False, True]


@pytest.mark.asyncio
async def test_runtime_tool_result_events_carry_dedup_metadata(tmp_path: Path) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = SideEffectTool()
    registry = _registry(tool, database)
    runtime = AgentRuntime(
        provider=DoubleCallProvider(),
        tools=registry,
        repository=SessionRepository(database),
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="重复调用工具")
        )
    ]

    tool_results = [event for event in events if event["type"] == "tool_result"]
    assert len(tool_results) == 2
    assert tool_results[0]["metadata"]["replayed"] is False
    assert tool_results[0]["metadata"]["deduplicated"] is False
    assert tool_results[1]["metadata"]["replayed"] is True
    assert tool_results[1]["metadata"]["deduplicated"] is True
    assert tool.calls == 1
    assert tool_results[1]["metadata"]["sources"] == [{"id": "s-1"}]


@pytest.mark.asyncio
async def test_tool_executions_table_is_created_on_legacy_database(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    async with aiosqlite.connect(path) as connection:
        await connection.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL DEFAULT 0
            )
            """
        )
        await connection.commit()

    database = Database(path)
    await database.initialize()

    async with aiosqlite.connect(path) as connection:
        cursor = await connection.execute("PRAGMA table_info(tool_executions)")
        columns = {str(row[1]) for row in await cursor.fetchall()}
    assert {
        "idempotency_key",
        "user_id",
        "session_id",
        "turn_id",
        "call_id",
        "tool_name",
        "arguments_hash",
        "read_only",
        "status",
        "result_content",
        "result_metadata",
        "error_content",
        "attempt_count",
        "created_at",
        "updated_at",
    } <= columns


@pytest.mark.asyncio
async def test_retryable_failure_can_be_taken_over_instead_of_replayed(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = TransientFailureTool()
    registry = _registry(tool, database)

    first = await registry.execute("transient", {}, context=_context(), call_id="call-1")
    second = await registry.execute("transient", {}, context=_context(), call_id="call-1")

    assert first.success is False
    assert first.metadata is not None
    assert first.metadata["replayed"] is False
    assert second.success is False
    assert second.metadata is not None
    assert second.metadata["replayed"] is False
    assert second.metadata["retryable"] is True
    assert second.metadata["execution_status"] == "failed"
    assert tool.calls == 4


@pytest.mark.asyncio
async def test_idempotency_is_skipped_without_turn_identity(tmp_path: Path) -> None:
    database = _database(tmp_path)
    await database.initialize()
    tool = SideEffectTool()
    registry = _registry(tool, database)

    await registry.execute("side_effect", {}, context=_context(turn_id=""), call_id="call-1")
    await registry.execute("side_effect", {}, context=_context(turn_id=""), call_id="call-1")

    assert tool.calls == 2
