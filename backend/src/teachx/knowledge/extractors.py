from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}


class UnsupportedDocumentError(ValueError):
    pass


def extract_text(filename: str, content: bytes) -> str:
    """把支持的文件类型转换为纯文本。"""

    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        return _decode_text(content)
    if suffix == ".pdf":
        return _extract_pdf(content)
    raise UnsupportedDocumentError(
        f"不支持的文件类型：{suffix or 'unknown'}。当前支持 .txt、.md、.markdown 和 .pdf。"
    )


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n\n".join(pages).strip()
    if not text:
        raise UnsupportedDocumentError("PDF 中没有可提取文本。扫描版 PDF 需要后续接入 OCR。")
    return text
