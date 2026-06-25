from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_username: str = "reviewer"
    app_password: str = "change-me"
    session_secret: str = Field(default="dev-session-secret-change-me", min_length=8)
    session_max_age_seconds: int = 60 * 60 * 12
    cookie_secure: bool = False

    data_dir: Path = Path("data")
    rag_top_k: int = 5
    rag_max_context_chars: int = 9000

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"
