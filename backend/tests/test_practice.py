import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from teachx.config import get_settings
from teachx.knowledge.service import KnowledgeService
from teachx.main import app
from teachx.practice.service import PracticeError, PracticeService
from teachx.providers.base import LLMUsage
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository
from teachx.usage.service import UsageService


class _StubProvider:
    """名字不是 mock 的假 Provider,用来覆盖"模型写题"这条路径。"""

    name = "stub"
    model = "stub-model"

    def __init__(self, content: str) -> None:
        self.content = content
        self.usage = LLMUsage(prompt_tokens=11, completion_tokens=22, total_tokens=33)

    async def complete(self, messages, tools, *, max_output_tokens=None):  # noqa: ANN001
        return SimpleNamespace(content=self.content, usage=self.usage)


async def _seed_mistake(
    database: Database,
    *,
    user_id: str,
    subject: str,
    note: str,
    question: str = "什么是特征值？",
    answer: str = "特征值描述线性变换在某个方向上的缩放倍数。",
    session_id: str,
) -> int:
    """造一条错题,返回它的 id。

    ``subject`` 写进助手消息的元数据里——真实的错题就是这样继承当轮所选
    知识库的(见 runtime/engine.py 的 assistant_metadata)。
    """

    repository = SessionRepository(database)
    await repository.ensure_session(session_id, title=subject or "无学科", user_id=user_id)
    user_message = await repository.add_message(
        session_id=session_id, role="user", content=question
    )
    assistant = await repository.add_message(
        session_id=session_id,
        role="assistant",
        content=answer,
        parent_message_id=user_message.id,
        metadata={"knowledge_bases": [subject] if subject else []},
    )
    record = await repository.upsert_answer_feedback(
        user_id=user_id,
        message_id=assistant.id,
        rating="wrong",
        note=note,
    )
    assert record is not None
    return int(record["id"])


async def _seed_practice_knowledge(database: Database, root: Path) -> None:
    knowledge = KnowledgeService(database, root)
    await knowledge.create_base("学习资料", owner_id="user-1")
    await knowledge.add_document(
        "学习资料",
        "memory.txt",
        (
            "内存和硬盘承担不同的数据保存职责。内存用于程序运行时快速访问，"
            "断电后内容通常消失；硬盘用于长期保存数据，速度较慢但可以持久化。"
        ).encode(),
        owner_id="user-1",
    )


def test_practice_generation_review_and_ownership(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "practice.db")
        await database.initialize()
        await _seed_practice_knowledge(database, tmp_path / "knowledge")
        service = PracticeService(database)

        questions = await service.generate(
            user_id="user-1",
            knowledge_base="学习资料",
            count=3,
        )
        assert len(questions) >= 1
        assert "内存和硬盘" in questions[0]["prompt"]

        queue = await service.queue(user_id="user-1")
        assert len(queue) == len(questions)
        assert await service.queue(user_id="user-2") == []

        result = await service.answer(
            user_id="user-1",
            question_id=int(questions[0]["id"]),
            answer="内存负责运行时快速访问，硬盘负责长期持久化。",
            rating="good",
        )
        assert result["rating"] == "good"
        assert result["interval_days"] == 4
        assert result["mastery_score"] == 8

        summary = await service.summary(user_id="user-1")
        assert summary["question_count"] == len(questions)
        assert summary["attempt_count"] == 1
        assert summary["next_due_at"] is not None
        assert summary["progress"][0]["mastery_score"] == 8

        try:
            await service.answer(
                user_id="user-2",
                question_id=int(questions[0]["id"]),
                answer="不属于我的回答",
                rating="easy",
            )
        except PracticeError:
            pass
        else:
            raise AssertionError("another user must not answer this question")

        assert (
            await service.delete_question(
                user_id="user-2",
                question_id=int(questions[0]["id"]),
            )
            is False
        )
        assert await service.delete_question(
            user_id="user-1",
            question_id=int(questions[0]["id"]),
        )

    asyncio.run(scenario())


