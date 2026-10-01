from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from teachx.api.auth_dependencies import require_user
from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container
from teachx.knowledge.extractors import SUPPORTED_EXTENSIONS
from teachx.knowledge.models import KnowledgeBaseRecord
from teachx.knowledge.service import KnowledgeError

router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["knowledge"],
    dependencies=[Depends(require_user)],
)


@router.get("")
async def list_knowledge_bases(
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, list[dict[str, object]]]:
    bases = await container.knowledge.list_bases()
    return {"knowledge_bases": [_serialize_base(base) for base in bases]}


@router.get("/rag-providers")
async def list_rag_providers() -> dict[str, list[dict[str, object]]]:
    return {
        "providers": [
            {
                "id": "sqlite-fts",
                "name": "SQLite FTS",
                "description": "内置全文检索，无需外部服务，适合个人知识库。",
                "configured": True,
                "requires_api_key": False,
                "modes": ["hybrid", "full-text", "vector"],
                "default_mode": "hybrid",
                "linkable": False,
            }
        ]
    }


@router.get("/supported-file-types")
async def supported_file_types() -> dict[str, object]:
    extensions = sorted(SUPPORTED_EXTENSIONS)
    return {
        "extensions": extensions,
        "accept": ",".join(extensions),
        "max_file_size_bytes": 20 * 1024 * 1024,
        "allow_any_extension": False,
    }


@router.get("/embedding-usage")
async def embedding_usage() -> dict[str, list[object]]:
    return {"knowledge_bases": []}


@router.post("")
async def create_knowledge_base(
    name: str = Form(...),
    rag_provider: str = Form(default="sqlite-fts"),
    files: list[UploadFile] = File(default=[]),
    rel_paths: list[str] = Form(default=[]),
    dest_subdir: str = Form(default=""),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        await container.knowledge.create_base(name, provider=rag_provider)
        created = await _ingest_files(
            container,
            name,
            files,
            rel_paths,
            dest_subdir=dest_subdir,
        )
    except KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "task_id": uuid.uuid4().hex,
        "message": f"知识库 {name} 创建完成，共处理 {created} 个文件。",
        "noop": False,
    }


@router.post("/delete")
async def delete_knowledge_base(
    payload: dict[str, str],
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, bool]:
    name = str(payload.get("name") or "")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    deleted = await container.knowledge.delete_base(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"deleted": True}


@router.put("/default/{name}")
async def set_default_knowledge_base(
    name: str,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, bool]:
    try:
        await container.knowledge.set_default(name)
    except KnowledgeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/{kb_name}")
async def get_knowledge_base(
    kb_name: str,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    base = await container.knowledge.get_base(kb_name)
    if base is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return _serialize_base(base)


@router.post("/{kb_name}/upload")
async def upload_knowledge_files(
    kb_name: str,
    files: list[UploadFile] = File(default=[]),
    rel_paths: list[str] = Form(default=[]),
    dest_subdir: str = Form(default=""),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        created = await _ingest_files(
            container,
            kb_name,
            files,
            rel_paths,
            dest_subdir=dest_subdir,
        )
    except KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "task_id": uuid.uuid4().hex,
        "message": f"已处理 {created} 个文件。",
        "noop": created == 0,
    }


@router.get("/{kb_name}/files")
async def list_knowledge_files(
    kb_name: str,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, list[dict[str, object]]]:
    try:
        files = await container.knowledge.list_documents(kb_name)
    except KnowledgeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"files": files}


@router.get("/{kb_name}/file-preview-text/{filename:path}")
async def preview_knowledge_file(
    kb_name: str,
    filename: str,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, str]:
    try:
        text = await container.knowledge.get_document_text(kb_name, filename)
    except KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if text is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"filename": filename, "content": text}


@router.get("/{kb_name}/files/{filename:path}")
async def download_knowledge_file(
    kb_name: str,
    filename: str,
    container: ApplicationContainer = Depends(get_container),
) -> FileResponse:
    try:
        path = container.knowledge.document_path(kb_name, filename)
    except KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=Path(filename).name)


@router.delete("/{kb_name}/files/{filename:path}")
async def delete_knowledge_file(
    kb_name: str,
    filename: str,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, bool]:
    try:
        deleted = await container.knowledge.delete_document(kb_name, filename)
    except KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"was_indexed": True}


@router.get("/{kb_name}/search")
async def search_knowledge_base(
    kb_name: str,
    q: str,
    limit: int = 5,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, list[dict[str, object]]]:
    hits = await container.knowledge.search(q, [kb_name], limit=limit)
    return {
        "results": [
            {
                "id": hit.chunk_id,
                "knowledge_base": hit.knowledge_base,
                "document": hit.document,
                "chunk_index": hit.chunk_index,
                "content": hit.content,
                "score": hit.score,
            }
            for hit in hits
        ]
    }


@router.post("/{kb_name}/reindex")
async def reindex_knowledge_base(
    kb_name: str,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    if await container.knowledge.get_base(kb_name) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    indexed = await container.knowledge.reindex_embeddings(kb_name)
    return {
        "noop": indexed == 0,
        "message": (
            "向量索引已经是最新状态。" if indexed == 0 else f"已为 {indexed} 个文本块补建向量索引。"
        ),
    }


async def _ingest_files(
    container: ApplicationContainer,
    kb_name: str,
    files: list[UploadFile],
    rel_paths: list[str],
    *,
    dest_subdir: str = "",
) -> int:
    created = 0
    for index, upload in enumerate(files):
        content = await upload.read()
        proposed_path = (
            rel_paths[index]
            if index < len(rel_paths) and rel_paths[index]
            else upload.filename or f"document-{index + 1}.txt"
        )
        if dest_subdir:
            proposed_path = f"{dest_subdir.strip('/')}/{proposed_path}"
        await container.knowledge.add_document(
            kb_name,
            upload.filename or Path(proposed_path).name,
            content,
            relative_path=proposed_path,
            mime_type=upload.content_type,
        )
        created += 1
    return created


def _serialize_base(base: KnowledgeBaseRecord) -> dict[str, object]:
    return {
        "id": base.name,
        "name": base.name,
        "is_default": base.is_default,
        "status": "ready",
        "source": "user",
        "available": True,
        "metadata": {
            "description": base.description,
            "provider": base.provider,
        },
        "statistics": {
            "document_count": base.document_count,
            "chunk_count": base.chunk_count,
        },
    }
