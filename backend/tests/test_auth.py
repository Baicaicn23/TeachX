from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from teachx.auth.service import AuthService, InvalidCredentials
from teachx.config import get_settings
from teachx.main import app
from teachx.storage.database import Database


async def test_auth_service_registers_first_admin_and_authenticates(tmp_path: Path) -> None:
    database = Database(tmp_path / "auth.db")
    await database.initialize()
    service = AuthService(
        database, secret="test-secret-that-is-at-least-32-bytes", token_ttl_minutes=30
    )

    user, first = await service.register("student@example.com", "password123")
    assert first is True
    assert user.role == "admin"

    authenticated = await service.authenticate("student@example.com", "password123")
    assert authenticated.id == user.id

    token = service.create_token(authenticated)
    restored = await service.user_from_token(token)
    assert restored is not None
    assert restored.username == "student@example.com"

    try:
        await service.authenticate("student@example.com", "wrong-password")
    except InvalidCredentials:
        pass
    else:
        raise AssertionError("wrong password should fail")


def test_auth_routes_and_session_protection(tmp_path: Path) -> None:
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "knowledge_root": settings.knowledge_root,
        "auth_enabled": settings.auth_enabled,
        "auth_secret": settings.auth_secret,
    }
    settings.database_path = tmp_path / "auth-api.db"
    settings.knowledge_root = tmp_path / "knowledge"
    settings.auth_enabled = True
    settings.auth_secret = "test-api-secret-that-is-at-least-32-bytes"
    try:
        with TestClient(app) as client:
            assert client.get("/api/auth/status").json() == {
                "enabled": True,
                "authenticated": False,
            }
            assert client.get("/api/auth/is_first_user").json()["is_first_user"] is True
            assert client.get("/api/sessions").status_code == 401
            with pytest.raises(WebSocketDisconnect) as rejected:
                with client.websocket_connect("/ws"):
                    pass
            assert rejected.value.code == 4401

            registered = client.post(
                "/api/auth/register",
                json={
                    "username": "student@example.com",
                    "password": "password123",
                },
            )
            assert registered.status_code == 200
            assert registered.json()["role"] == "admin"

            logged_in = client.post(
                "/api/auth/login",
                json={
                    "username": "student@example.com",
                    "password": "password123",
                },
            )
            assert logged_in.status_code == 200
            assert "dt_token" in logged_in.cookies

            status = client.get("/api/auth/status").json()
            assert status["authenticated"] is True
            assert status["is_admin"] is True
            assert client.get("/api/sessions").status_code == 200
            with client.websocket_connect("/ws") as websocket:
                websocket.send_json(
                    {
                        "type": "start_turn",
                        "protocol_version": "2.0",
                        "command_id": "auth-ws",
                        "content": "计算 2 + 2",
                        "capability": "chat",
                    }
                )
                while websocket.receive_json()["type"] != "done":
                    pass

            assert client.post("/api/auth/logout").status_code == 200
            assert client.get("/api/sessions").status_code == 401
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
