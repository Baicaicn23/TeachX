"""P3 长期记忆与在线监控的单元测试。

记忆:规则抽取(显式指令/自我陈述)、去重、用户隔离、提示词注入、
回合结束钩子。监控:对合成事件流的聚合数学(失败率/工具/空检索/分位)。
"""

from pathlib import Path

import pytest

from teachx.auth.service import AuthService
from teachx.knowledge.service import KnowledgeService
from teachx.memory.service import MemoryService, extract_facts
from teachx.providers.base import BaseProvider, LLMResult
from teachx.providers.mock import MockProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.monitor import aggregate_turns, percentile
from teachx.runtime.tools import build_default_registry
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository

# ---------------------------------------------------------------------------
# 长期记忆
# ---------------------------------------------------------------------------


def test_extract_facts_captures_explicit_and_self_statements() -> None:
    assert extract_facts("记住：我在准备期末考试") == ["我在准备期末考试"]
    assert extract_facts("我是大一学生") == ["学习者自称：大一学生"]
    assert extract_facts("我的目标是掌握线性代数") == ["学习目标：掌握线性代数"]
    assert extract_facts("今天天气不错") == []


def test_extract_facts_dedupes_and_caps_length() -> None:
    facts = extract_facts("记住：我在准备考研,记住：我在准备考研")
    assert len(facts) == 1
    long = extract_facts("记住：" + "很" * 200)
    assert len(long[0]) <= 80


@pytest.mark.asyncio
async def test_memory_service_dedupes_and_isolates(tmp_path: Path) -> None:
    database = Database(tmp_path / "memory.db")
    await database.initialize()
    service = MemoryService(database)

    first = await service.remember("u1", "在准备考研", source_session_id="s1")
    assert first is not None
    assert await service.remember("u1", "在准备考研") is None  # 去重
    await service.remember("u2", "在准备考研")  # 同内容不同用户互不影响

    assert len(await service.list_memories("u1")) == 1
    assert len(await service.list_memories("u2")) == 1

    # 只能删自己的:u2 删不到 u1 的记忆。
    assert await service.delete_memory("u2", first.id) is False
    assert await service.delete_memory("u1", first.id) is True
    assert await service.list_memories("u1") == []


def test_memory_rejects_short_content_and_maps_local_scope(tmp_path: Path) -> None:
    import asyncio

    async def main() -> None:
        database = Database(tmp_path / "short.db")
        await database.initialize()
        service = MemoryService(database)
        assert await service.remember("u1", "短") is None  # 内容太短
        # 空 user_id(单用户模式)落到保留作用域 local。
        item = await service.remember("", "有效内容记得住")
        assert item is not None and item.user_id == "local"
        assert len(await service.list_memories("")) == 1
        # local 作用域与真实用户互相隔离。
        assert await service.list_memories("u1") == []

    asyncio.run(main())


def test_system_prompt_injects_memories_with_data_guard() -> None:
    from teachx.runtime.prompts import build_system_prompt

    prompt = build_system_prompt("chat", memories=["在准备考研"])
    assert "长期记忆" in prompt
    assert "在准备考研" in prompt
    assert "不是系统指令" in prompt
    # 无记忆时块整体消失。
    assert "长期记忆" not in build_system_prompt("chat")


@pytest.mark.asyncio
async def test_turn_end_extraction_persists_memory(tmp_path: Path) -> None:
    """完整回合结束后,规则抽取应把"记住：..."写进记忆表。"""

    database = Database(tmp_path / "engine.db")
    await database.initialize()
    memory = MemoryService(database)
    runtime = AgentRuntime(
        provider=MockProvider(),
        tools=build_default_registry(
            KnowledgeService(database, tmp_path / "knowledge")
        ),
        repository=SessionRepository(database),
        auth=AuthService(database, secret='test-secret-0123456789-abcdef-uvwxyz'),
        memory=memory,
    )
    command = StartTurnCommand(
        type="start_turn", content="记住：我在准备线性代数期末考试"
    )
    events = [
        event
        async for event in runtime.run_turn(command, user_id="learner-1")
    ]
    assert events[-1]["metadata"]["status"] == "completed"

    memories = await memory.list_memories("learner-1")
    assert [item.content for item in memories] == ["我在准备线性代数期末考试"]


