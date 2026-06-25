from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from goodomics.storage.database import DEFAULT_DATABASE_URL


class Settings(BaseSettings):
    database_url: str = DEFAULT_DATABASE_URL
    analytics_path: str | None = None
    analytics_root: str = ".goodomics"
    file_root: str = ".goodomics/files"
    dashboard_dev_url: str | None = None
    ai_provider: str = "openai-compatible"
    ai_api_key: str | None = None
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4.1-mini"
    ai_max_tool_rounds: int = 4

    model_config = SettingsConfigDict(env_prefix="GOODOMICS_", extra="ignore")
