from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    """统一表示模型请求执行的一次工具调用。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMResult:
    """一次模型调用的完整结果，流式与非流式最终都转换为此对象。"""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


@dataclass(slots=True)
class ContentDelta:
    """模型流式产生的文本片段。"""

    content: str


@dataclass(slots=True)
class StreamFinished:
    """流式调用结束后的完整结果。"""

    result: LLMResult


ProviderEvent = ContentDelta | StreamFinished


class BaseProvider(ABC):
    """所有模型适配器必须满足的最小接口。"""

    name: str = "base"

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResult:
        """一次性返回完整结果，适合标题生成等短调用。"""
        raise NotImplementedError

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[ProviderEvent]:
        """默认流式实现：调用 complete，然后把完整文本作为单个片段返回。"""

        result = await self.complete(messages, tools)
        if result.content:
            yield ContentDelta(result.content)
        yield StreamFinished(result)
