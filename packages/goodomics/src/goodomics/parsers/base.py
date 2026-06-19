from __future__ import annotations

from pathlib import Path
from typing import Protocol

from goodomics.schemas.models import Metric


class Parser(Protocol):
    def parse(self, path: Path) -> list[Metric]:
        """Parse a results file into metrics."""
        ...
