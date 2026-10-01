from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from teachx.auth.models import UserRecord
from teachx.storage.database import Database

_DUMMY_PASSWORD_HASH = "$2b$12$xHpruRxVD/ASH/EOPVjQweju.OBSoeCw11WByWLkuyVafnfH1O7YG"
_USERNAME_PATTERN = re.compile(r"^[^\s]{3,64}$")


class AuthError(ValueError):
    pass


class InvalidCredentials(AuthError):
    pass


class UsernameTaken(AuthError):
    pass


class InvalidToken(AuthError):
    pass


class AuthService:
    """Own user records, password hashing, and JWT session tokens."""

    def __init__(
        self,
        database: Database,
        *,
        secret: str,
        token_ttl_minutes: int = 1440,
    ) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise AuthError("JWT 密钥至少需要 32 个 UTF-8 字节")
        self.database = database
        self.secret = secret
        self.token_ttl_minutes = token_ttl_minutes

    async def is_first_user(self) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute("SELECT COUNT(*) FROM users")
            row = await cursor.fetchone()
        return int(row[0] if row else 0) == 0

    async def register(self, username: str, password: str) -> tuple[UserRecord, bool]:
        username = self._validate_username(username)
        self._validate_password(password)
        first_user = await self.is_first_user()
        role = "admin" if first_user else "user"
        user_id = uuid.uuid4().hex
        now = time.time()
        password_hash = await asyncio.to_thread(self._hash_password, password)

        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,),
            )
            if await cursor.fetchone() is not None:
                raise UsernameTaken("用户名已存在")
            await connection.execute(
                """
                INSERT INTO users (
                    id, username, password_hash, role, onboarding_completed,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (user_id, username, password_hash, role, now, now),
            )
            await connection.commit()

        return (
            UserRecord(
                id=user_id,
                username=username,
                role=role,
                created_at=now,
                onboarding_completed=False,
            ),
            first_user,
        )

    async def authenticate(self, username: str, password: str) -> UserRecord:
        clean_username = username.strip()
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (clean_username,),
            )
            row = await cursor.fetchone()

        encoded = password.encode("utf-8")
        stored_hash = str(row["password_hash"]) if row else _DUMMY_PASSWORD_HASH
        valid = await asyncio.to_thread(bcrypt.checkpw, encoded, stored_hash.encode())
        if row is None or not valid:
            raise InvalidCredentials("用户名或密码错误")

        now = time.time()
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                (now, now, row["id"]),
            )
            await connection.commit()
        return self._user_from_row(row, last_login_at=now)

    def create_token(self, user: UserRecord) -> str:
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=self.token_ttl_minutes)
        payload = {
            "sub": user.id,
            "username": user.username,
            "role": user.role,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    async def user_from_token(self, token: str | None) -> UserRecord | None:
        if not token:
            return None
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
            )
        except jwt.PyJWTError as exc:
            raise InvalidToken("登录状态已失效") from exc

        user_id = str(payload.get("sub") or "")
        if not user_id:
            raise InvalidToken("登录状态缺少用户标识")
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        return self._user_from_row(row) if row else None

    async def get_user(self, user_id: str) -> UserRecord | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        return self._user_from_row(row) if row else None

    async def update_avatar(self, user_id: str, avatar: str) -> UserRecord | None:
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE users SET avatar = ?, updated_at = ? WHERE id = ?",
                (avatar, time.time(), user_id),
            )
            await connection.commit()
        return await self.get_user(user_id)

    async def update_personalization(
        self,
        user_id: str,
        enabled: bool,
    ) -> UserRecord | None:
        async with self.database.connect() as connection:
            await connection.execute(
                ("UPDATE users SET personalization_enabled = ?, updated_at = ? WHERE id = ?"),
                (int(enabled), time.time(), user_id),
            )
            await connection.commit()
        return await self.get_user(user_id)

    async def update_learner_profile(
        self,
        user_id: str,
        profile: dict[str, Any],
    ) -> UserRecord | None:
        current = await self.get_user(user_id)
        if current is None:
            return None
        previous_goal = str((current.learner_profile or {}).get("learning_goal") or "")
        next_goal = str(profile.get("learning_goal") or "")
        if next_goal and next_goal != previous_goal:
            profile = {**profile, "learning_goal_status": "active"}
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE users SET learner_profile = ?, updated_at = ? WHERE id = ?",
                (json.dumps(profile, ensure_ascii=False), time.time(), user_id),
            )
            await connection.commit()
        return await self.get_user(user_id)

    async def complete_onboarding(self, user_id: str) -> UserRecord | None:
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE users SET onboarding_completed = 1, updated_at = ? WHERE id = ?",
                (time.time(), user_id),
            )
            await connection.commit()
        return await self.get_user(user_id)

    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

    @staticmethod
    def _validate_username(username: str) -> str:
        clean = username.strip()
        if not _USERNAME_PATTERN.fullmatch(clean):
            raise AuthError("用户名长度必须为 3 到 64 个字符，且不能包含空格")
        return clean

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 8:
            raise AuthError("密码至少需要 8 个字符")
        if len(password.encode("utf-8")) > 72:
            raise AuthError("密码不能超过 72 个 UTF-8 字节")

    @staticmethod
    def _user_from_row(row: Any, *, last_login_at: float | None = None) -> UserRecord:
        return UserRecord(
            id=str(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            created_at=float(row["created_at"]),
            last_login_at=(
                float(last_login_at)
                if last_login_at is not None
                else float(row["last_login_at"])
                if row["last_login_at"] is not None
                else None
            ),
            avatar=str(row["avatar"] or ""),
            learner_profile=(
                json.loads(row["learner_profile"]) if row["learner_profile"] else None
            ),
            personalization_enabled=bool(row["personalization_enabled"]),
            onboarding_completed=bool(row["onboarding_completed"]),
        )
