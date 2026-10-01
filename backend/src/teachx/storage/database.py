from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    active_turn_id TEXT NOT NULL DEFAULT '',
    preferences TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    capability TEXT NOT NULL DEFAULT '',
    events TEXT NOT NULL DEFAULT '[]',
    attachments TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    parent_message_id INTEGER NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS answer_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    rating TEXT NOT NULL CHECK(rating IN ('helpful', 'unclear', 'wrong')),
    note TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(user_id, message_id)
);

CREATE TABLE IF NOT EXISTS practice_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    knowledge_base TEXT NOT NULL REFERENCES knowledge_bases(name) ON DELETE CASCADE,
    source_chunk_id INTEGER REFERENCES knowledge_chunks(id) ON DELETE SET NULL,
    prompt TEXT NOT NULL,
    source_excerpt TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    UNIQUE(user_id, source_chunk_id)
);

CREATE TABLE IF NOT EXISTS practice_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES practice_questions(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    answer TEXT NOT NULL,
    rating TEXT NOT NULL CHECK(rating IN ('again', 'hard', 'good', 'easy')),
    interval_days INTEGER NOT NULL,
    due_at REAL NOT NULL,
    mastery_score INTEGER NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS practice_progress (
    user_id TEXT NOT NULL,
    knowledge_base TEXT NOT NULL REFERENCES knowledge_bases(name) ON DELETE CASCADE,
    mastery_score INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, knowledge_base)
);

CREATE INDEX IF NOT EXISTS idx_messages_session_created
ON messages(session_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_answer_feedback_user_updated
ON answer_feedback(user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_answer_feedback_session
ON answer_feedback(session_id, message_id);

CREATE INDEX IF NOT EXISTS idx_practice_questions_user
ON practice_questions(user_id, knowledge_base, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_practice_attempts_question
ON practice_attempts(question_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_practice_attempts_due
ON practice_attempts(user_id, due_at);

CREATE INDEX IF NOT EXISTS idx_sessions_updated
ON sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    avatar TEXT NOT NULL DEFAULT '',
    learner_profile TEXT NOT NULL DEFAULT '{}',
    personalization_enabled INTEGER NOT NULL DEFAULT 1,
    onboarding_completed INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_login_at REAL NULL
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'sqlite-fts',
    owner_id TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_name TEXT NOT NULL REFERENCES knowledge_bases(name) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL DEFAULT '',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(kb_name, relative_path)
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    kb_name TEXT NOT NULL REFERENCES knowledge_bases(name) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    character_count INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb
ON knowledge_documents(kb_name, relative_path);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_kb
ON knowledge_chunks(kb_name, document_id, chunk_index);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
USING fts5(content, chunk_id UNINDEXED, kb_name UNINDEXED, tokenize='unicode61');

CREATE TABLE IF NOT EXISTS knowledge_chunk_vectors (
    chunk_id INTEGER PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_model
ON knowledge_chunk_vectors(model);
"""


class Database:
    """Small SQLite gateway used by the session repository."""

    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as connection:
            await connection.executescript(SCHEMA)
            await self._ensure_column(
                connection,
                table="sessions",
                column="user_id",
                definition="TEXT NOT NULL DEFAULT ''",
            )
            await self._ensure_column(
                connection,
                table="knowledge_bases",
                column="owner_id",
                definition="TEXT NOT NULL DEFAULT ''",
            )
            await self._ensure_column(
                connection,
                table="users",
                column="avatar",
                definition="TEXT NOT NULL DEFAULT ''",
            )
            await self._ensure_column(
                connection,
                table="users",
                column="learner_profile",
                definition="TEXT NOT NULL DEFAULT '{}'",
            )
            await self._ensure_column(
                connection,
                table="users",
                column="personalization_enabled",
                definition="INTEGER NOT NULL DEFAULT 1",
            )
            # Existing accounts predate first-run onboarding. Defaulting the
            # migration to 1 prevents them from being forced through it, while
            # new registrations explicitly insert 0.
            await self._ensure_column(
                connection,
                table="users",
                column="onboarding_completed",
                definition="INTEGER NOT NULL DEFAULT 1",
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_updated "
                "ON sessions(user_id, updated_at DESC)"
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_owner "
                "ON knowledge_bases(owner_id, updated_at DESC)"
            )
            await connection.commit()

    @staticmethod
    async def _ensure_column(
        connection: aiosqlite.Connection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        cursor = await connection.execute(f"PRAGMA table_info({table})")
        columns = {str(row[1]) for row in await cursor.fetchall()}
        if column not in columns:
            await connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            await connection.close()
