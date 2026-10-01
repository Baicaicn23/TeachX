import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from teachx.config import get_settings
from teachx.main import app
from teachx.storage.database import Database


def test_existing_accounts_are_not_forced_into_onboarding(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                avatar TEXT NOT NULL DEFAULT '',
                learner_profile TEXT NOT NULL DEFAULT '{}',
                personalization_enabled INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                last_login_at REAL NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO users (
                id, username, password_hash, role, created_at, updated_at
            ) VALUES ('legacy-user', 'legacy@example.com', 'hash', 'user', 1, 1)
            """
        )
        connection.commit()

    import asyncio

    asyncio.run(Database(database_path).initialize())

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT onboarding_completed FROM users WHERE id = 'legacy-user'"
        ).fetchone()
    assert row == (1,)


def test_onboarding_api_completes_after_profile_save(tmp_path: Path) -> None:
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "knowledge_root": settings.knowledge_root,
        "auth_enabled": settings.auth_enabled,
        "auth_secret": settings.auth_secret,
    }
    settings.database_path = tmp_path / "onboarding-api.db"
    settings.knowledge_root = tmp_path / "knowledge"
    settings.auth_enabled = True
    settings.auth_secret = "onboarding-test-secret-at-least-32-bytes"
    try:
        with TestClient(app) as client:
            assert client.get("/api/auth/onboarding").status_code == 401

            registered = client.post(
                "/api/auth/register",
                json={"username": "new@example.com", "password": "password123"},
            )
            assert registered.status_code == 200
            assert registered.json()["onboarding_completed"] is False
            assert "dt_token" in registered.cookies

            onboarding = client.get("/api/auth/onboarding")
            assert onboarding.status_code == 200
            assert onboarding.json() == {
                "completed": False,
                "available": True,
                "learner_profile": {},
            }

            saved = client.put(
                "/api/auth/profile/learner-profile",
                json={
                    "grade_level": "本科",
                    "learning_goal": "通过期末考试",
                    "explanation_style": "先例子后原理",
                },
            )
            assert saved.status_code == 200
            assert saved.json()["learner_profile"]["learning_goal"] == "通过期末考试"

            completed = client.post("/api/auth/onboarding/complete")
            assert completed.status_code == 200
            assert completed.json() == {"completed": True}
            assert client.get("/api/auth/onboarding").json()["completed"] is True
            assert client.get("/api/auth/status").json()["onboarding_completed"] is True
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
