from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

DATABASE_URL_ENV = "GOODOMICS_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///.goodomics/goodomics.db"
SQLITE_AIOSQLITE_PREFIX = "sqlite+aiosqlite:///"


def resolve_database_url(
    database_url: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the control database URL from argument, environment, or default."""
    environment = os.environ if environ is None else environ
    return database_url or environment.get(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)


def sqlite_database_path(database_url: str) -> Path | None:
    """Return the local SQLite database path for URLs Goodomics can prepare."""
    if not database_url.startswith(SQLITE_AIOSQLITE_PREFIX):
        return None
    db_path = Path(database_url.removeprefix(SQLITE_AIOSQLITE_PREFIX))
    if str(db_path) == ":memory:":
        return None
    return db_path


def ensure_sqlite_parent(database_url: str) -> None:
    """Create the parent directory for local SQLite URLs before connecting."""
    db_path = sqlite_database_path(database_url)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)


def create_async_database_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine after preparing local SQLite paths."""
    ensure_sqlite_parent(database_url)
    return create_async_engine(database_url)
