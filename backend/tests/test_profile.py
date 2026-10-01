import base64
from pathlib import Path

from fastapi.testclient import TestClient

from teachx.config import get_settings
from teachx.main import app

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_profile_avatar_and_learner_profile(tmp_path: Path) -> None:
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "knowledge_root": settings.knowledge_root,
        "avatar_root": settings.avatar_root,
        "auth_enabled": settings.auth_enabled,
        "auth_secret": settings.auth_secret,
    }
    settings.database_path = tmp_path / "profile.db"
    settings.knowledge_root = tmp_path / "knowledge"
    settings.avatar_root = tmp_path / "avatars"
    settings.auth_enabled = True
    settings.auth_secret = "profile-test-secret-that-is-at-least-32-bytes"
    try:
        with TestClient(app) as client:
            client.post(
                "/api/auth/register",
                json={"username": "learner@example.com", "password": "password123"},
            )
            client.post(
                "/api/auth/login",
                json={"username": "learner@example.com", "password": "password123"},
            )

            profile = client.get("/api/auth/profile").json()
            assert profile["username"] == "learner@example.com"
            assert profile["avatar"] == ""

            marker = client.put(
                "/api/auth/profile",
                json={"avatar": "icon:book:blue"},
            )
            assert marker.status_code == 200
            assert marker.json()["avatar"] == "icon:book:blue"

            learner = client.put(
                "/api/auth/profile/learner-profile",
                json={
                    "age": 19,
                    "grade_level": "大一",
                    "learning_goal": "掌握线性代数",
                    "learning_goal_progress": 40,
                    "language": "zh",
                    "explanation_style": "先例子后原理",
                },
            )
            assert learner.status_code == 200
            assert learner.json()["learner_profile"]["age"] == 19
            assert learner.json()["learner_profile"]["learning_goal"] == "掌握线性代数"
            assert learner.json()["learner_profile"]["learning_goal_progress"] == 40

            completed = client.put(
                "/api/auth/profile/learner-profile",
                json={
                    "grade_level": "大一",
                    "learning_goal": "掌握线性代数",
                    "learning_goal_progress": 100,
                    "learning_goal_status": "completed",
                },
            )
            assert completed.status_code == 200
            assert completed.json()["learner_profile"]["learning_goal_status"] == "completed"

            reactivated = client.put(
                "/api/auth/profile/learner-profile",
                json={
                    "grade_level": "大一",
                    "learning_goal": "掌握概率论",
                    "learning_goal_progress": 0,
                },
            )
            assert reactivated.status_code == 200
            assert reactivated.json()["learner_profile"]["learning_goal_status"] == "active"
            assert (
                client.get("/api/auth/profile/learner-profile").json()["learner_profile"][
                    "grade_level"
                ]
                == "大一"
            )

            uploaded = client.put(
                "/api/auth/profile/avatar",
                files={"file": ("avatar.png", PNG_1X1, "image/png")},
            )
            assert uploaded.status_code == 200
            user_id = profile["id"]
            assert uploaded.json()["avatar"].startswith("img:")
            image = client.get(f"/api/auth/avatar/{user_id}")
            assert image.status_code == 200
            assert image.content.startswith(b"\x89PNG")

            disabled = client.put(
                "/api/auth/profile",
                json={"personalization_enabled": False},
            )
            assert disabled.status_code == 200
            assert disabled.json()["personalization_enabled"] is False
            assert client.get("/api/auth/profile").json()["personalization_enabled"] is False

            deleted = client.delete("/api/auth/profile/avatar")
            assert deleted.status_code == 200
            assert client.get(f"/api/auth/avatar/{user_id}").status_code == 404
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
