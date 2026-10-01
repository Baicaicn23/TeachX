from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from teachx.api.auth_dependencies import require_user
from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container
from teachx.auth.models import LOCAL_USER, UserRecord
from teachx.auth.service import AuthError, InvalidCredentials, InvalidToken

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


@router.get("/status")
async def auth_status(
    request: Request,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    if not container.settings.auth_enabled:
        return _status_payload(LOCAL_USER, enabled=False)

    token = request.cookies.get(container.settings.auth_cookie_name)
    try:
        user = await container.auth.user_from_token(token)
    except InvalidToken:
        user = None
    return _status_payload(user, enabled=True)


@router.get("/is_first_user")
async def is_first_user(
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, bool]:
    return {"is_first_user": await container.auth.is_first_user()}


@router.post("/register")
async def register(
    credentials: Credentials,
    response: Response,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        user, first_user = await container.auth.register(
            credentials.username,
            credentials.password,
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Registration is the start of the first-run flow, so establish the same
    # session login would create and send the user directly to onboarding.
    token = container.auth.create_token(user)
    _set_auth_cookie(response, container, token)
    return {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "is_first_user": first_user,
        "onboarding_completed": user.onboarding_completed,
    }


@router.get("/onboarding")
async def onboarding_status(
    user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    if not user.id:
        return {"completed": True, "available": False, "learner_profile": None}
    current = await container.auth.get_user(user.id)
    if current is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "completed": current.onboarding_completed,
        "available": True,
        "learner_profile": current.learner_profile,
    }


@router.post("/onboarding/complete")
async def complete_onboarding(
    user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    if not user.id:
        return {"completed": True}
    updated = await container.auth.complete_onboarding(user.id)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"completed": updated.onboarding_completed}


@router.post("/login")
async def login(
    credentials: Credentials,
    response: Response,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        user = await container.auth.authenticate(
            credentials.username,
            credentials.password,
        )
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    token = container.auth.create_token(user)
    _set_auth_cookie(response, container, token)
    return _status_payload(user, enabled=True)


@router.post("/logout")
async def logout(
    response: Response,
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, bool]:
    response.delete_cookie(
        container.settings.auth_cookie_name,
        path="/",
        secure=container.settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


def _set_auth_cookie(
    response: Response,
    container: ApplicationContainer,
    token: str,
) -> None:
    response.set_cookie(
        key=container.settings.auth_cookie_name,
        value=token,
        max_age=container.settings.auth_token_ttl_minutes * 60,
        path="/",
        secure=container.settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _status_payload(user: UserRecord | None, *, enabled: bool) -> dict[str, object]:
    if user is None:
        return {"enabled": enabled, "authenticated": False}
    return {
        "enabled": enabled,
        "authenticated": True,
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "is_admin": user.is_admin,
        "preset": "standard",
        "avatar": user.avatar,
        "learning_policy": None,
        "onboarding_completed": user.onboarding_completed,
    }
