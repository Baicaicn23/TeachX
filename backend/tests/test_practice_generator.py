"""练习出题"模型写题"层(generator)的单元测试。

覆盖:提示词拼装、模型返回解析(含代码块/坏 JSON/敷衍输出)、模型不可用时
回退模板、模型抛异常时回退模板。全程不联网、不消耗额度。
"""

import asyncio
from types import SimpleNamespace

from teachx.practice.generator import (
    build_excerpt_instruction,
    build_mistake_instruction,
    parse_written_question,
    template_excerpt_question,
    template_mistake_question,
    write_question,
)


class _StubProvider:
    """名字不是 mock 的假 Provider,用来覆盖模型路径。"""

    name = "stub"
    model = "stub-model"

    def __init__(self, content: str) -> None:
        self.content = content

    async def complete(self, messages, tools, *, max_output_tokens=None):  # noqa: ANN001
        return SimpleNamespace(content=self.content, usage=None)


class _BoomProvider(_StubProvider):
    async def complete(self, messages, tools, *, max_output_tokens=None):  # noqa: ANN001
        raise RuntimeError("provider down")


def test_parse_written_question_accepts_json_and_rejects_junk() -> None:
    assert parse_written_question('{"question": "请解释定积分与不定积分的区别。"}') == (
        "请解释定积分与不定积分的区别。"
    )
    # 模型顺手包了 markdown 代码块也要认。
    fenced = '```json\n{"question": "求 ∫₀²(3x²+2x)dx 的值。"}\n```'
    assert parse_written_question(fenced) == "求 ∫₀²(3x²+2x)dx 的值。"
    # 前后有多余文字时,取第一个大括号到最后一个大括号。
    noisy = '好的，这是题目：{"question": "用一句话说明什么是极限。"} 希望有帮助'
    assert parse_written_question(noisy) == "用一句话说明什么是极限。"
    # 以下都应判为失败,交给模板兜底。
    assert parse_written_question("") is None
    assert parse_written_question("无法出题") is None
    assert parse_written_question("{不是 JSON}") is None
    assert parse_written_question('{"question": "略"}') is None
    assert parse_written_question('{"focus": "没有 question 字段"}') is None


def test_instruction_builders_include_the_material() -> None:
    instruction = build_mistake_instruction(
        subject="线性代数",
        question="什么是特征值？",
        note="我把特征向量和基向量混淆了。",
    )
    assert "线性代数" in instruction
    assert "什么是特征值？" in instruction
    assert "我把特征向量和基向量混淆了。" in instruction

    excerpt_instruction = build_excerpt_instruction("内存用于运行时快速访问。")
    assert "内存用于运行时快速访问。" in excerpt_instruction


def test_templates_are_usable_without_a_model() -> None:
    # 知识库来源的模板必须与改造前逐字一致,避免改变既有行为。
    assert template_excerpt_question("内存和硬盘的区别") == (
        "请用自己的话解释下面这段资料。回答时说明核心概念、"
        "关键关系和一个具体例子。\n\n"
        "资料摘录：\n「内存和硬盘的区别」"
    )
    mistake = template_mistake_question(
        question="什么是特征值？",
        note="我把特征向量和基向量混淆了。",
    )
    assert "什么是特征值？" in mistake
    assert "我把特征向量和基向量混淆了。" in mistake
    assert "重新独立做一遍" in mistake


def test_write_question_falls_back_without_a_model() -> None:
    async def scenario() -> None:
        # 没有 provider:模板出题。
        none_provider = await write_question(None, "要求", fallback="模板题")
        assert none_provider.generator == "template"
        assert none_provider.prompt == "模板题"

        # Mock Provider:按约定直接走模板(Mock 不遵循本模块的 JSON 约定)。
        mock = _StubProvider('{"question": "这批题不该出现"}')
        mock.name = "mock"
        mocked = await write_question(mock, "要求", fallback="模板题")
        assert mocked.generator == "template"
        assert mocked.prompt == "模板题"

    asyncio.run(scenario())


def test_write_question_falls_back_on_bad_output_or_error() -> None:
    async def scenario() -> None:
        # 模型返回解析不了的输出 → 模板。
        junk = await write_question(
            _StubProvider("我觉得这个问题很好，但我不打算给 JSON"),
            "要求",
            fallback="模板题",
        )
        assert junk.generator == "template"
        assert junk.prompt == "模板题"

        # 模型直接抛异常 → 模板,而且不把异常抛给调用方。
        broken = await write_question(
            _BoomProvider(""),
            "要求",
            fallback="模板题",
        )
        assert broken.generator == "template"
        assert broken.prompt == "模板题"

    asyncio.run(scenario())


def test_write_question_uses_model_output_when_valid() -> None:
    async def scenario() -> None:
        written = await write_question(
            _StubProvider('{"question": "求 ∫₀²(3x²+2x)dx 的值，并说明用到的定理。"}'),
            "要求",
            fallback="模板题",
        )
        assert written.generator == "model"
        assert written.prompt == "求 ∫₀²(3x²+2x)dx 的值，并说明用到的定理。"

    asyncio.run(scenario())
