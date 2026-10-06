"""P0 意图识别与多 Agent 路由(学习版)。

每回合开始时先识别用户意图(六类教学场景),再按"意图 → 子 agent 配置表"
选择专属系统提示词和工具子集。识别分两层:

1. LLM 结构化 JSON 输出(主路径):``provider.complete`` 低 token 调用,
   输出 ``{"intent": "...", "confidence": ...}``;解析失败或调用异常时回退规则。
2. 规则关键词兜底(纯函数,确定性,零成本):Mock Provider 与自动测试全走
   这条;规则给出强信号(如数学表达式)时跳过 LLM 调用,省一次往返。

路由表把每个意图映射到一个子 agent:专属提示词 + 工具策略。工具最小权限
在这里落地——练习 agent 一律不给检索工具,进度 agent 只读不配任何工具;
被拒绝的工具即使模型仍发起调用,运行时也会在执行层拦截(返回
``tool_not_allowed`` 失败结果),而不是只靠"不给模型看 schema"的软约束。
默认对话保持引入路由之前的工具面,用户显式选择的工具不被收窄。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from teachx.providers.base import BaseProvider, LLMUsage

INTENT_CONCEPT_EXPLAIN = "concept_explain"
INTENT_PRACTICE = "practice"
INTENT_PROGRESS = "progress"
INTENT_RETRIEVAL = "retrieval"
INTENT_CALCULATION = "calculation"
INTENT_SMALLTALK = "smalltalk"

VALID_INTENTS: frozenset[str] = frozenset(
    {
        INTENT_CONCEPT_EXPLAIN,
        INTENT_PRACTICE,
        INTENT_PROGRESS,
        INTENT_RETRIEVAL,
        INTENT_CALCULATION,
        INTENT_SMALLTALK,
    }
)

# 规则置信度达到该值时视为强信号,跳过 LLM 复核调用。
STRONG_RULE_CONFIDENCE = 0.9

_DATE_PATTERN = re.compile(r"\d{4}\s*[-/]\s*\d{1,2}")
_MATH_PATTERN = re.compile(r"(?<!\w)-?\d+(?:\.\d+)?\s*[+\-*/^]\s*-?\d+(?:\.\d+)?")
_CALCULATION_WORDS = (
    "计算",
    "算一下",
    "算算",
    "等于多少",
    "等于几",
    "求值",
    "开平方",
    "除以",
    "乘以",
    "多少加",
    "多少乘",
)

_PROGRESS_WORDS = (
    "学习进度",
    "我的进度",
    "进度怎么样",
    "掌握度",
    "掌握得怎么样",
    "学习目标",
    "目标还有多远",
    "离目标",
    "复习计划",
    "复习安排",
    "学习情况",
)

_PRACTICE_WORDS = (
    "出题",
    "出一道",
    "出几道",
    "练习题",
    "做题",
    "刷题",
    "考考我",
    "测试我",
    "自测",
    "quiz",
)
_PRACTICE_PATTERN = re.compile(r"(出|来|给|要)\s*\d+\s*道")

_RETRIEVAL_WORDS = (
    "我的资料",
    "我的文档",
    "我上传",
    "我的知识库",
    "知识库",
    "文档里",
    "资料里",
    "根据资料",
    "根据文档",
    "根据我",
    "检索",
    "查一下我的",
    "找一下",
    "帮我找",
)

_CONCEPT_WORDS = (
    "什么是",
    "是什么意思",
    "的定义",
    "定义是什么",
    "怎么理解",
    "如何理解",
    "为什么",
    "解释一下",
    "解释下",
    "讲讲",
    "讲一下",
    "介绍一下",
    "有什么区别",
    "通俗",
    "原理是什么",
    "概念",
)

_SMALLTALK_WORDS = (
    "你好",
    "您好",
    "哈喽",
    "嗨",
    "在吗",
    "你是谁",
    "你叫什么",
    "你能做什么",
    "你有什么功能",
    "天气",
    "笑话",
)
_SMALLTALK_PATTERN = re.compile(r"^(hi|hello|hey)\b", re.IGNORECASE)

_INTENT_LLM_SYSTEM_PROMPT = """你是教学助手的意图分类器。判断用户最新一条消息属于哪一类:
- concept_explain:讲解概念、原理、定义,或围绕知识点答疑
- practice:出题、练习、做题、测验
- progress:查询学习进度、掌握度、目标完成情况
- retrieval:在用户自己的知识库、资料或文档里查找内容
- calculation:数学计算或数值求解
- smalltalk:寒暄、闲聊、询问助手本身,或与学习无关的话
只输出一行 JSON,不要输出任何其他文字:{"intent": "类别", "confidence": 0到1的小数}"""


@dataclass(frozen=True)
class IntentResult:
    """一次意图识别的结果。

    ``detector`` 记录结果来源:``rule``(规则)、``llm``(模型输出)或
    ``fallback``(规则未命中任何关键词的默认值),事件和 trace 用它区分
    决策路径。``usage`` 是 LLM 识别调用的 token 用量,规则路径为 None。
    """

    intent: str
    confidence: float
    detector: str = "rule"
    usage: LLMUsage | None = field(default=None, compare=False)


@dataclass(frozen=True)
class AgentProfile:
    """一个子 agent 的路由配置:专属提示词 + 工具策略。

    ``default_tools`` 是前端未显式选择工具时的默认启用集;``denied_tools``
    是无论工具从哪里来(默认集、用户选择、知识库联动)最终都要移除的黑名单;
    ``deny_all=True`` 直接清空全部工具,表达"只读子 agent"。拒绝集在运行时
    执行层同样生效:模型仍请求被拒工具时收到 ``tool_not_allowed`` 失败结果。
    """

    agent: str
    default_tools: tuple[str, ...] = ("calculator",)
    denied_tools: tuple[str, ...] = ()
    deny_all: bool = False
    allow_mcp_tools: bool = True
    system_prompt: str = ""


AGENT_PROFILES: dict[str, AgentProfile] = {
    INTENT_CONCEPT_EXPLAIN: AgentProfile(
        agent="tutor",
        default_tools=("calculator", "save_to_knowledge_base"),
        allow_mcp_tools=True,
        system_prompt=(
            "你现在是讲解导师。先用学习者能懂的语言拆解概念,再给一个具体例子;"
            "如果学习者选择了知识库,先调用知识检索找到资料,基于资料回答并给出引用;"
            "涉及数值时必须用计算器工具,不要心算。"
        ),
    ),
    INTENT_PRACTICE: AgentProfile(
        agent="practice",
        # 工具最小权限:练习 agent 不给检索工具,出题只依赖模型自身与对话上下文。
        default_tools=(),
        denied_tools=("knowledge_search",),
        allow_mcp_tools=False,
        system_prompt=(
            "你现在是出题教练。生成有梯度的练习题,覆盖理解、应用和迁移三个层次;"
            "每道题写清作答要求,除非学习者要求,先不要公布答案。"
            "你没有检索工具,不要假装引用了任何资料。"
        ),
    ),
    INTENT_PROGRESS: AgentProfile(
        agent="progress",
        # 只读子 agent:deny_all 清空全部工具,不触碰知识库和计算。
        default_tools=(),
        deny_all=True,
        allow_mcp_tools=False,
        system_prompt=(
            "你现在是学习进度报告员。只依据学习者档案中的目标、进度和本次对话内容回答;"
            "没有相关数据时如实说明,不要编造进度数字或复习计划。"
        ),
    ),
    INTENT_RETRIEVAL: AgentProfile(
        agent="retriever",
        default_tools=("knowledge_search", "save_to_knowledge_base"),
        allow_mcp_tools=False,
        system_prompt=(
            "你现在是资料检索助手。把学习者的需求改写成聚焦的检索词,调用知识检索,"
            "基于返回的片段回答并给出来源;检索不到时如实说明,并建议换一种问法。"
        ),
    ),
    INTENT_CALCULATION: AgentProfile(
        agent="calculator",
        default_tools=("calculator",),
        denied_tools=("knowledge_search",),
        allow_mcp_tools=False,
        system_prompt=(
            "你现在是计算助手。所有算式必须调用计算器工具求值,展示算式和结果,"
            "并解释计算步骤;不要心算,不要跳过中间步骤。"
        ),
    ),
    INTENT_SMALLTALK: AgentProfile(
        agent="chat",
        # 默认子 agent:保持与引入路由之前一致的工具配置,外加"沉淀进
        # 知识库"——学生随手把题目/笔记存进学科库的核心动作。
        default_tools=("calculator", "save_to_knowledge_base"),
        allow_mcp_tools=True,
        system_prompt="",
    ),
}

DEFAULT_PROFILE = AGENT_PROFILES[INTENT_SMALLTALK]


def get_agent_profile(intent: str) -> AgentProfile:
    """意图 → 子 agent 配置;未知意图一律回默认 chat。"""

    return AGENT_PROFILES.get(intent, DEFAULT_PROFILE)


def classify_by_rules(text: str) -> IntentResult:
    """规则关键词意图分类(纯函数,确定性)。

    判定顺序按"信号越具体越优先":数学表达式 → 进度 → 练习 → 检索 →
    概念 → 闲聊/兜底。任何分支都不抛异常,空文本安全。
    """

    compact = " ".join(str(text or "").split())
    lowered = compact.lower()

    if (
        not _DATE_PATTERN.search(compact)
        and (_MATH_PATTERN.search(compact) or _contains(compact, _CALCULATION_WORDS))
    ):
        return IntentResult(INTENT_CALCULATION, 0.95, "rule")

    if _contains(compact, _PROGRESS_WORDS):
        return IntentResult(INTENT_PROGRESS, 0.85, "rule")

    if _contains(lowered, _PRACTICE_WORDS) or _PRACTICE_PATTERN.search(compact):
        return IntentResult(INTENT_PRACTICE, 0.85, "rule")

    if _contains(compact, _RETRIEVAL_WORDS):
        return IntentResult(INTENT_RETRIEVAL, 0.85, "rule")

    if _contains(compact, _CONCEPT_WORDS):
        return IntentResult(INTENT_CONCEPT_EXPLAIN, 0.8, "rule")

    if _contains(compact, _SMALLTALK_WORDS) or _SMALLTALK_PATTERN.match(lowered):
        return IntentResult(INTENT_SMALLTALK, 0.8, "rule")

    return IntentResult(INTENT_SMALLTALK, 0.3, "fallback")


async def detect_intent(
    text: str,
    provider: BaseProvider,
    *,
    llm_enabled: bool = True,
) -> IntentResult:
    """识别一条用户消息的意图:强规则直接返回,否则 LLM 识别,失败回退规则。

    Mock Provider 直接走规则——它的输出不遵循意图 JSON 约定,问它没有
    信息量;这也保证自动测试(全程 Mock)确定性可断言、零 API 消耗。
    本函数永不抛异常:任何 LLM 侧失败都回退规则结果,不阻塞回合。
    """

    rule = classify_by_rules(text)
    if rule.confidence >= STRONG_RULE_CONFIDENCE:
        return rule
    if not llm_enabled or getattr(provider, "name", "") == "mock":
        return rule
    try:
        result = await provider.complete(
            [
                {"role": "system", "content": _INTENT_LLM_SYSTEM_PROMPT},
                {"role": "user", "content": str(text or "")[:500]},
            ],
            [],
            max_output_tokens=64,
        )
        parsed = parse_intent_json(result.content)
    except Exception:  # noqa: BLE001 — 意图识别失败绝不阻塞正常回合
        return rule
    if parsed is None:
        return rule
    return IntentResult(
        parsed.intent,
        parsed.confidence,
        "llm",
        usage=result.usage,
    )


def parse_intent_json(content: str) -> IntentResult | None:
    """解析 LLM 的意图 JSON 输出;格式或取值非法时返回 None。"""

    text = str(content or "").strip()
    if not text:
        return None
    # 兼容模型顺手包上的 markdown 代码块。
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    intent = payload.get("intent")
    if intent not in VALID_INTENTS:
        return None
    try:
        confidence = float(payload.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    confidence = min(1.0, max(0.0, confidence))
    return IntentResult(str(intent), confidence, "llm")


def build_agent_prompt(profile: AgentProfile, base_prompt: str) -> str:
    """把子 agent 专属提示词叠加在能力提示词之后;空提示词原样返回。"""

    if not profile.system_prompt:
        return base_prompt
    return f"{base_prompt}\n\n{profile.system_prompt}"


def _contains(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


__all__ = [
    "AGENT_PROFILES",
    "AgentProfile",
    "DEFAULT_PROFILE",
    "INTENT_CALCULATION",
    "INTENT_CONCEPT_EXPLAIN",
    "INTENT_PRACTICE",
    "INTENT_PROGRESS",
    "INTENT_RETRIEVAL",
    "INTENT_SMALLTALK",
    "IntentResult",
    "STRONG_RULE_CONFIDENCE",
    "VALID_INTENTS",
    "build_agent_prompt",
    "classify_by_rules",
    "detect_intent",
    "get_agent_profile",
    "parse_intent_json",
]
