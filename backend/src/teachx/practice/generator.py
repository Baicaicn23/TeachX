"""用模型写练习题(2026-10-08)。

出题原先只有一种做法:把知识库片段原样抠出来,套一句固定的话。它确定、
零成本,但出的题不像题;更要紧的是,完全用不上学生自己记过的误区——
"记录我的误区"写下的东西只躺在学习记录页里,从来没被用来出过题。

本模块加一层"模型写题":给模型看学生的误区(或一段资料),让它写一道新题。
结构照抄 ``runtime/intents.py`` 的意图识别——提示词是纯函数、要求模型返回
结构化 JSON、**任何失败都回退模板**。出题永远不会因为模型不可用而失败,
只会退化成老办法,所以调用方不需要处理异常。

代价要说清楚:模板出题零 API 消耗,模型出题不是。调用方负责在预算超限或
没有可用模型时传 ``provider=None``,本模块就只走模板。

测试注意:Mock Provider 直接走模板(与意图识别同一约定——它的输出不遵循
本模块的 JSON 约定,问它没有信息量)。要覆盖模型路径请用一个自定义的测试
Provider(名字不是 "mock")。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# 塞进提示词的原文上限,防止把一整份资料倒给模型。
MAX_INSTRUCTION_CHARS = 1200
# 模型写出的题面上限,超出截断。
MAX_QUESTION_CHARS = 600
# 题面太短多半是"略""无法出题"之类的敷衍输出,视为解析失败。
MIN_QUESTION_CHARS = 8

_SYSTEM_PROMPT = (
    "你是一位出题教练,为一位大学生出一道练习题。"
    "只输出 JSON,不要任何解释、不要 markdown 代码块,格式为:"
    '{"question": "题目正文"}。'
    "题面要自成一体(学习者不看资料也能作答),用简体中文,"
    "数学式子用纯文本写清楚,不要给出答案或解题步骤,题面不超过 200 字。"
)


@dataclass(frozen=True)
class WrittenQuestion:
    """一道写好的题。``generator`` 标明它出自模型还是模板,便于排查。"""

    prompt: str
    generator: str  # "model" | "template"
    usage: Any | None = None


def template_excerpt_question(excerpt: str) -> str:
    """知识库来源的模板题——与改造前逐字一致,保持既有行为。"""

    return (
        "请用自己的话解释下面这段资料。回答时说明核心概念、"
        "关键关系和一个具体例子。\n\n"
        f"资料摘录：\n「{excerpt}」"
    )


def template_mistake_question(*, question: str, note: str) -> str:
    """误区来源的模板题——没有模型时也能出一道具名指姓的题。"""

    parts = ["你之前在这一块卡过。现在不看资料、也不看当时的答案，重新独立做一遍。"]
    clean_question = str(question or "").strip()
    clean_note = str(note or "").strip()
    if clean_question:
        parts.append(f"【当时的问题】\n{clean_question}")
    if clean_note:
        parts.append(f"【你当时记下的误区】\n{clean_note}")
    parts.append("先写出你的完整思路，再对照检查是卡在哪一步。")
    return "\n\n".join(parts)


def build_mistake_instruction(*, subject: str, question: str, note: str) -> str:
    """拼给模型的出题要求(纯函数,可单测)。"""

    lines = []
    if str(subject or "").strip():
        lines.append(f"学科：{subject.strip()}")
    if str(question or "").strip():
        lines.append(f"学习者当时问的问题：{question.strip()}")
    if str(note or "").strip():
        lines.append(f"学习者自己记下的误区：{note.strip()}")
    lines.append(
        "请针对这个误区出一道新题:考察同一个知识点,但换个问法或换组数字,"
        "让学习者能自己验证是不是真的弄懂了。"
    )
    return "\n".join(lines)


def build_excerpt_instruction(excerpt: str) -> str:
    """知识库来源的模型出题要求(纯函数)。"""

    return (
        f"资料摘录：\n{excerpt}\n\n"
        "请根据这段资料出一道新题:考察资料里的核心概念或关键关系,"
        "要求学习者自己组织答案,而不是照抄原文。"
    )


def parse_written_question(content: str) -> str | None:
    """解析模型返回的 JSON 题面;格式、取值非法或明显敷衍时返回 None。"""

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
    question = " ".join(str(payload.get("question") or "").split())
    if len(question) < MIN_QUESTION_CHARS:
        return None
    return question[:MAX_QUESTION_CHARS]


async def write_question(
    provider: Any | None,
    instruction: str,
    *,
    fallback: str,
    max_output_tokens: int | None = None,
) -> WrittenQuestion:
    """先让模型写题,失败或没有模型就用 ``fallback``。本函数永不抛异常。

    ``max_output_tokens`` 默认为 None,即不覆盖——用 Provider 自己配置的
    输出预算。这一点很重要:推理型模型会把预算先花在"思考"上,如果这里
    硬压一个很小的上限(例如 512),模型会返回**空内容**。让上限由配置决定,
    和回合里的模型调用保持同一口径。
    """

    if provider is None or getattr(provider, "name", "") == "mock":
        return WrittenQuestion(prompt=fallback, generator="template")
    try:
        result = await provider.complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": instruction[:MAX_INSTRUCTION_CHARS]},
            ],
            [],
            **({"max_output_tokens": max_output_tokens} if max_output_tokens else {}),
        )
        question = parse_written_question(result.content)
    except Exception as exc:  # noqa: BLE001 — 出题失败绝不阻塞,退回模板
        # 退化本身可以接受,但原因必须留在日志里,否则"模型写题不生效"
        # 会变成一个查不出来的哑故障。
        print(f"[practice] 模型写题失败,改用模板: {type(exc).__name__}: {exc}")
        return WrittenQuestion(prompt=fallback, generator="template")
    if question is None:
        print(
            "[practice] 模型返回无法解析,改用模板: "
            f"{str(result.content)[:160]!r}"
        )
        return WrittenQuestion(prompt=fallback, generator="template")
    return WrittenQuestion(prompt=question, generator="model", usage=result.usage)


__all__ = [
    "WrittenQuestion",
    "build_excerpt_instruction",
    "build_mistake_instruction",
    "parse_written_question",
    "template_excerpt_question",
    "template_mistake_question",
    "write_question",
]
