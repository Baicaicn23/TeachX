from __future__ import annotations

import time
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
from teachx.runtime.tools import BaseTool, ToolContext, ToolRegistry, ToolResult
from teachx.runtime.turn_trace import analyze_turn_events, attribute_error_code, render_trace
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


def _event(event_type: str, metadata: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "type": event_type,
        "metadata": metadata or {},
        "timestamp": time.time(),
        **extra,
    }


def test_error_code_attribution() -> None:
    assert attribute_error_code("provider_timeout") == "model"
    assert attribute_error_code("rate_limited") == "model"
    assert attribute_error_code("stream_interrupted") == "model"
    assert attribute_error_code("turn_timeout") == "orchestration"
    assert attribute_error_code("max_rounds_exceeded") == "orchestration"
    assert attribute_error_code("daily_budget_exceeded") == "cost"
    assert attribute_error_code("tool_execution_in_progress") == "tool"
    assert attribute_error_code("never-seen-code") == "unknown"


def test_happy_path_has_no_findings() -> None:
    events = [
        _event("session", {"turn_id": "t1"}),
        _event("content", {"round": 1}),
        _event(
            "tool_result",
            {
                "call_id": "c1",
                "tool": "calculator",
                "success": True,
                "attempt_count": 1,
                "retry_count": 0,
            },
        ),
        _event("done", {"status": "completed", "rounds_used": 2, "tool_call_count": 1}),
    ]

    report = analyze_turn_events(events)

    assert report["status"] == "completed"
    assert report["rounds_used"] == 2
    assert report["tool_call_count"] == 1
    assert report["findings"] == []


def test_provider_error_maps_to_model_layer() -> None:
    events = [
        _event("session", {"turn_id": "t1"}),
        _event(
            "error",
            {
                "status": "failed",
                "turn_terminal": True,
                "retryable": True,
                "error_code": "stream_interrupted",
            },
        ),
        _event("done", {"status": "failed"}),
    ]

    report = analyze_turn_events(events)

    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["severity"] == "error"
    assert finding["layer"] == "model"
    assert finding["code"] == "stream_interrupted"


def test_failed_knowledge_search_maps_to_retrieval_layer() -> None:
    events = [
        _event("session", {"turn_id": "t1"}),
        _event(
            "tool_result",
            {
                "call_id": "c1",
                "tool": "knowledge_search",
                "success": False,
                "error_code": "tool_transient_error",
                "attempt_count": 3,
                "retry_count": 2,
            },
        ),
        _event("done", {"status": "completed"}),
    ]

    report = analyze_turn_events(events)

    layers = {(f["severity"], f["layer"], f["code"]) for f in report["findings"]}
    # 检索失败是错误;中间发生过重试是警告。
    assert ("error", "retrieval", "tool_transient_error") in layers
    assert ("warning", "retrieval", "tool_retried") in layers


def test_failed_generic_tool_maps_to_tool_layer() -> None:
    events = [
        _event(
            "tool_result",
            {
                "call_id": "c1",
                "tool": "calculator",
                "success": False,
                "error_code": "tool_error",
                "attempt_count": 1,
                "retry_count": 0,
            },
        ),
        _event("done", {"status": "completed"}),
    ]

    report = analyze_turn_events(events)

    assert any(
        f["layer"] == "tool" and f["severity"] == "error" for f in report["findings"]
    )


def test_empty_retrieval_and_truncation_are_warnings() -> None:
    events = [
        _event(
            "tool_result",
            {
                "call_id": "c1",
                "tool": "knowledge_search",
                "success": True,
                "sources": [],
                "context_truncated": True,
                "attempt_count": 1,
                "retry_count": 0,
            },
        ),
        _event("done", {"status": "completed"}),
    ]

    report = analyze_turn_events(events)

    codes = {f["code"] for f in report["findings"]}
    assert "empty_retrieval" in codes
    assert "tool_context_truncated" in codes


def test_missing_done_event_is_flagged() -> None:
    report = analyze_turn_events([_event("session", {"turn_id": "t1"}), _event("content")])

    assert report["status"] == "unknown"
    assert any(
        f["code"] == "turn_not_finalized" and f["severity"] == "warning"
        for f in report["findings"]
    )


def test_render_contains_key_lines() -> None:
    events = [
        _event("session", {"turn_id": "t1"}),
        _event(
            "tool_result",
            {
                "call_id": "c1",
                "tool": "calculator",
                "success": True,
                "attempt_count": 1,
                "retry_count": 0,
                "duration_ms": 12.5,
            },
        ),
        _event("done", {"status": "completed", "rounds_used": 2, "tool_call_count": 1}),
    ]

    text = render_trace(analyze_turn_events(events))

    assert "回合 trace" in text
    assert "状态=completed" in text
    assert "calculator" in text


class ToolCallProvider(BaseProvider):
    name = "trace-test"

    def __init__(self) -> None:
        self.round = 0

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
        self.round += 1
        if self.round == 1:
            yield ContentDelta("先查一下")
            yield StreamFinished(
                LLMResult(
                    tool_calls=[ToolCall(id="c1", name="echo", arguments={})],
                    finish_reason="tool_calls",
                )
            )
            return
        yield ContentDelta("完成")
        yield StreamFinished(LLMResult(content="完成"))


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo."
    parameters = {"type": "object", "properties": {}}

    async def execute(self, context: ToolContext | None = None, **kwargs: Any) -> ToolResult:
        del context, kwargs
        return ToolResult(content="ok")


@pytest.mark.asyncio
async def test_analyze_real_persisted_turn(tmp_path: Path) -> None:
    """端到端:跑一个真实回合,直接分析它持久化的事件。"""
    database = Database(tmp_path / "trace.db")
    await database.initialize()
    registry = ToolRegistry()
    registry.register(EchoTool())
    runtime = AgentRuntime(
        provider=ToolCallProvider(),
        tools=registry,
        repository=SessionRepository(database),
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="测试")
        )
    ]
    session_id = events[0]["session_id"]
    done = events[-1]["metadata"]
    repository = SessionRepository(database)
    persisted = await repository.message_events(session_id, done["assistant_message_id"])

    report = analyze_turn_events(persisted)

    assert report["status"] == "completed"
    assert report["tool_call_count"] == 1
    assert report["findings"] == []
