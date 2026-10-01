from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from teachx.api.auth_dependencies import require_user
from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container
from teachx.auth.models import UserRecord
from teachx.schemas import (
    BranchSelectionRequest,
    OrganizationPatch,
    QuizResultsRequest,
    RenameSessionRequest,
    ReplyLanguageRequest,
    SessionDetail,
    SessionList,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=SessionList)
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> SessionList:
    return SessionList(
        sessions=await container.repository.list_sessions(limit, offset, user_id=user.id)
    )


@router.get("/search")
async def search_sessions(
    q: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    sessions, total = await container.repository.search_sessions(q, limit, offset, user_id=user.id)
    return {"sessions": sessions, "total": total, "limit": limit, "offset": offset}


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> SessionDetail:
    session = await container.repository.get_session(session_id, user_id=user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}")
async def rename_session(
    session_id: str,
    payload: RenameSessionRequest,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, SessionDetail]:
    session = await container.repository.rename_session(session_id, payload.title, user_id=user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, bool]:
    deleted = await container.repository.delete_session(session_id, user_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


@router.patch("/{session_id}/reply-language")
async def update_reply_language(
    session_id: str,
    payload: ReplyLanguageRequest,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, SessionDetail]:
    session = await container.repository.update_reply_language(
        session_id, payload.language, user_id=user.id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.patch("/{session_id}/organization")
async def update_organization(
    session_id: str,
    payload: OrganizationPatch,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, SessionDetail]:
    session = await container.repository.update_organization(
        session_id,
        payload.model_dump(exclude_none=True),
        user_id=user.id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.get("/{session_id}/ask-hint")
async def ask_hint(
    session_id: str,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, str]:
    session = await container.repository.get_session(session_id, user_id=user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"hint": "继续追问一个具体步骤，或者让我换一种讲法。"}


@router.get("/{session_id}/messages/{message_id}/events")
async def message_events(
    session_id: str,
    message_id: int,
    after_seq: int = 0,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    events = await container.repository.message_events(session_id, message_id, user_id=user.id)
    normalized = []
    for index, event in enumerate(events):
        if event.get("seq", 0) <= after_seq:
            continue
        normalized.append({**event, "seq": index + 1, "protocol_version": "2.0"})
    return {
        "session_id": session_id,
        "message_id": message_id,
        "turn_id": (normalized[-1].get("turn_id") if normalized else None),
        "events": normalized,
        "total": len(normalized),
        "last_seq": len(events),
        "next_seq": None,
        "complete": True,
    }


@router.delete("/{session_id}/messages/{message_id}")
async def delete_message(
    session_id: str,
    message_id: int,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, bool]:
    deleted = await container.repository.delete_message(session_id, message_id, user_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"deleted": True}


@router.put("/{session_id}/branch-selection")
async def update_branch_selection(
    session_id: str,
    payload: BranchSelectionRequest,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, dict[str, int]]:
    selected = await container.repository.update_branch_selection(
        session_id,
        payload.selected_branches,
        user_id=user.id,
    )
    return {"selected_branches": selected}


@router.post("/{session_id}/quiz-results")
async def record_quiz_results(
    session_id: str,
    payload: QuizResultsRequest,
    container: ApplicationContainer = Depends(get_container),
    user: UserRecord = Depends(require_user),
) -> dict[str, bool]:
    if await container.repository.get_session(session_id, user_id=user.id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"recorded": bool(payload.answers)}
