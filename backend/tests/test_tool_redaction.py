from __future__ import annotations

import json
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
from teachx.runtime.tool_executions import (
    ToolExecutionStore,
    compute_idempotency_key,
)
from teachx.runtime.tools import (
    BaseTool,
    ToolContext,
    ToolExecutionDefaults,
    ToolPolicy,
    ToolRegistry,
    ToolResult,
)
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


class SensitiveTool(BaseTool):
    name = "send_email"
    description = "Pretends to send an email using a provider API key."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(
        read_only=False,
        max_attempts=1,
        timeout_seconds=1.0,
        sensitive_arguments=("api_key", "password"),
    )

    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context
        self.received.append(dict(kwargs))
        return ToolResult(
            content="email-sent",
            metadata={
                "api_key": kwargs.get("api_key", ""),
                "recipient": kwargs.get("to", ""),
                "provider": "test",
            },
        )


class PlainTool(BaseTool):
    name = "plain"
    description = "A tool without sensitive argument declarations."
    parameters = {"type": "object", "properties": {}}
    policy = ToolPolicy(read_only=True, max_attempts=1, timeout_seconds=1.0)

    async def execute(
        self,
        context: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context, kwargs
        return ToolResult(content="ok", metadata={})


class SensitiveCallProvider(BaseProvider):
    """Emits one sensitive tool call in round 1, then answers in round 2."""

    name = "sensitive-call-test"

    def __init__(self) -> None:
        self.assistant_tool_messages: list[dict[str, Any]] = []

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
        del tools
        self.assistant_tool_messages.extend(
            item
            for item in messages
            if isinstance(item, dict)
            and item.get("role") == "assistant"
            and item.get("tool_calls")
        )
        if not self.assistant_tool_messages:
            yield StreamFinished(
                LLMResult(
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="send_email",
                            arguments={
                                "to": "learner@example.com",
                                "api_key": "sk-secret-123456",
                            },
                        )
                    ],
                    finish_reason="tool_calls",
                )
            )
            return
        yield ContentDelta("邮件已发送")
        yield StreamFinished(LLMResult(content="邮件已发送"))


def _registry(
    tool: BaseTool,
    database: Database | None = None,
    *,
    redaction_enabled: bool = True,
) -> ToolRegistry:
    registry = ToolRegistry(
        ToolExecutionDefaults(
            max_attempts=3,
            timeout_seconds=1.0,
            retry_base_delay_seconds=0,
            retry_max_delay_seconds=0,
        ),
        execution_store=ToolExecutionStore(database) if database else None,
        redaction_enabled=redaction_enabled,
    )
    registry.register(tool)
    return registry


def _context() -> ToolContext:
    return ToolContext(session_id="s1", user_id="u1", turn_id="t1")


def test_declared_sensitive_arguments_are_masked() -> None:
    registry = _registry(SensitiveTool())

    redacted = registry.redacted_arguments(
        "send_email",
        {"to": "a@example.com", "api_key": "sk-secret", "password": "hunter2"},
    )

    assert redacted == {
        "to": "a@example.com",
        "api_key": "***",
        "password": "***",
    }


def test_undeclared_arguments_pass_through_unchanged() -> None:
    registry = _registry(PlainTool())
    arguments = {"query": "线性代数", "token": "should-stay"}

    assert registry.redacted_arguments("plain", arguments) == arguments


def test_redaction_can_be_disabled() -> None:
    registry = _registry(SensitiveTool(), redaction_enabled=False)

    assert registry.redacted_arguments("send_email", {"api_key": "sk-secret"}) == {
        "api_key": "sk-secret"
    }


def test_unknown_tool_arguments_are_returned_unchanged() -> None:
    registry = _registry(SensitiveTool())

    assert registry.redacted_arguments("missing", {"api_key": "sk-secret"}) == {
        "api_key": "sk-secret"
    }


@pytest.mark.asyncio
async def test_result_metadata_echoing_sensitive_names_is_masked(tmp_path: Path) -> None:
    database = Database(tmp_path / "redaction.db")
    await database.initialize()
    tool = SensitiveTool()
    registry = _registry(tool, database)
    arguments = {"to": "a@example.com", "api_key": "sk-secret-123456"}

    result = await registry.execute(
        "send_email",
        arguments,
        context=_context(),
        call_id="call-1",
    )

    assert result.metadata is not None
    assert result.metadata["api_key"] == "***"
    assert result.metadata["recipient"] == "a@example.com"

    key = compute_idempotency_key(
        user_id="u1",
        session_id="s1",
        turn_id="t1",
        call_id="call-1",
        tool_name="send_email",
        arguments=arguments,
    )
    record = await ToolExecutionStore(database).get(key)
    assert record is not None
    assert record.status == "completed"
    assert record.result_metadata["api_key"] == "***"
    assert "sk-secret-123456" not in json.dumps(
        record.result_metadata, ensure_ascii=False
    )


@pytest.mark.asyncio
async def test_idempotency_still_uses_raw_arguments(tmp_path: Path) -> None:
    database = Database(tmp_path / "redaction-idempotency.db")
    await database.initialize()
    tool = SensitiveTool()
    registry = _registry(tool, database)
    arguments = {"to": "a@example.com", "api_key": "sk-secret-123456"}

    first = await registry.execute(
        "send_email", arguments, context=_context(), call_id="call-1"
    )
    second = await registry.execute(
        "send_email", arguments, context=_context(), call_id="call-1"
    )

    assert tool.received == [
        {"to": "a@example.com", "api_key": "sk-secret-123456"}
    ]
    assert first.metadata is not None and first.metadata["replayed"] is False
    assert second.metadata is not None and second.metadata["replayed"] is True
    assert second.metadata["api_key"] == "***"


@pytest.mark.asyncio
async def test_runtime_events_masked_but_model_and_tool_get_raw(tmp_path: Path) -> None:
    database = Database(tmp_path / "redaction-runtime.db")
    await database.initialize()
    tool = SensitiveTool()
    provider = SensitiveCallProvider()
    runtime = AgentRuntime(
        provider=provider,
        tools=_registry(tool, database),
        repository=SessionRepository(database),
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="发送邮件")
        )
    ]

    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 1
    arguments = tool_call_events[0]["metadata"]["arguments"]
    assert arguments["api_key"] == "***"
    assert arguments["to"] == "learner@example.com"
    assert "sk-secret-123456" not in str(tool_call_events[0]["metadata"])

    tool_result_events = [e for e in events if e["type"] == "tool_result"]
    assert tool_result_events[0]["metadata"]["api_key"] == "***"

    # 模型必须在 tool 消息里收到真实参数,否则无法执行工具。
    assert len(provider.assistant_tool_messages) == 1
    raw_arguments = provider.assistant_tool_messages[0]["tool_calls"][0]["function"][
        "arguments"
    ]
    assert "sk-secret-123456" in raw_arguments

    # 工具本身收到真实参数。
    assert tool.received == [{"to": "learner@example.com", "api_key": "sk-secret-123456"}]
    assert events[-1]["metadata"]["status"] == "completed"
