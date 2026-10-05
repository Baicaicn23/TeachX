from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from teachx.knowledge.service import KnowledgeService
from teachx.providers.base import (
    BaseProvider,
    ContentDelta,
    LLMResult,
    LLMUsage,
    ProviderError,
    ProviderEvent,
    StreamFinished,
)
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import build_default_registry
from teachx.schemas import SessionMessage, StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository
from teachx.usage.service import UsageService


class RecordingProvider(BaseProvider):
    name = "openai"
    model = "test-model"
    max_output_tokens = 128

    def __init__(self) -> None:
        self.stream_calls = 0
        self.complete_calls = 0

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        del messages, tools, max_output_tokens
        self.complete_calls += 1
        return LLMResult(
            content="模型标题",
            usage=LLMUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        del messages, tools, max_output_tokens
        self.stream_calls += 1
        result = LLMResult(
            content="真实模型回答",
            usage=LLMUsage(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                cached_tokens=40,
                duration_seconds=1.5,
                ttft_seconds=0.5,
            ),
        )
        yield ContentDelta(result.content)
        yield StreamFinished(result)


class FailingProvider(RecordingProvider):
    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        del messages, tools, max_output_tokens
        self.stream_calls += 1
        raise ProviderError(
            "模型请求超时，请稍后重试",
            code="provider_timeout",
            retryable=True,
        )
        yield StreamFinished(LLMResult())


async def _runtime(
    tmp_path: Path,
    *,
    provider: BaseProvider | None = None,
    generate_titles: bool = False,
    daily_token_budget: int = 0,
    budget_exceeded_action: str = "block",
) -> tuple[AgentRuntime, SessionRepository, UsageService, RecordingProvider]:
    database = Database(tmp_path / "cost-control.db")
    await database.initialize()
    repository = SessionRepository(database)
    usage = UsageService(database)
    recording = provider or RecordingProvider()
    runtime = AgentRuntime(
        provider=recording,
        tools=build_default_registry(
            KnowledgeService(database, tmp_path / "knowledge")
        ),
        repository=repository,
        usage=usage,
        generate_titles=generate_titles,
        daily_token_budget=daily_token_budget,
        budget_exceeded_action=budget_exceeded_action,  # type: ignore[arg-type]
        # 本组测试只验证主循环与标题的费用记账;意图识别的 LLM 调用记账
        # 由 test_intent_routing 单独覆盖。
        intent_llm_enabled=False,
    )
    return runtime, repository, usage, recording  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_runtime_persists_real_usage_and_keeps_titles_local_by_default(
    tmp_path: Path,
) -> None:
    runtime, repository, _, provider = await _runtime(tmp_path)

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="解释常量"),
            user_id="user-1",
        )
    ]

    done = events[-1]
    summary = done["metadata"]["usage_summary"]
    assert done["metadata"]["status"] == "completed"
    assert summary["total_tokens"] == 120
    assert summary["prompt_tokens"] == 100
    assert summary["completion_tokens"] == 20
    assert summary["total_calls"] == 1
    assert provider.complete_calls == 0

    result = next(event for event in events if event["type"] == "result")
    assert result["metadata"]["metadata"]["usage_summary"]["total_tokens"] == 120
    session_id = events[0]["session_id"]
    session = await repository.get_session(session_id, user_id="user-1")
    assert session is not None
    assistant = session.messages[-1]
    assert assistant.metadata["usage_summary"]["total_tokens"] == 120
    assert [event["type"] for event in assistant.events[-2:]] == ["result", "done"]


@pytest.mark.asyncio
async def test_runtime_counts_title_usage_when_enabled(tmp_path: Path) -> None:
    runtime, _, _, provider = await _runtime(tmp_path, generate_titles=True)

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="解释常量"),
            user_id="user-1",
        )
    ]

    summary = events[-1]["metadata"]["usage_summary"]
    assert provider.complete_calls == 1
    assert summary["total_calls"] == 2
    assert summary["total_tokens"] == 135
    assert summary["call_details"][-1]["call_kind"] == "session_title"


@pytest.mark.asyncio
async def test_runtime_blocks_billable_calls_after_daily_budget(tmp_path: Path) -> None:
    runtime, _, usage, provider = await _runtime(
        tmp_path,
        daily_token_budget=100,
    )
    await usage.record_call(
        user_id="user-1",
        session_id="previous",
        turn_id="previous-turn",
        call_kind="agent_loop_round",
        provider="openai",
        model="test-model",
        usage=LLMUsage(prompt_tokens=80, completion_tokens=30, total_tokens=110),
        billable=True,
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="继续解释"),
            user_id="user-1",
        )
    ]

    error = next(event for event in events if event["type"] == "error")
    assert error["metadata"]["error_code"] == "daily_budget_exceeded"
    assert error["metadata"]["retryable"] is False
    assert events[-1]["metadata"]["status"] == "failed"
    assert events[-1]["metadata"]["budget"]["exceeded"] is True
    assert provider.stream_calls == 0


@pytest.mark.asyncio
async def test_runtime_can_fall_back_to_mock_after_daily_budget(tmp_path: Path) -> None:
    runtime, _, usage, provider = await _runtime(
        tmp_path,
        daily_token_budget=100,
        budget_exceeded_action="mock",
    )
    await usage.record_call(
        user_id="user-1",
        session_id="previous",
        turn_id="previous-turn",
        call_kind="agent_loop_round",
        provider="openai",
        model="test-model",
        usage=LLMUsage(prompt_tokens=100, completion_tokens=10, total_tokens=110),
        billable=True,
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="继续解释"),
            user_id="user-1",
        )
    ]

    assert events[-1]["metadata"]["status"] == "completed"
    assert events[-1]["metadata"]["budget_fallback"] is True
    assert provider.stream_calls == 0


@pytest.mark.asyncio
async def test_runtime_emits_typed_provider_failure(tmp_path: Path) -> None:
    runtime, _, _, provider = await _runtime(
        tmp_path,
        provider=FailingProvider(),
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(type="start_turn", content="继续解释"),
            user_id="user-1",
        )
    ]

    error = next(event for event in events if event["type"] == "error")
    assert error["metadata"]["error_code"] == "provider_timeout"
    assert error["metadata"]["retryable"] is True
    assert events[-1]["metadata"]["status"] == "failed"
    assert provider.stream_calls == 1


def test_history_and_tool_result_limits_are_deterministic() -> None:
    runtime = AgentRuntime(
        provider=RecordingProvider(),
        tools=build_default_registry(KnowledgeService(Database(Path("unused.db")), Path("unused"))),
        repository=SessionRepository(Database(Path("unused.db"))),
        max_history_messages=4,
        max_history_chars=1000,
        max_tool_result_chars=40,
    )
    history = [
        SessionMessage(
            id=index,
            session_id="session",
            role="user" if index % 2 else "assistant",
            content=f"message-{index}",
            created_at=float(index),
        )
        for index in range(1, 7)
    ]

    trimmed = runtime._trim_history(history)
    # E7 起,超出窗口的 message-1/2 会压缩为一条"前情提要"置顶。
    assert "前情提要" in trimmed[0]["content"]
    assert "message-1" in trimmed[0]["content"]
    assert "message-2" in trimmed[0]["content"]
    assert [item["content"] for item in trimmed[1:]] == [
        "message-3",
        "message-4",
        "message-5",
        "message-6",
    ]
    truncated = runtime._truncate_tool_result("x" * 500)
    assert len(truncated) == 40
    assert "已截断" in truncated
