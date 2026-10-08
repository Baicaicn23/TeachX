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
PracticeSource = Literal["knowledge_base", "mistakes"]


class GeneratePracticeRequest(BaseModel):
    source: PracticeSource = "knowledge_base"
    # "从错题出题"不需要选知识库(留空表示所有学科的错题都要),
    # 所以这里不强制非空,由服务层按来源判断。
    knowledge_base: str = Field(default="", max_length=64)
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
) -> dict[str, object]:
    provider = await _question_writer(container, user)
    try:
        questions = await container.practice.generate(
            user_id=user.id,
            knowledge_base=payload.knowledge_base,
            count=payload.count,
            source=payload.source,
            provider=provider,
        )
    except PracticeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"questions": questions}


async def _question_writer(
    container: ApplicationContainer,
    user: UserRecord,
) -> object | None:
    """出题用的模型;返回 None 表示这次只能模板出题。

    "用模型写题"要花钱,所以这里替用户把两道闸:当日预算已超,或取不到模型
    (没配置、连接不可用),一律返回 None——出题退回模板,**不会因为超额或
    模型不可用而失败**。这与回合里"超预算回退 Mock"是同一个取舍。
    """

    try:
        status = await container.usage.daily_status(
            user_id=user.id,
            limit=container.settings.daily_token_budget,
            exceeded_action=container.settings.budget_exceeded_action,
        )
        if status.get("exceeded"):
            print("[practice] 当日预算已超,本次改为模板出题")
            return None
        # 用户没连自己的模型时回退到平台默认 Provider——与回合里的
        # ``provider or self.provider`` 是同一个取舍。平台默认是 Mock 时,
        # write_question 会自动走模板,不需要在这里判断。
        provider = await container.model_connections.provider_for_user(user_id=user.id)
        return provider or container.provider
    except Exception as exc:  # noqa: BLE001 — 拿不到模型就模板出题,不阻塞
        # 不静默吞掉:出题退化本身没关系,但"为什么退化"要留在日志里,
        # 否则配置类问题(比如容器少了依赖)会一直看不见。
        print(f"[practice] 取模型失败,本次改为模板出题: {type(exc).__name__}: {exc}")
        return None


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
