from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from teachx.providers.base import (
    BaseProvider,
    ContentDelta,
    LLMResult,
    StreamFinished,
    ToolCall,
)
from teachx.runtime.prompts import PROMPT_VERSION, build_system_prompt
from teachx.runtime.tools import ToolContext, ToolRegistry
from teachx.schemas import SessionMessage, StartTurnCommand
from teachx.storage.repository import SessionRepository


class AgentRuntime:
    """执行一次支持流式输出和工具调用的 TeachX 回合。"""

    def __init__(
        self,
        *,
        provider: BaseProvider,
        tools: ToolRegistry,
        repository: SessionRepository,
        max_rounds: int = 6,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.repository = repository
        self.max_rounds = max_rounds

    async def run_turn(self, command: StartTurnCommand) -> AsyncIterator[dict[str, Any]]:
        command.capability = command.capability or "chat"
        fallback_title = self._title_from_prompt(command.content)
        session_id = await self.repository.ensure_session(
            command.session_id,
            title=fallback_title,
        )
        turn_id = uuid.uuid4().hex
        history = await self.repository.get_messages(session_id)
        is_first_turn = not history
        parent_message_id = history[-1].id if history else None
        user_message = await self.repository.add_message(
            session_id=session_id,
            role="user",
            content=command.content,
            capability=command.capability,
            attachments=command.attachments,
            parent_message_id=parent_message_id,
        )

        yield {
            "type": "session",
            "source": "runtime",
            "metadata": {"session_id": session_id, "turn_id": turn_id},
            "session_id": session_id,
            "turn_id": turn_id,
        }
        yield {
            "type": "stage_start",
            "source": command.capability,
            "stage": "exploring",
            "content": "",
            "session_id": session_id,
            "turn_id": turn_id,
        }

        messages = self._build_messages(command, history, user_message)
        enabled_tools = ["calculator"] if command.tools is None else list(command.tools)
        if command.knowledge_bases and "knowledge_search" not in enabled_tools:
            enabled_tools.append("knowledge_search")
        tool_schemas = self.tools.schemas(enabled_tools)
        tool_context = ToolContext(
            session_id=session_id,
            knowledge_bases=tuple(command.knowledge_bases),
        )
        saved_events: list[dict[str, Any]] = []
        final_content_parts: list[str] = []
        finish_reason = "stop"
        rounds_used = 0
        tool_call_count = 0

        try:
            for round_index in range(self.max_rounds):
                rounds_used = round_index + 1
                result: LLMResult | None = None
                round_content = ""

                async for item in self.provider.stream(messages, tool_schemas):
                    if isinstance(item, ContentDelta):
                        round_content += item.content
                        final_content_parts.append(item.content)
                        event = self._event(
                            "content",
                            session_id,
                            turn_id,
                            command.capability,
                            content=item.content,
                            metadata={
                                "round": round_index + 1,
                                "call_kind": "agent_loop_round",
                                "answer_visible": True,
                            },
                        )
                        saved_events.append(event)
                        yield event
                    elif isinstance(item, StreamFinished):
                        result = item.result

                if result is None:
                    raise RuntimeError("模型流没有返回最终结果")

                finish_reason = result.finish_reason
                if result.tool_calls:
                    messages.append(self._assistant_tool_message(result.content, result.tool_calls))
                    for call in result.tool_calls:
                        tool_call_count += 1
                        yield_event = self._event(
                            "tool_call",
                            session_id,
                            turn_id,
                            command.capability,
                            content=f"调用工具：{call.name}",
                            metadata={
                                "call_id": call.id,
                                "call_kind": "tool",
                                "call_state": "running",
                                "tool": call.name,
                                "arguments": call.arguments,
                                "round": round_index + 1,
                            },
                        )
                        saved_events.append(yield_event)
                        yield yield_event

                        started_at = time.perf_counter()
                        tool_result = await self.tools.execute(
                            call.name,
                            call.arguments,
                            context=tool_context,
                        )
                        duration_ms = round(
                            (time.perf_counter() - started_at) * 1000,
                            2,
                        )
                        result_event = self._event(
                            "tool_result",
                            session_id,
                            turn_id,
                            command.capability,
                            content=tool_result.content,
                            metadata={
                                "call_id": call.id,
                                "call_kind": "tool",
                                "call_state": "complete",
                                "tool": call.name,
                                "success": tool_result.success,
                                "duration_ms": duration_ms,
                                **(tool_result.metadata or {}),
                            },
                        )
                        saved_events.append(result_event)
                        yield result_event

                        sources = (tool_result.metadata or {}).get("sources")
                        if isinstance(sources, list) and sources:
                            sources_event = self._event(
                                "sources",
                                session_id,
                                turn_id,
                                command.capability,
                                content=f"找到 {len(sources)} 条相关资料",
                                metadata={
                                    "call_id": call.id,
                                    "tool": call.name,
                                    "sources": sources,
                                },
                            )
                            saved_events.append(sources_event)
                            yield sources_event

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "name": call.name,
                                "content": tool_result.content,
                            }
                        )
                    continue

                # 兼容没有产生增量、只在最终结果中返回文本的模型适配器。
                if not round_content and result.content:
                    final_content_parts.append(result.content)
                    event = self._event(
                        "content",
                        session_id,
                        turn_id,
                        command.capability,
                        content=result.content,
                        metadata={
                            "round": round_index + 1,
                            "call_kind": "llm_final_response",
                            "answer_visible": True,
                        },
                    )
                    saved_events.append(event)
                    yield event
                break

            final_content = "".join(final_content_parts).strip()
            if not final_content:
                finish_reason = "max_rounds"
                final_content = "本轮推理达到最大工具调用轮数，请缩小问题范围后重试。"
                fallback_event = self._event(
                    "content",
                    session_id,
                    turn_id,
                    command.capability,
                    content=final_content,
                    metadata={
                        "round": rounds_used,
                        "call_kind": "llm_final_response",
                        "answer_visible": True,
                    },
                )
                saved_events.append(fallback_event)
                yield fallback_event

            final_title = fallback_title
            if is_first_turn:
                final_title = await self._generate_title(
                    command.content,
                    final_content,
                    fallback_title,
                )
                await self.repository.rename_session(session_id, final_title)
                yield {
                    "type": "session_meta",
                    "source": "runtime",
                    "content": "",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "metadata": {"title": final_title},
                }

            assistant_message = await self.repository.add_message(
                session_id=session_id,
                role="assistant",
                content=final_content,
                capability=command.capability,
                events=saved_events,
                metadata={
                    "finish_reason": finish_reason,
                    "turn_id": turn_id,
                    "prompt_version": PROMPT_VERSION,
                    "rounds_used": rounds_used,
                    "tool_call_count": tool_call_count,
                },
                parent_message_id=user_message.id,
            )
            yield {
                "type": "stage_end",
                "source": command.capability,
                "stage": "exploring",
                "content": "",
                "session_id": session_id,
                "turn_id": turn_id,
            }
            yield {
                "type": "result",
                "source": command.capability,
                "content": final_content,
                "session_id": session_id,
                "turn_id": turn_id,
                "metadata": {
                    "finish_reason": finish_reason,
                    "rounds_used": rounds_used,
                    "tool_call_count": tool_call_count,
                    "prompt_version": PROMPT_VERSION,
                },
            }
            yield {
                "type": "done",
                "source": "runtime",
                "content": "",
                "session_id": session_id,
                "turn_id": turn_id,
                "metadata": {
                    "status": "completed",
                    "user_message_id": user_message.id,
                    "assistant_message_id": assistant_message.id,
                    "title": final_title,
                    "rounds_used": rounds_used,
                    "tool_call_count": tool_call_count,
                },
            }
        except Exception as exc:
            failed_event = self._event(
                "error",
                session_id,
                turn_id,
                command.capability,
                content=str(exc),
                metadata={
                    "status": "failed",
                    "turn_terminal": True,
                    "retryable": True,
                },
            )
            yield failed_event
            yield {
                "type": "done",
                "source": "runtime",
                "content": "",
                "session_id": session_id,
                "turn_id": turn_id,
                "metadata": {
                    "status": "failed",
                    "user_message_id": user_message.id,
                    "assistant_message_id": None,
                },
            }

    def _build_messages(
        self,
        command: StartTurnCommand,
        history: list[SessionMessage],
        user_message: SessionMessage,
    ) -> list[dict[str, Any]]:
        system = build_system_prompt(
            command.capability or "chat",
            command.language or "zh",
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for message in history:
            if message.role == "system":
                continue
            messages.append({"role": message.role, "content": message.content})
        messages.append({"role": "user", "content": user_message.content})
        return messages

    async def _generate_title(
        self,
        user_content: str,
        assistant_content: str,
        fallback: str,
    ) -> str:
        """使用模型生成短标题，失败时保留稳定的本地标题。"""

        if getattr(self.provider, "name", "") == "mock":
            return fallback
        try:
            result = await self.provider.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是会话标题生成器。只输出一个不超过 18 个汉字的标题，"
                            "不要引号、不要句号、不要解释。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"用户问题：{user_content}\n"
                            f"助手回答：{assistant_content[:1200]}\n"
                            "请生成标题。"
                        ),
                    },
                ],
                [],
            )
            title = result.content.strip().splitlines()[0].strip("“”\"'。 ")
            return title[:32] or fallback
        except Exception:
            return fallback

    @staticmethod
    def _assistant_tool_message(
        content: str,
        tool_calls: list[ToolCall],
    ) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in tool_calls
            ],
        }

    @staticmethod
    def _title_from_prompt(content: str) -> str:
        compact = " ".join(content.strip().split())
        return compact[:28] + ("…" if len(compact) > 28 else "") or "新对话"

    @staticmethod
    def _event(
        event_type: str,
        session_id: str,
        turn_id: str,
        source: str,
        *,
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": event_type,
            "source": source,
            "stage": "",
            "content": content,
            "metadata": metadata or {},
            "session_id": session_id,
            "turn_id": turn_id,
            "timestamp": time.time(),
        }
