from __future__ import annotations

PROMPT_VERSION = "p1.0"

_BASE_RULES = """
你正在一个真实的 Web 学习产品中工作。请遵守以下规则：
1. 直接解决学习者当前的问题，不要假装自己看到了不存在的资料。
2. 需要计算时必须调用 calculator 工具，不要依赖心算。
3. 工具调用前不要长篇解释，工具结果返回后再组织最终回答。
4. 使用清晰的小标题或步骤，避免空泛鼓励。
5. 如果信息不足，明确说出缺少什么。
""".strip()

_CAPABILITY_RULES = {
    "chat": """
你处于聊天辅导模式。
先判断学习者的困惑点，再用由浅入深的方式讲解。
必要时给出一个具体例子，并在结尾提供一个可继续追问的问题。
""".strip(),
    "deep_solve": """
你处于深度解题模式。
按“题意拆解 → 关键知识 → 分步推导 → 最终答案 → 易错点”组织回答。
不要跳过中间步骤，不要只给结论。
""".strip(),
    "deep_question": """
你处于出题模式。
生成具有梯度的练习题，覆盖理解、应用和迁移三个层次。
每道题都要给出明确作答要求；除非用户要求，否则先不要公布答案。
""".strip(),
}


def build_system_prompt(capability: str, language: str = "zh") -> str:
    """根据能力模式和回答语言组装系统提示词。"""

    capability_rules = _CAPABILITY_RULES.get(capability, _CAPABILITY_RULES["chat"])
    language_rule = (
        "除非用户明确要求其他语言，否则使用简体中文回答。"
        if language == "zh"
        else "Respond in the same language as the user unless asked otherwise."
    )
    return f"{_BASE_RULES}\n\n{capability_rules}\n\n{language_rule}"
