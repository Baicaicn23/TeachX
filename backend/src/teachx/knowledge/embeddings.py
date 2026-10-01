from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from openai import AsyncOpenAI


class EmbeddingError(ValueError):
    pass


class BaseEmbeddingProvider(ABC):
    """把文本转换为归一化向量。"""

    name: str
    model: str

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic hash embedding used for local development and tests.

    This is not a semantic production model. It gives overlapping terms a
    similar vector so the complete hybrid-search path can be tested without an
    API key.
    """

    name = "mock"
    model = "teachx-hash-v1"
    dimensions = 256

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, "big")
            index = raw % self.dimensions
            sign = 1.0 if raw & 1 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI-compatible embedding adapter."""

    name = "openai"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None,
        batch_size: int = 64,
    ) -> None:
        self.model = model
        self.batch_size = batch_size
        self.client = AsyncOpenAI(
            api_key=api_key or "missing-api-key",
            base_url=base_url,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = await self.client.embeddings.create(
                model=self.model,
                input=batch,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend([list(item.embedding) for item in ordered])
        if len(vectors) != len(texts):
            raise EmbeddingError("Embedding API 返回数量与输入数量不一致")
        return vectors


def build_embedding_provider(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> BaseEmbeddingProvider | None:
    normalized = provider.strip().lower()
    if normalized in {"", "none", "disabled"}:
        return None
    if normalized == "mock":
        return MockEmbeddingProvider()
    if normalized == "openai":
        return OpenAIEmbeddingProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
    raise EmbeddingError(f"不支持的 Embedding Provider：{provider}")


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", match):
            tokens.extend(match)
            tokens.extend(match[index : index + 2] for index in range(len(match) - 1))
        else:
            tokens.append(match)
    return [token for token in tokens if token]
