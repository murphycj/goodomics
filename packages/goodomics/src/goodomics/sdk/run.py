"""Python SDK helpers for recording Goodomics run context.

This module implements the small Python SDK entry point:

```python
from goodomics import run

with run("my-run") as ctx:
    ctx.log_metric("S1", "pct_mapped", 97.2)
```

The SDK buffers user calls in memory, then flushes them into the same catalog
and analytics storage path used by parser/ingest workflows. SQL stores durable
entities and relationships; DuckDB stores metric observations.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

from goodomics.profiles.registry import built_in_data_profile
from goodomics.profiles.sdk import GOODOMICS_SDK_METRICS
from goodomics.projects import analytics_path_for_project
from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    DataProfileField,
    Run,
    RunSample,
    Sample,
    UnresolvedAnalyticalRecord,
)
from goodomics.storage.analytics_resolution import (
    resolve_analytics_batch_catalog_ids,
    resolve_catalog_id,
)
from goodomics.storage.database import ensure_sqlite_parent, resolve_database_url

JsonMetricValue = float | int | str
"""Metric value accepted by the lightweight SDK logging API."""


@dataclass(frozen=True)
class LoggedMetric:
    """Metric buffered by the SDK before persistence.

    Buffered metrics are converted into DuckDB analytical rows during
    :meth:`GoodomicsRun.flush`; they are not stored directly in the SQL catalog.
    """

    sample_id: str | None
    """Stable sample ID for sample-scoped metrics, or ``None`` for run-level metrics."""

    name: str
    """Metric field name supplied by the SDK caller."""

    value: JsonMetricValue
    """Metric value before conversion into a typed analytical value column."""

    unit: str | None = None
    """Optional unit label, such as ``"percent"`` or ``"reads"``."""


@dataclass
class GoodomicsRun:
    """In-memory SDK context for recording a Goodomics run.

    A ``GoodomicsRun`` buffers metrics and files while user code runs. Calling
    :meth:`flush`, or exiting a successful ``with run(...)`` block, writes the
    run catalog records to SQL and metric observations to DuckDB.

    Field-level docstrings below document constructor arguments and dataclass
    attributes for API reference pages and editor hover. The class docstring
    stays focused on lifecycle and storage behavior.
    """

    name: str
    """Public run label used as the SDK run ID."""

    project: str | None = None
    """Project ID, slug, display-ish name, or ``None`` for the default workspace."""

    assay: str | None = None
    """Optional assay label copied onto run, run-sample, and profile records."""

    database_url: str | None = None
    """Optional SQL catalog database URL override."""

    analytics_path: Path | None = None
    """Optional direct DuckDB analytics file override."""

    analytics_root: Path = Path(".goodomics")
    """Root directory used for project-scoped DuckDB files."""

    auto_persist: bool = True
    """Whether a successful context-manager exit should automatically flush."""

    metrics: list[LoggedMetric] = field(default_factory=list)
    """In-memory metric buffer populated by :meth:`log_metric`."""

    files: list[Path] = field(default_factory=list)
    """In-memory file path buffer populated by :meth:`log_file`."""

    # Prevent duplicate writes if flush() is called manually and then the context
    # manager exits, or if user code calls flush() more than once.
    _flushed: bool = field(default=False, init=False, repr=False)

    def __enter__(self) -> GoodomicsRun:
        """Enter a ``with`` block and return the mutable SDK run context."""

        # The object itself is the context manager state. User code records
        # metrics/files directly on this instance.
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Flush buffered data when a context manager exits successfully.

        Failed ``with`` blocks intentionally leave no partial SDK write behind.
        """

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
        """Buffer a metric for this run.

        Args:
            sample_id: Stable sample ID for sample-scoped metrics, or ``None``
                for run-level metrics.
            name: Metric field name, such as ``"pct_mapped"``.
            value: Numeric or string metric value.
            unit: Optional unit label.
        """

        # Keep logging side-effect-free until flush(). This makes the SDK cheap
        # to use inside notebooks/scripts and avoids partial persistence if user
        # code raises before the context manager exits.
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
        """Alias for :meth:`log_metric` with ``sample_id`` as a keyword argument."""

        # Convenience alias with sample_id as a keyword argument. This is handy
        # for users who think of the metric name/value first.
        self.log_metric(sample_id, name, value, unit=unit)

    def log_file(self, path: str | Path) -> None:
        """Buffer a file path associated with this run.

        File persistence is reserved for a later SDK path; this method records
        the path in memory so the public API shape is already available.
        """

        # File logging is currently buffered for future catalog/file persistence.
        # Metrics are the only SDK payload written by flush() today.
        self.files.append(Path(path))

    def file(self, path: str | Path) -> None:
        """Alias for :meth:`log_file`."""

        # Short alias to match metric().
        self.log_file(path)

    def to_analytics_batch(
        self,
        *,
        run_id: str | None = None,
        data_profile_id: str | None = None,
    ) -> AnalyticsIngestBatch:
        """Convert buffered metrics into an unresolved analytics batch.

        The returned rows still contain public labels like ``run_id`` and
        ``field_id``. :meth:`flush` resolves those labels to SQL-owned integer
        IDs after it writes the catalog records.
        """

        # Build the unresolved DuckDB batch. "Unresolved" means rows still carry
        # public labels like run_id/sample_id/field_id; flush() resolves those
        # labels to SQL-owned integer IDs after the catalog write.
        resolved_run_id = run_id or self.name
        resolved_profile_id = data_profile_id or GOODOMICS_SDK_METRICS
        metrics: list[UnresolvedAnalyticalRecord] = []

        for metric in self.metrics:
            # Each SDK metric name becomes a stable profile field scoped to
            # the SDK data profile.
            metric_id = f"{resolved_profile_id}:{metric.name}"
            common: dict[str, Any] = {
                "data_profile_id": resolved_profile_id,
                "run_id": resolved_run_id,
                "run_sample_id": (
                    f"{resolved_run_id}:{metric.sample_id}"
                    if metric.sample_id is not None
                    else None
                ),
                "sample_id": metric.sample_id,
                "field_id": metric_id,
            }
            if _is_numeric_metric(metric.value):
                # Numeric and string metrics share the sample_metrics table but
                # use different typed value columns.
                metrics.append(
                    UnresolvedAnalyticalRecord(
                        **common,
                        value_type="numeric",
                        value_numeric=float(metric.value),
                    )
                )
            else:
                # The SDK accepts ints/floats/strings only. Non-numeric values
                # are normalized to strings for consistent storage.
                metrics.append(
                    UnresolvedAnalyticalRecord(
                        **common,
                        value_type="string",
                        value_string=str(metric.value),
                    )
                )

        return AnalyticsIngestBatch(sample_metrics=metrics)

    def flush(self) -> None:
        """Persist buffered SDK data to the SQL catalog and DuckDB analytics store.

        The method is idempotent for one ``GoodomicsRun`` instance: later calls
        return immediately after a successful flush.
        """

        # flush() is the single persistence boundary for the SDK. It is safe to
        # call manually, and __exit__ will no-op afterward because of _flushed.
        if self._flushed:
            return
        # These imports are intentionally local so importing goodomics.sdk.run
        # does not eagerly import DuckDB/SQLModel storage machinery for users who
        # only construct a run object or inspect SDK helpers.
        from goodomics.storage.duckdb import DuckDBAnalyticsStore
        from goodomics.storage.sqlalchemy import (
            SQLModelGoodomicsStore,
            catalog_id_maps_from_records,
        )

        # SQL owns the catalog shape: project, run, samples, run-samples, and
        # the data profile that says where queryable observations live.
        # resolve_database_url() honors the explicit SDK argument, environment
        # variables, and Goodomics defaults.
        database_url = resolve_database_url(self.database_url)
        # SQLite URLs may point at a file in a not-yet-created directory.
        ensure_sqlite_parent(database_url)
        store = SQLModelGoodomicsStore(database_url)
        # ensure_project() returns the default project when self.project is None,
        # or creates/resolves the requested project otherwise.
        project = asyncio.run(store.ensure_project(self.project))
        run_id = self.name
        # Derive sample catalog rows from logged sample-scoped metrics. Run-level
        # metrics have sample_id=None and therefore do not create run_samples.
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
            # run_sample_id is the processed-sample identity: this sample in
            # this run. The SDK uses "<run_id>:<sample_id>" as a stable label.
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
        data_profile_id = GOODOMICS_SDK_METRICS
        # Metrics are queryable through a data profile. The built-in profile
        # provides the stable semantic contract; SDK-specific metric names become
        # profile fields below.
        data_profiles = (
            [
                built_in_data_profile(data_profile_id).model_copy(
                    update={"assay": self.assay}
                )
            ]
            if self.metrics
            else []
        )
        # The SQL catalog run stores execution/context metadata and links to the
        # stable samples. It does not store the metric values themselves.
        catalog_run = Run(
            run_id=run_id,
            project_id=project.project_id,
            project=project.slug,
            name=self.name,
            assay=self.assay,
            samples=samples,
            metadata_json={"source": "goodomics-sdk"},
        )
        # Replace the catalog slice for this run so repeated SDK writes update
        # the run, samples/run_samples, profile, and field definitions together.
        catalog_result = asyncio.run(
            store.replace_run_catalog(
                catalog_run,
                samples=samples,
                run_samples=run_samples,
                data_profiles=data_profiles,
                data_profile_fields=_metric_profile_fields(
                    self.metrics,
                    data_profile_id=data_profile_id,
                ),
            )
        )
        if self.metrics:
            # DuckDB owns the observation values themselves, keeping SDK metrics
            # on the same analytical path as parser and ingest metrics.
            #
            # catalog_id_maps maps public labels like run_id and field_id to the
            # integer IDs SQL assigned during replace_run_catalog().
            catalog_id_maps = catalog_id_maps_from_records(catalog_result)
            # Resolve every analytical row to those integer IDs before writing
            # to DuckDB. This keeps the analytical store aligned with the SQL
            # catalog identity model.
            resolved_batch = resolve_analytics_batch_catalog_ids(
                self.to_analytics_batch(
                    run_id=run_id,
                    data_profile_id=data_profile_id,
                ),
                catalog_id_maps,
            )
            # replace_run_data() deletes/replaces by the resolved integer run ID,
            # not the public label, because DuckDB stores catalog IDs as ints.
            resolved_duckdb_run_id = resolve_catalog_id(
                "run_id", run_id, catalog_id_maps
            )
            analytics_path = self._resolved_analytics_path(project.project_id)
            DuckDBAnalyticsStore(analytics_path).replace_run_data(
                resolved_duckdb_run_id,
                resolved_batch,
            )
        # Mark flushed after all catalog/analytics writes complete successfully.
        self._flushed = True

    def _resolved_analytics_path(self, project_id: str) -> Path:
        """Resolve the DuckDB analytics path for a project."""

        # Precedence: explicit SDK argument, environment override, environment
        # root, then the dataclass default root.
        if self.analytics_path is not None:
            return self.analytics_path
        env_path = os.environ.get("GOODOMICS_ANALYTICS_PATH")
        if env_path:
            # Direct file path override is useful when one process should write
            # a single known DuckDB database regardless of project.
            return Path(env_path)
        env_root = os.environ.get("GOODOMICS_ANALYTICS_ROOT")
        analytics_root = Path(env_root) if env_root else self.analytics_root
        # Project-scoped analytics paths keep separate project workspaces from
        # sharing one DuckDB file by accident.
        return analytics_path_for_project(analytics_root, project_id)


