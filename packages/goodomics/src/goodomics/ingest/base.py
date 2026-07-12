"""Shared ingest contracts and normalized result container types."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from goodomics.schemas.models import (
    AnalysisMethod,
    AnalysisType,
    AnalyticsIngestBatch,
    DataContract,
    DataContractAnalysisType,
    DataContractField,
    DataImport,
    FileAsset,
    FileLink,
    Run,
    RunContract,
    RunContractSample,
    RunRelationship,
    RunSample,
    Sample,
    SampleSet,
    SampleSetMember,
    Subject,
)


class AnalyticsBulkLoad(Protocol):
    """DuckDB-backed analytical load that avoids materializing huge row lists."""

    @property
    def run_id(self) -> str:
        """Run whose analytical records are loaded."""
        ...

    def load(self, connection: Any) -> None:
        """Write analytical records using an open DuckDB connection."""
        ...

    def resolve_catalog_ids(
        self, catalog_id_maps: Mapping[str, Mapping[Any, int]]
    ) -> AnalyticsBulkLoad:
        """Return a bulk loader that writes SQL-owned catalog references as ints."""
        ...


class AnalyticsStagedLoad(Protocol):
    """File-backed analytical load prepared outside the small in-memory batch."""

    def load(self, connection: Any) -> None:
        """Write staged analytical records using an open DuckDB connection."""
        ...

    def resolve_catalog_ids(
        self, catalog_id_maps: Mapping[str, Mapping[Any, int]]
    ) -> AnalyticsStagedLoad:
        """Return a staged loader that writes SQL-owned catalog references as ints."""
        ...


@dataclass
class NormalizedIngestResult:
    """Canonical parsed ingest payload spanning catalog and analytical records."""

    run: Run
    runs: list[Run] = field(default_factory=list)
    data_import: DataImport | None = None
    subjects: list[Subject] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    run_samples: list[RunSample] = field(default_factory=list)
    run_relationships: list[RunRelationship] = field(default_factory=list)
    analysis_types: list[AnalysisType] = field(default_factory=list)
    analysis_methods: list[AnalysisMethod] = field(default_factory=list)
    data_contracts: list[DataContract] = field(default_factory=list)
    data_contract_analysis_types: list[DataContractAnalysisType] = field(
        default_factory=list
    )
    run_contracts: list[RunContract] = field(default_factory=list)
    run_contract_samples: list[RunContractSample] = field(default_factory=list)
    data_contract_fields: list[DataContractField] = field(default_factory=list)
    files: list[FileAsset] = field(default_factory=list)
    file_links: list[FileLink] = field(default_factory=list)
    sample_sets: list[SampleSet] = field(default_factory=list)
    sample_set_members: list[SampleSetMember] = field(default_factory=list)
    analytics_batch: AnalyticsIngestBatch = field(default_factory=AnalyticsIngestBatch)
    bulk_loads: list[AnalyticsBulkLoad] = field(default_factory=list)
    staged_loads: list[AnalyticsStagedLoad] = field(default_factory=list)
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
    """Merge analytics batch collections by concatenating each modeled row list."""

    merged = AnalyticsIngestBatch()
    for batch in batches:
        for field_name in merged.model_fields:
            getattr(merged, field_name).extend(getattr(batch, field_name))
    return merged
