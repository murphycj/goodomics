from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GoodomicsRun:
    name: str
    assay: str | None = None
    metrics: list[dict[str, object]] = field(default_factory=list)
    artifacts: list[Path] = field(default_factory=list)

    def log_metric(
        self,
        sample_id: str,
        name: str,
        value: float | int | str,
        *,
        unit: str | None = None,
    ) -> None:
        self.metrics.append(
            {
                "sample_id": sample_id,
                "name": name,
                "value": value,
                "unit": unit,
            }
        )

    def log_artifact(self, path: str | Path) -> None:
        self.artifacts.append(Path(path))


def run(name: str, assay: str | None = None) -> GoodomicsRun:
    return GoodomicsRun(name=name, assay=assay)
