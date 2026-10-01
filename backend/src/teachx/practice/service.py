from __future__ import annotations

import time
from typing import Any

from teachx.storage.database import Database

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

    def __init__(self, database: Database) -> None:
        self.database = database

    async def generate(
        self,
        *,
        user_id: str,
        knowledge_base: str,
        count: int,
    ) -> list[dict[str, Any]]:
        if count < 1 or count > 10:
            raise PracticeError("每次可生成 1 到 10 道练习题")
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
                prompt = (
                    "请用自己的话解释下面这段资料。回答时说明核心概念、"
                    "关键关系和一个具体例子。\n\n"
                    f"资料摘录：\n「{excerpt}」"
                )
                cursor = await connection.execute(
                    """
                    INSERT INTO practice_questions (
                        user_id, knowledge_base, source_chunk_id,
                        prompt, source_excerpt, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        knowledge_base,
                        int(row["chunk_id"]),
                        prompt,
                        excerpt,
                        now,
                    ),
                )
                created.append(
                    {
                        "id": int(cursor.lastrowid),
                        "knowledge_base": knowledge_base,
                        "prompt": prompt,
                        "source_excerpt": excerpt,
                        "source_document": str(row["filename"] or ""),
                        "created_at": now,
                        "rating": None,
                        "due_at": None,
                        "answer": "",
                        "mastery_score": 0,
                        "attempt_count": 0,
                    }
                )
            await connection.commit()
        return created

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
        "created_at": float(row["created_at"]),
        "mastery_score": int(row["mastery_score"]),
        "rating": str(row["rating"]) if row["rating"] else None,
        "answer": str(row["answer"] or ""),
        "due_at": float(row["due_at"]) if row["due_at"] is not None else None,
        "attempt_count": int(row["attempt_count"]),
    }
