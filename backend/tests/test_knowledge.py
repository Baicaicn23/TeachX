from pathlib import Path

import pytest

from teachx.knowledge.chunker import TextChunker
from teachx.knowledge.extractors import extract_text
from teachx.knowledge.service import KnowledgeService
from teachx.providers.base import BaseProvider, ContentDelta, LLMResult, StreamFinished, ToolCall
from teachx.providers.mock import MockProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import build_default_registry
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


@pytest.mark.asyncio
async def test_chunk_search_and_delete(tmp_path: Path) -> None:
    database = Database(tmp_path / "knowledge.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "files")
    await service.create_base("Python 基础")

    result = await service.add_document(
        "Python 基础",
        "agent_loop.md",
        (
            "# Agent Loop\n\n"
            "Agent Loop 会根据模型输出决定是否调用工具。\n\n"
            "如果模型请求计算器，后端执行工具并把结果发回模型。"
        ).encode(),
    )

    assert result.chunks >= 1
    hits = await service.search("模型调用工具", ["Python 基础"])
    assert hits
    assert hits[0].document == "agent_loop.md"

    files = await service.list_documents("Python 基础")
    assert files[0]["name"] == "agent_loop.md"

    assert await service.delete_document("Python 基础", "agent_loop.md") is True
    assert await service.search("模型调用工具", ["Python 基础"]) == []


def test_extractor_and_chunker() -> None:
    text = extract_text("lesson.txt", "第一段。\n\n第二段。".encode())
    chunks = TextChunker(max_chars=200, overlap_chars=20).chunk(text)
    assert chunks == ["第一段。\n\n第二段。"]


@pytest.mark.asyncio
async def test_agent_emits_sources_for_knowledge_search(tmp_path: Path) -> None:
    database = Database(tmp_path / "turn.db")
    await database.initialize()
    repository = SessionRepository(database)
    knowledge = KnowledgeService(database, tmp_path / "knowledge-files")
    await knowledge.create_base("课程资料")
    await knowledge.add_document(
        "课程资料",
        "agent.md",
        "Agent Loop 在工具返回结果后会继续调用模型。".encode(),
    )
    runtime = AgentRuntime(
        provider=_KnowledgeProvider(),
        tools=build_default_registry(knowledge),
        repository=repository,
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(
                type="start_turn",
                content="Agent Loop 工具返回后会做什么？",
                knowledge_bases=["课程资料"],
            )
        )
    ]

    event_types = [event["type"] for event in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "sources" in event_types
    sources_event = next(event for event in events if event["type"] == "sources")
    assert sources_event["metadata"]["sources"][0]["title"] == "agent.md"


class _KnowledgeProvider(BaseProvider):
    name = "knowledge-test"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages: list[dict[str, object]], tools: list[dict[str, object]]):
        self.calls += 1
        if self.calls == 1:
            return LLMResult(
                tool_calls=[
                    ToolCall(
                        id="search-1",
                        name="knowledge_search",
                        arguments={"query": "Agent Loop 工具返回"},
                    )
                ],
                finish_reason="tool_calls",
            )
        return LLMResult(content="工具结果返回后，Agent 会再次调用模型形成回答。")

    async def stream(self, messages: list[dict[str, object]], tools: list[dict[str, object]]):
        result = await self.complete(messages, tools)
        for chunk in ["工具结果", "返回后继续推理。"]:
            if result.tool_calls:
                break
            yield ContentDelta(chunk)
        yield StreamFinished(result)


@pytest.mark.asyncio
async def test_mock_provider_can_use_selected_knowledge_base(tmp_path: Path) -> None:
    database = Database(tmp_path / "mock-kb.db")
    await database.initialize()
    repository = SessionRepository(database)
    knowledge = KnowledgeService(database, tmp_path / "mock-kb-files")
    await knowledge.create_base("教材")
    await knowledge.add_document(
        "教材",
        "loop.md",
        "工具结果返回后，Agent Loop 会继续调用模型。".encode(),
    )
    runtime = AgentRuntime(
        provider=MockProvider(),
        tools=build_default_registry(knowledge),
        repository=repository,
    )

    events = [
        event
        async for event in runtime.run_turn(
            StartTurnCommand(
                type="start_turn",
                content="请根据知识库资料说明工具返回后会发生什么？",
                knowledge_bases=["教材"],
            )
        )
    ]

    tool_calls = [event for event in events if event["type"] == "tool_call"]
    sources = [event for event in events if event["type"] == "sources"]
    assert tool_calls[0]["metadata"]["tool"] == "knowledge_search"
    assert sources
