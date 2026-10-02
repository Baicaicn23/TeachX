from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="TEACHX_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "TeachX"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: Path = Field(default=Path("data/teachx.db"))
    knowledge_root: Path = Field(default=Path("data/knowledge"))
    avatar_root: Path = Field(default=Path("data/avatars"))
    max_upload_bytes: int = 20 * 1024 * 1024

    llm_provider: str = "mock"
    model: str = "gpt-4.1-mini"
    api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    temperature: float = 0.2
    max_agent_rounds: int = 6
    max_output_tokens: int = Field(default=1024, gt=0)
    max_history_messages: int = Field(default=24, ge=0)
    max_history_chars: int = Field(default=16000, ge=0)
    max_tool_result_chars: int = Field(default=6000, ge=0)
    tool_max_attempts: int = Field(default=3, ge=1)
    tool_timeout_seconds: float = Field(default=30.0, gt=0)
    tool_retry_base_delay_ms: int = Field(default=200, ge=0)
    tool_retry_max_delay_ms: int = Field(default=2000, ge=0)
    generate_titles: bool = False
    include_stream_usage: bool = True

    daily_token_budget: int = Field(default=0, ge=0)
    budget_exceeded_action: Literal["block", "mock"] = "block"

    embedding_provider: str = "mock"
    embedding_model: str = "text-embedding-3-small"

    auth_enabled: bool = False
    auth_secret: str = "dev-only-change-this-secret-before-production"
    auth_cookie_name: str = "dt_token"
    auth_cookie_secure: bool = False
    auth_token_ttl_minutes: int = 1440

    def _resolve_project_path(self, path: Path) -> Path:
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        return path.resolve()

    def resolved_database_path(self) -> Path:
        return self._resolve_project_path(self.database_path)

    def resolved_knowledge_root(self) -> Path:
        return self._resolve_project_path(self.knowledge_root)

    def resolved_avatar_root(self) -> Path:
        return self._resolve_project_path(self.avatar_root)


@lru_cache
def get_settings() -> Settings:
    return Settings()
