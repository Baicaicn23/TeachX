from __future__ import annotations

import json
import time
import uuid
from typing import Any

from teachx.schemas import (
    SessionDetail,
    SessionMessage,
    SessionPreferences,
    SessionSummary,
)
from teachx.storage.database import Database


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class SessionRepository:
    """Persistence interface for conversations and turn history."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_session(self, title: str = "新对话") -> str:
        now = time.time()
        session_id = uuid.uuid4().hex
        preferences = SessionPreferences()
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO sessions (id, title, created_at, updated_at, preferences)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, title, now, now, _json_dumps(preferences.model_dump())),
            )
            await connection.commit()
        return session_id

    async def ensure_session(self, session_id: str | None, title: str = "新对话") -> str:
        if not session_id:
            return await self.create_session(title)
        async with self.database.connect() as connection:
            cursor = await connection.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
            row = await cursor.fetchone()
            if row is None:
                now = time.time()
                preferences = SessionPreferences()
                await connection.execute(
                    """
                    INSERT INTO sessions (id, title, created_at, updated_at, preferences)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, title, now, now, _json_dumps(preferences.model_dump())),
                )
                await connection.commit()
        return session_id

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[SessionSummary]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    s.*,
                    COUNT(m.id) AS message_count,
                    COALESCE((
                        SELECT content FROM messages
                        WHERE session_id = s.id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    ), '') AS last_message
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = await cursor.fetchall()
        return [self._summary_from_row(row) for row in rows]

    async def get_session(self, session_id: str) -> SessionDetail | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    s.*,
                    COUNT(m.id) AS message_count,
                    COALESCE((
                        SELECT content FROM messages
                        WHERE session_id = s.id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    ), '') AS last_message
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                WHERE s.id = ?
                GROUP BY s.id
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            cursor = await connection.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            )
            message_rows = await cursor.fetchall()
        summary = self._summary_from_row(row)
        return SessionDetail(
            **summary.model_dump(),
            messages=[self._message_from_row(item) for item in message_rows],
        )

    async def get_messages(self, session_id: str) -> list[SessionMessage]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
        return [self._message_from_row(row) for row in rows]

    async def add_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        capability: str = "",
        events: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        parent_message_id: int | None = None,
    ) -> SessionMessage:
        now = time.time()
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO messages (
                    session_id, role, content, capability, events,
                    attachments, metadata, parent_message_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    capability,
                    _json_dumps(events or []),
                    _json_dumps(attachments or []),
                    _json_dumps(metadata or {}),
                    parent_message_id,
                    now,
                ),
            )
            message_id = int(cursor.lastrowid)
            await connection.execute(
                (
                    "UPDATE sessions SET updated_at = ?, status = 'idle', "
                    "active_turn_id = '' WHERE id = ?"
                ),
                (now, session_id),
            )
            await connection.commit()
        return SessionMessage(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            capability=capability,
            events=events or [],
            attachments=attachments or [],
            metadata=metadata or {},
            created_at=now,
            parent_message_id=parent_message_id,
        )

    async def rename_session(self, session_id: str, title: str) -> SessionDetail | None:
        now = time.time()
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip() or "新对话", now, session_id),
            )
            await connection.commit()
        return await self.get_session(session_id)

    async def update_reply_language(
        self, session_id: str, language: str | None
    ) -> SessionDetail | None:
        return await self._update_preferences(
            session_id,
            {"reply_language_override": language},
        )

    async def update_organization(
        self, session_id: str, patch: dict[str, Any]
    ) -> SessionDetail | None:
        preferences = {
            "pinned": patch.get("pinned"),
            "archived": patch.get("archived"),
        }
        clean = {key: value for key, value in preferences.items() if value is not None}
        return await self._update_preferences(session_id, clean)

    async def update_branch_selection(
        self, session_id: str, selected_branches: dict[str, int]
    ) -> dict[str, int]:
        await self._update_preferences(
            session_id,
            {"selected_branches": selected_branches},
        )
        return selected_branches

    async def delete_session(self, session_id: str) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await connection.commit()
            return cursor.rowcount > 0

    async def delete_message(self, session_id: str, message_id: int) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "DELETE FROM messages WHERE id = ? AND session_id = ?",
                (message_id, session_id),
            )
            await connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (time.time(), session_id),
            )
            await connection.commit()
            return cursor.rowcount > 0

    async def message_events(self, session_id: str, message_id: int) -> list[dict[str, Any]]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT events FROM messages WHERE id = ? AND session_id = ?",
                (message_id, session_id),
            )
            row = await cursor.fetchone()
        return _json_loads(row["events"], []) if row else []

    async def search_sessions(
        self, query: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        pattern = f"%{query}%"
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT DISTINCT s.*
                FROM sessions s
                JOIN messages m ON m.session_id = s.id
                WHERE m.content LIKE ?
                ORDER BY s.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (pattern, limit, offset),
            )
            rows = await cursor.fetchall()
            cursor = await connection.execute(
                """
                SELECT COUNT(DISTINCT s.id)
                FROM sessions s
                JOIN messages m ON m.session_id = s.id
                WHERE m.content LIKE ?
                """,
                (pattern,),
            )
            total_row = await cursor.fetchone()
        results = []
        for row in rows:
            summary = self._summary_from_row(row).model_dump()
            summary.update(
                {
                    "match_excerpt": query,
                    "match_role": None,
                    "match_message_id": None,
                    "match_created_at": None,
                }
            )
            results.append(summary)
        return results, int(total_row[0] if total_row else 0)

    async def _update_preferences(
        self, session_id: str, patch: dict[str, Any]
    ) -> SessionDetail | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT preferences FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            preferences = _json_loads(row["preferences"], {})
            preferences.update({key: value for key, value in patch.items() if value is not None})
            await connection.execute(
                "UPDATE sessions SET preferences = ?, updated_at = ? WHERE id = ?",
                (_json_dumps(preferences), time.time(), session_id),
            )
            await connection.commit()
        return await self.get_session(session_id)

    @staticmethod
    def _summary_from_row(row: Any) -> SessionSummary:
        preferences = SessionPreferences.model_validate(_json_loads(row["preferences"], {}))
        return SessionSummary(
            id=row["id"],
            session_id=row["id"],
            title=row["title"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            message_count=int(row["message_count"]) if "message_count" in row.keys() else 0,
            last_message=str(row["last_message"] or "") if "last_message" in row.keys() else "",
            status=str(row["status"] or "idle"),
            active_turn_id=str(row["active_turn_id"] or ""),
            preferences=preferences,
        )

    @staticmethod
    def _message_from_row(row: Any) -> SessionMessage:
        return SessionMessage(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            capability=str(row["capability"] or ""),
            events=_json_loads(row["events"], []),
            attachments=_json_loads(row["attachments"], []),
            metadata=_json_loads(row["metadata"], {}),
            created_at=float(row["created_at"]),
            parent_message_id=row["parent_message_id"],
        )
