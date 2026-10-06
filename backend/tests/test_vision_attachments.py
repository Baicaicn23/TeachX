"""图片附件 → 多模态内容块的测试(发图即问)。

运行时应把用户消息里的图片附件组装成 OpenAI 兼容的 image_url 内容块
发给模型;没有图片附件时保持纯文本(回归保护)。
"""

from pathlib import Path

import pytest

from teachx.auth.service import AuthService
from teachx.knowledge.service import KnowledgeService
from teachx.providers.base import BaseProvider, LLMResult
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import build_default_registry
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


class _MessageCaptureProvider(BaseProvider):
    name = "capture-messages"

    def __init__(self) -> None:
        self.last_messages: list[dict] = []

    async def complete(self, messages, tools, *, max_output_tokens=None):
        self.last_messages = messages
        return LLMResult(content="好的")

    async def stream(self, messages, tools, *, max_output_tokens=None):
        from teachx.providers.base import ContentDelta, StreamFinished

        self.last_messages = messages
        yield ContentDelta("好的")
        yield StreamFinished(LLMResult(content="好的"))


async def _run(command: StartTurnCommand, tmp_path: Path, user_id: str = "u1"):
    database = Database(tmp_path / "vision.db")
    await database.initialize()
    provider = _MessageCaptureProvider()
    runtime = AgentRuntime(
        provider=provider,
        tools=build_default_registry(
            KnowledgeService(database, tmp_path / "knowledge")
        ),
        repository=SessionRepository(database),
        auth=AuthService(database, secret="test-secret-0123456789-abcdef-uvwxyz"),
    )
    events = [event async for event in runtime.run_turn(command, user_id=user_id)]
    return provider, events


@pytest.mark.asyncio
async def test_image_attachments_become_content_parts(tmp_path: Path) -> None:
    command = StartTurnCommand(
        type="start_turn",
        content="这张图是什么？",
        attachments=[
            {
                "type": "image",
                "filename": "board.png",
                "mime_type": "image/png",
                "base64": "QUJD",
            }
        ],
    )
    provider, events = await _run(command, tmp_path)

    assert events[-1]["metadata"]["status"] == "completed"
    user_messages = [m for m in provider.last_messages if m["role"] == "user"]
    last = user_messages[-1]
    assert isinstance(last["content"], list)
    assert last["content"][0] == {"type": "text", "text": "这张图是什么？"}
    assert last["content"][1]["type"] == "image_url"
    assert last["content"][1]["image_url"]["url"] == "data:image/png;base64,QUJD"


@pytest.mark.asyncio
async def test_text_only_attachments_stay_plain_text(tmp_path: Path) -> None:
    """非图片附件不触发多模态内容块(回归保护)。"""

    command = StartTurnCommand(
        type="start_turn",
        content="帮我看这份资料",
        attachments=[
            {"type": "file", "filename": "a.txt", "mime_type": "text/plain"}
        ],
    )
    provider, events = await _run(command, tmp_path)

    assert events[-1]["metadata"]["status"] == "completed"
    user_messages = [m for m in provider.last_messages if m["role"] == "user"]
    assert user_messages[-1]["content"] == "帮我看这份资料"
