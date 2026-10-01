from pathlib import Path

import pytest

from teachx.knowledge.service import KnowledgeService
from teachx.providers.mock import MockProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import build_default_registry
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


@pytest.mark.asyncio
async def test_runtime_persists_tool_using_turn(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    await database.initialize()
    repository = SessionRepository(database)
    knowledge = KnowledgeService(database, tmp_path / "knowledge")
    runtime = AgentRuntime(
        provider=MockProvider(),
        tools=build_default_registry(knowledge),
        repository=repository,
    )
    command = StartTurnCommand(
        type="start_turn",
        command_id="test-command",
        content="计算 12 + 8",
    )

    events = [event async for event in runtime.run_turn(command)]

    assert [event["type"] for event in events][0:3] == [
        "session",
        "stage_start",
        "tool_call",
    ]
    assert events[-1]["type"] == "done"
    session_id = events[0]["session_id"]
    session = await repository.get_session(session_id)
    assert session is not None
    assert [message.role for message in session.messages] == ["user", "assistant"]
    assert "20" in session.messages[-1].content
