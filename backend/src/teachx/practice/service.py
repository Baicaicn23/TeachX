from __future__ import annotations

import time
from typing import Any

from teachx.practice.generator import (
    build_excerpt_instruction,
    build_mistake_instruction,
    template_excerpt_question,
    template_mistake_question,
    write_question,
)
from teachx.storage.database import Database
from teachx.usage.service import UsageService

# 出题来源:从知识库片段出题(原有),或从学生自己记过的误区出题(新增)。
SOURCE_KNOWLEDGE_BASE = "knowledge_base"
SOURCE_MISTAKES = "mistakes"

_RATING_DELTA = {
    "again": -10,
    "hard": 0,
    "good": 8,
    "easy": 12,
}
_RATING_INTERVAL_DAYS = {
    "again": 1,
    "hard": 2,
    "good": 4,
    "easy": 7,
}


class PracticeError(ValueError):
    pass


class PracticeService:
    """Create and review practice questions from the learner's knowledge bases."""

    def __init__(self, database: Database, usage: UsageService | None = None) -> None:
        self.database = database
        self.usage = usage

    async def generate(
        self,
        *,
        user_id: str,
        knowledge_base: str = "",
        count: int,
        source: str = SOURCE_KNOWLEDGE_BASE,
        provider: Any | None = None,
    ) -> list[dict[str, Any]]:
        """出练习题。

        ``source`` 决定题目从哪里来:知识库片段(原有)或学生记过的误区(新增)。
        ``provider`` 是当前用户的模型,用来"写"一道新题;为 None(或 Mock)时
        退回模板出题——所以这个参数是可选的,出题不会因为没有模型而失败。
        """

        if count < 1 or count > 10:
            raise PracticeError("每次可生成 1 到 10 道练习题")
        if source == SOURCE_MISTAKES:
            return await self._generate_from_mistakes(
                user_id=user_id,
                knowledge_base=knowledge_base,
                count=count,
                provider=provider,
            )
        if source != SOURCE_KNOWLEDGE_BASE:
            raise PracticeError(f"不支持的出题来源：{source}")
        return await self._generate_from_knowledge_base(
            user_id=user_id,
            knowledge_base=knowledge_base,
            count=count,
            provider=provider,
        )

    async def _generate_from_knowledge_base(
        self,
        *,
        user_id: str,
        knowledge_base: str,
        count: int,
        provider: Any | None,
    ) -> list[dict[str, Any]]:
        if not knowledge_base:
            raise PracticeError("请先选择知识库")
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT name FROM knowledge_bases
                WHERE name = ? AND owner_id = ?
                """,
                (knowledge_base, user_id),
            )
            if await cursor.fetchone() is None:
                raise PracticeError("知识库不存在或无权访问")

            cursor = await connection.execute(
                """
                SELECT
                    c.id AS chunk_id,
                    c.content,
                    d.filename
                FROM knowledge_chunks c
                JOIN knowledge_documents d ON d.id = c.document_id
                WHERE c.kb_name = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM practice_questions q
                      WHERE q.user_id = ? AND q.source_chunk_id = c.id
                  )
                ORDER BY c.id ASC
                LIMIT ?
                """,
                (knowledge_base, user_id, count),
            )
            rows = await cursor.fetchall()
            if not rows:
                raise PracticeError("这个知识库没有可用于生成练习的新资料片段")

            now = time.time()
            created: list[dict[str, Any]] = []
            for row in rows:
                excerpt = _normalize_excerpt(str(row["content"]))
                written = await write_question(
                    provider,
                    build_excerpt_instruction(excerpt),
                    fallback=template_excerpt_question(excerpt),
                )
                await self._record_question_usage(
                    user_id=user_id, provider=provider, written=written
                )
                created.append(
                    await self._insert_question(
                        connection,
                        user_id=user_id,
                        knowledge_base=knowledge_base,
                        source_chunk_id=int(row["chunk_id"]),
                        source_feedback_id=None,
                        prompt=written.prompt,
                        excerpt=excerpt,
                        source_document=str(row["filename"] or ""),
                        generator=written.generator,
                        now=now,
                    )
                )
            await connection.commit()
        return created

    async def _generate_from_mistakes(
        self,
        *,
        user_id: str,
        knowledge_base: str,
        count: int,
        provider: Any | None,
    ) -> list[dict[str, Any]]:
        """从学生自己记过的误区出题。

        只取有学科标签、且还没出过题的误区:练习题在数据库里必须挂在某个
        知识库下(题目表对知识库是必填的),所以没有学科的误区出不了题。
        切到"从错题出题"时未选知识库,就是"所有学科的错题都要"。
        """

        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    f.id,
                    f.knowledge_base,
                    f.note,
                    COALESCE(parent.content, '') AS question
                FROM answer_feedback f
                JOIN messages assistant ON assistant.id = f.message_id
                LEFT JOIN messages parent ON parent.id = assistant.parent_message_id
                WHERE f.user_id = ?
                  AND f.rating = 'wrong'
                  AND f.knowledge_base != ''
                  AND (? = '' OR f.knowledge_base = ?)
                  AND NOT EXISTS (
                      SELECT 1 FROM practice_questions q
                      WHERE q.user_id = f.user_id AND q.source_feedback_id = f.id
                  )
                ORDER BY f.updated_at DESC, f.id DESC
                LIMIT ?
                """,
                (user_id, knowledge_base, knowledge_base, count),
            )
            rows = await cursor.fetchall()
            if not rows:
                raise PracticeError(
                    "还没有可用于出题的新错题：请先在回答下方点“记录我的误区”写下你的误区"
                )

            now = time.time()
            created: list[dict[str, Any]] = []
            for row in rows:
                subject = str(row["knowledge_base"])
                note = str(row["note"] or "")
                asked = str(row["question"] or "")
                excerpt = _normalize_excerpt(f"{asked} {note}".strip())
                written = await write_question(
                    provider,
                    build_mistake_instruction(
                        subject=subject, question=asked, note=note
                    ),
                    fallback=template_mistake_question(question=asked, note=note),
                )
                await self._record_question_usage(
                    user_id=user_id, provider=provider, written=written
                )
                created.append(
                    await self._insert_question(
                        connection,
                        user_id=user_id,
                        knowledge_base=subject,
                        source_chunk_id=None,
                        source_feedback_id=int(row["id"]),
                        prompt=written.prompt,
                        excerpt=excerpt,
                        source_document="",
                        generator=written.generator,
                        now=now,
                    )
                )
            await connection.commit()
        return created

    async def _insert_question(
        self,
        connection: Any,
        *,
        user_id: str,
        knowledge_base: str,
        source_chunk_id: int | None,
        source_feedback_id: int | None,
        prompt: str,
        excerpt: str,
        source_document: str,
        generator: str,
        now: float,
    ) -> dict[str, Any]:
        cursor = await connection.execute(
            """
            INSERT INTO practice_questions (
                user_id, knowledge_base, source_chunk_id, source_feedback_id,
                prompt, source_excerpt, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                knowledge_base,
                source_chunk_id,
                source_feedback_id,
                prompt,
                excerpt,
                now,
            ),
        )
        return {
            "id": int(cursor.lastrowid),
            "knowledge_base": knowledge_base,
            "prompt": prompt,
            "source_excerpt": excerpt,
            "source_document": source_document,
            "source": "mistake" if source_feedback_id is not None else "knowledge_base",
            "generator": generator,
            "created_at": now,
            "rating": None,
            "due_at": None,
            "answer": "",
            "mastery_score": 0,
            "attempt_count": 0,
        }

    async def _record_question_usage(
        self,
        *,
        user_id: str,
        provider: Any | None,
        written: Any,
    ) -> None:
        """把"模型写题"这一次调用的用量记进账单(模板出题不计)。

        出题不属于任何会话,所以 session_id/turn_id 留空。记账失败不能影响
        出题——题目已经写好了,账目问题不该让用户拿不到题。
        """

        if self.usage is None or provider is None or written.usage is None:
            return
        name = str(getattr(provider, "name", ""))
        try:
            await self.usage.record_call(
                user_id=user_id,
                session_id="",
                turn_id="",
                call_kind="practice_question",
                provider=name,
                model=str(getattr(provider, "model", name)),
                usage=written.usage,
                billable=True,
            )
        except Exception:  # noqa: BLE001 — 记账失败不影响出题
            return

    async def queue(
        self,
        *,
        user_id: str,
        knowledge_base: str = "",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 50:
            raise PracticeError("练习题数量必须在 1 到 50 之间")
        now = time.time()
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    q.id,
                    q.knowledge_base,
                    q.prompt,
                    q.source_excerpt,
                    q.source_feedback_id,
                    q.created_at,
                    COALESCE(p.mastery_score, 0) AS mastery_score,
                    a.rating,
                    a.answer,
                    a.due_at,
                    a.created_at AS attempted_at,
                    COALESCE((
                        SELECT COUNT(*) FROM practice_attempts history
                        WHERE history.question_id = q.id
                    ), 0) AS attempt_count
                FROM practice_questions q
                LEFT JOIN practice_progress p
                  ON p.user_id = q.user_id AND p.knowledge_base = q.knowledge_base
                LEFT JOIN practice_attempts a
                  ON a.id = (
                      SELECT latest.id FROM practice_attempts latest
                      WHERE latest.question_id = q.id
                      ORDER BY latest.created_at DESC, latest.id DESC
                      LIMIT 1
                  )
                WHERE q.user_id = ?
                  AND (? = '' OR q.knowledge_base = ?)
                  AND (a.due_at IS NULL OR a.due_at <= ?)
                ORDER BY
                    CASE WHEN a.due_at IS NULL THEN 0 ELSE 1 END,
                    a.due_at ASC,
                    q.created_at ASC,
                    q.id ASC
                LIMIT ?
                """,
                (user_id, knowledge_base, knowledge_base, now, limit),
            )
            rows = await cursor.fetchall()
        return [_question_from_row(row) for row in rows]

    async def answer(
        self,
        *,
        user_id: str,
        question_id: int,
        answer: str,
        rating: str,
    ) -> dict[str, Any]:
        if rating not in _RATING_DELTA:
            raise PracticeError("不支持的复习评分")
        clean_answer = answer.strip()
        if not clean_answer:
            raise PracticeError("请先写下你的回答")

        now = time.time()
        interval_days = _RATING_INTERVAL_DAYS[rating]
        due_at = now + interval_days * 24 * 60 * 60
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT id, knowledge_base FROM practice_questions
                WHERE id = ? AND user_id = ?
                """,
                (question_id, user_id),
            )
            question = await cursor.fetchone()
            if question is None:
                raise PracticeError("练习题不存在或无权访问")

            knowledge_base = str(question["knowledge_base"])
            cursor = await connection.execute(
                """
                SELECT mastery_score FROM practice_progress
                WHERE user_id = ? AND knowledge_base = ?
                """,
                (user_id, knowledge_base),
            )
            progress = await cursor.fetchone()
            current_score = int(progress["mastery_score"]) if progress else 0
            mastery_score = max(
                0,
                min(100, current_score + _RATING_DELTA[rating]),
            )

            await connection.execute(
                """
                INSERT INTO practice_attempts (
                    question_id, user_id, answer, rating, interval_days,
                    due_at, mastery_score, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    user_id,
                    clean_answer[:5000],
                    rating,
                    interval_days,
                    due_at,
                    mastery_score,
                    now,
                ),
            )
            await connection.execute(
                """
                INSERT INTO practice_progress (
                    user_id, knowledge_base, mastery_score,
                    attempt_count, updated_at
                )
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(user_id, knowledge_base) DO UPDATE SET
                    mastery_score = excluded.mastery_score,
                    attempt_count = practice_progress.attempt_count + 1,
                    updated_at = excluded.updated_at
                """,
                (user_id, knowledge_base, mastery_score, now),
            )
            await connection.commit()

        return {
            "question_id": question_id,
            "rating": rating,
            "interval_days": interval_days,
            "due_at": due_at,
            "mastery_score": mastery_score,
        }

    async def summary(self, *, user_id: str) -> dict[str, Any]:
        now = time.time()
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT COUNT(*) AS question_count
                FROM practice_questions
                WHERE user_id = ?
                """,
                (user_id,),
            )
            question_row = await cursor.fetchone()
            cursor = await connection.execute(
                """
                SELECT
                    COALESCE(SUM(
                        CASE WHEN a.due_at IS NULL OR a.due_at <= ? THEN 1 ELSE 0 END
                    ), 0) AS due_count,
                    MIN(
                        CASE WHEN a.due_at > ? THEN a.due_at END
                    ) AS next_due_at
                FROM practice_questions q
                LEFT JOIN practice_attempts a
                  ON a.id = (
                      SELECT latest.id FROM practice_attempts latest
                      WHERE latest.question_id = q.id
                      ORDER BY latest.created_at DESC, latest.id DESC
                      LIMIT 1
                  )
                WHERE q.user_id = ?
                """,
                (now, now, user_id),
            )
            due_row = await cursor.fetchone()
            cursor = await connection.execute(
                """
                SELECT COALESCE(SUM(attempt_count), 0) AS attempt_count
                FROM practice_progress
                WHERE user_id = ?
                """,
                (user_id,),
            )
            attempt_row = await cursor.fetchone()
            cursor = await connection.execute(
                """
                SELECT knowledge_base, mastery_score, attempt_count, updated_at
                FROM practice_progress
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            )
            progress_rows = await cursor.fetchall()
        return {
            "question_count": int(question_row["question_count"] if question_row else 0),
            "due_count": int(due_row["due_count"] if due_row else 0),
            "next_due_at": (
                float(due_row["next_due_at"])
                if due_row and due_row["next_due_at"] is not None
                else None
            ),
            "attempt_count": int(attempt_row["attempt_count"] if attempt_row else 0),
            "progress": [
                {
                    "knowledge_base": str(row["knowledge_base"]),
                    "mastery_score": int(row["mastery_score"]),
                    "attempt_count": int(row["attempt_count"]),
                    "updated_at": float(row["updated_at"]),
                }
                for row in progress_rows
            ],
        }

    async def delete_question(self, *, user_id: str, question_id: int) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "DELETE FROM practice_questions WHERE id = ? AND user_id = ?",
                (question_id, user_id),
            )
            await connection.commit()
            return cursor.rowcount > 0


def _normalize_excerpt(value: str) -> str:
    clean = " ".join(value.split())
    if len(clean) <= 500:
        return clean
    return f"{clean[:500]}…"


def _question_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "knowledge_base": str(row["knowledge_base"]),
        "prompt": str(row["prompt"]),
        "source_excerpt": str(row["source_excerpt"] or ""),
        "source": "mistake" if row["source_feedback_id"] is not None else "knowledge_base",
        "created_at": float(row["created_at"]),
        "mastery_score": int(row["mastery_score"]),
        "rating": str(row["rating"]) if row["rating"] else None,
        "answer": str(row["answer"] or ""),
        "due_at": float(row["due_at"]) if row["due_at"] is not None else None,
        "attempt_count": int(row["attempt_count"]),
    }
