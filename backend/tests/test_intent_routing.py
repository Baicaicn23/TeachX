"""P0 意图识别与多 Agent 路由的自动测试(全程 Mock/规则,零 API 消耗)。

覆盖三层:
1. 规则分类器 classify_by_rules 的确定性判定;
2. LLM 结构化识别 parse_intent_json / detect_intent 与失败回退(用测试桩,
   不调用真实模型);
3. AgentRuntime 路由集成:意图 → 子 agent 提示词与工具策略,包括执行层的
   工具拒绝(tool_not_allowed);
4. 意图评测集门槛(≥30 条、准确率 ≥0.90)与基线回归。
"""

from pathlib import Path

import pytest

from teachx.evals.run_intent_eval import compare_with_baseline, run_eval
from teachx.knowledge.service import KnowledgeService
from teachx.providers.base import BaseProvider, LLMResult, LLMUsage, ToolCall
from teachx.providers.mock import MockProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.intents import (
    INTENT_CALCULATION,
    INTENT_CONCEPT_EXPLAIN,
    INTENT_PRACTICE,
    INTENT_PROGRESS,
    INTENT_RETRIEVAL,
    INTENT_SMALLTALK,
    IntentResult,
    classify_by_rules,
    detect_intent,
    get_agent_profile,
    parse_intent_json,
)
from teachx.runtime.tools import build_default_registry
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository

DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "evals" / "datasets" / "intent_classification.json"
)
BASELINE_PATH = (
    Path(__file__).resolve().parents[1] / "evals" / "baselines" / "intent_rules.json"
)


# ---------------------------------------------------------------------------
# 1. 规则分类器
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("计算 12 * 8", INTENT_CALCULATION),
        ("帮我算一下 3^4 等于多少", INTENT_CALCULATION),
        ("1024 除以 8 结果是多少", INTENT_CALCULATION),
        ("我的学习进度怎么样了？", INTENT_PROGRESS),
        ("我离目标还有多远？", INTENT_PROGRESS),
        ("给我出 5 道线性代数练习题", INTENT_PRACTICE),
        ("考考我几个英语单词", INTENT_PRACTICE),
        ("在我的资料里找一下特征值的定义", INTENT_RETRIEVAL),
        ("知识库里有没有关于矩阵乘法的内容？", INTENT_RETRIEVAL),
        ("什么是矩阵的秩？", INTENT_CONCEPT_EXPLAIN),
        ("为什么矩阵乘法不满足交换律？", INTENT_CONCEPT_EXPLAIN),
        ("你好呀！", INTENT_SMALLTALK),
        ("你是谁？", INTENT_SMALLTALK),
    ],
)
def test_rule_classifier_routes_representative_phrases(text: str, expected: str) -> None:
    assert classify_by_rules(text).intent == expected


def test_rule_classifier_does_not_mistake_dates_for_math() -> None:
    result = classify_by_rules("帮我看看 2026-10 的复习计划")
    assert result.intent == INTENT_PROGRESS


def test_rule_classifier_falls_back_to_smalltalk() -> None:
    result = classify_by_rules("嗯嗯好的就这样")
    assert result.intent == INTENT_SMALLTALK
    assert result.detector == "fallback"


# ---------------------------------------------------------------------------
# 2. LLM 结构化识别与失败回退(测试桩,不调用真实模型)
# ---------------------------------------------------------------------------


class _ScriptedIntentProvider(BaseProvider):
    """意图分类调用按脚本返回;可统计调用次数验证"强信号跳过 LLM"。"""

    name = "scripted-intent"

    def __init__(self, output: str | Exception) -> None:
        self.output = output
        self.complete_calls = 0

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        *,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        self.complete_calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return LLMResult(content=self.output, finish_reason="stop")


@pytest.mark.asyncio
async def test_detect_intent_with_mock_provider_skips_llm() -> None:
    result = await detect_intent("什么是矩阵的秩？", MockProvider())
    assert result.intent == INTENT_CONCEPT_EXPLAIN
    assert result.detector == "rule"


