from __future__ import annotations

from goodomics.storage.sqlalchemy import SQLModelGoodomicsStore


def create_store(database_url: str) -> SQLModelGoodomicsStore:
    return SQLModelGoodomicsStore(database_url)
