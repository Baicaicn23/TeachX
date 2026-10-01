from fastapi import APIRouter

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/ui")
async def ui_settings() -> dict[str, str]:
    return {
        "language": "zh",
        "response_language": "zh",
        "theme": "light",
    }
