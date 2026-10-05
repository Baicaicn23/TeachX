from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from teachx.providers.base import LLMResult
from teachx.schemas import SessionMessage
from teachx.storage.repository import SessionRepository  # noqa: F401


def _msg(role: str, content: str) -> SessionMessage:
    return SessionMessage(
        id=0,
        session_id="s",
        role=role,
        content=content,
        capability="chat",
        events=[],
        attachments=[],
        metadata={},
        created_at=0.0,
        parent_message_id=None,
    )


def _runtime(**overrides: Any):
    from teachx.runtime.engine import AgentRuntime
    from teachx.runtime.tools import ToolRegistry

    defaults = {"provider": None, "tools": ToolRegistry(), "repository": None}
    defaults.update(overrides)
    return AgentRuntime(**defaults)


class _NullProvider:
    name = "null"

    async def complete(self, *a: Any, **k: Any) -> LLMResult:
        return LLMResult(content="")

    async def stream(self, *a: Any, **k: Any):
        yield


def _runtime_real(**overrides: Any) -> Any:
    from teachx.runtime.engine import AgentRuntime
    from teachx.runtime.tools import ToolRegistry

    params: dict[str, Any] = {
        "provider": _NullProvider(),
        "tools": ToolRegistry(),
        "repository": None,
    }
    params.update(overrides)
    return AgentRuntime(**params)


def test_short_history_is_untouched() -> None:
    runtime = _runtime_real(max_history_messages=6)
    history = [_msg("user", f"问题{i}") for i in range(4)]

    messages = runtime._trim_history(history)

    assert len(messages) == 4
    assert all(m["role"] != "system" or "前情提要" not in m["content"] for m in messages)


def test_overflow_is_summarized_and_recent_kept() -> None:
    runtime = _runtime_real(max_history_messages=4)
    history = [_msg("user", f"很旧的问题{i},包含关键概念超导{i}") for i in range(8)]

    messages = runtime._trim_history(history)

    # 第一条是前情提要(system),后面是最近 4 条原文。
    assert "前情提要" in messages[0]["content"]
    assert "超导0" in messages[0]["content"]
    assert len(messages) == 1 + 4
    assert messages[1]["content"] == "很旧的问题4,包含关键概念超导4"
    assert messages[-1]["content"] == "很旧的问题7,包含关键概念超导7"


def test_summary_snippets_are_truncated() -> None:
    runtime = _runtime_real(max_history_messages=2, summary_snippet_chars=20)
    long_text = "这是一条非常长的旧消息" * 10
    history = [
        _msg("user", long_text),
        _msg("user", "另一条很长的旧消息" * 8),
        _msg("user", "近期的问题一"),
        _msg("user", "近期的问题二"),
    ]

    messages = runtime._trim_history(history)

    summary = messages[0]["content"]
    assert "前情提要" in summary
    # 截断后不能包含完整长文本。
    assert long_text not in summary
    assert len(summary) < 200


def test_summary_can_be_disabled() -> None:
    runtime = _runtime_real(max_history_messages=2, history_summary_enabled=False)
    history = [_msg("user", f"旧消息{i}") for i in range(5)]

    messages = runtime._trim_history(history)

    assert len(messages) == 2
    assert not any("前情提要" in m["content"] for m in messages)


def test_summary_respects_character_budget() -> None:
    runtime = _runtime_real(
        max_history_messages=2, max_history_chars=100, summary_snippet_chars=15
    )
    history = [_msg("user", f"旧消息{i}" + "内容" * 30) for i in range(4)]
    history += [_msg("user", "近期消息" + "内容" * 30)]

    messages = runtime._trim_history(history)

    # 前情提要永远保留,其余受字符预算约束。
    assert "前情提要" in messages[0]["content"]
    total = sum(len(m["content"]) for m in messages[1:])
    assert total <= 100 + len(messages[1:]) * 10


@pytest.mark.asyncio
async def test_runtime_builds_messages_with_summary(tmp_path: Path) -> None:
    """端到端:_build_messages 组装系统提示词 + 前情提要 + 最近消息。"""
    asyncio.get_event_loop()
    runtime = _runtime_real(max_history_messages=2)
    history = [_msg("user", f"历史问题{i}") for i in range(4)]
    user_message = _msg("user", "新问题")

    from teachx.schemas import StartTurnCommand

    messages = runtime._build_messages(
        StartTurnCommand(type="start_turn", content="新问题"),
        history,
        user_message,
    )

    assert messages[0]["role"] == "system"  # 能力提示词
    assert "前情提要" in messages[1]["content"]  # 压缩的历史
    assert messages[-1]["content"] == "新问题"
    # 系统提示词 + 前情提要 + 最近 2 条 + 用户新消息
    assert len(messages) == 5
