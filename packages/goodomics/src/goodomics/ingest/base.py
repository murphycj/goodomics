from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    DataImport,
    DataProfile,
    FileAsset,
    FileLink,
    Run,
    RunSample,
    Sample,
    SampleSet,
    SampleSetMember,
    Subject,
)


class AnalyticsBulkLoad(Protocol):
    """DuckDB-backed analytical load that avoids materializing huge fact lists."""

    @property
    def run_id(self) -> str:
        """Run whose analytical records are loaded."""
        ...

    def load(self, connection: Any) -> None:
        """Write analytical records using an open DuckDB connection."""
        ...


@dataclass
class NormalizedIngestResult:
    run: Run
    runs: list[Run] = field(default_factory=list)
    data_import: DataImport | None = None
    subjects: list[Subject] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    run_samples: list[RunSample] = field(default_factory=list)
    data_profiles: list[DataProfile] = field(default_factory=list)
    files: list[FileAsset] = field(default_factory=list)
    file_links: list[FileLink] = field(default_factory=list)
    sample_sets: list[SampleSet] = field(default_factory=list)
    sample_set_members: list[SampleSetMember] = field(default_factory=list)
    analytics_batch: AnalyticsIngestBatch = field(default_factory=AnalyticsIngestBatch)
    bulk_loads: list[AnalyticsBulkLoad] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def sample_ids(self) -> set[str]:
        return {sample.sample_id for sample in self.samples}

    @property
    def all_runs(self) -> list[Run]:
        return self.runs or [self.run]

    @property
    def run_sample_ids(self) -> set[str]:
        return {run_sample.run_sample_id for run_sample in self.run_samples}


def merge_batches(batches: Iterable[AnalyticsIngestBatch]) -> AnalyticsIngestBatch:
    merged = AnalyticsIngestBatch()
    for batch in batches:
        for field_name in merged.model_fields:
            getattr(merged, field_name).extend(getattr(batch, field_name))
    return merged
