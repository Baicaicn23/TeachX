from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container
from teachx.auth.models import LOCAL_USER, UserRecord
from teachx.auth.service import InvalidToken


async def require_user(
    request: Request,
    container: ApplicationContainer = Depends(get_container),
) -> UserRecord:
    if not container.settings.auth_enabled:
        return LOCAL_USER

    token = request.cookies.get(container.settings.auth_cookie_name)
    try:
        user = await container.auth.user_from_token(token)
    except InvalidToken as exc:
        raise HTTPException(status_code=401, detail="登录状态已失效") from exc
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user
