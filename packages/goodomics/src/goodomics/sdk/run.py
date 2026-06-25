from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

from goodomics.projects import analytics_path_for_project
from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    DataProfile,
    MetricDefinition,
    Run,
    RunSample,
    Sample,
    SampleMetricNumeric,
    SampleMetricString,
)
from goodomics.storage.database import ensure_sqlite_parent, resolve_database_url

JsonMetricValue = float | int | str


@dataclass(frozen=True)
class LoggedMetric:
    # Lightweight SDK buffer record; persisted metrics are materialized into
    # DuckDB analytics tables rather than the SQL control store.
    sample_id: str | None
    name: str
    value: JsonMetricValue
    unit: str | None = None


@dataclass
class GoodomicsRun:
    name: str
    project: str | None = None
    assay: str | None = None
    database_url: str | None = None
    analytics_path: Path | None = None
    analytics_root: Path = Path(".goodomics")
    auto_persist: bool = True
    metrics: list[LoggedMetric] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    _flushed: bool = field(default=False, init=False, repr=False)

    def __enter__(self) -> GoodomicsRun:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Treat the context manager as the normal persistence boundary: failed
        # blocks leave no partial SDK write behind, while successful blocks flush.
        if exc_type is None and self.auto_persist:
            self.flush()
        return None

    def log_metric(
        self,
        sample_id: str | None,
        name: str,
        value: JsonMetricValue,
        *,
        unit: str | None = None,
    ) -> None:
        self.metrics.append(
            LoggedMetric(sample_id=sample_id, name=name, value=value, unit=unit)
        )

    def metric(
        self,
        name: str,
        value: JsonMetricValue,
        *,
        sample_id: str | None = None,
        unit: str | None = None,
    ) -> None:
        self.log_metric(sample_id, name, value, unit=unit)

    def log_file(self, path: str | Path) -> None:
        self.files.append(Path(path))

    def file(self, path: str | Path) -> None:
        self.log_file(path)

    def to_analytics_batch(
        self,
        *,
        run_id: str | None = None,
        data_profile_key: str | None = None,
    ) -> AnalyticsIngestBatch:
        resolved_run_id = run_id or self.name
        resolved_profile_key = data_profile_key or f"{resolved_run_id}:sdk_metrics"
        definitions: dict[str, MetricDefinition] = {}
        numeric_values: list[SampleMetricNumeric] = []
        string_values: list[SampleMetricString] = []

        for metric in self.metrics:
            # Each SDK metric name becomes a stable DuckDB metric definition
            # scoped to this run's SDK data profile.
            metric_key = f"{resolved_profile_key}:{metric.name}"
            value_type = "numeric" if _is_numeric_metric(metric.value) else "string"
            definitions.setdefault(
                metric_key,
                MetricDefinition(
                    metric_key=metric_key,
                    metric_id=metric.name,
                    namespace=resolved_profile_key,
                    metric_name=metric.name,
                    display_name=metric.name,
                    value_type=value_type,
                    unit=metric.unit,
                    producer_tool="goodomics-sdk",
                ),
            )
            common: dict[str, Any] = {
                "data_profile_key": resolved_profile_key,
                "run_id": resolved_run_id,
                "run_sample_key": f"{resolved_run_id}:{metric.sample_id}"
                if metric.sample_id is not None
                else None,
                "sample_key": metric.sample_id,
                "metric_key": metric_key,
            }
            if _is_numeric_metric(metric.value):
                numeric_values.append(
                    SampleMetricNumeric(value=float(metric.value), **common)
                )
            else:
                string_values.append(
                    SampleMetricString(value=str(metric.value), **common)
                )

        return AnalyticsIngestBatch(
            metric_definitions=list(definitions.values()),
            sample_metric_numeric=numeric_values,
            sample_metric_string=string_values,
        )

    def flush(self) -> None:
        if self._flushed:
            return
        from goodomics.storage.duckdb import DuckDBAnalyticsStore
        from goodomics.storage.sqlalchemy import SQLModelGoodomicsStore

        # SQL owns the catalog shape: project, run, samples, run-samples, and
        # the data profile that says where queryable observations live.
        database_url = self._resolved_database_url()
        ensure_sqlite_parent(database_url)
        store = SQLModelGoodomicsStore(database_url)
        project = asyncio.run(store.ensure_project(self.project))
        run_id = self.name
        sample_ids = sorted(
            {
                metric.sample_id
                for metric in self.metrics
                if metric.sample_id is not None
            }
        )
        samples = [
            Sample(sample_id=sample_id, project_id=project.project_id)
            for sample_id in sample_ids
        ]
        run_samples = [
            RunSample(
                run_sample_id=f"{run_id}:{sample_id}",
                project_id=project.project_id,
                run_id=run_id,
                sample_id=sample_id,
                assay=self.assay,
                status="complete",
                metadata_json={"source": "goodomics-sdk"},
            )
            for sample_id in sample_ids
        ]
        data_profile_key = f"{run_id}:sdk_metrics"
        data_profiles = (
            [
                DataProfile(
                    data_profile_id=data_profile_key,
                    project_id=project.project_id,
                    run_id=run_id,
                    name="SDK metrics",
                    data_type="generic_metrics",
                    assay=self.assay,
                    producer_tool="goodomics-sdk",
                    value_type="mixed",
                    query_modes_json={"sample_metrics": True},
                )
            ]
            if self.metrics
            else []
        )
        catalog_run = Run(
            run_id=run_id,
            project_id=project.project_id,
            project=project.slug,
            name=self.name,
            assay=self.assay,
            samples=samples,
            metadata_json={"source": "goodomics-sdk"},
        )
        asyncio.run(
            store.replace_run_catalog(
                catalog_run,
                samples=samples,
                run_samples=run_samples,
                data_profiles=data_profiles,
            )
        )
        if self.metrics:
            # DuckDB owns the observation values themselves, keeping SDK metrics
            # on the same analytical path as parser and ingest metrics.
            analytics_path = self._resolved_analytics_path(project.project_id)
            DuckDBAnalyticsStore(analytics_path).replace_run_data(
                run_id,
                self.to_analytics_batch(
                    run_id=run_id,
                    data_profile_key=data_profile_key,
                ),
            )
        self._flushed = True

    def _resolved_database_url(self) -> str:
        return resolve_database_url(self.database_url)

    def _resolved_analytics_path(self, project_id: str) -> Path:
        if self.analytics_path is not None:
            return self.analytics_path
        env_path = os.environ.get("GOODOMICS_ANALYTICS_PATH")
        if env_path:
            return Path(env_path)
        env_root = os.environ.get("GOODOMICS_ANALYTICS_ROOT")
        analytics_root = Path(env_root) if env_root else self.analytics_root
        return analytics_path_for_project(analytics_root, project_id)


def _is_numeric_metric(value: JsonMetricValue) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def run(
    name: str,
    *,
    project: str | None = None,
    assay: str | None = None,
    database_url: str | None = None,
    analytics_path: str | Path | None = None,
    auto_persist: bool = True,
) -> GoodomicsRun:
    return GoodomicsRun(
        name=name,
        project=project,
        assay=assay,
        database_url=database_url,
        analytics_path=Path(analytics_path) if analytics_path is not None else None,
        auto_persist=auto_persist,
    )
