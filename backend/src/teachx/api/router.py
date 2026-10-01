from fastapi import APIRouter

from teachx.api.routes import (
    capabilities,
    compat,
    health,
    knowledge,
    sessions,
    settings,
    tools,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(capabilities.router)
api_router.include_router(compat.router)
api_router.include_router(knowledge.router)
api_router.include_router(sessions.router)
api_router.include_router(settings.router)
api_router.include_router(tools.router)
