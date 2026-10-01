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

CREATE INDEX IF NOT EXISTS idx_messages_session_created
ON messages(session_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_sessions_updated
ON sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'sqlite-fts',
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
            await connection.commit()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            await connection.close()