def _is_numeric_metric(value: JsonMetricValue) -> bool:
    """Return whether an SDK metric value should use the numeric value column."""

    # bool is a subclass of int in Python, but SDK booleans should not be stored
    # as numeric QC values.
    return isinstance(value, int | float) and not isinstance(value, bool)


def _metric_profile_fields(
    metrics: list[LoggedMetric],
    *,
    data_profile_id: str,
) -> list[DataProfileField]:
    """Build data profile field definitions for buffered SDK metrics."""

    # The SDK profile is stable, but each metric name becomes a field inside
    # that profile. Field definitions let report/query builders discover units,
    # labels, value types, and the analytical column that stores the value.
    fields: dict[str, DataProfileField] = {}
    for metric in metrics:
        field_id = f"{data_profile_id}:{metric.name}"
        value_type = "numeric" if _is_numeric_metric(metric.value) else "string"
        # Multiple samples may log the same metric. setdefault keeps the first
        # field definition and prevents duplicate field rows for the run.
        fields.setdefault(
            field_id,
            DataProfileField(
                data_profile_id=data_profile_id,
                field_id=field_id,
                field_role="metric",
                entity_scope="run_sample",
                display_name=metric.name,
                value_type=value_type,
                unit=metric.unit,
                query_ref_json={
                    # query_ref_json tells profile-first query compilation how
                    # to find this field in the generic sample_metrics table.
                    "table": "sample_metrics",
                    "field_column": "field_id",
                    "field_value": field_id,
                    "value_column": (
                        "value_numeric" if value_type == "numeric" else "value_string"
                    ),
                },
                metadata_json={"producer_tool": "goodomics-sdk"},
            ),
        )
    # Deterministic ordering keeps catalog writes and tests stable.
    return [fields[key] for key in sorted(fields)]


def run(
    name: str,
    *,
    project: str | None = None,
    assay: str | None = None,
    database_url: str | None = None,
    analytics_path: str | Path | None = None,
    auto_persist: bool = True,
) -> GoodomicsRun:
    """Create a Goodomics SDK run context.

    Args:
        name: Public run label used as the SDK run ID.
        project: Project ID, slug, display-ish name, or ``None`` for the default
            workspace.
        assay: Optional assay label copied onto run, run-sample, and profile
            records.
        database_url: Optional SQL catalog database URL override.
        analytics_path: Optional direct DuckDB analytics file override.
        auto_persist: Whether successful context-manager exit should call
            :meth:`GoodomicsRun.flush`.

    Returns:
        A mutable :class:`GoodomicsRun` context.
    """

    # Public convenience factory. Keeping this as a function lets users write
    # goodomics.run("...") without importing the GoodomicsRun dataclass directly.
    return GoodomicsRun(
        name=name,
        project=project,
        assay=assay,
        database_url=database_url,
        analytics_path=Path(analytics_path) if analytics_path is not None else None,
        auto_persist=auto_persist,
    )
