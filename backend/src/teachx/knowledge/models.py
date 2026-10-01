from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class KnowledgeBaseRecord:
    name: str
    description: str = ""
    provider: str = "sqlite-fts"
    created_at: float = 0.0
    updated_at: float = 0.0
    is_default: bool = False
    document_count: int = 0
    chunk_count: int = 0


@dataclass(slots=True)
class SearchHit:
    chunk_id: int
    knowledge_base: str
    document: str
    chunk_index: int
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IngestResult:
    knowledge_base: str
    filename: str
    chunks: int
    characters: int
