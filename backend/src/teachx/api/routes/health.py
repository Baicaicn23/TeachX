from fastapi import APIRouter, Depends

from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(container: ApplicationContainer = Depends(get_container)) -> dict[str, object]:
    return {
        "status": "ok",
        "service": container.settings.app_name,
        "provider": container.settings.llm_provider,
        "model": container.settings.model,
    }
