from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from teachx.api.auth_dependencies import require_user
from teachx.api.container import ApplicationContainer
from teachx.api.dependencies import get_container
from teachx.auth.models import UserRecord

router = APIRouter(prefix="/api/auth", tags=["profile"])

MAX_AVATAR_BYTES = 1024 * 1024


class ProfileUpdate(BaseModel):
    avatar: str | None = Field(default=None, max_length=128)
    personalization_enabled: bool | None = None


class LearnerProfileUpdate(BaseModel):
    age: int | None = Field(default=None, ge=3, le=120)
    grade_level: str | None = Field(default=None, max_length=64)
    curriculum: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=32)
    reading_level: str | None = Field(default=None, max_length=64)
    explanation_style: str | None = Field(default=None, max_length=128)


@router.get("/personalization")
async def get_personalization_status(
    user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    current = await container.auth.get_user(user.id)
    if current is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    profile = current.learner_profile or {}
    return {
        "available": bool(profile),
        "enabled": current.personalization_enabled,
        "learner_profile": profile,
    }


@router.get("/profile")
async def get_profile(
    user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    return _profile_payload(user)


@router.put("/profile")
async def update_profile(
    payload: ProfileUpdate,
    user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    updated = user
    if payload.avatar is not None:
        avatar = payload.avatar.strip()
        if avatar and not (avatar.startswith("icon:") or avatar.startswith("img:")):
            raise HTTPException(status_code=400, detail="无效的头像标记")
        changed = await container.auth.update_avatar(user.id, avatar)
        if changed is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        updated = changed

    if payload.personalization_enabled is not None:
        changed = await container.auth.update_personalization(
            user.id,
            payload.personalization_enabled,
        )
        if changed is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        updated = changed

    return _profile_payload(updated)


@router.put("/profile/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, str]:
    content = await file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="头像不能超过 1 MB")
    extension = _image_extension(content)
    if extension is None:
        raise HTTPException(status_code=400, detail="只支持 PNG、JPEG 或 WebP 头像")

    avatar_root = container.settings.resolved_avatar_root()
    avatar_root.mkdir(parents=True, exist_ok=True)
    _remove_avatar_files(avatar_root, user.id)
    path = avatar_root / f"{user.id}{extension}"
    path.write_bytes(content)

    marker = f"img:{int(time.time() * 1000)}"
    updated = await container.auth.update_avatar(user.id, marker)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"avatar": updated.avatar}


@router.delete("/profile/avatar")
async def delete_avatar(
    user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, bool]:
    _remove_avatar_files(container.settings.resolved_avatar_root(), user.id)
    await container.auth.update_avatar(user.id, "")
    return {"deleted": True}


@router.get("/avatar/{user_id}")
async def get_avatar(
    user_id: str,
    current_user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> FileResponse:
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权访问该头像")
    avatar_root = container.settings.resolved_avatar_root()
    path = _find_avatar_file(avatar_root, user_id)
    if path is None:
        raise HTTPException(status_code=404, detail="头像不存在")
    return FileResponse(path)


@router.get("/profile/learner-profile")
async def get_learner_profile(
    user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    current = await container.auth.get_user(user.id)
    if current is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"learner_profile": current.learner_profile}


@router.put("/profile/learner-profile")
async def update_learner_profile(
    payload: LearnerProfileUpdate,
    user: UserRecord = Depends(require_user),
    container: ApplicationContainer = Depends(get_container),
) -> dict[str, object]:
    profile = payload.model_dump(exclude_none=True)
    updated = await container.auth.update_learner_profile(user.id, profile)
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"learner_profile": updated.learner_profile}


def _profile_payload(user: UserRecord) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "created_at": datetime.fromtimestamp(user.created_at, UTC).isoformat(),
        "disabled": False,
        "avatar": user.avatar,
        "personalization_enabled": user.personalization_enabled,
    }


def _image_extension(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    return None


def _remove_avatar_files(root: Path, user_id: str) -> None:
    if not root.exists():
        return
    for path in root.glob(f"{user_id}.*"):
        if path.is_file():
            path.unlink()


def _find_avatar_file(root: Path, user_id: str) -> Path | None:
    if not root.exists():
        return None
    for extension in (".webp", ".png", ".jpg", ".jpeg"):
        path = root / f"{user_id}{extension}"
        if path.is_file():
            return path
    return None
