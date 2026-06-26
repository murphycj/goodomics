from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from goodomics.ingest.base import NormalizedIngestResult
from goodomics.profiles.base import profile as make_profile
from goodomics.profiles.registry import built_in_data_profile
from goodomics.projects import analytics_path_for_project
from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    DataImport,
    DataProfile,
    Feature,
    FeatureCall,
    FeatureValueNumeric,
    FileAsset,
    FileLink,
    MetricDefinition,
    ProfilePayload,
    Run,
    RunSample,
    Sample,
    SampleMetricNumeric,
    SampleMetricString,
)
from goodomics.sources import SourceSpec, register_source
from goodomics.storage.database import ensure_sqlite_parent, resolve_database_url
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import SQLModelGoodomicsStore

ParserFunction = Callable[[Any, "ParserOutput"], None]


@dataclass
class CustomParserResult:
    # Small summary object for notebook users; detailed records live in SQL and
    # DuckDB rather than being returned from the parse call.
    run_id: str
    data_import_id: str
    samples_ingested: int
    profiles_ingested: int
    metrics_ingested: int
    feature_values_ingested: int
    feature_calls_ingested: int
    payloads_ingested: int
    files_registered: int
    database_url: str
    analytics_path: Path


@dataclass
class ParserOutput:
    """Collect normalized records emitted by a user-authored parser.

    Parser functions receive one of these as `out`. Each helper method appends
    catalog records, analytical records, or both, while hiding the lower-level
    `Run`, `RunSample`, `DataImport`, and DuckDB batch objects from notebook
    code.
    """

    run_id: str
    parser_key: str
    project_id: str
    assay: str | None = None
    data_import_id: str | None = None
    data_profiles: dict[str, DataProfile] = field(default_factory=dict)
    samples: dict[str, Sample] = field(default_factory=dict)
    run_samples: dict[str, RunSample] = field(default_factory=dict)
    files: dict[str, FileAsset] = field(default_factory=dict)
    file_links: list[FileLink] = field(default_factory=list)
    batch: AnalyticsIngestBatch = field(default_factory=AnalyticsIngestBatch)

    def profile(self, data_profile: DataProfile | str, **kwargs: Any) -> DataProfile:
        """Register a data profile that this parser can emit.

        Pass a full `DataProfile` when you have one, or pass a profile ID plus
        keyword fields accepted by `goodomics.profile(...)`. The profile is
        written to the SQL catalog during ingest and can then be referenced by
        later metric, feature, call, or payload records.
        """
        if isinstance(data_profile, DataProfile):
            resolved = data_profile
        else:
            resolved = make_profile(
                data_profile,
                producer_tool=self.parser_key,
                **kwargs,
            )
        self.data_profiles[resolved.data_profile_id] = resolved
        return resolved

    def sample(
        self,
        sample_id: str,
        *,
        sample_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Sample:
        """Register a biological/material sample and its processed-sample row.

        Custom parser observations are stored at the run-sample grain, so adding
        a sample also creates the `RunSample` that ties this run to that sample.
        Most parser helpers call this automatically when they receive
        `sample_id`, but calling it directly lets users attach sample names or
        metadata before emitting observations.
        """
        sample = self.samples.get(sample_id)
        if sample is None:
            # Samples imply run-samples for the custom parser path because
            # Goodomics persists observations at the processed-sample grain.
            sample = Sample(
                sample_id=sample_id,
                project_id=self.project_id,
                sample_name=sample_name,
                metadata_json=dict(metadata or {}),
            )
            self.samples[sample_id] = sample
            self.run_samples[sample_id] = RunSample(
                run_sample_id=self.run_sample_id(sample_id),
                project_id=self.project_id,
                run_id=self.run_id,
                sample_id=sample_id,
                assay=self.assay,
                status="complete",
                metadata_json={"source": self.parser_key},
            )
        return sample

    def metric(
        self,
        name: str,
        value: float | int | str,
        *,
        sample_id: str | None = None,
        profile: DataProfile | str | None = None,
        unit: str | None = None,
    ) -> None:
        """Emit a sample-level or run-level metric.

        Numeric values go to `sample_metric_numeric`; strings go to
        `sample_metric_string`. When `sample_id` is omitted, the metric belongs
        to the run rather than a specific sample. When `profile` is omitted,
        Goodomics creates a default `user:<parser-key>:metrics` profile so simple
        metric-only parsers stay lightweight.
        """
        profile_id = self._profile_id(profile)
        metric_key = f"{profile_id}:{name}"
        value_type = "numeric" if isinstance(value, int | float) else "string"
        # Metric definitions are the metric catalog; metric observations below
        # are the actual sample/run values stored in DuckDB.
        self._add_metric_definition(metric_key, name, profile_id, value_type, unit)
        common = {
            "data_profile_key": profile_id,
            "run_id": self.run_id,
            "run_sample_key": self.run_sample_id(sample_id)
            if sample_id is not None
            else None,
            "sample_key": sample_id,
            "metric_key": metric_key,
        }
        if sample_id is not None:
            self.sample(sample_id)
        if value_type == "numeric":
            self.batch.sample_metric_numeric.append(
                SampleMetricNumeric(value=float(value), **common)
            )
        else:
            self.batch.sample_metric_string.append(
                SampleMetricString(value=str(value), **common)
            )

    def feature_value(
        self,
        *,
        sample_id: str,
        feature_id: str,
        value: float | int,
        profile: DataProfile | str,
        feature_type: str = "gene",
        value_semantics: str = "value",
    ) -> None:
        """Emit a numeric value for a feature in one sample.

        Use this for matrix-like data such as gene expression, protein
        abundance, methylation beta values, or generic feature measurements.
        `feature_type` controls the feature namespace, so `gene` and `protein`
        values with the same `feature_id` remain distinct.
        """
        data_profile_key = self._profile_id(profile)
        feature_key = f"{feature_type}:{feature_id}"
        self.sample(sample_id)
        # Feature records are dimensional rows. They are deduped before writing
        # so parser loops can emit values naturally without managing a feature
        # registry themselves.
        self.batch.features.append(
            Feature(
                feature_key=feature_key,
                feature_id=feature_id,
                feature_type=feature_type,
                symbol=feature_id,
            )
        )
        self.batch.feature_value_numeric.append(
            FeatureValueNumeric(
                data_profile_key=data_profile_key,
                run_id=self.run_id,
                run_sample_key=self.run_sample_id(sample_id),
                sample_key=sample_id,
                feature_key=feature_key,
                value=float(value),
                value_semantics=value_semantics,
            )
        )

    def feature_call(
        self,
        *,
        sample_id: str,
        feature_id: str,
        call_code: str,
        profile: DataProfile | str,
        feature_type: str = "gene",
        call_label: str | None = None,
    ) -> None:
        """Emit a categorical call for a feature in one sample.

        Use this for observations such as copy-number calls, mutation presence,
        binary assay calls, or other discrete feature states. `call_code` is the
        stable machine-readable value; `call_label` can be a display label.
        """
        data_profile_key = self._profile_id(profile)
        feature_key = f"{feature_type}:{feature_id}"
        self.sample(sample_id)
        self.batch.features.append(
            Feature(
                feature_key=feature_key,
                feature_id=feature_id,
                feature_type=feature_type,
                symbol=feature_id,
            )
        )
        self.batch.feature_call.append(
            FeatureCall(
                data_profile_key=data_profile_key,
                run_id=self.run_id,
                run_sample_key=self.run_sample_id(sample_id),
                sample_key=sample_id,
                feature_key=feature_key,
                call_code=call_code,
                call_label=call_label,
            )
        )

    def payload(
        self,
        name: str,
        rows: list[dict[str, Any]],
        *,
        profile: DataProfile | str,
        payload_kind: str = "table",
        sample_id: str | None = None,
    ) -> None:
        """Attach a small inline payload table to a data profile.

        Payloads preserve source-shaped rows that do not yet deserve a dedicated
        typed analytical table. They are useful for lightweight provenance,
        source summaries, or early parser development. Large payloads should
        eventually move to file-backed storage or typed DuckDB tables.
        """
        data_profile_key = self._profile_id(profile)
        if sample_id is not None:
            self.sample(sample_id)
        columns = list(rows[0]) if rows else []
        self.batch.profile_payloads.append(
            ProfilePayload(
                payload_id=f"{self.run_id}:{name}:{len(self.batch.profile_payloads)}",
                data_profile_key=data_profile_key,
                run_id=self.run_id,
                run_sample_key=self.run_sample_id(sample_id)
                if sample_id is not None
                else None,
                payload_name=name,
                payload_kind=payload_kind,
                storage_format="inline_json",
                row_count=len(rows),
                metadata_json={
                    "columns": columns,
                    "rows": rows,
                    "sample_key": sample_id,
                },
            )
        )

    def file(self, path: str | Path, *, role: str = "source") -> FileAsset:
        """Register a file or directory as evidence for this parser run.

        This records file metadata and creates a link from the file to the
        current run/import. The file is not copied; custom parsers currently
        record the path that the user provided.
        """
        resolved = Path(path)
        file_id = f"{self.run_id}:{role}:{_path_digest(resolved)}:{resolved.name}"
        file = FileAsset(
            file_id=file_id,
            project_id=self.project_id,
            path=str(resolved),
            file_role=role,
            format=resolved.suffix.removeprefix(".") if resolved.is_file() else "dir",
            size_bytes=_path_size(resolved) if resolved.exists() else None,
            sha256=_path_hash(resolved) if resolved.exists() else None,
            created_at=datetime.now(UTC),
            metadata_json={"source": self.parser_key},
        )
        self.files[file_id] = file
        self.file_links.append(
            FileLink(
                file_id=file_id,
                project_id=self.project_id,
                data_import_id=self.data_import_id,
                run_id=self.run_id,
                link_role=role,
            )
        )
        return file

    def run_sample_id(self, sample_id: str) -> str:
        """Return the deterministic processed-sample ID for this run/sample."""
        return f"{self.run_id}:{sample_id}"

    def to_normalized_result(
        self,
        *,
        source_path: str | None,
        project_slug: str | None,
    ) -> NormalizedIngestResult:
        # Compile the notebook-friendly builder into the same normalized ingest
        # contract used by built-in parsers.
        data_import = DataImport(
            data_import_id=self.data_import_id or self.run_id,
            project_id=self.project_id,
            source_type=self.parser_key,
            source_path=source_path,
            importer_name=self.parser_key,
            status="complete",
            summary_json={
                "samples": len(self.samples),
                "profiles": len(self.data_profiles),
            },
            metadata_json={"source": "custom_parser"},
        )
        run = Run(
            run_id=self.run_id,
            project_id=self.project_id,
            data_import_id=data_import.data_import_id,
            project=project_slug,
            name=self.run_id,
            run_kind="imported_result",
            assay=self.assay,
            pipeline_name=self.parser_key,
            status="complete",
            metadata_json={"source": "custom_parser"},
            samples=sorted(self.samples.values(), key=lambda sample: sample.sample_id),
        )
        return NormalizedIngestResult(
            run=run,
            data_import=data_import,
            samples=sorted(self.samples.values(), key=lambda sample: sample.sample_id),
            run_samples=sorted(
                self.run_samples.values(),
                key=lambda run_sample: run_sample.run_sample_id,
            ),
            data_profiles=sorted(
                self.data_profiles.values(),
                key=lambda data_profile: data_profile.data_profile_id,
            ),
            files=sorted(self.files.values(), key=lambda file: file.file_id),
            file_links=self.file_links,
            analytics_batch=self._deduped_batch(),
        )

    def _profile_id(self, value: DataProfile | str | None) -> str:
        """Resolve a user-facing profile argument to a cataloged profile ID."""
        if value is None:
            # Metric-only parsers should work without forcing users to learn
            # profile modeling before they can persist a useful first result.
            default = default_metric_profile(self.parser_key)
            self.profile(default)
            return default.data_profile_id
        if isinstance(value, DataProfile):
            self.profile(value)
            return value.data_profile_id
        if value not in self.data_profiles:
            self.profile(_profile_from_id(value, self.parser_key))
        return value

    def _add_metric_definition(
        self,
        metric_key: str,
        name: str,
        namespace: str,
        value_type: str,
        unit: str | None,
    ) -> None:
        """Add one metric definition unless it is already staged."""
        if any(
            metric.metric_key == metric_key for metric in self.batch.metric_definitions
        ):
            return
        self.batch.metric_definitions.append(
            MetricDefinition(
                metric_key=metric_key,
                metric_id=name,
                namespace=namespace,
                metric_name=name,
                display_name=name,
                value_type="numeric" if value_type == "numeric" else "string",
                unit=unit,
                producer_tool=self.parser_key,
            )
        )

    def _deduped_batch(self) -> AnalyticsIngestBatch:
        """Remove duplicate dimension records emitted by natural parser loops."""
        self.batch.features = list(
            {feature.feature_key: feature for feature in self.batch.features}.values()
        )
        return self.batch


@dataclass
class CustomParser:
    key: str
    label: str
    function: ParserFunction
    profiles: list[DataProfile] = field(default_factory=list)

    def __call__(self, value: Any, out: ParserOutput) -> None:
        self.function(value, out)

    @property
    def source_spec(self) -> SourceSpec:
        return SourceSpec(
            key=self.key,
            label=self.label,
            ingest=self.ingest,
            parser=self.function,
            data_profile_provider=self.profiles,
            ingest_parameters=(
                "project",
                "assay",
                "run_id",
                "database_url",
                "analytics_path",
            ),
        )

    def ingest(
        self,
        value: Any,
        *,
        project: str | None = None,
        assay: str | None = None,
        run_id: str | None = None,
        database_url: str | None = None,
        analytics_path: Path | None = None,
    ) -> CustomParserResult:
        # The decorated parser path owns persistence so user code only has to
        # describe how to read values into ParserOutput.
        resolved_database_url = resolve_database_url(database_url)
        ensure_sqlite_parent(resolved_database_url)
        store = SQLModelGoodomicsStore(resolved_database_url)
        project_record = asyncio.run(store.ensure_project(project))
        resolved_run_id = run_id or _default_run_id(value, self.key)
        data_import_id = resolved_run_id
        out = ParserOutput(
            run_id=resolved_run_id,
            parser_key=self.key,
            project_id=project_record.project_id,
            assay=assay,
            data_import_id=data_import_id,
        )
        for data_profile in self.profiles:
            out.profile(data_profile)
        self.function(value, out)
        normalized = out.to_normalized_result(
            source_path=str(value) if isinstance(value, str | Path) else None,
            project_slug=project_record.slug,
        )
        asyncio.run(
            store.replace_run_catalog(
                normalized.run,
                data_import=normalized.data_import,
                samples=normalized.samples,
                run_samples=normalized.run_samples,
                data_profiles=normalized.data_profiles,
                files=normalized.files,
                file_links=normalized.file_links,
            )
        )
        resolved_analytics_path = analytics_path or analytics_path_for_project(
            Path(".goodomics"), project_record.project_id
        )
        DuckDBAnalyticsStore(resolved_analytics_path).replace_run_data(
            resolved_run_id,
            normalized.analytics_batch,
        )
        return CustomParserResult(
            run_id=resolved_run_id,
            data_import_id=data_import_id,
            samples_ingested=len(normalized.samples),
            profiles_ingested=len(normalized.data_profiles),
            metrics_ingested=len(normalized.analytics_batch.sample_metric_numeric)
            + len(normalized.analytics_batch.sample_metric_string),
            feature_values_ingested=len(
                normalized.analytics_batch.feature_value_numeric
            ),
            feature_calls_ingested=len(normalized.analytics_batch.feature_call),
            payloads_ingested=len(normalized.analytics_batch.profile_payloads),
            files_registered=len(normalized.files),
            database_url=resolved_database_url,
            analytics_path=resolved_analytics_path,
        )


def parser(
    *,
    key: str,
    label: str | None = None,
    profiles: Iterable[DataProfile | str] | None = None,
) -> Callable[[ParserFunction], CustomParser]:
    def decorate(function: ParserFunction) -> CustomParser:
        custom_parser = CustomParser(
            key=key,
            label=label or key,
            function=function,
            profiles=[_coerce_profile(item, key) for item in profiles or []],
        )
        register_source(custom_parser.source_spec, replace=True)
        return custom_parser

    return decorate


def default_metric_profile(parser_key: str) -> DataProfile:
    return make_profile(
        f"user:{parser_key}:metrics",
        name=f"{parser_key} metrics",
        data_type="generic_metrics",
        producer_tool=parser_key,
        feature_type="metric",
        value_type="mixed",
        query_modes=["sample", "metric", "cohort"],
        description=f"Custom metrics emitted by the {parser_key} parser.",
    )


def _coerce_profile(value: DataProfile | str, parser_key: str) -> DataProfile:
    if isinstance(value, DataProfile):
        return value
    return _profile_from_id(value, parser_key)


def _profile_from_id(value: str, parser_key: str) -> DataProfile:
    try:
        return built_in_data_profile(value)
    except KeyError:
        pass
    return make_profile(
        value,
        name=value,
        data_type="generic_metrics",
        producer_tool=parser_key,
        feature_type="metric",
        value_type="mixed",
        query_modes=["sample", "metric", "cohort"],
    )


def _default_run_id(value: Any, parser_key: str) -> str:
    if isinstance(value, str | Path):
        path = Path(value)
        if path.name:
            return path.stem if path.is_file() else path.name
    return f"{parser_key}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


def _path_digest(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _path_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        _update_hash(digest, path)
    else:
        for item in sorted(path.rglob("*")):
            if item.is_file():
                digest.update(str(item.relative_to(path)).encode("utf-8"))
                _update_hash(digest, item)
    return digest.hexdigest()


def _update_hash(digest: Any, path: Path) -> None:
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
