from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from teachx import __version__
from teachx.api.container import ApplicationContainer
from teachx.api.router import api_router
from teachx.api.routes.ws import router as ws_router
from teachx.config import get_settings
from teachx.providers import build_provider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import build_default_registry
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    database = Database(settings.resolved_database_path())
    await database.initialize()
    repository = SessionRepository(database)
    tools = build_default_registry()
    provider = build_provider(settings)
    runtime = AgentRuntime(
        provider=provider,
        tools=tools,
        repository=repository,
        max_rounds=settings.max_agent_rounds,
    )
    app.state.container = ApplicationContainer(
        settings=settings,
        repository=repository,
        provider=provider,
        tools=tools,
        runtime=runtime,
    )
    yield


app = FastAPI(
    title="TeachX API",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(ws_router)
