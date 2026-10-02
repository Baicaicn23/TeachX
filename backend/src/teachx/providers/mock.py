from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

from teachx.providers.base import (
    BaseProvider,
    ContentDelta,
    LLMResult,
    LLMUsage,
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
        *,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        del max_output_tokens
        result = await self._complete(messages, tools)
        result.usage = self._estimate_usage(messages, result.content)
        return result

    async def _complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResult:
        latest_user = self._latest_content(messages, "user")
        latest_tool = self._latest_tool(messages)
        if latest_tool:
            tool_name, tool_content = latest_tool
            if tool_name == "knowledge_search":
                if "没有找到" in tool_content:
                    content = "当前知识库中没有找到足够相关的资料，请换一种问法或补充文档。"
                else:
                    preview = tool_content[:600]
                    content = (
                        "根据检索到的知识库资料，可以得到以下信息：\n\n"
                        f"{preview}\n\n"
                        "以上片段已附带来源信息；如果原文较长，可以继续追问具体部分。"
                    )
            else:
                content = (
                    f"计算结果已经得到：{tool_content}。\n\n这次回答由 TeachX 的工具调用链路生成。"
                )
            return LLMResult(content=content, finish_reason="stop")

        expression = self._find_expression(latest_user)
        tool_names = {tool["function"]["name"] for tool in tools}
        if expression and "calculator" in tool_names:
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

        if "knowledge_search" in tool_names and self._needs_knowledge_search(latest_user):
            return LLMResult(
                tool_calls=[
                    ToolCall(
                        id="mock-knowledge-1",
                        name="knowledge_search",
                        arguments={"query": latest_user, "limit": 5},
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
        *,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        result = await self.complete(
            messages,
            tools,
            max_output_tokens=max_output_tokens,
        )
        for chunk in self._chunks(result.content):
            yield ContentDelta(chunk)
        yield StreamFinished(result)

    @staticmethod
    def _latest_tool(messages: list[dict[str, Any]]) -> tuple[str, str] | None:
        for item in reversed(messages):
            if item.get("role") == "tool":
                return str(item.get("name") or "tool"), str(item.get("content") or "")
        return None

    @staticmethod
    def _needs_knowledge_search(text: str) -> bool:
        markers = ("知识库", "资料", "文档", "原文", "来源", "根据资料", "检索")
        return any(marker in text for marker in markers) or "?" in text or "？" in text

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

    @staticmethod
    def _estimate_usage(
        messages: list[dict[str, Any]],
        completion: str,
    ) -> LLMUsage:
        prompt_chars = sum(len(str(item.get("content") or "")) for item in messages)
        prompt_tokens = max(1, prompt_chars // 4)
        completion_tokens = max(1, len(completion) // 4) if completion else 0
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated=True,
        )