@pytest.mark.asyncio
async def test_detect_intent_strong_rule_signal_skips_llm_call() -> None:
    provider = _ScriptedIntentProvider('{"intent": "smalltalk", "confidence": 0.9}')
    result = await detect_intent("计算 3 * 4", provider)
    assert result.intent == INTENT_CALCULATION
    assert result.detector == "rule"
    assert provider.complete_calls == 0


@pytest.mark.asyncio
async def test_detect_intent_uses_llm_json_when_rule_is_weak() -> None:
    provider = _ScriptedIntentProvider('{"intent": "practice", "confidence": 0.9}')
    result = await detect_intent("随便来点题目呗", provider)
    assert result.intent == INTENT_PRACTICE
    assert result.detector == "llm"
    assert provider.complete_calls == 1


@pytest.mark.asyncio
async def test_detect_intent_parses_markdown_fenced_json() -> None:
    provider = _ScriptedIntentProvider(
        '```json\n{"intent": "retrieval", "confidence": 0.8}\n```'
    )
    result = await detect_intent("随便聊聊吧", provider)
    assert result.intent == INTENT_RETRIEVAL
    assert result.detector == "llm"


@pytest.mark.asyncio
async def test_detect_intent_falls_back_to_rule_on_garbage_output() -> None:
    provider = _ScriptedIntentProvider("抱歉，我不明白你的意思。")
    result = await detect_intent("随便聊聊吧", provider)
    assert result.intent == INTENT_SMALLTALK
    assert result.detector == "fallback"


@pytest.mark.asyncio
async def test_detect_intent_falls_back_to_rule_on_provider_error() -> None:
    provider = _ScriptedIntentProvider(RuntimeError("provider down"))
    result = await detect_intent("给我出几道题", provider)
    assert result.intent == INTENT_PRACTICE
    assert result.detector == "rule"


def test_parse_intent_json_rejects_unknown_intent() -> None:
    assert parse_intent_json('{"intent": "hack", "confidence": 0.9}') is None
    assert parse_intent_json("not json at all") is None
    assert parse_intent_json("") is None


def test_parse_intent_json_clamps_confidence() -> None:
    result = parse_intent_json('{"intent": "practice", "confidence": 7}')
    assert result is not None
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# 3. AgentRuntime 路由集成
# ---------------------------------------------------------------------------


class _LoopRecordingProvider(BaseProvider):
    """意图调用返回脚本 JSON;代理循环调用记录工具清单并可发起工具调用。"""

    name = "loop-recording"

    def __init__(
        self,
        intent_output: str = '{"intent": "smalltalk", "confidence": 0.9}',
        loop_tool_calls: list[list[ToolCall]] | None = None,
    ) -> None:
        self.intent_output = intent_output
        self.loop_tool_calls = loop_tool_calls or []
        self.loop_calls = 0
        self.seen_tool_names: list[list[str]] = []

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        *,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        system = str(messages[0].get("content", "")) if messages else ""
        if "意图分类器" in system:
            return LLMResult(
                content=self.intent_output,
                finish_reason="stop",
                usage=LLMUsage(total_tokens=42),
            )
        self.loop_calls += 1
        self.seen_tool_names.append([tool["function"]["name"] for tool in tools])
        if self.loop_calls <= len(self.loop_tool_calls):
            return LLMResult(
                tool_calls=self.loop_tool_calls[self.loop_calls - 1],
                finish_reason="tool_calls",
            )
        return LLMResult(content="这是最终回答。", finish_reason="stop")


async def _build_runtime(
    tmp_path: Path,
    provider: BaseProvider,
    **runtime_kwargs: object,
) -> AgentRuntime:
    database = Database(tmp_path / "intent-routing.db")
    await database.initialize()
    knowledge = KnowledgeService(database, tmp_path / "knowledge")
    return AgentRuntime(
        provider=provider,
        tools=build_default_registry(knowledge),
        repository=SessionRepository(database),
        **runtime_kwargs,
    )


