from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

from teachx.providers.base import (
    BaseProvider,
    ContentDelta,
    LLMResult,
    ProviderEvent,
    StreamFinished,
    ToolCall,
)

_MATH_PATTERN = re.compile(r"(?<!\w)(-?\d+(?:\.\d+)?\s*[+\-*/]\s*-?\d+(?:\.\d+)?)")


class MockProvider(BaseProvider):
    """用于本地开发和测试的确定性模型实现。"""

    name = "mock"

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResult:
        latest_user = self._latest_content(messages, "user")
        latest_tool = self._latest_content(messages, "tool")
        if latest_tool:
            return LLMResult(
                content=(
                    f"计算结果已经得到：{latest_tool}。\n\n这次回答由 TeachX 的工具调用链路生成。"
                ),
                finish_reason="stop",
            )

        expression = self._find_expression(latest_user)
        if expression and any(tool["function"]["name"] == "calculator" for tool in tools):
            return LLMResult(
                tool_calls=[
                    ToolCall(
                        id="mock-calculator-1",
                        name="calculator",
                        arguments={"expression": expression},
                    )
                ],
                finish_reason="tool_calls",
            )

        if "出题" in latest_user or "quiz" in latest_user.lower():
            content = (
                "下面给你一组练习题：\n\n"
                "1. 用自己的话解释什么是 Agent Loop。\n"
                "2. 为什么工具调用需要结构化参数？\n"
                "3. 举一个适合加入学习助手的工具。\n\n"
                "先独立作答，再把你最不确定的一题发给我，我会针对性地讲解。"
            )
        elif "rag" in latest_user.lower() or "知识库" in latest_user:
            content = (
                "RAG 可以先理解成“先查资料，再回答”。\n\n"
                "一次完整流程是：文档切分 → 建立索引 → 用户提问 → 召回相关片段 → "
                "把片段放进提示词 → 模型基于片段作答并给出引用。\n\n"
                "当前项目下一步会把这个流程接到知识库页面。"
            )
        else:
            content = (
                "我现在运行在 mock 模式，但整条链路是真实的："
                "WebSocket → Agent Runtime → Tool Registry → Session Storage。\n\n"
                f"你刚才的问题是：{latest_user}\n\n"
                "配置 `TEACHX_LLM_PROVIDER=openai` 和对应 API Key 后，"
                "同一个链路会改为调用真实模型。"
            )
        return LLMResult(content=content, finish_reason="stop")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[ProviderEvent]:
        result = await self.complete(messages, tools)
        for chunk in self._chunks(result.content):
            yield ContentDelta(chunk)
        yield StreamFinished(result)

    @staticmethod
    def _latest_content(messages: list[dict[str, Any]], role: str) -> str:
        return next(
            (
                str(item.get("content") or "")
                for item in reversed(messages)
                if item.get("role") == role
            ),
            "",
        )

    @staticmethod
    def _find_expression(text: str) -> str | None:
        match = _MATH_PATTERN.search(text)
        return match.group(1) if match else None

    @staticmethod
    def _chunks(text: str, size: int = 12) -> list[str]:
        return [text[index : index + size] for index in range(0, len(text), size)]
