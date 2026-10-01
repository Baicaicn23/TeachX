from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from teachx.config import get_settings
from teachx.knowledge.service import KnowledgeService
from teachx.main import app
from teachx.runtime.tools import KnowledgeSearchTool, ToolContext
from teachx.storage.database import Database


@pytest.mark.asyncio
async def test_knowledge_service_enforces_owner_scope(tmp_path: Path) -> None:
    database = Database(tmp_path / "ownership.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "files")

    await service.create_base("用户一资料", owner_id="user-1")
    await service.add_document(
        "用户一资料",
        "private.md",
        "这是用户一的私有资料。".encode(),
        owner_id="user-1",
    )

    assert await service.list_bases("user-2") == []
    assert await service.get_base("用户一资料", "user-2") is None
    assert (
        await service.search(
            "私有资料",
            ["用户一资料"],
            owner_id="user-2",
        )
        == []
    )
    assert await service.delete_base("用户一资料", "user-2") is False

    own_hits = await service.search(
        "私有资料",
        ["用户一资料"],
        owner_id="user-1",
    )
    admin_bases = await service.list_bases("admin", is_admin=True)

    assert own_hits
    assert [base.name for base in admin_bases] == ["用户一资料"]


def test_knowledge_api_isolated_between_users(tmp_path: Path) -> None:
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "knowledge_root": settings.knowledge_root,
        "auth_enabled": settings.auth_enabled,
        "auth_secret": settings.auth_secret,
    }
    settings.database_path = tmp_path / "authz-api.db"
    settings.knowledge_root = tmp_path / "knowledge"
    settings.auth_enabled = True
    settings.auth_secret = "authorization-test-secret-at-least-32-bytes"
    try:
        with TestClient(app) as admin_client:
            _register_and_login(admin_client, "admin@example.com")

            with TestClient(app) as user_client:
                _register_and_login(user_client, "user@example.com")

                admin_create = admin_client.post(
                    "/api/knowledge-bases",
                    data={"name": "管理员资料", "rag_provider": "sqlite-fts"},
                )
                assert admin_create.status_code == 200

                user_create = user_client.post(
                    "/api/knowledge-bases",
                    data={"name": "用户资料", "rag_provider": "sqlite-fts"},
                )
                assert user_create.status_code == 200

                user_bases = user_client.get("/api/knowledge-bases").json()["knowledge_bases"]
                admin_bases = admin_client.get("/api/knowledge-bases").json()["knowledge_bases"]

                assert [base["name"] for base in user_bases] == ["用户资料"]
                assert {base["name"] for base in admin_bases} == {
                    "管理员资料",
                    "用户资料",
                }
                assert user_client.get("/api/knowledge-bases/管理员资料").status_code == 404
                assert admin_client.get("/api/knowledge-bases/用户资料").status_code == 200
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def _register_and_login(client: TestClient, username: str) -> None:
    password = "password123"
    registered = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert registered.status_code == 200
    logged_in = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert logged_in.status_code == 200


@pytest.mark.asyncio
async def test_knowledge_tool_respects_user_scope(tmp_path: Path) -> None:
    database = Database(tmp_path / "tool-ownership.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "tool-files")
    await service.create_base("私有资料", owner_id="user-1")
    await service.add_document(
        "私有资料",
        "secret.md",
        "只有用户一可以看到这段私有知识。".encode(),
        owner_id="user-1",
    )
    tool = KnowledgeSearchTool(service)

    denied = await tool.execute(
        ToolContext(user_id="user-2", knowledge_bases=("私有资料",)),
        query="私有知识",
    )
    allowed = await tool.execute(
        ToolContext(user_id="user-1", knowledge_bases=("私有资料",)),
        query="私有知识",
    )

    assert denied.metadata["sources"] == []
    assert allowed.metadata["sources"][0]["title"] == "secret.md"
