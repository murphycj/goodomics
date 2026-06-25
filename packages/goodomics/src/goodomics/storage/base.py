from __future__ import annotations

from typing import Protocol

from goodomics.schemas.models import Run


class GoodomicsStore(Protocol):
    async def save_run(self, run: Run) -> None:
        """Persist a run and its related records."""
        ...

    async def get_run(self, run_id: str) -> Run | None:
        """Fetch a run by ID."""
        ...
