from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from teachx import __version__
from teachx.api.container import ApplicationContainer
from teachx.api.router import api_router
from teachx.api.routes.ws import router as ws_router
from teachx.auth.service import AuthService
from teachx.config import get_settings
from teachx.knowledge.embeddings import build_embedding_provider
from teachx.knowledge.service import KnowledgeService
from teachx.memory.service import MemoryService
from teachx.model_connections.service import ModelConnectionService
from teachx.practice.service import PracticeService
from teachx.providers import build_provider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.mcp_client import McpBridge, McpStdioClient
from teachx.runtime.tool_executions import ToolExecutionStore
from teachx.runtime.tools import ToolExecutionDefaults, build_default_registry
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository
from teachx.usage.service import UsageService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    database = Database(settings.resolved_database_path())
    await database.initialize()
    repository = SessionRepository(database)
    auth = AuthService(
        database,
        secret=settings.auth_secret,
        token_ttl_minutes=settings.auth_token_ttl_minutes,
    )
    embedder = build_embedding_provider(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        api_key=settings.api_key,
        base_url=settings.base_url,
    )
    knowledge = KnowledgeService(
        database,
        settings.resolved_knowledge_root(),
        max_file_bytes=settings.max_upload_bytes,
        embedder=embedder,
    )
    practice = PracticeService(database)
    usage = UsageService(database)
    memory = MemoryService(database)
    model_connections = ModelConnectionService(
        database,
        secret=settings.auth_secret,
        max_output_tokens=settings.max_output_tokens,
        temperature=settings.temperature,
        include_stream_usage=settings.include_stream_usage,
    )
    execution_store = ToolExecutionStore(
        database,
        stale_seconds=settings.tool_execution_stale_seconds,
    )
    tools = build_default_registry(
        knowledge,
        defaults=ToolExecutionDefaults(
            max_attempts=settings.tool_max_attempts,
            timeout_seconds=settings.tool_timeout_seconds,
            retry_base_delay_seconds=settings.tool_retry_base_delay_ms / 1000,
            retry_max_delay_seconds=settings.tool_retry_max_delay_ms / 1000,
        ),
        execution_store=execution_store,
        idempotency_enabled=settings.tool_idempotency_enabled,
        redaction_enabled=settings.tool_redaction_enabled,
    )
    # E9:注册 MCP server 的远端工具(学习版)。单个 server 不可用只告警,
    # 不阻塞应用启动。
    try:
        server_specs = json.loads(settings.mcp_servers) if settings.mcp_servers else []
    except json.JSONDecodeError:
        print(f"[mcp] TEACHX_MCP_SERVERS 不是合法 JSON,已忽略: {settings.mcp_servers[:80]}")
        server_specs = []
    for spec in server_specs:
        name = str(spec.get("name") or "mcp")
        command = [str(spec.get("command") or "")] + [str(a) for a in spec.get("args", [])]
        if not command[0]:
            continue
        try:
            client = McpStdioClient(command)
            bridge = McpBridge(name, client)
            registered = await bridge.register_into(tools)
            print(f"[mcp] server={name} 注册工具: {registered}")
        except Exception as exc:  # noqa: BLE001
            print(f"[mcp] server={name} 连接失败,已跳过: {exc}")
    provider = build_provider(settings)
    runtime = AgentRuntime(
        provider=provider,
        tools=tools,
        repository=repository,
        auth=auth,
        max_rounds=settings.max_agent_rounds,
        usage=usage,
        max_history_messages=settings.max_history_messages,
        max_history_chars=settings.max_history_chars,
        history_summary_enabled=settings.history_summary_enabled,
        summary_snippet_chars=settings.summary_snippet_chars,
        max_tool_result_chars=settings.max_tool_result_chars,
        max_tool_concurrency=settings.tool_max_concurrency,
        turn_timeout_seconds=settings.turn_timeout_seconds,
        generate_titles=settings.generate_titles,
        daily_token_budget=settings.daily_token_budget,
        budget_exceeded_action=settings.budget_exceeded_action,
        intent_enabled=settings.intent_enabled,
        intent_llm_enabled=settings.intent_llm_enabled,
        memory=memory,
        memory_enabled=settings.memory_enabled,
    )
    app.state.container = ApplicationContainer(
        settings=settings,
        repository=repository,
        auth=auth,
        knowledge=knowledge,
        practice=practice,
        model_connections=model_connections,
        provider=provider,
        tools=tools,
        runtime=runtime,
        memory=memory,
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
