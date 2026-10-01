from functools import lru_cache
from pathlib import Path

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

    llm_provider: str = "mock"
    model: str = "gpt-4.1-mini"
    api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    temperature: float = 0.2
    max_agent_rounds: int = 6

    def resolved_database_path(self) -> Path:
        path = self.database_path
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        return path.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