@pytest.mark.asyncio
async def test_calculation_turn_routes_to_calculator_agent(tmp_path: Path) -> None:
    runtime = await _build_runtime(tmp_path, MockProvider())
    command = StartTurnCommand(type="start_turn", content="计算 12 * 8")

    events = [event async for event in runtime.run_turn(command)]

    tool_call = next(event for event in events if event["type"] == "tool_call")
    assert tool_call["metadata"]["tool"] == "calculator"
    assert tool_call["metadata"]["intent"] == INTENT_CALCULATION
    assert tool_call["metadata"]["agent"] == "calculator"
    done = events[-1]
    assert done["metadata"]["intent"] == INTENT_CALCULATION
    assert done["metadata"]["agent"] == "calculator"
    assert done["metadata"]["intent_detector"] == "rule"
    assert done["metadata"]["status"] == "completed"


@pytest.mark.asyncio
async def test_practice_intent_denies_knowledge_search_even_with_bases(
    tmp_path: Path,
) -> None:
    provider = _LoopRecordingProvider(
        intent_output='{"intent": "practice", "confidence": 0.9}',
        loop_tool_calls=[
            [ToolCall(id="call-1", name="knowledge_search", arguments={"query": "测试"})]
        ],
    )
    runtime = await _build_runtime(tmp_path, provider)
    command = StartTurnCommand(
        type="start_turn",
        content="给我出 5 道练习题",
        knowledge_bases=["我的资料库"],
    )

    events = [event async for event in runtime.run_turn(command)]

    # 模型看不到检索工具的 schema……
    assert "knowledge_search" not in provider.seen_tool_names[0]
    # ……模型仍发起检索调用时,执行层也会拦截。
    tool_result = next(event for event in events if event["type"] == "tool_result")
    assert tool_result["metadata"]["tool"] == "knowledge_search"
    assert tool_result["metadata"]["success"] is False
    assert tool_result["metadata"]["error_code"] == "tool_not_allowed"
    done = events[-1]
    assert done["metadata"]["intent"] == INTENT_PRACTICE
    assert done["metadata"]["agent"] == "practice"


@pytest.mark.asyncio
async def test_practice_intent_filters_user_selected_tools(tmp_path: Path) -> None:
    provider = _LoopRecordingProvider(
        intent_output='{"intent": "practice", "confidence": 0.9}'
    )
    runtime = await _build_runtime(tmp_path, provider)
    command = StartTurnCommand(
        type="start_turn",
        content="出一道题",
        tools=["knowledge_search", "calculator"],
    )

    events = [event async for event in runtime.run_turn(command)]

    assert provider.seen_tool_names[0] == ["calculator"]
    assert events[-1]["metadata"]["intent"] == INTENT_PRACTICE


@pytest.mark.asyncio
async def test_progress_intent_is_read_only_without_tools(tmp_path: Path) -> None:
    provider = _LoopRecordingProvider(
        intent_output='{"intent": "progress", "confidence": 0.9}'
    )
    runtime = await _build_runtime(tmp_path, provider)
    command = StartTurnCommand(
        type="start_turn",
        content="我的学习进度怎么样了？",
        knowledge_bases=["我的资料库"],
    )

    events = [event async for event in runtime.run_turn(command)]

    assert provider.seen_tool_names[0] == []
    done = events[-1]
    assert done["metadata"]["intent"] == INTENT_PROGRESS
    assert done["metadata"]["agent"] == "progress"
    assert done["metadata"]["status"] == "completed"


@pytest.mark.asyncio
async def test_concept_intent_with_bases_exposes_knowledge_search(
    tmp_path: Path,
) -> None:
    provider = _LoopRecordingProvider(
        intent_output='{"intent": "concept_explain", "confidence": 0.9}'
    )
    runtime = await _build_runtime(tmp_path, provider)
    command = StartTurnCommand(
        type="start_turn",
        content="什么是矩阵的秩？",
        knowledge_bases=["我的资料库"],
    )

    events = [event async for event in runtime.run_turn(command)]

    assert "knowledge_search" in provider.seen_tool_names[0]
    assert events[-1]["metadata"]["intent"] == INTENT_CONCEPT_EXPLAIN
    assert events[-1]["metadata"]["agent"] == "tutor"


