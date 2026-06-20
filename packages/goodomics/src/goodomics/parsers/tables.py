from __future__ import annotations

from pathlib import Path

from goodomics.schemas.models import Metric


def parse_table(path: Path) -> list[Metric]:
    if not path.exists():
        return []
    return [Metric(sample_id=None, name="table", value=path.name)]
