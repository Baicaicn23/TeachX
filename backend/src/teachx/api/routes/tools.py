from fastapi import APIRouter

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools() -> dict[str, list[str]]:
    return {"enabled_optional_tools": ["calculator"]}