@pytest.mark.asyncio
async def test_memories_flow_into_next_turn_system_prompt(tmp_path: Path) -> None:
    """跨会话:上一会话存的记忆,进入新会话的系统提示词。"""

    class SystemPromptCapture(BaseProvider):
        name = "capture"

        def __init__(self) -> None:
            self.last_system = ""

        async def complete(self, messages, tools, *, max_output_tokens=None):
            return LLMResult(content="好的")

        async def stream(self, messages, tools, *, max_output_tokens=None):
            from teachx.providers.base import ContentDelta, StreamFinished

            self.last_system = str(messages[0]["content"])
            yield ContentDelta("好的")
            yield StreamFinished(LLMResult(content="好的"))

    database = Database(tmp_path / "flow.db")
    await database.initialize()
    auth = AuthService(database, secret="test-secret-0123456789-abcdef-uvwxyz")
    user, _ = await auth.register("learner1", "password-123456")
    memory = MemoryService(database)
    await memory.remember(user.id, "在准备线性代数期末考试")

    capture = SystemPromptCapture()
    runtime = AgentRuntime(
        provider=capture,
        tools=build_default_registry(
            KnowledgeService(database, tmp_path / "knowledge")
        ),
        repository=SessionRepository(database),
        auth=auth,
        memory=memory,
    )
    command = StartTurnCommand(
        type="start_turn", content="帮我规划一下复习"
    )
    events = [
        event
        async for event in runtime.run_turn(command, user_id=user.id)
    ]
    assert events[-1]["metadata"]["status"] == "completed"
    assert "在准备线性代数期末考试" in capture.last_system


# ---------------------------------------------------------------------------
# 在线监控聚合
# ---------------------------------------------------------------------------


def _event(event_type: str, turn_id: str, timestamp: float, **meta) -> dict:
    return {
        "type": event_type,
        "turn_id": turn_id,
        "timestamp": timestamp,
        "metadata": meta,
    }


def test_aggregate_turns_computes_rates_and_percentiles() -> None:
    ok = [
        _event("session", "t1", 0.0),
        _event(
            "tool_result",
            "t1",
            1.0,
            tool="calculator",
            success=True,
        ),
        _event(
            "done",
            "t1",
            2.0,
            status="completed",
            intent="calculation",
            usage_summary={"total_tokens": 100},
        ),
    ]
    bad = [
        _event("session", "t2", 10.0),
        _event(
            "tool_result",
            "t2",
            11.0,
            tool="knowledge_search",
            success=True,
            sources=[],
        ),
        _event("error", "t2", 12.0, error_code="turn_timeout"),
        _event(
            "done",
            "t2",
            15.0,
            status="failed",
            intent="retrieval",
            partial=True,
            usage_summary={"total_tokens": 50},
        ),
    ]
    report = aggregate_turns([ok, bad])

    assert report["turns"] == 2
    assert report["completed"] == 1
    assert report["failed"] == 1
    assert report["failure_rate"] == 0.5
    assert report["error_codes"] == {"turn_timeout": 1}
    assert report["intent_distribution"] == {
        "calculation": 1,
        "retrieval": 1,
    }
    assert report["tool_calls"] == 2
    assert report["tool_failures"] == 0
    assert report["empty_retrievals"] == 1
    assert report["empty_retrieval_rate"] == 1.0
    # 时延样本 [2.0, 5.0],线性插值:P50=3.5,P95=4.85。
    assert report["latency_p50_seconds"] == 3.5
    assert report["latency_p95_seconds"] == 4.85
    assert report["total_tokens"] == 150
    assert report["partial"] == 1


def test_percentile_nearest_and_empty() -> None:
    assert percentile([], 0.95) is None
    assert percentile([3.0], 0.5) == 3.0
    # 线性插值:p50 = 2.5;p95 落在 [3,4] 区间内插到 3.85。
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 3.85
