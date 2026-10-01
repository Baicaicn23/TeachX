from fastapi import APIRouter

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])


@router.get("")
async def list_knowledge_bases() -> dict[str, list[object]]:
    """Initial contract used by the reused frontend while RAG is being built."""
    return {"knowledge_bases": []}
