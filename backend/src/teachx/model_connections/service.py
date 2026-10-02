from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from teachx.providers.openai_compat import OpenAICompatibleProvider
from teachx.storage.database import Database


class ModelConnectionError(ValueError):
    pass


class _CredentialCipher:
    def __init__(self, secret: str) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self.fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ModelConnectionError("模型凭据无法解密，请重新保存 API Key") from exc


class ModelConnectionService:
    """Store user-owned OpenAI-compatible provider connections."""

    def __init__(
        self,
        database: Database,
        *,
        secret: str,
        max_output_tokens: int = 1024,
        temperature: float = 0.2,
        include_stream_usage: bool = True,
    ) -> None:
        self.database = database
        self.cipher = _CredentialCipher(secret)
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.include_stream_usage = include_stream_usage

    async def list_connections(self, *, user_id: str) -> list[dict[str, Any]]:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT id, name, base_url, default_model, models, active,
                       created_at, updated_at, api_key_encrypted
                FROM model_connections
                WHERE user_id = ?
                ORDER BY active DESC, updated_at DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [_public_record(row) for row in rows]

    async def save_connection(
        self,
        *,
        user_id: str,
        connection_id: str | None,
        name: str,
        base_url: str,
        api_key: str | None,
        default_model: str,
        models: list[str],
    ) -> dict[str, Any]:
        clean_name = name.strip()
        clean_base_url = _normalize_base_url(base_url)
        clean_model = default_model.strip()
        clean_models = _normalize_models(models)
        if not clean_name:
            raise ModelConnectionError("连接名称不能为空")
        if not clean_model and clean_models:
            clean_model = clean_models[0]
        if not clean_model:
            raise ModelConnectionError("请选择或填写默认模型")

        now = time.time()
        async with self.database.connect() as connection:
            existing = None
            if connection_id:
                cursor = await connection.execute(
                    "SELECT * FROM model_connections WHERE id = ? AND user_id = ?",
                    (connection_id, user_id),
                )
                existing = await cursor.fetchone()
                if existing is None:
                    raise ModelConnectionError("模型连接不存在")
            clean_api_key = (api_key or "").strip()
            if existing is None and not clean_api_key:
                raise ModelConnectionError("首次创建连接时必须填写 API Key")
            encrypted_key = (
                self.cipher.encrypt(clean_api_key)
                if clean_api_key
                else str(existing["api_key_encrypted"])
            )
            cursor = await connection.execute(
                """
                SELECT COUNT(*) FROM model_connections WHERE user_id = ?
                """,
                (user_id,),
            )
            count_row = await cursor.fetchone()
            should_activate = bool(existing and existing["active"])
            if existing is None and int(count_row[0] if count_row else 0) == 0:
                should_activate = True

            record_id = connection_id or uuid.uuid4().hex
            if existing is None:
                await connection.execute(
                    """
                    INSERT INTO model_connections (
                        id, user_id, name, base_url, api_key_encrypted,
                        default_model, models, active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        user_id,
                        clean_name,
                        clean_base_url,
                        encrypted_key,
                        clean_model,
                        json.dumps(clean_models, ensure_ascii=False),
                        int(should_activate),
                        now,
                        now,
                    ),
                )
            else:
                await connection.execute(
                    """
                    UPDATE model_connections
                    SET name = ?, base_url = ?, api_key_encrypted = ?,
                        default_model = ?, models = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        clean_name,
                        clean_base_url,
                        encrypted_key,
                        clean_model,
                        json.dumps(clean_models, ensure_ascii=False),
                        now,
                        record_id,
                        user_id,
                    ),
                )
            await connection.commit()
            cursor = await connection.execute(
                "SELECT * FROM model_connections WHERE id = ?",
                (record_id,),
            )
            saved = await cursor.fetchone()
        if saved is None:
            raise ModelConnectionError("模型连接保存失败")
        return _public_record(saved)

    async def activate_connection(self, *, user_id: str, connection_id: str) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT id FROM model_connections WHERE id = ? AND user_id = ?",
                (connection_id, user_id),
            )
            if await cursor.fetchone() is None:
                return False
            await connection.execute(
                "UPDATE model_connections SET active = 0 WHERE user_id = ?",
                (user_id,),
            )
            await connection.execute(
                """
                UPDATE model_connections
                SET active = 1, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (time.time(), connection_id, user_id),
            )
            await connection.commit()
        return True

    async def activate_platform_default(self, *, user_id: str) -> None:
        async with self.database.connect() as connection:
            await connection.execute(
                "UPDATE model_connections SET active = 0 WHERE user_id = ?",
                (user_id,),
            )
            await connection.commit()

    async def delete_connection(self, *, user_id: str, connection_id: str) -> bool:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "DELETE FROM model_connections WHERE id = ? AND user_id = ?",
                (connection_id, user_id),
            )
            await connection.commit()
            return cursor.rowcount > 0

    async def test_connection(
        self,
        *,
        user_id: str,
        base_url: str,
        api_key: str | None = None,
        connection_id: str | None = None,
    ) -> list[str]:
        clean_key = (api_key or "").strip()
        if not clean_key and connection_id:
            record = await self._record(user_id=user_id, connection_id=connection_id)
            if record is None:
                raise ModelConnectionError("模型连接不存在")
            clean_key = self.cipher.decrypt(str(record["api_key_encrypted"]))
        if not clean_key:
            raise ModelConnectionError("请填写 API Key")
        return await self._fetch_models(
            base_url=_normalize_base_url(base_url),
            api_key=clean_key,
        )

    async def provider_for_user(self, *, user_id: str) -> OpenAICompatibleProvider | None:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM model_connections
                WHERE user_id = ? AND active = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            record = await cursor.fetchone()
        if record is None:
            return None
        return OpenAICompatibleProvider(
            model=str(record["default_model"]),
            api_key=self.cipher.decrypt(str(record["api_key_encrypted"])),
            base_url=str(record["base_url"]),
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            include_stream_usage=self.include_stream_usage,
        )

    async def _record(self, *, user_id: str, connection_id: str) -> Any:
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM model_connections WHERE id = ? AND user_id = ?",
                (connection_id, user_id),
            )
            return await cursor.fetchone()

    @staticmethod
    async def _fetch_models(*, base_url: str, api_key: str) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise ModelConnectionError(
                f"模型平台返回 {exc.response.status_code}: {detail}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelConnectionError("无法连接模型平台或响应格式不正确") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        models = sorted(
            {
                str(item.get("id"))
                for item in data or []
                if isinstance(item, dict) and item.get("id")
            }
        )
        if not models:
            raise ModelConnectionError("平台没有返回可用模型")
        return models


def _normalize_base_url(value: str) -> str:
    clean = value.strip().rstrip("/")
    if not clean.startswith(("http://", "https://")):
        raise ModelConnectionError("Base URL 必须以 http:// 或 https:// 开头")
    if len(clean) > 500:
        raise ModelConnectionError("Base URL 过长")
    return clean


def _normalize_models(models: list[str]) -> list[str]:
    return sorted({str(model).strip() for model in models if str(model).strip()})[:200]


def _public_record(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "base_url": str(row["base_url"]),
        "default_model": str(row["default_model"]),
        "models": _json_models(row["models"]),
        "active": bool(row["active"]),
        "has_api_key": bool(row["api_key_encrypted"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def _json_models(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return _normalize_models(parsed if isinstance(parsed, list) else [])
