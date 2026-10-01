from __future__ import annotations

import json
import logging
import math
import mimetypes
import re
import time
from pathlib import Path, PurePosixPath
from typing import Any

from teachx.knowledge.chunker import TextChunker
from teachx.knowledge.embeddings import BaseEmbeddingProvider
from teachx.knowledge.extractors import extract_text
from teachx.knowledge.models import IngestResult, KnowledgeBaseRecord, SearchHit
from teachx.storage.database import Database

logger = logging.getLogger(__name__)


class KnowledgeError(ValueError):
    pass


class KnowledgeService:
    """Own document ingestion, storage, indexing, and retrieval."""

    def __init__(
        self,
        database: Database,
        root: Path,
        *,
        max_file_bytes: int = 20 * 1024 * 1024,
        chunker: TextChunker | None = None,
        embedder: BaseEmbeddingProvider | None = None,
    ) -> None:
        self.database = database
        self.root = root
        self.max_file_bytes = max_file_bytes
        self.chunker = chunker or TextChunker()
        self.embedder = embedder

    async def create_base(
        self,
        name: str,
        description: str = "",
        provider: str = "sqlite-fts",
    ) -> KnowledgeBaseRecord:
        name = self._validate_name(name)
        now = time.time()
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT name FROM knowledge_bases WHERE name = ?",
                (name,),
            )
            exists = await cursor.fetchone()
            if exists:
                raise KnowledgeError(f"知识库已存在：{name}")

            cursor = await connection.execute("SELECT COUNT(*) FROM knowledge_bases")
            count_row = await cursor.fetchone()
            is_default = int(count_row[0] if count_row else 0) == 0
            await connection.execute(
                """
                INSERT INTO knowledge_bases (
                    name, description, provider, is_default, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, description.strip(), provider.strip() or "sqlite-fts", is_default, now, now),
            )
            await connection.commit()
        (self.root / name / "raw").mkdir(parents=True, exist_ok=True)
        record = await self.get_base(name)
        if record is None:
            raise KnowledgeError("知识库创建失败")
        return record

    async def ensure_base(self, name: str) -> KnowledgeBaseRecord:
        record = await self.get_base(name)
        if record is None:
            return await self.create_base(name)
        return record

    async def list_bases(self) -> list[KnowledgeBaseRecord]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    b.*,
                    COUNT(DISTINCT d.id) AS document_count,
                    COUNT(DISTINCT c.id) AS chunk_count
                FROM knowledge_bases b
                LEFT JOIN knowledge_documents d ON d.kb_name = b.name
                LEFT JOIN knowledge_chunks c ON c.kb_name = b.name
                GROUP BY b.name
                ORDER BY b.is_default DESC, b.updated_at DESC
                """
            )
            rows = await cursor.fetchall()
        return [self._base_from_row(row) for row in rows]

    async def get_base(self, name: str) -> KnowledgeBaseRecord | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    b.*,
                    COUNT(DISTINCT d.id) AS document_count,
                    COUNT(DISTINCT c.id) AS chunk_count
                FROM knowledge_bases b
                LEFT JOIN knowledge_documents d ON d.kb_name = b.name
                LEFT JOIN knowledge_chunks c ON c.kb_name = b.name
                WHERE b.name = ?
                GROUP BY b.name
                """,
                (name,),
            )
            row = await cursor.fetchone()
        return self._base_from_row(row) if row else None

    async def add_document(
        self,
        knowledge_base: str,
        filename: str,
        content: bytes,
        *,
        relative_path: str = "",
        mime_type: str | None = None,
    ) -> IngestResult:
        if len(content) > self.max_file_bytes:
            raise KnowledgeError(f"文件超过大小限制：{len(content)} > {self.max_file_bytes} bytes")

        await self.ensure_base(knowledge_base)
        rel_path = self._safe_relative_path(relative_path or filename)
        text = extract_text(filename, content)
        chunks = self.chunker.chunk(text)
        if not chunks:
            raise KnowledgeError("文档没有可用文本")
        embeddings = await self._embed_chunks(chunks)

        now = time.time()
        file_path = self._document_path(knowledge_base, rel_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        guessed_mime = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT id FROM knowledge_documents WHERE kb_name = ? AND relative_path = ?",
                (knowledge_base, rel_path),
            )
            existing = await cursor.fetchone()
            if existing:
                await self._remove_document_index(connection, int(existing["id"]))

            cursor = await connection.execute(
                """
                INSERT INTO knowledge_documents (
                    kb_name, filename, relative_path, mime_type, size_bytes,
                    content, chunk_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    knowledge_base,
                    filename,
                    rel_path,
                    guessed_mime,
                    len(content),
                    text,
                    len(chunks),
                    now,
                    now,
                ),
            )
            document_id = int(cursor.lastrowid)

            for index, chunk in enumerate(chunks):
                cursor = await connection.execute(
                    """
                    INSERT INTO knowledge_chunks (
                        document_id, kb_name, chunk_index, content, character_count, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        knowledge_base,
                        index,
                        chunk,
                        len(chunk),
                        json.dumps({"relative_path": rel_path}, ensure_ascii=False),
                    ),
                )
                chunk_id = int(cursor.lastrowid)
                await connection.execute(
                    """
                    INSERT INTO knowledge_chunks_fts (rowid, content, chunk_id, kb_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chunk_id, chunk, chunk_id, knowledge_base),
                )
                if embeddings is not None:
                    vector = embeddings[index]
                    await connection.execute(
                        """
                        INSERT INTO knowledge_chunk_vectors (
                            chunk_id, model, dimensions, vector, created_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            chunk_id,
                            self.embedder.model,
                            len(vector),
                            json.dumps(vector),
                            now,
                        ),
                    )

            await connection.execute(
                "UPDATE knowledge_bases SET updated_at = ? WHERE name = ?",
                (now, knowledge_base),
            )
            await connection.commit()

        return IngestResult(
            knowledge_base=knowledge_base,
            filename=rel_path,
            chunks=len(chunks),
            characters=len(text),
        )

    async def list_documents(self, knowledge_base: str) -> list[dict[str, Any]]:
        if await self.get_base(knowledge_base) is None:
            raise KnowledgeError(f"知识库不存在：{knowledge_base}")
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT relative_path, mime_type, size_bytes, updated_at
                FROM knowledge_documents
                WHERE kb_name = ?
                ORDER BY relative_path
                """,
                (knowledge_base,),
            )
            rows = await cursor.fetchall()
        return [
            {
                "name": str(row["relative_path"]),
                "type": "file",
                "size": int(row["size_bytes"]),
                "modified": float(row["updated_at"]),
                "mime_type": row["mime_type"],
            }
            for row in rows
        ]

    def document_path(self, knowledge_base: str, relative_path: str) -> Path:
        return self._document_path(
            knowledge_base,
            self._safe_relative_path(relative_path),
        )

    async def get_document_text(
        self,
        knowledge_base: str,
        relative_path: str,
    ) -> str | None:
        safe_path = self._safe_relative_path(relative_path)
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT content FROM knowledge_documents
                WHERE kb_name = ? AND relative_path = ?
                """,
                (knowledge_base, safe_path),
            )
            row = await cursor.fetchone()
        return str(row["content"]) if row else None

    async def delete_document(self, knowledge_base: str, relative_path: str) -> bool:
        safe_path = self._safe_relative_path(relative_path)
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT id FROM knowledge_documents WHERE kb_name = ? AND relative_path = ?",
                (knowledge_base, safe_path),
            )
            row = await cursor.fetchone()
            if row is None:
                return False
            await self._remove_document_index(connection, int(row["id"]))
            await connection.commit()

        file_path = self._document_path(knowledge_base, safe_path)
        if file_path.exists():
            file_path.unlink()
        return True

    async def delete_base(self, name: str) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT c.id
                FROM knowledge_chunks c
                WHERE c.kb_name = ?
                """,
                (name,),
            )
            chunk_ids = [int(row["id"]) for row in await cursor.fetchall()]
            if chunk_ids:
                await connection.executemany(
                    "DELETE FROM knowledge_chunks_fts WHERE rowid = ?",
                    [(chunk_id,) for chunk_id in chunk_ids],
                )
            cursor = await connection.execute(
                "DELETE FROM knowledge_bases WHERE name = ?",
                (name,),
            )
            await connection.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            base_dir = self.root / name
            if base_dir.exists():
                for path in sorted(base_dir.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                base_dir.rmdir()
        return deleted

    async def set_default(self, name: str) -> None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT name FROM knowledge_bases WHERE name = ?",
                (name,),
            )
            if await cursor.fetchone() is None:
                raise KnowledgeError(f"知识库不存在：{name}")
            await connection.execute("UPDATE knowledge_bases SET is_default = 0")
            await connection.execute(
                "UPDATE knowledge_bases SET is_default = 1, updated_at = ? WHERE name = ?",
                (time.time(), name),
            )
            await connection.commit()

    async def search(
        self,
        query: str,
        knowledge_bases: list[str] | tuple[str, ...] | None = None,
        *,
        limit: int = 5,
    ) -> list[SearchHit]:
        query = query.strip()
        if not query:
            return []
        limit = max(1, min(limit, 20))
        names = list(knowledge_bases or [])
        if not names:
            bases = await self.list_bases()
            names = [base.name for base in bases]
        if not names:
            return []

        fts_hits = await self._search_fts(query, names, limit * 3)
        vector_hits = await self._search_vectors(query, names, limit * 3)
        return self._fuse_results([fts_hits, vector_hits], limit)

    async def reindex_embeddings(self, knowledge_base: str) -> int:
        """为已有文本块补建当前 embedding 模型对应的向量。"""

        if self.embedder is None:
            return 0
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT c.id, c.content
                FROM knowledge_chunks c
                LEFT JOIN knowledge_chunk_vectors v
                  ON v.chunk_id = c.id AND v.model = ?
                WHERE c.kb_name = ? AND v.chunk_id IS NULL
                ORDER BY c.id
                """,
                (self.embedder.model, knowledge_base),
            )
            rows = await cursor.fetchall()

        if not rows:
            return 0
        chunk_ids = [int(row["id"]) for row in rows]
        texts = [str(row["content"]) for row in rows]
        vectors = await self.embedder.embed(texts)
        if len(vectors) != len(chunk_ids):
            raise KnowledgeError("重新建立向量索引失败：向量数量不一致")

        now = time.time()
        async with self.database.connect() as connection:
            for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
                await connection.execute(
                    """
                    INSERT INTO knowledge_chunk_vectors (
                        chunk_id, model, dimensions, vector, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        model = excluded.model,
                        dimensions = excluded.dimensions,
                        vector = excluded.vector,
                        created_at = excluded.created_at
                    """,
                    (
                        chunk_id,
                        self.embedder.model,
                        len(vector),
                        json.dumps(vector),
                        now,
                    ),
                )
            await connection.commit()
        return len(chunk_ids)

    async def _search_fts(
        self,
        query: str,
        names: list[str],
        limit: int,
    ) -> list[SearchHit]:
        terms = self._query_terms(query)
        if not terms:
            return []
        placeholders = ", ".join("?" for _ in names)
        fts_query = " OR ".join(f'"{term}"' for term in terms)
        sql = f"""
            SELECT
                c.id AS chunk_id,
                c.kb_name,
                c.chunk_index,
                c.content,
                d.relative_path,
                bm25(knowledge_chunks_fts) AS rank
            FROM knowledge_chunks_fts
            JOIN knowledge_chunks c ON c.id = knowledge_chunks_fts.rowid
            JOIN knowledge_documents d ON d.id = c.document_id
            WHERE knowledge_chunks_fts MATCH ?
              AND c.kb_name IN ({placeholders})
            ORDER BY rank
            LIMIT ?
        """
        async with self.database.connect() as connection:
            try:
                cursor = await connection.execute(sql, (fts_query, *names, limit))
                rows = await cursor.fetchall()
            except Exception:
                rows = []

            if not rows:
                like_clauses = " OR ".join("c.content LIKE ?" for _ in terms)
                fallback_sql = f"""
                    SELECT
                        c.id AS chunk_id,
                        c.kb_name,
                        c.chunk_index,
                        c.content,
                        d.relative_path,
                        0.0 AS rank
                    FROM knowledge_chunks c
                    JOIN knowledge_documents d ON d.id = c.document_id
                    WHERE ({like_clauses})
                      AND c.kb_name IN ({placeholders})
                    LIMIT ?
                """
                params = [f"%{term}%" for term in terms] + names + [limit]
                cursor = await connection.execute(fallback_sql, params)
                rows = await cursor.fetchall()

        return [
            SearchHit(
                chunk_id=int(row["chunk_id"]),
                knowledge_base=str(row["kb_name"]),
                document=str(row["relative_path"]),
                chunk_index=int(row["chunk_index"]),
                content=str(row["content"]),
                score=float(row["rank"]),
                metadata={"retriever": "fts"},
            )
            for row in rows
        ]

    async def _search_vectors(
        self,
        query: str,
        names: list[str],
        limit: int,
    ) -> list[SearchHit]:
        if self.embedder is None:
            return []
        try:
            query_vector = (await self.embedder.embed([query]))[0]
        except Exception:
            logger.warning("Query embedding failed; falling back to FTS", exc_info=True)
            return []

        placeholders = ", ".join("?" for _ in names)
        sql = f"""
            SELECT
                c.id AS chunk_id,
                c.kb_name,
                c.chunk_index,
                c.content,
                d.relative_path,
                v.vector
            FROM knowledge_chunk_vectors v
            JOIN knowledge_chunks c ON c.id = v.chunk_id
            JOIN knowledge_documents d ON d.id = c.document_id
            WHERE v.model = ?
              AND c.kb_name IN ({placeholders})
        """
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                sql,
                (self.embedder.model, *names),
            )
            rows = await cursor.fetchall()

        hits: list[SearchHit] = []
        for row in rows:
            try:
                vector = json.loads(row["vector"])
            except (TypeError, json.JSONDecodeError):
                continue
            similarity = self._cosine_similarity(query_vector, vector)
            hits.append(
                SearchHit(
                    chunk_id=int(row["chunk_id"]),
                    knowledge_base=str(row["kb_name"]),
                    document=str(row["relative_path"]),
                    chunk_index=int(row["chunk_index"]),
                    content=str(row["content"]),
                    score=similarity,
                    metadata={"retriever": "vector"},
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]

    @staticmethod
    def _fuse_results(
        rankings: list[list[SearchHit]],
        limit: int,
    ) -> list[SearchHit]:
        """使用 Reciprocal Rank Fusion 合并不同检索器的排名。"""

        fused: dict[int, dict[str, Any]] = {}
        for ranking in rankings:
            for rank, hit in enumerate(ranking, start=1):
                entry = fused.setdefault(
                    hit.chunk_id,
                    {"hit": hit, "score": 0.0, "retrievers": []},
                )
                entry["score"] += 1.0 / (60 + rank)
                entry["retrievers"].append(hit.metadata.get("retriever", "unknown"))

        ordered = sorted(fused.values(), key=lambda item: item["score"], reverse=True)
        results: list[SearchHit] = []
        for entry in ordered[:limit]:
            hit = entry["hit"]
            results.append(
                SearchHit(
                    chunk_id=hit.chunk_id,
                    knowledge_base=hit.knowledge_base,
                    document=hit.document,
                    chunk_index=hit.chunk_index,
                    content=hit.content,
                    score=round(float(entry["score"]), 8),
                    metadata={"retrievers": entry["retrievers"]},
                )
            )
        return results

    async def _embed_chunks(self, chunks: list[str]) -> list[list[float]] | None:
        if self.embedder is None:
            return None
        try:
            vectors = await self.embedder.embed(chunks)
        except Exception:
            logger.warning("Document embedding failed; FTS remains available", exc_info=True)
            return None
        if len(vectors) != len(chunks):
            logger.warning(
                "Embedding count mismatch: expected=%s actual=%s",
                len(chunks),
                len(vectors),
            )
            return None
        return vectors

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    async def _remove_document_index(self, connection: Any, document_id: int) -> None:
        cursor = await connection.execute(
            "SELECT id FROM knowledge_chunks WHERE document_id = ?",
            (document_id,),
        )
        chunk_ids = [int(row["id"]) for row in await cursor.fetchall()]
        if chunk_ids:
            await connection.executemany(
                "DELETE FROM knowledge_chunks_fts WHERE rowid = ?",
                [(chunk_id,) for chunk_id in chunk_ids],
            )
        await connection.execute(
            "DELETE FROM knowledge_documents WHERE id = ?",
            (document_id,),
        )

    def _document_path(self, knowledge_base: str, relative_path: str) -> Path:
        base = (self.root / self._validate_name(knowledge_base) / "raw").resolve()
        candidate = (base / relative_path).resolve()
        if base not in candidate.parents and candidate != base:
            raise KnowledgeError("非法文件路径")
        return candidate

    @staticmethod
    def _validate_name(name: str) -> str:
        clean = name.strip()
        if not clean or len(clean) > 64:
            raise KnowledgeError("知识库名称长度必须为 1 到 64 个字符")
        if not re.fullmatch(r"[\w\u4e00-\u9fff ._-]+", clean):
            raise KnowledgeError("知识库名称只能包含中英文、数字、空格、点、下划线和连字符")
        if clean in {".", ".."}:
            raise KnowledgeError("非法知识库名称")
        return clean

    @staticmethod
    def _safe_relative_path(value: str) -> str:
        normalized = value.replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or ".." in path.parts:
            raise KnowledgeError("非法文件路径")
        return str(path)

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", query)
        terms: list[str] = []
        for token in tokens:
            clean = token.strip()
            if not clean:
                continue
            terms.append(clean)
            if re.fullmatch(r"[\u4e00-\u9fff]{3,}", clean):
                terms.extend(clean[index : index + 2] for index in range(len(clean) - 1))
        return list(dict.fromkeys(terms))

    @staticmethod
    def _base_from_row(row: Any) -> KnowledgeBaseRecord:
        return KnowledgeBaseRecord(
            name=str(row["name"]),
            description=str(row["description"] or ""),
            provider=str(row["provider"] or "sqlite-fts"),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            is_default=bool(row["is_default"]),
            document_count=int(row["document_count"]),
            chunk_count=int(row["chunk_count"]),
        )
