from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./goodomics.db"

    model_config = SettingsConfigDict(env_prefix="GOODOMICS_", extra="ignore")
