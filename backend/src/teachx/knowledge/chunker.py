from __future__ import annotations

import re


class TextChunker:
    """按段落组合文本块，并保留少量重叠内容。"""

    def __init__(self, max_chars: int = 900, overlap_chars: int = 120) -> None:
        if max_chars < 200:
            raise ValueError("max_chars must be at least 200")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk(self, text: str) -> list[str]:
        normalized = self._normalize(text)
        if not normalized:
            return []

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= self.max_chars:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = self._overlap_tail(current)

            if len(paragraph) <= self.max_chars:
                current = f"{current}\n\n{paragraph}".strip() if current else paragraph
                continue

            long_parts = self._split_long_text(paragraph)
            for part in long_parts:
                candidate = f"{current}\n\n{part}".strip() if current else part
                if len(candidate) <= self.max_chars:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                        current = self._overlap_tail(current)
                    current = f"{current}\n\n{part}".strip() if current else part

        if current:
            chunks.append(current)

        return self._deduplicate(chunks)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_long_text(self, text: str) -> list[str]:
        sentences = re.split(r"(?<=[。！？.!?])\s*", text)
        parts: list[str] = []
        current = ""
        for sentence in sentences:
            if not sentence:
                continue
            candidate = f"{current}{sentence}"
            if len(candidate) <= self.max_chars:
                current = candidate
            else:
                if current:
                    parts.append(current)
                current = sentence
        if current:
            parts.append(current)
        return parts or [text]

    def _overlap_tail(self, text: str) -> str:
        if self.overlap_chars == 0:
            return ""
        return text[-self.overlap_chars :].strip()

    @staticmethod
    def _deduplicate(chunks: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for chunk in chunks:
            clean = chunk.strip()
            if clean and clean not in seen:
                seen.add(clean)
                result.append(clean)
        return result
