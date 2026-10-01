from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from teachx.providers.base import BaseProvider, ToolCall
from teachx.runtime.tools import ToolRegistry
from teachx.schemas import SessionMessage, StartTurnCommand
from teachx.storage.repository import SessionRepository

SYSTEM_PROMPTS = {
    "chat": (
        "你是 TeachX，一名耐心、严谨的 AI 学习导师。"
        "先判断学习者真正卡在哪里，再用清晰的步骤回答。"
        "需要计算时调用工具，不要凭空心算。"
    ),
    "deep_solve": (
        "你是 TeachX 的解题模式。先拆解题目，再分步骤推理。"
        "需要算术时调用 calculator 工具。最后给出答案和易错点。"
    ),
    "deep_question": (
        "你是 TeachX 的出题模式。根据用户要求生成有梯度、可检查的练习题。"
        "题目应覆盖理解、应用和迁移三个层次。"
    ),
}


class AgentRuntime:
    """Execute one TeachX turn as a streaming tool-using agent loop."""

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
        title = self._title_from_prompt(command.content)
        session_id = await self.repository.ensure_session(command.session_id, title=title)
        turn_id = uuid.uuid4().hex
        history = await self.repository.get_messages(session_id)
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
        enabled_tools = ["calculator"] if command.tools is None else command.tools
        tool_schemas = self.tools.schemas(enabled_tools)
        saved_events: list[dict[str, Any]] = []
        final_content = ""
        finish_reason = "stop"

        try:
            for round_index in range(self.max_rounds):
                result = await self.provider.complete(messages, tool_schemas)
                finish_reason = result.finish_reason

                if result.tool_calls:
                    messages.append(self._assistant_tool_message(result.content, result.tool_calls))
                    for call in result.tool_calls:
                        call_event = self._event(
                            "tool_call",
                            session_id,
                            turn_id,
                            command.capability,
                            content=f"调用工具：{call.name}",
                            metadata={"tool": call.name, "arguments": call.arguments},
                        )
                        saved_events.append(call_event)
                        yield call_event

                        tool_result = await self.tools.execute(call.name, call.arguments)
                        result_event = self._event(
                            "tool_result",
                            session_id,
                            turn_id,
                            command.capability,
                            content=tool_result.content,
                            metadata={
                                "tool": call.name,
                                "success": tool_result.success,
                                **(tool_result.metadata or {}),
                            },
                        )
                        saved_events.append(result_event)
                        yield result_event
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "name": call.name,
                                "content": tool_result.content,
                            }
                        )
                    continue

                final_content = result.content
                for chunk in self._chunks(final_content):
                    event = self._event(
                        "content",
                        session_id,
                        turn_id,
                        command.capability,
                        content=chunk,
                        metadata={"round": round_index},
                    )
                    saved_events.append(event)
                    yield event
                break

            if not final_content:
                finish_reason = "max_rounds"
                final_content = "本轮推理达到最大工具调用轮数，请缩小问题范围后重试。"

            assistant_message = await self.repository.add_message(
                session_id=session_id,
                role="assistant",
                content=final_content,
                capability=command.capability,
                events=saved_events,
                metadata={"finish_reason": finish_reason, "turn_id": turn_id},
                parent_message_id=user_message.id,
            )
            yield {
                "type": "stage_end",
                "source": command.capability,
                "stage": "responding",
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
                "metadata": {"finish_reason": finish_reason},
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
                    "title": title,
                },
            }
        except Exception as exc:
            failed_event = self._event(
                "error",
                session_id,
                turn_id,
                command.capability,
                content=str(exc),
                metadata={"status": "failed", "turn_terminal": True, "retryable": True},
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
        system = SYSTEM_PROMPTS.get(command.capability, SYSTEM_PROMPTS["chat"])
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for message in history:
            if message.role == "system":
                continue
            messages.append({"role": message.role, "content": message.content})
        messages.append({"role": "user", "content": user_message.content})
        return messages

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
    def _chunks(text: str, size: int = 18) -> list[str]:
        return [text[index : index + size] for index in range(0, len(text), size)] or [""]

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
