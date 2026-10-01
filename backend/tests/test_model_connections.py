import asyncio
from pathlib import Path

from teachx.model_connections.service import (
    ModelConnectionError,
    ModelConnectionService,
)
from teachx.storage.database import Database


def test_model_connection_storage_activates_and_encrypts_key(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "connections.db")
        await database.initialize()
        service = ModelConnectionService(database, secret="connection-secret-at-least-32-bytes")

        saved = await service.save_connection(
            user_id="user-1",
            connection_id=None,
            name="DeepSeek Flash",
            base_url="https://api.deepseek.com/v1/",
            api_key="sk-secret-value",
            default_model="deepseek-flash",
            models=["deepseek-flash", "deepseek-v4-pro"],
        )
        assert saved["active"] is True
        assert saved["has_api_key"] is True
        assert "api_key" not in saved

        async with database.connect() as connection:
            cursor = await connection.execute(
                "SELECT api_key_encrypted FROM model_connections WHERE id = ?",
                (saved["id"],),
            )
            row = await cursor.fetchone()
        assert row is not None
        assert row["api_key_encrypted"] != "sk-secret-value"
        assert "sk-secret-value" not in str(row["api_key_encrypted"])

        provider = await service.provider_for_user(user_id="user-1")
        assert provider is not None
        assert provider.model == "deepseek-flash"

        assert await service.activate_platform_default(user_id="user-1") is None
        assert await service.provider_for_user(user_id="user-1") is None
        assert (
            await service.activate_connection(
                user_id="user-1",
                connection_id=str(saved["id"]),
            )
            is True
        )

        assert await service.list_connections(user_id="user-2") == []
        assert (
            await service.delete_connection(
                user_id="user-2",
                connection_id=str(saved["id"]),
            )
            is False
        )
        assert await service.delete_connection(
            user_id="user-1",
            connection_id=str(saved["id"]),
        )

    asyncio.run(scenario())


def test_model_connection_requires_key_on_create(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = Database(tmp_path / "connections-required.db")
        await database.initialize()
        service = ModelConnectionService(database, secret="connection-secret-at-least-32-bytes")
        try:
            await service.save_connection(
                user_id="user-1",
                connection_id=None,
                name="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key="",
                default_model="gpt-4.1-mini",
                models=["gpt-4.1-mini"],
            )
        except ModelConnectionError:
            pass
        else:
            raise AssertionError("creating a connection without a key must fail")

    asyncio.run(scenario())
