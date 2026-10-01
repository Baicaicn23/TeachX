from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from teachx.api.auth_dependencies import require_user
from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container
from teachx.auth.models import UserRecord

router = APIRouter(prefix="/api/learning", tags=["learning"])

FeedbackRating = Literal["helpful", "unclear", "wrong"]


class FeedbackUpdate(BaseModel):
    rating: FeedbackRating
    note: str = Field(default="", max_length=2000)


@router.get("/feedback")
async def list_session_feedback(
    session_id: str = "",
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, list[dict[str, object]]]:
    records = await container.repository.list_answer_feedback(
        user_id=user.id,
        session_id=session_id,
    )
    return {"records": records}


@router.get("/records")
async def list_learning_records(
    rating: FeedbackRating | None = Query(default=None),
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, list[dict[str, object]]]:
    records = await container.repository.list_answer_feedback(
        user_id=user.id,
        rating=rating or "",
    )
    return {"records": records}


@router.put("/feedback/{message_id}")
async def update_answer_feedback(
    message_id: int,
    payload: FeedbackUpdate,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, dict[str, object]]:
    record = await container.repository.upsert_answer_feedback(
        user_id=user.id,
        message_id=message_id,
        rating=payload.rating,
        note=payload.note,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="回答不存在或无权访问")
    return {"record": record}


@router.delete("/records/{feedback_id}")
async def delete_learning_record(
    feedback_id: int,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, bool]:
    deleted = await container.repository.delete_answer_feedback(
        user_id=user.id,
        feedback_id=feedback_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="学习记录不存在")
    return {"deleted": True}
