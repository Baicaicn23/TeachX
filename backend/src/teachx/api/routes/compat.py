from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["frontend-compatibility"])

SUGGESTIONS = {
    "suggestions": [
        {
            "label": "用一个具体问题理解 Agent Loop",
            "prompt": "用大一学生能懂的方式解释 Agent Loop，并举一个工具调用的例子。",
        },
        {
            "label": "把一次 RAG 流程画成数据流",
            "prompt": "把 RAG 从文档切分到最终回答的完整数据流讲清楚。",
        },
        {
            "label": "生成一组人工智能基础练习题",
            "prompt": "围绕人工智能基础生成 3 道由浅入深的练习题。",
        },
    ],
    "stale": False,
    "status": "ready",
}


@router.get("/api/settings")
async def settings() -> dict[str, object]:
    """Compatibility payload for the reused frontend settings shell."""
    return {
        "catalog": {
            "active": {"profile_id": "mock", "model_id": "teachx-mock"},
            "profiles": [],
        },
        "language": "zh",
        "theme": "light",
    }


@router.get("/api/settings/llm-options")
async def llm_options() -> dict[str, object]:
    active = {"profile_id": "mock", "model_id": "teachx-mock"}
    return {
        "active": active,
        "options": [
            {
                **active,
                "profile_name": "TeachX Mock",
                "model_name": "teachx-mock",
                "model": "teachx-mock",
                "provider": "mock",
                "provider_label": "Local Mock",
                "context_window": 32768,
                "supports_vision": False,
                "is_active_default": True,
            }
        ],
    }


@router.get("/api/settings/chat-attachments")
async def chat_attachments() -> dict[str, object]:
    return {
        "effective": {
            "max_file_bytes": 20 * 1024 * 1024,
            "max_total_bytes": 50 * 1024 * 1024,
        }
    }


@router.get("/api/settings/workspace/registrations")
async def workspace_registrations() -> dict[str, list[object]]:
    return {"workspaces": []}


@router.get("/api/settings/workspace/resources")
async def workspace_resources() -> dict[str, list[object]]:
    return {"skills": [], "mcp": [], "knowledge_bases": []}


@router.get("/api/auth/status")
async def auth_status() -> dict[str, object]:
    return {
        "enabled": False,
        "authenticated": True,
        "is_admin": True,
        "username": "Local learner",
    }


@router.get("/api/system/update")
async def app_update() -> dict[str, object]:
    return {
        "current_version": "0.1.0",
        "check_enabled": False,
        "checked_at": "",
        "cached": True,
        "check_error": "",
        "update_available": False,
        "release": None,
        "installation": {
            "mode": "source",
            "automatic_update": False,
            "command": "",
            "reason": "TeachX is under active development.",
        },
        "launcher_managed": False,
        "is_admin": True,
        "job": None,
    }


@router.get("/api/dashboard/suggestions")
async def suggestions() -> dict[str, object]:
    return SUGGESTIONS


@router.post("/api/dashboard/suggestions/refresh")
async def refresh_suggestions() -> dict[str, object]:
    return SUGGESTIONS


@router.get("/api/courses")
async def courses() -> dict[str, list[object]]:
    return {"courses": []}


@router.get("/api/mastery-paths/topics/index")
async def mastery_topics() -> dict[str, list[object]]:
    return {"topics": []}


@router.get("/api/reading/workspaces/index")
async def reading_workspaces() -> dict[str, list[object]]:
    return {"collections": []}


@router.get("/api/partners")
async def partners() -> list[object]:
    return []


@router.get("/api/partner-groups")
async def partner_groups() -> list[object]:
    return []


@router.get("/api/subagents/settings")
async def subagent_settings() -> dict[str, object]:
    return {"connections": [], "enabled_backends": []}
