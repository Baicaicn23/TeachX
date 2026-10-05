from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from teachx.auth.service import AuthService
from teachx.providers.base import (
    BaseProvider,
    ContentDelta,
    LLMResult,
    LLMUsage,
    ProviderError,
    StreamFinished,
    ToolCall,
)
from teachx.providers.mock import MockProvider
from teachx.runtime.prompts import PROMPT_VERSION, build_system_prompt
from teachx.runtime.tools import ToolContext, ToolRegistry, ToolResult
from teachx.schemas import SessionMessage, StartTurnCommand
from teachx.storage.repository import SessionRepository
from teachx.usage.service import UsageService

_STREAM_END = object()


class _TurnTimeoutError(RuntimeError):
    """The whole turn exceeded its configured time budget."""


async def _next_chunk(
    iterator: AsyncIterator[Any],
) -> Any:
    """Advance a stream, converting StopAsyncIteration into a sentinel.

    The sentinel keeps ``asyncio.wait_for`` usable as a per-chunk watchdog:
    raising StopAsyncIteration through a wrapped Task is undefined behavior.
    """

    try:
        return await iterator.__anext__()
    except StopAsyncIteration:
        return _STREAM_END


class AgentRuntime:
    """执行一次支持流式输出和工具调用的 TeachX 回合。"""

    def __init__(
        self,
        *,
        provider: BaseProvider,
        tools: ToolRegistry,
        repository: SessionRepository,
        auth: AuthService | None = None,
        max_rounds: int = 6,
        usage: UsageService | None = None,
        max_history_messages: int = 24,
        max_history_chars: int = 16000,
        max_tool_result_chars: int = 6000,
        max_tool_concurrency: int = 4,
        turn_timeout_seconds: float = 300.0,
        history_summary_enabled: bool = True,
        summary_snippet_chars: int = 50,
        generate_titles: bool = False,
        daily_token_budget: int = 0,
        budget_exceeded_action: Literal["block", "mock"] = "block",
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.repository = repository
        self.auth = auth
        self.max_rounds = max_rounds
        self.usage = usage
        self.max_history_messages = max_history_messages
        self.max_history_chars = max_history_chars
        self.max_tool_result_chars = max_tool_result_chars
        self.max_tool_concurrency = max(1, int(max_tool_concurrency))
        self.turn_timeout_seconds = max(0.0, float(turn_timeout_seconds))
        self.history_summary_enabled = history_summary_enabled
        self.summary_snippet_chars = max(1, int(summary_snippet_chars))
        self.generate_titles = generate_titles
        self.daily_token_budget = daily_token_budget
        self.budget_exceeded_action = budget_exceeded_action

    async def run_turn(
        self,
        command: StartTurnCommand,
        *,
        user_id: str = "",
        is_admin: bool = False,
        provider: BaseProvider | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        active_provider = provider or self.provider
        budget_status = await self._budget_status(user_id)
        budget_blocked = bool(
            budget_status.get("exceeded")
            and active_provider.name != "mock"
            and self.budget_exceeded_action == "block"
        )
        budget_fallback = bool(
            budget_status.get("exceeded")
            and active_provider.name != "mock"
            and self.budget_exceeded_action == "mock"
        )
        if budget_fallback:
            active_provider = MockProvider()
        command.capability = command.capability or "chat"
        fallback_title = self._title_from_prompt(command.content)
        session_id = await self.repository.ensure_session(
            command.session_id,
            title=fallback_title,
            user_id=user_id,
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

        learner_profile: dict[str, Any] | None = None
        if user_id and self.auth is not None:
            current_user = await self.auth.get_user(user_id)
            if current_user and current_user.personalization_enabled:
                learner_profile = current_user.learner_profile or {}
        personalization_applied = bool(learner_profile)
        messages = self._build_messages(
            command,
            history,
            user_message,
            learner_profile=learner_profile,
        )
        history_messages_used = max(0, len(messages) - 2)
        enabled_tools = ["calculator"] if command.tools is None else list(command.tools)
        if command.knowledge_bases and "knowledge_search" not in enabled_tools:
            enabled_tools.append("knowledge_search")
        tool_schemas = self.tools.schemas(enabled_tools)
        tool_context = ToolContext(
            session_id=session_id,
            user_id=user_id,
            is_admin=is_admin,
            knowledge_bases=tuple(command.knowledge_bases),
            turn_id=turn_id,
        )
        saved_events: list[dict[str, Any]] = []
        final_content_parts: list[str] = []
        finish_reason = "stop"
        rounds_used = 0
        tool_call_count = 0
        usage_calls: list[dict[str, Any]] = []

        if budget_blocked:
            message = "今日 token 预算已用完。为避免继续产生费用，本轮未调用真实模型。"
            error_event = self._event(
                "error",
                session_id,
                turn_id,
                command.capability,
                content=message,
                metadata={
                    "status": "failed",
                    "turn_terminal": True,
                    "retryable": False,
                    "error_code": "daily_budget_exceeded",
                    "budget": budget_status,
                },
            )
            yield error_event
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
                    "history_messages_used": history_messages_used,
                    "budget": budget_status,
                    "usage_summary": self._usage_summary([], budget_status),
                },
            }
            return

        try:
            deadline = (
                time.monotonic() + self.turn_timeout_seconds
                if self.turn_timeout_seconds > 0
                else None
            )
            hit_max_rounds = False
            for round_index in range(self.max_rounds):
                self._check_turn_deadline(deadline)
                if round_index > 0 and budget_status.get("exceeded"):
                    finish_reason = "budget_exceeded"
                    break
                rounds_used = round_index + 1
                result: LLMResult | None = None
                round_content = ""

                stream_iterator = active_provider.stream(messages, tool_schemas)
                while True:
                    chunk_timeout = (
                        deadline - time.monotonic() if deadline is not None else None
                    )
                    if chunk_timeout is not None and chunk_timeout <= 0:
                        raise _TurnTimeoutError("回合时间预算已耗尽")
                    if chunk_timeout is None:
                        item = await _next_chunk(stream_iterator)
                    else:
                        try:
                            item = await asyncio.wait_for(
                                _next_chunk(stream_iterator),
                                timeout=chunk_timeout,
                            )
                        except TimeoutError as exc:
                            raise _TurnTimeoutError("回合时间预算已耗尽") from exc
                    if item is _STREAM_END:
                        break
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

                usage_calls.append(
                    await self._record_usage(
                        user_id=user_id,
                        session_id=session_id,
                        turn_id=turn_id,
                        call_kind="agent_loop_round",
                        provider=active_provider,
                        usage=result.usage,
                        billable=active_provider.name != "mock",
                    )
                )
                budget_status = await self._budget_status(user_id)

                finish_reason = result.finish_reason
                if result.tool_calls:
                    messages.append(self._assistant_tool_message(result.content, result.tool_calls))
                    # E4 多工具执行策略:连续的只读调用组成一批并发执行,
                    # 有副作用(或未知)的工具单独串行。gather 保持批次内顺序,
                    # 所以事件和 tool 消息始终与模型的调用顺序一致。
                    for batch in self._plan_tool_batches(result.tool_calls):
                        for call in batch:
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
                                    "arguments": self.tools.redacted_arguments(
                                        call.name, call.arguments
                                    ),
                                    "round": round_index + 1,
                                    "batch_size": len(batch),
                                    "parallel": len(batch) > 1,
                                },
                            )
                            saved_events.append(yield_event)
                            yield yield_event

                        outcomes = await self._execute_tool_batch_guarded(
                            batch, tool_context, deadline
                        )
                        for call, tool_result in zip(batch, outcomes, strict=True):
                            context_content = self._truncate_tool_result(tool_result.content)
                            result_event = self._event(
                                "tool_result",
                                session_id,
                                turn_id,
                                command.capability,
                                content=context_content,
                                metadata={
                                    "call_id": call.id,
                                    "call_kind": "tool",
                                    "call_state": "complete",
                                    "tool": call.name,
                                    "success": tool_result.success,
                                    "context_truncated": context_content != tool_result.content,
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
                                    "content": context_content,
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
            else:
                hit_max_rounds = True

            final_content = "".join(final_content_parts).strip()
            turn_error_code: str | None = None
            turn_error_message = ""
            if hit_max_rounds:
                finish_reason = "max_rounds"
                turn_error_code = "max_rounds_exceeded"
                turn_error_message = (
                    "本轮推理达到最大工具调用轮数，未能形成完整回答。"
                    "请缩小问题范围后重试。"
                )
            if finish_reason == "budget_exceeded":
                notice = (
                    "\n\n本轮已达到今日 token 预算，后续模型调用已停止。"
                    if final_content
                    else "本轮已达到今日 token 预算，后续模型调用已停止。"
                )
                final_content += notice
                notice_event = self._event(
                    "content",
                    session_id,
                    turn_id,
                    command.capability,
                    content=notice if final_content != notice else notice,
                    metadata={
                        "round": rounds_used,
                        "call_kind": "budget_notice",
                        "answer_visible": True,
                    },
                )
                saved_events.append(notice_event)
                yield notice_event

            final_title = fallback_title
            if is_first_turn:
                final_title, title_usage = await self._generate_title(
                    command.content,
                    final_content,
                    fallback_title,
                    provider=active_provider,
                    budget_exceeded=bool(budget_status.get("exceeded")),
                )
                if title_usage is not None:
                    usage_calls.append(
                        await self._record_usage(
                            user_id=user_id,
                            session_id=session_id,
                            turn_id=turn_id,
                            call_kind="session_title",
                            provider=active_provider,
                            usage=title_usage,
                            billable=active_provider.name != "mock",
                        )
                    )
                    budget_status = await self._budget_status(user_id)
                await self.repository.rename_session(session_id, final_title)
                yield {
                    "type": "session_meta",
                    "source": "runtime",
                    "content": "",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "metadata": {"title": final_title},
                }

            usage_summary = self._usage_summary(usage_calls, budget_status)
            partial_turn = turn_error_code is not None

            assistant_message = None
            if final_content:
                assistant_metadata: dict[str, Any] = {
                    "finish_reason": finish_reason,
                    "turn_id": turn_id,
                    "prompt_version": PROMPT_VERSION,
                    "rounds_used": rounds_used,
                    "tool_call_count": tool_call_count,
                    "history_messages_used": history_messages_used,
                    "budget_fallback": budget_fallback,
                    "usage_summary": usage_summary,
                }
                if partial_turn:
                    assistant_metadata.update(
                        {"partial": True, "turn_error_code": turn_error_code}
                    )
                assistant_message = await self.repository.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=final_content,
                    capability=command.capability,
                    events=saved_events,
                    metadata=assistant_metadata,
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
            if final_content:
                result_event = {
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
                        **({"partial": True} if partial_turn else {}),
                        "metadata": {"usage_summary": usage_summary},
                    },
                }
                saved_events.append(result_event)
                yield result_event
            if partial_turn:
                turn_error_event = self._event(
                    "error",
                    session_id,
                    turn_id,
                    command.capability,
                    content=turn_error_message,
                    metadata={
                        "status": "failed",
                        "turn_terminal": True,
                        "retryable": True,
                        "error_code": turn_error_code,
                        "usage_summary": usage_summary,
                        "budget": budget_status,
                    },
                )
                saved_events.append(turn_error_event)
                yield turn_error_event
            done_event = {
                "type": "done",
                "source": "runtime",
                "content": "",
                "session_id": session_id,
                "turn_id": turn_id,
                "metadata": {
                    "status": "failed" if partial_turn else "completed",
                    "user_message_id": user_message.id,
                    "assistant_message_id": (
                        assistant_message.id if assistant_message else None
                    ),
                    "title": final_title,
                    "rounds_used": rounds_used,
                    "tool_call_count": tool_call_count,
                    "personalization_applied": personalization_applied,
                    "history_messages_used": history_messages_used,
                    "budget_fallback": budget_fallback,
                    "budget": budget_status,
                    "usage_summary": usage_summary,
                    **(
                        {"partial": True, "error_code": turn_error_code, "retryable": True}
                        if partial_turn
                        else {}
                    ),
                },
            }
            saved_events.append(done_event)
            if assistant_message is not None:
                await self.repository.update_message_events(
                    assistant_message.id,
                    saved_events,
                    user_id=user_id,
                )
            yield done_event
        except _TurnTimeoutError:
            budget_status = await self._budget_status(user_id)
            usage_summary = self._usage_summary(usage_calls, budget_status)
            partial_content = "".join(final_content_parts).strip()
            error_event = self._event(
                "error",
                session_id,
                turn_id,
                command.capability,
                content="本轮回答超时，已停止后续模型调用。已生成的部分回答已保留，可以重试。",
                metadata={
                    "status": "failed",
                    "turn_terminal": True,
                    "retryable": True,
                    "error_code": "turn_timeout",
                    "usage_summary": usage_summary,
                    "budget": budget_status,
                },
            )
            assistant_message = None
            if partial_content:
                saved_events.append(error_event)
                result_event = {
                    "type": "result",
                    "source": command.capability,
                    "content": partial_content,
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "metadata": {
                        "finish_reason": "turn_timeout",
                        "rounds_used": rounds_used,
                        "tool_call_count": tool_call_count,
                        "prompt_version": PROMPT_VERSION,
                        "partial": True,
                        "metadata": {"usage_summary": usage_summary},
                    },
                }
                saved_events.append(result_event)
                assistant_message = await self.repository.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=partial_content,
                    capability=command.capability,
                    events=saved_events,
                    metadata={
                        "finish_reason": "turn_timeout",
                        "turn_id": turn_id,
                        "prompt_version": PROMPT_VERSION,
                        "rounds_used": rounds_used,
                        "tool_call_count": tool_call_count,
                        "history_messages_used": history_messages_used,
                        "partial": True,
                        "turn_error_code": "turn_timeout",
                        "usage_summary": usage_summary,
                    },
                    parent_message_id=user_message.id,
                )
                yield result_event
            yield error_event
            yield {
                "type": "done",
                "source": "runtime",
                "content": "",
                "session_id": session_id,
                "turn_id": turn_id,
                "metadata": {
                    "status": "failed",
                    "user_message_id": user_message.id,
                    "assistant_message_id": (
                        assistant_message.id if assistant_message else None
                    ),
                    "history_messages_used": history_messages_used,
                    "error_code": "turn_timeout",
                    "retryable": True,
                    "budget": budget_status,
                    "usage_summary": usage_summary,
                    **({"partial": True} if partial_content else {}),
                },
            }
        except ProviderError as exc:
            budget_status = await self._budget_status(user_id)
            usage_summary = self._usage_summary(usage_calls, budget_status)
            failed_event = self._event(
                "error",
                session_id,
                turn_id,
                command.capability,
                content=str(exc),
                metadata={
                    "status": "failed",
                    "turn_terminal": True,
                    "retryable": exc.retryable,
                    "error_code": exc.code,
                    "provider_status_code": exc.status_code,
                    "usage_summary": usage_summary,
                    "budget": budget_status,
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
                    "history_messages_used": history_messages_used,
                    "budget": budget_status,
                    "usage_summary": usage_summary,
                },
            }
        except Exception:
            budget_status = await self._budget_status(user_id)
            usage_summary = self._usage_summary(usage_calls, budget_status)
            failed_event = self._event(
                "error",
                session_id,
                turn_id,
                command.capability,
                content="运行时处理失败，请稍后重试。",
                metadata={
                    "status": "failed",
                    "turn_terminal": True,
                    "retryable": False,
                    "error_code": "runtime_error",
                    "usage_summary": usage_summary,
                    "budget": budget_status,
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
                    "history_messages_used": history_messages_used,
                    "budget": budget_status,
                    "usage_summary": usage_summary,
                },
            }

    @staticmethod
    def _check_turn_deadline(deadline: float | None) -> None:
        if deadline is not None and time.monotonic() >= deadline:
            raise _TurnTimeoutError("回合时间预算已耗尽")

    async def _execute_tool_batch_guarded(
        self,
        batch: list[ToolCall],
        tool_context: ToolContext,
        deadline: float | None,
    ) -> list[ToolResult]:
        if deadline is None:
            return await self._execute_tool_batch(batch, tool_context)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _TurnTimeoutError("回合时间预算已耗尽")
        try:
            return await asyncio.wait_for(
                self._execute_tool_batch(batch, tool_context),
                timeout=remaining,
            )
        except TimeoutError as exc:
            raise _TurnTimeoutError("回合时间预算已耗尽") from exc

    def _plan_tool_batches(
        self,
        calls: list[ToolCall],
    ) -> list[list[ToolCall]]:
        """Group model-ordered calls into execution batches.

        Consecutive read-only calls share one batch and may run concurrently;
        any side-effect (or unknown) call becomes its own single-call batch so
        it executes serially. Batch order preserves the model's call order.
        """
        batches: list[list[ToolCall]] = []
        read_only_run: list[ToolCall] = []
        for call in calls:
            if self.tools.is_read_only(call.name):
                read_only_run.append(call)
                continue
            if read_only_run:
                batches.append(read_only_run)
                read_only_run = []
            batches.append([call])
        if read_only_run:
            batches.append(read_only_run)
        return batches

    async def _execute_tool_batch(
        self,
        batch: list[ToolCall],
        tool_context: ToolContext,
    ) -> list[ToolResult]:
        semaphore = asyncio.Semaphore(self.max_tool_concurrency)

        async def run(call: ToolCall):
            async with semaphore:
                return await self.tools.execute(
                    call.name,
                    call.arguments,
                    context=tool_context,
                    call_id=call.id,
                )

        if len(batch) == 1:
            return [await run(batch[0])]
        return list(await asyncio.gather(*(run(call) for call in batch)))

    def _build_messages(
        self,
        command: StartTurnCommand,
        history: list[SessionMessage],
        user_message: SessionMessage,
        *,
        learner_profile: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        system = build_system_prompt(
            command.capability or "chat",
            command.language or "zh",
            learner_profile=learner_profile,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.extend(self._trim_history(history))
        messages.append({"role": "user", "content": user_message.content})
        return messages

    async def _generate_title(
        self,
        user_content: str,
        assistant_content: str,
        fallback: str,
        *,
        provider: BaseProvider | None = None,
        budget_exceeded: bool = False,
    ) -> tuple[str, LLMUsage | None]:
        """使用模型生成短标题，失败时保留稳定的本地标题。"""

        active_provider = provider or self.provider
        if (
            not self.generate_titles
            or budget_exceeded
            or getattr(active_provider, "name", "") == "mock"
        ):
            return fallback, None
        try:
            configured_limit = int(
                getattr(active_provider, "max_output_tokens", 1024)
            )
            result = await active_provider.complete(
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
                max_output_tokens=min(configured_limit, 64),
            )
            title = result.content.strip().splitlines()[0].strip("“”\"'。 ")
            return title[:32] or fallback, result.usage
        except Exception:
            return fallback, None

    def _trim_history(self, history: list[SessionMessage]) -> list[dict[str, Any]]:
        items = [
            {"role": message.role, "content": message.content}
            for message in history
            if message.role != "system"
        ]
        # E7 上下文压缩:超出保留窗口的旧消息不丢弃,压成一段"前情提要",
        # 作为紧跟系统提示词的 system 消息进入上下文。
        overflow: list[dict[str, Any]] = []
        if self.max_history_messages > 0 and len(items) > self.max_history_messages:
            overflow = items[: -self.max_history_messages]
            items = items[-self.max_history_messages :]

        messages: list[dict[str, Any]] = []
        if overflow and self.history_summary_enabled:
            summary = self._build_history_summary(overflow)
            if summary:
                messages.append({"role": "system", "content": summary})

        if self.max_history_chars > 0:
            selected: list[dict[str, Any]] = []
            used_chars = 0
            for item in reversed(items):
                content_chars = len(str(item["content"]))
                if selected and used_chars + content_chars > self.max_history_chars:
                    break
                selected.append(item)
                used_chars += content_chars
            items = list(reversed(selected))
        while items and items[0]["role"] != "user":
            items.pop(0)
        messages.extend(items)
        return messages

    def _build_history_summary(self, overflow: list[dict[str, Any]]) -> str:
        lines = [f"【前情提要】更早的 {len(overflow)} 条对话已压缩为要点:"]
        for item in overflow:
            role = "用户" if item["role"] == "user" else "助手"
            snippet = " ".join(str(item["content"]).split())
            if len(snippet) > self.summary_snippet_chars:
                snippet = snippet[: self.summary_snippet_chars] + "…"
            lines.append(f"- {role}:{snippet}" if snippet else f"- {role}:（空消息）")
        return "\n".join(lines)

    def _truncate_tool_result(self, content: str) -> str:
        if self.max_tool_result_chars <= 0 or len(content) <= self.max_tool_result_chars:
            return content
        notice = "\n\n[工具结果过长，已截断后传给模型]"
        if self.max_tool_result_chars <= len(notice):
            return notice[: self.max_tool_result_chars]
        keep = max(0, self.max_tool_result_chars - len(notice))
        return content[:keep] + notice

    async def _budget_status(self, user_id: str) -> dict[str, Any]:
        if self.usage is None:
            return {
                "enabled": False,
                "limit_tokens": self.daily_token_budget,
                "used_tokens": 0,
                "remaining_tokens": 0,
                "exceeded": False,
                "exceeded_action": self.budget_exceeded_action,
            }
        return await self.usage.daily_status(
            user_id=user_id,
            limit=self.daily_token_budget,
            exceeded_action=self.budget_exceeded_action,
        )

    async def _record_usage(
        self,
        *,
        user_id: str,
        session_id: str,
        turn_id: str,
        call_kind: str,
        provider: BaseProvider,
        usage: LLMUsage | None,
        billable: bool,
    ) -> dict[str, Any]:
        usage = usage or LLMUsage()
        model = str(getattr(provider, "model", provider.name))
        if self.usage is not None:
            await self.usage.record_call(
                user_id=user_id,
                session_id=session_id,
                turn_id=turn_id,
                call_kind=call_kind,
                provider=provider.name,
                model=model,
                usage=usage,
                billable=billable,
            )
        return {
            "model": model,
            "provider": provider.name,
            "call_kind": call_kind,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cache_read_input_tokens": usage.cached_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
            "estimated": usage.estimated,
            "duration_seconds": usage.duration_seconds,
            "ttft_seconds": usage.ttft_seconds,
        }

    @staticmethod
    def _usage_summary(
        calls: list[dict[str, Any]],
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        prompt_tokens = sum(int(call.get("prompt_tokens", 0)) for call in calls)
        completion_tokens = sum(
            int(call.get("completion_tokens", 0)) for call in calls
        )
        total_tokens = sum(int(call.get("total_tokens", 0)) for call in calls)
        cache_calls = [
            call for call in calls if call.get("cache_read_input_tokens") is not None
        ]
        cache_input_tokens = sum(
            int(call.get("prompt_tokens", 0)) for call in cache_calls
        )
        cache_read_tokens = sum(
            int(call.get("cache_read_input_tokens", 0)) for call in cache_calls
        )
        duration_seconds = sum(
            float(call.get("duration_seconds") or 0) for call in calls
        )
        ttft_calls = [call for call in calls if call.get("ttft_seconds") is not None]
        generation_seconds = 0.0
        timed_completion_tokens = 0
        for call in calls:
            duration = call.get("duration_seconds")
            ttft = call.get("ttft_seconds")
            if duration is None or ttft is None:
                continue
            generation_seconds += max(0.0, float(duration) - float(ttft))
            timed_completion_tokens += int(call.get("completion_tokens", 0))
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "total_calls": len(calls),
            "cache_read_input_tokens": cache_read_tokens,
            "cache_input_tokens": cache_input_tokens,
            "cache_reported_calls": len(cache_calls),
            "cache_hit_rate": (
                cache_read_tokens / cache_input_tokens if cache_input_tokens else None
            ),
            "reasoning_tokens": sum(
                int(call.get("reasoning_tokens") or 0) for call in calls
            ),
            "estimated_calls": sum(1 for call in calls if call.get("estimated")),
            "duration_seconds": duration_seconds,
            "ttft_calls": len(ttft_calls),
            "ttft_seconds": (
                sum(float(call.get("ttft_seconds") or 0) for call in ttft_calls)
                / len(ttft_calls)
                if ttft_calls
                else None
            ),
            "generation_seconds": generation_seconds,
            "timed_completion_tokens": timed_completion_tokens,
            "tokens_per_second": (
                timed_completion_tokens / generation_seconds
                if generation_seconds
                else None
            ),
            "call_details": calls,
            "budget": budget,
        }

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
