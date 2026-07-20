from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.storage.sqlalchemy import SQLModelGoodomicsStore


def create_store(database_url: str) -> SQLModelGoodomicsStore:
    """Create the application-owned SQL metadata store."""

    return SQLModelGoodomicsStore(database_url)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield and then close one SQL session for the current HTTP request."""

    async with request.app.state.store.session() as session:
        request.state.db_session = session
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
