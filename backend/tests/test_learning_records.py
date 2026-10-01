import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from teachx.config import get_settings
from teachx.main import app
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository


async def _add_feedback_message(
    repository: SessionRepository,
    *,
    user_id: str,
    session_id: str,
    question: str,
    answer: str,
):
    await repository.ensure_session(
        session_id,
        title="线性代数",
        user_id=user_id,
    )
    user_message = await repository.add_message(
        session_id=session_id,
        role="user",
        content=question,
    )
    return await repository.add_message(
        session_id=session_id,
        role="assistant",
        content=answer,
        parent_message_id=user_message.id,
    )


def test_feedback_links_to_message_and_respects_user_ownership(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "feedback.db")
        await database.initialize()
        repository = SessionRepository(database)
        assistant = await _add_feedback_message(
            repository,
            user_id="user-1",
            session_id="session-1",
            question="什么是特征值？",
            answer="特征值描述线性变换在某个方向上的缩放。",
        )

        record = await repository.upsert_answer_feedback(
            user_id="user-1",
            message_id=assistant.id,
            rating="wrong",
            note="我把特征向量和基向量混淆了。",
        )
        assert record is not None
        assert record["question"] == "什么是特征值？"
        assert record["answer"].startswith("特征值")
        assert record["note"] == "我把特征向量和基向量混淆了。"
        assert record["session_title"] == "线性代数"

        assert (
            await repository.upsert_answer_feedback(
                user_id="user-2",
                message_id=assistant.id,
                rating="helpful",
            )
            is None
        )
        assert await repository.list_answer_feedback(user_id="user-2") == []
        assert await repository.list_answer_feedback(user_id="user-1", rating="wrong")

        assert (
            await repository.delete_answer_feedback(
                user_id="user-2",
                feedback_id=int(record["id"]),
            )
            is False
        )
        assert await repository.delete_answer_feedback(
            user_id="user-1",
            feedback_id=int(record["id"]),
        )
        assert await repository.list_answer_feedback(user_id="user-1") == []

    asyncio.run(scenario())


def test_learning_record_api_upserts_lists_and_deletes(tmp_path: Path) -> None:
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "knowledge_root": settings.knowledge_root,
        "auth_enabled": settings.auth_enabled,
        "auth_secret": settings.auth_secret,
    }
    settings.database_path = tmp_path / "learning-api.db"
    settings.knowledge_root = tmp_path / "knowledge"
    settings.auth_enabled = True
    settings.auth_secret = "learning-test-secret-at-least-32-bytes"
    try:
        with TestClient(app) as client:
            registered = client.post(
                "/api/auth/register",
                json={"username": "learner@example.com", "password": "password123"},
            )
            user_id = str(registered.json()["user_id"])
            repository = client.app.state.container.repository
            assistant = asyncio.run(
                _add_feedback_message(
                    repository,
                    user_id=user_id,
                    session_id="learning-session",
                    question="为什么矩阵乘法不满足交换律？",
                    answer="因为变换的顺序会改变最终结果。",
                )
            )

            created = client.put(
                f"/api/learning/feedback/{assistant.id}",
                json={"rating": "helpful", "note": ""},
            )
            assert created.status_code == 200
            record = created.json()["record"]
            assert record["rating"] == "helpful"

            updated = client.put(
                f"/api/learning/feedback/{assistant.id}",
                json={"rating": "wrong", "note": "我没有区分左乘和右乘。"},
            )
            assert updated.status_code == 200
            assert updated.json()["record"]["id"] == record["id"]
            assert updated.json()["record"]["note"] == "我没有区分左乘和右乘。"

            listed = client.get("/api/learning/records?rating=wrong")
            assert listed.status_code == 200
            assert len(listed.json()["records"]) == 1
            assert listed.json()["records"][0]["question"].startswith("为什么矩阵")

            invalid = client.put(
                f"/api/learning/feedback/{assistant.id}",
                json={"rating": "unknown", "note": ""},
            )
            assert invalid.status_code == 422

            deleted = client.delete(f"/api/learning/records/{record['id']}")
            assert deleted.status_code == 200
            assert client.get("/api/learning/records").json()["records"] == []
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