@pytest.mark.asyncio
async def test_unrecognized_message_falls_back_to_default_chat(tmp_path: Path) -> None:
    provider = _LoopRecordingProvider(intent_output="不是 JSON 的输出")
    runtime = await _build_runtime(tmp_path, provider)
    command = StartTurnCommand(type="start_turn", content="随便聊聊吧")

    events = [event async for event in runtime.run_turn(command)]

    assert provider.seen_tool_names[0] == ["calculator"]
    done = events[-1]
    assert done["metadata"]["intent"] == INTENT_SMALLTALK
    assert done["metadata"]["agent"] == "chat"
    assert done["metadata"]["intent_detector"] == "fallback"


@pytest.mark.asyncio
async def test_intent_llm_call_is_recorded_as_usage(tmp_path: Path) -> None:
    provider = _LoopRecordingProvider(
        intent_output='{"intent": "smalltalk", "confidence": 0.9}'
    )
    runtime = await _build_runtime(tmp_path, provider)
    command = StartTurnCommand(type="start_turn", content="你好呀")

    events = [event async for event in runtime.run_turn(command)]

    call_kinds = [
        call["call_kind"]
        for call in events[-1]["metadata"]["usage_summary"]["call_details"]
    ]
    assert "intent_detection" in call_kinds
    intent_call = next(
        call
        for call in events[-1]["metadata"]["usage_summary"]["call_details"]
        if call["call_kind"] == "intent_detection"
    )
    assert intent_call["total_tokens"] == 42


@pytest.mark.asyncio
async def test_intent_router_can_be_disabled(tmp_path: Path) -> None:
    runtime = await _build_runtime(tmp_path, MockProvider(), intent_enabled=False)
    command = StartTurnCommand(type="start_turn", content="计算 12 * 8")

    events = [event async for event in runtime.run_turn(command)]

    done = events[-1]
    assert "intent" not in done["metadata"]
    assert "agent" not in done["metadata"]
    tool_call = next(event for event in events if event["type"] == "tool_call")
    assert tool_call["metadata"]["intent"] == ""
    assert "96" in next(
        event["content"] for event in events if event["type"] == "result"
    )


@pytest.mark.asyncio
async def test_empty_tools_list_from_frontend_uses_profile_defaults(
    tmp_path: Path,
) -> None:
    """浏览器默认发送 tools=[];应视同未选择,按子 agent 默认集装配。"""

    runtime = await _build_runtime(tmp_path, MockProvider())
    command = StartTurnCommand(type="start_turn", content="计算 7 * 9", tools=[])

    events = [event async for event in runtime.run_turn(command)]

    tool_call = next(event for event in events if event["type"] == "tool_call")
    assert tool_call["metadata"]["tool"] == "calculator"
    assert tool_call["metadata"]["intent"] == INTENT_CALCULATION


def test_unknown_intent_maps_to_default_profile() -> None:
    assert get_agent_profile("不存在的意图").agent == "chat"


def test_intent_result_defaults() -> None:
    result = IntentResult(intent=INTENT_RETRIEVAL, confidence=0.5)
    assert result.detector == "rule"
    assert result.usage is None


# ---------------------------------------------------------------------------
# 4. 意图评测集门槛与基线回归
# ---------------------------------------------------------------------------


def test_intent_dataset_has_enough_samples_and_meets_threshold() -> None:
    results = run_eval(DATASET_PATH)
    assert results["total"] >= 30
    assert results["accuracy"] >= 0.90


def test_intent_eval_matches_saved_baseline() -> None:
    results = run_eval(DATASET_PATH)
    assert compare_with_baseline(results, BASELINE_PATH)
