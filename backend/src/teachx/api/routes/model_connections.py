from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from teachx.api.auth_dependencies import require_user
from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container
from teachx.auth.models import UserRecord
from teachx.model_connections.service import ModelConnectionError

router = APIRouter(prefix="/api/model-connections", tags=["model-connections"])


class ConnectionSaveRequest(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    default_model: str = Field(default="", max_length=200)
    models: list[str] = Field(default_factory=list)


class ConnectionTestRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    connection_id: str | None = None


@router.get("")
async def list_model_connections(
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    settings = container.settings
    return {
        "platform_default": {
            "provider": settings.llm_provider,
            "model": settings.model,
            "base_url": settings.base_url or "",
        },
        "connections": await container.model_connections.list_connections(
            user_id=user.id
        ),
    }


@router.post("")
async def save_model_connection(
    payload: ConnectionSaveRequest,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    try:
        record = await container.model_connections.save_connection(
            user_id=user.id,
            connection_id=payload.id,
            name=payload.name,
            base_url=payload.base_url,
            api_key=payload.api_key,
            default_model=payload.default_model,
            models=payload.models,
        )
    except ModelConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"connection": record}


@router.post("/test")
async def test_model_connection(
    payload: ConnectionTestRequest,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, list[str]]:
    try:
        models = await container.model_connections.test_connection(
            user_id=user.id,
            base_url=payload.base_url,
            api_key=payload.api_key,
            connection_id=payload.connection_id,
        )
    except ModelConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"models": models}


@router.post("/default/activate")
async def activate_platform_default(
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, bool]:
    await container.model_connections.activate_platform_default(user_id=user.id)
    return {"ok": True}


@router.post("/{connection_id}/activate")
async def activate_model_connection(
    connection_id: str,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, bool]:
    activated = await container.model_connections.activate_connection(
        user_id=user.id,
        connection_id=connection_id,
    )
    if not activated:
        raise HTTPException(status_code=404, detail="模型连接不存在")
    return {"ok": True}


@router.delete("/{connection_id}")
async def delete_model_connection(
    connection_id: str,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, bool]:
    deleted = await container.model_connections.delete_connection(
        user_id=user.id,
        connection_id=connection_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="模型连接不存在")
    return {"deleted": True}
