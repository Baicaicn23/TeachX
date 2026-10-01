from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from teachx.api.auth_dependencies import require_user
from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container
from teachx.auth.models import UserRecord
from teachx.practice.service import PracticeError

router = APIRouter(prefix="/api/practice", tags=["practice"])

PracticeRating = Literal["again", "hard", "good", "easy"]


class GeneratePracticeRequest(BaseModel):
    knowledge_base: str = Field(min_length=1, max_length=64)
    count: int = Field(default=3, ge=1, le=10)


class PracticeAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
    rating: PracticeRating


@router.get("/summary")
async def practice_summary(
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    return await container.practice.summary(user_id=user.id)


@router.get("/knowledge-bases")
async def practice_knowledge_bases(
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, list[dict[str, object]]]:
    bases = await container.knowledge.list_bases(user.id, is_admin=user.is_admin)
    return {
        "knowledge_bases": [
            {
                "name": base.name,
                "document_count": base.document_count,
                "chunk_count": base.chunk_count,
            }
            for base in bases
        ]
    }


@router.get("/queue")
async def practice_queue(
    knowledge_base: str = "",
    limit: int = Query(default=10, ge=1, le=50),
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, list[dict[str, object]]]:
    try:
        questions = await container.practice.queue(
            user_id=user.id,
            knowledge_base=knowledge_base,
            limit=limit,
        )
    except PracticeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"questions": questions}


@router.post("/generate")
async def generate_practice(
    payload: GeneratePracticeRequest,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, list[dict[str, object]]]:
    try:
        questions = await container.practice.generate(
            user_id=user.id,
            knowledge_base=payload.knowledge_base,
            count=payload.count,
        )
    except PracticeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"questions": questions}


@router.post("/questions/{question_id}/answer")
async def answer_practice_question(
    question_id: int,
    payload: PracticeAnswerRequest,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    try:
        result = await container.practice.answer(
            user_id=user.id,
            question_id=question_id,
            answer=payload.answer,
            rating=payload.rating,
        )
    except PracticeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.delete("/questions/{question_id}")
async def delete_practice_question(
    question_id: int,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, bool]:
    deleted = await container.practice.delete_question(
        user_id=user.id,
        question_id=question_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="练习题不存在")
    return {"deleted": True}
