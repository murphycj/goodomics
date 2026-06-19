from __future__ import annotations

from goodomics.storage.sqlalchemy import SQLAlchemyGoodomicsStore


def create_store(database_url: str) -> SQLAlchemyGoodomicsStore:
    return SQLAlchemyGoodomicsStore(database_url)
