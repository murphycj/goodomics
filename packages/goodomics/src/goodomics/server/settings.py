from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///.goodomics/goodomics.db"
    analytics_path: str | None = None
    analytics_root: str = ".goodomics"
    artifact_root: str = ".goodomics/artifacts"
    dashboard_dev_url: str | None = None

    model_config = SettingsConfigDict(env_prefix="GOODOMICS_", extra="ignore")
