from fastapi import APIRouter

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])

CAPABILITIES = [
    {
        "id": "chat",
        "kind": "turn",
        "available": True,
        "manifest": {
            "name": "chat",
            "description": "流式学习对话，可调用计算器等工具。",
            "stages": ["exploring", "responding"],
            "tools_used": ["calculator"],
            "cli_aliases": ["chat"],
        },
        "config_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "id": "deep_solve",
        "kind": "turn",
        "available": True,
        "manifest": {
            "name": "deep_solve",
            "description": "分步骤解决数学和逻辑问题的解题模式。",
            "stages": ["exploring", "responding"],
            "tools_used": ["calculator"],
            "cli_aliases": ["solve"],
        },
        "config_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "id": "deep_question",
        "kind": "turn",
        "available": True,
        "manifest": {
            "name": "deep_question",
            "description": "生成有梯度的练习题和测验。",
            "stages": ["ideation", "generation"],
            "tools_used": [],
            "cli_aliases": ["quiz"],
        },
        "config_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


@router.get("/registered")
async def registered() -> dict[str, object]:
    return {"capabilities": CAPABILITIES}
