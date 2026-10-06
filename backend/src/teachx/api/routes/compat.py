from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["frontend-compatibility"])

SUGGESTIONS = {
    "suggestions": [
        {
            "label": "用我的知识库讲一个概念",
            "prompt": "结合我的知识库，用通俗的例子讲讲什么是极限，并给出出处。",
        },
        {
            "label": "算一道题并解释步骤",
            "prompt": "帮我算一下 37 * 43，并解释计算步骤。",
        },
        {
            "label": "来一组练习题测测我",
            "prompt": "围绕我的知识库内容出 3 道由浅入深的练习题，先不要给答案。",
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
            "version": 1,
            "connections": [],
            "services": {
                "llm": {
                    "active_profile_id": None,
                    "active_model_id": None,
                    "profiles": [],
                },
                "task": {
                    "active_profile_id": None,
                    "active_model_id": None,
                    "profiles": [],
                },
                "embedding": {
                    "active_profile_id": None,
                    "active_model_id": None,
                    "profiles": [],
                },
                "search": {"active_profile_id": None, "profiles": []},
                "tts": {
                    "active_profile_id": None,
                    "active_model_id": None,
                    "profiles": [],
                },
                "stt": {
                    "active_profile_id": None,
                    "active_model_id": None,
                    "profiles": [],
                },
                "imagegen": {
                    "active_profile_id": None,
                    "active_model_id": None,
                    "profiles": [],
                },
                "videogen": {
                    "active_profile_id": None,
                    "active_model_id": None,
                    "profiles": [],
                },
            },
        },
        "ui": {
            "theme": "light",
            "language": "zh",
            "response_language": "zh",
            "code_block_theme": "github-dark",
            "code_block_show_line_numbers": True,
            "code_block_wrap_long_lines": False,
        },
        "providers": {
            "llm": [],
            "task": [],
            "embedding": [],
            "search": [],
            "tts": [],
            "stt": [],
            "imagegen": [],
            "videogen": [],
        },
        "connection_targets": {},
        "task_kinds": [],
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


@router.get("/api/subagents/connections")
async def subagent_connections() -> list[object]:
    return []


@router.get("/api/subagents/backends/options")
async def subagent_backend_options() -> list[object]:
    return []