def test_practice_api_generates_and_reviews_questions(tmp_path: Path) -> None:
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "knowledge_root": settings.knowledge_root,
        "auth_enabled": settings.auth_enabled,
        "auth_secret": settings.auth_secret,
    }
    settings.database_path = tmp_path / "practice-api.db"
    settings.knowledge_root = tmp_path / "knowledge"
    settings.auth_enabled = True
    settings.auth_secret = "practice-test-secret-at-least-32-bytes"
    try:
        with TestClient(app) as client:
            registered = client.post(
                "/api/auth/register",
                json={"username": "practice@example.com", "password": "password123"},
            )
            user_id = str(registered.json()["user_id"])
            container = client.app.state.container

            async def seed() -> None:
                await container.knowledge.create_base("练习资料", owner_id=user_id)
                await container.knowledge.add_document(
                    "练习资料",
                    "loop.txt",
                    "循环把同一段逻辑重复执行，直到满足停止条件。".encode(),
                    owner_id=user_id,
                )

            asyncio.run(seed())

            generated = client.post(
                "/api/practice/generate",
                json={"knowledge_base": "练习资料", "count": 2},
            )
            assert generated.status_code == 200
            question = generated.json()["questions"][0]

            summary = client.get("/api/practice/summary")
            assert summary.status_code == 200
            assert summary.json()["question_count"] >= 1

            answered = client.post(
                f"/api/practice/questions/{question['id']}/answer",
                json={"answer": "循环会重复执行逻辑。", "rating": "hard"},
            )
            assert answered.status_code == 200
            assert answered.json()["interval_days"] == 2

            invalid = client.post(
                f"/api/practice/questions/{question['id']}/answer",
                json={"answer": "答案", "rating": "perfect"},
            )
            assert invalid.status_code == 422

            deleted = client.delete(f"/api/practice/questions/{question['id']}")
            assert deleted.status_code == 200
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def test_practice_from_mistakes_files_question_under_its_subject(tmp_path: Path) -> None:
    """从错题出题:新题挂到误区所属学科下,且同一条误区只出一次。"""

    async def scenario() -> None:
        database = Database(tmp_path / "mistakes.db")
        await database.initialize()
        knowledge = KnowledgeService(database, tmp_path / "knowledge")
        # 练习题在数据库里必须挂在某个知识库下,所以错题的学科要真实存在。
        await knowledge.create_base("线性代数", owner_id="user-1")
        await _seed_mistake(
            database,
            user_id="user-1",
            subject="线性代数",
            note="我把特征向量和基向量混淆了。",
            session_id="session-1",
        )
        service = PracticeService(database)

        questions = await service.generate(user_id="user-1", source="mistakes", count=3)

        assert len(questions) == 1
        question = questions[0]
        assert question["knowledge_base"] == "线性代数"
        assert question["source"] == "mistake"
        # 没有传 provider → 模板出题,不花钱。
        assert question["generator"] == "template"
        assert "我把特征向量和基向量混淆了。" in question["prompt"]
        assert "什么是特征值？" in question["prompt"]

        try:
            await service.generate(user_id="user-1", source="mistakes", count=3)
        except PracticeError:
            pass
        else:
            raise AssertionError("同一条误区不该重复出题")

    asyncio.run(scenario())


def test_practice_from_mistakes_skips_other_users_and_subjectless(tmp_path: Path) -> None:
    """跨用户隔离:别人的错题、以及没有学科的错题都不参与出题。"""

    async def scenario() -> None:
        database = Database(tmp_path / "mistakes-scope.db")
        await database.initialize()
        knowledge = KnowledgeService(database, tmp_path / "knowledge")
        await knowledge.create_base("线性代数", owner_id="user-1")
        await _seed_mistake(
            database,
            user_id="user-2",
            subject="线性代数",
            note="别人的误区",
            session_id="session-user-2",
        )
        await _seed_mistake(
            database,
            user_id="user-1",
            subject="",  # 聊天时没选知识库 → 没有学科
            note="这条没有学科",
            session_id="session-no-subject",
        )
        service = PracticeService(database)

        try:
            await service.generate(user_id="user-1", source="mistakes", count=3)
        except PracticeError as exc:
            assert "错题" in str(exc)
        else:
            raise AssertionError("只有别人的错题和无学科错题时不该出题")

    asyncio.run(scenario())


def test_practice_from_mistakes_uses_model_and_records_usage(tmp_path: Path) -> None:
    """给了模型就让模型写题,并把这次调用的用量记进账单。"""

    async def scenario() -> None:
        database = Database(tmp_path / "mistakes-model.db")
        await database.initialize()
        knowledge = KnowledgeService(database, tmp_path / "knowledge")
        await knowledge.create_base("线性代数", owner_id="user-1")
        await _seed_mistake(
            database,
            user_id="user-1",
            subject="线性代数",
            note="我把特征向量和基向量混淆了。",
            session_id="session-1",
        )
        usage = UsageService(database)
        service = PracticeService(database, usage)
        provider = _StubProvider('{"question": "给出一个 2×2 矩阵，求它的特征值。"}')

        questions = await service.generate(
            user_id="user-1", source="mistakes", count=3, provider=provider
        )

        assert questions[0]["generator"] == "model"
        assert questions[0]["prompt"] == "给出一个 2×2 矩阵，求它的特征值。"

        async with database.connect() as connection:
            cursor = await connection.execute(
                "SELECT call_kind, total_tokens FROM llm_usage WHERE user_id = ?",
                ("user-1",),
            )
            rows = await cursor.fetchall()
        assert [(row["call_kind"], row["total_tokens"]) for row in rows] == [
            ("practice_question", 33)
        ]

    asyncio.run(scenario())


def test_practice_rejects_unknown_source(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "source.db")
        await database.initialize()
        service = PracticeService(database)
        try:
            await service.generate(user_id="user-1", source="magic", count=1)
        except PracticeError as exc:
            assert "来源" in str(exc)
        else:
            raise AssertionError("未知出题来源应当报错")

    asyncio.run(scenario())
