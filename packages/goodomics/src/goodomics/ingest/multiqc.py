"""Ingest orchestration for MultiQC outputs into catalog and analytics stores."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from goodomics.analysis import QUALITY_CONTROL, analysis_method, resolve_analysis_type
from goodomics.parsers.multiqc import (
    MultiQCOutput,
    discover_multiqc_outputs,
    multiqc_upstream_run_id,
    parse_multiqc_bundle,
    parse_multiqc_outputs,
)
from goodomics.projects import analytics_path_for_project
from goodomics.schemas.models import (
    DataContractAnalysisType,
    DataImport,
    FileAsset,
    FileLink,
    Run,
    RunContract,
    RunContractSample,
    RunRelationship,
    RunSample,
    Sample,
    Subject,
)
from goodomics.storage.analytics_resolution import (
    resolve_analytics_batch_catalog_ids,
    resolve_catalog_id,
)
from goodomics.storage.database import (
    DEFAULT_DATABASE_URL,
    ensure_sqlite_parent,
)
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    SQLModelGoodomicsStore,
    catalog_id_maps_from_records,
)


@dataclass(frozen=True)
class MultiQCIngestResult:
    """Summary of a persisted MultiQC ingest run and storage targets."""

    run_id: str
    data_import_id: str
    outputs_found: int
    metrics_ingested: int
    payloads_ingested: int
    files_stored: int
    upstream_runs: int
    run_relationships: int
    database_url: str
    analytics_path: Path
    file_root: Path


def default_run_id(results: Path) -> str:
    """Infer a stable default run id from the results path."""

    name = results.resolve().name if results.name else "run"
    return name or f"run-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


def default_run_id_for_output(output: MultiQCOutput) -> str:
    """Infer a run id for one discovered MultiQC output bundle."""

    if output.root_dir.name == "multiqc" and output.root_dir.parent.name:
        return output.root_dir.parent.name
    if output.report_html is not None:
        stem = output.report_html.stem
        for suffix in ("_multiqc_report", "_multiqc"):
            if stem.endswith(suffix):
                stem = stem.removesuffix(suffix)
                break
        if stem:
            return stem
    return default_run_id(output.root_dir)


def ingest_multiqc_runs(
    results: Path,
    *,
    run_id: str | None = None,
    project: str | None = None,
    analysis_type_id: str = QUALITY_CONTROL,
    database_url: str = DEFAULT_DATABASE_URL,
    analytics_path: Path | None = None,
    file_root: Path = Path(".goodomics/files"),
) -> list[MultiQCIngestResult]:
    """Ingest one or more MultiQC outputs, grouping by inferred run id when needed."""

    outputs = discover_multiqc_outputs(results)
    if not outputs:
        raise ValueError(f"No MultiQC output found under {results}")
    if run_id is not None or len(outputs) == 1:
        return [
            ingest_multiqc(
                results,
                run_id=run_id,
                project=project,
                analysis_type_id=analysis_type_id,
                database_url=database_url,
                analytics_path=analytics_path,
                file_root=file_root,
            )
        ]

    grouped_outputs: dict[str, list[MultiQCOutput]] = {}
    for output in outputs:
        grouped_outputs.setdefault(default_run_id_for_output(output), []).append(output)

    return [
        _ingest_multiqc_outputs(
            grouped,
            run_id=group_run_id,
            project=project,
            analysis_type_id=analysis_type_id,
            database_url=database_url,
            analytics_path=analytics_path,
            file_root=file_root,
        )
        for group_run_id, grouped in sorted(grouped_outputs.items())
    ]


def ingest_multiqc(
    results: Path,
    *,
    run_id: str | None = None,
    project: str | None = None,
    analysis_type_id: str = QUALITY_CONTROL,
    database_url: str = DEFAULT_DATABASE_URL,
    analytics_path: Path | None = None,
    file_root: Path = Path(".goodomics/files"),
) -> MultiQCIngestResult:
    """Ingest a single parquet-backed MultiQC bundle path as one report run."""

    resolved_run_id = run_id or default_run_id(results)
    parsed = parse_multiqc_bundle(results, run_id=resolved_run_id)
    return _save_multiqc_parse_result(
        parsed,
        run_id=resolved_run_id,
        project=project,
        analysis_type_id=analysis_type_id,
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )


def _ingest_multiqc_outputs(
    outputs: list[MultiQCOutput],
    *,
    run_id: str,
    project: str | None,
    analysis_type_id: str,
    database_url: str,
    analytics_path: Path | None,
    file_root: Path,
) -> MultiQCIngestResult:
    parsed = parse_multiqc_outputs(outputs, run_id=run_id)
    return _save_multiqc_parse_result(
        parsed,
        run_id=run_id,
        project=project,
        analysis_type_id=analysis_type_id,
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )


def _save_multiqc_parse_result(
    parsed: Any,
    *,
    run_id: str,
    project: str | None,
    analysis_type_id: str,
    database_url: str,
    analytics_path: Path | None,
    file_root: Path,
) -> MultiQCIngestResult:
    ensure_sqlite_parent(database_url)
    file_root.mkdir(parents=True, exist_ok=True)

    catalog_store = SQLModelGoodomicsStore(database_url)
    asyncio.run(catalog_store.ensure_schema())
    project_record = asyncio.run(catalog_store.ensure_project(project))
    resolved_analytics_path = analytics_path or analytics_path_for_project(
        Path(".goodomics"), project_record.project_id
    )
    data_import = DataImport(
        data_import_id=run_id,
        project_id=project_record.project_id,
        source_type="multiqc",
        source_path=str(parsed.outputs[0].root_dir)
        if len(parsed.outputs) == 1
        else None,
        importer_name="multiqc",
        status="complete",
        parameters_json={"analysis_type_id": analysis_type_id},
        summary_json={
            "outputs_found": len(parsed.outputs),
            "metrics_ingested": len(parsed.metrics),
            "payloads_ingested": len(parsed.payloads),
            "canonical_samples": len(parsed.sample_ids),
            "upstream_runs": len(parsed.sample_ids),
        },
        metadata_json={
            "source_paths": [str(output.root_dir) for output in parsed.outputs],
        },
    )
    analysis_type = resolve_analysis_type(analysis_type_id)
    report_method = analysis_method("multiqc", name="MultiQC", method_kind="importer")
    upstream_method = analysis_method(
        "multiqc/inferred_upstream",
        name="MultiQC inferred upstream analysis",
        method_kind="workflow",
    )
    report_run = Run(
        run_id=run_id,
        project_id=project_record.project_id,
        data_import_id=data_import.data_import_id,
        project=project_record.slug,
        name=f"MultiQC report {run_id}",
        run_kind="multiqc_report",
        analysis_type_id=analysis_type.analysis_type_id,
        method_id=report_method.method_id,
        status="complete",
        metadata_json={"source": "multiqc_report"},
    )
    subjects = [
        Subject(subject_id=sample_id, project_id=project_record.project_id)
        for sample_id in sorted(parsed.sample_ids)
    ]
    samples = [
        Sample(
            sample_id=sample_id,
            project_id=project_record.project_id,
            subject_id=sample_id,
            sample_name=sample_id,
            metadata_json={"source": "multiqc_general_stats"},
        )
        for sample_id in sorted(parsed.sample_ids)
    ]
    upstream_runs = [
        Run(
            run_id=multiqc_upstream_run_id(run_id, sample.sample_id),
            project_id=project_record.project_id,
            data_import_id=data_import.data_import_id,
            project=project_record.slug,
            name=f"{sample.sample_id} upstream analysis",
            run_kind="pipeline_run",
            analysis_type_id=analysis_type.analysis_type_id,
            method_id=upstream_method.method_id,
            status="complete",
            metadata_json={
                "source": "multiqc_general_stats",
                "provenance_strength": "inferred",
                "multiqc_report_run_id": run_id,
            },
        )
        for sample in samples
    ]
    run_samples = [
        RunSample(
            run_sample_id=(
                f"{multiqc_upstream_run_id(run_id, sample.sample_id)}:"
                f"{sample.sample_id}"
            ),
            run_id=multiqc_upstream_run_id(
                run_id,
                sample.sample_id,
            ),
            sample_id=sample.sample_id,
        )
        for sample in samples
    ]
    run_relationships = [
        RunRelationship(
            source_run_id=run_id,
            target_run_id=upstream_run.run_id,
            relationship_type="summarizes",
            metadata_json={
                "source": "multiqc",
                "relationship": "multiqc_report_run summarizes upstream_sample_run",
            },
        )
        for upstream_run in upstream_runs
    ]
    run_contracts, run_contract_samples = _run_contract_occurrences(
        parsed.to_batch(run_id=run_id),
        runs=[report_run, *upstream_runs],
    )

    files = _copy_multiqc_files(
        parsed.outputs,
        run_id=run_id,
        project_id=project_record.project_id,
        file_root=file_root,
    )
    file_links = [
        FileLink(
            file_id=file.file_id,
            project_id=project_record.project_id,
            data_import_id=data_import.data_import_id,
            run_id=run_id,
            link_role="source"
            if file.file_role in {"multiqc_data", "multiqc_parquet", "multiqc_log"}
            else "report",
        )
        for file in files
    ]
    try:
        catalog_result = asyncio.run(
            catalog_store.replace_runs_catalog(
                [report_run, *upstream_runs],
                data_import=data_import,
                analysis_types=[analysis_type],
                analysis_methods=[report_method, upstream_method],
                subjects=subjects,
                samples=samples,
                run_samples=run_samples,
                run_relationships=run_relationships,
                data_contracts=[
                    data_contract.model_copy(
                        update={"project_id": project_record.project_id}
                    )
                    for data_contract in parsed.contracts
                ],
                data_contract_analysis_types=[
                    DataContractAnalysisType(
                        data_contract_id=contract.data_contract_id,
                        analysis_type_id=analysis_type.analysis_type_id,
                    )
                    for contract in parsed.contracts
                ],
                run_contracts=run_contracts,
                run_contract_samples=run_contract_samples,
                data_contract_fields=parsed.contract_fields,
                files=files,
                file_links=file_links,
            )
        )
    finally:
        asyncio.run(catalog_store.dispose())
    catalog_id_maps = catalog_id_maps_from_records(catalog_result)
    resolved_batch = resolve_analytics_batch_catalog_ids(
        parsed.to_batch(run_id=run_id),
        catalog_id_maps,
    )
    resolved_run_ids = [
        resolve_catalog_id("run_id", row.run_id, catalog_id_maps)
        for row in catalog_result.runs
    ]

    DuckDBAnalyticsStore(resolved_analytics_path).write_batch(
        resolved_batch,
        replace_run_ids=[run_id for run_id in resolved_run_ids if run_id is not None],
    )

    return MultiQCIngestResult(
        run_id=run_id,
        data_import_id=data_import.data_import_id,
        outputs_found=len(parsed.outputs),
        metrics_ingested=len(parsed.metrics),
        payloads_ingested=len(parsed.payloads),
        files_stored=len(files),
        upstream_runs=len(upstream_runs),
        run_relationships=len(run_relationships),
        database_url=database_url,
        analytics_path=resolved_analytics_path,
        file_root=file_root,
    )


def _run_contract_occurrences(
    batch: Any,
    *,
    runs: list[Run],
) -> tuple[list[RunContract], list[RunContractSample]]:
    """Build authoritative contract occurrences from emitted analytical rows."""

    run_by_id = {run.run_id: run for run in runs}
    pairs: dict[tuple[str, str], set[str]] = {}
    for field_name in type(batch).model_fields:
        for row in getattr(batch, field_name):
            run_label = getattr(row, "run_id", None)
            contract_label = getattr(row, "data_contract_id", None)
            if run_label is None and getattr(row, "model_extra", None):
                run_label = row.model_extra.get("run_id")
            if contract_label is None and getattr(row, "model_extra", None):
                contract_label = row.model_extra.get("data_contract_id")
            if not isinstance(run_label, str) or not isinstance(contract_label, str):
                continue
            sample_link = getattr(row, "run_sample_id", None)
            if sample_link is None and getattr(row, "model_extra", None):
                sample_link = row.model_extra.get("run_sample_id")
            pairs.setdefault((run_label, contract_label), set())
            if isinstance(sample_link, str):
                pairs[(run_label, contract_label)].add(sample_link)

    occurrences: list[RunContract] = []
    availability: list[RunContractSample] = []
    for run_label, contract_label in sorted(pairs):
        run = run_by_id[run_label]
        occurrence_id = f"{run_label}:{contract_label}"
        occurrences.append(
            RunContract(
                run_contract_id=occurrence_id,
                run_id=run_label,
                data_contract_id=contract_label,
                producer_method_id=run.method_id,
                producer_version=run.method_version,
                status="available",
            )
        )
        availability.extend(
            RunContractSample(
                run_contract_id=occurrence_id,
                run_sample_id=run_sample_id,
                availability="observed",
            )
            for run_sample_id in sorted(pairs[(run_label, contract_label)])
        )
    return occurrences, availability


def _copy_multiqc_files(
    outputs: list[MultiQCOutput],
    *,
    run_id: str,
    project_id: str,
    file_root: Path,
) -> list[FileAsset]:
    destination_root = file_root / run_id / "multiqc"
    if destination_root.exists():
        shutil.rmtree(destination_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    files: list[FileAsset] = []
    for index, output in enumerate(outputs, start=1):
        output_destination = (
            destination_root if len(outputs) == 1 else destination_root / str(index)
        )
        output_destination.mkdir(parents=True, exist_ok=True)
        if output.report_html is not None:
            report_destination = output_destination / output.report_html.name
            shutil.copy2(output.report_html, report_destination)
            files.append(
                _file_metadata(
                    run_id=run_id,
                    project_id=project_id,
                    kind="multiqc_report",
                    source=output.report_html,
                    destination=report_destination,
                )
            )

        data_destination = output_destination / output.data_dir.name
        shutil.copytree(output.data_dir, data_destination)
        files.append(
            _file_metadata(
                run_id=run_id,
                project_id=project_id,
                kind="multiqc_data",
                source=output.data_dir,
                destination=data_destination,
            )
        )
        parquet_destination = data_destination / output.parquet_path.name
        if parquet_destination.exists():
            files.append(
                _file_metadata(
                    run_id=run_id,
                    project_id=project_id,
                    kind="multiqc_parquet",
                    source=output.parquet_path,
                    destination=parquet_destination,
                )
            )
        log_source = output.data_dir / "multiqc.log"
        log_destination = data_destination / "multiqc.log"
        if log_source.exists() and log_destination.exists():
            files.append(
                _file_metadata(
                    run_id=run_id,
                    project_id=project_id,
                    kind="multiqc_log",
                    source=log_source,
                    destination=log_destination,
                )
            )
    return files


def _file_metadata(
    *,
    run_id: str,
    project_id: str,
    kind: str,
    source: Path,
    destination: Path,
) -> FileAsset:
    path_digest = hashlib.sha256(str(destination).encode("utf-8")).hexdigest()[:12]
    return FileAsset(
        file_id=f"{run_id}:{kind}:{path_digest}:{destination.name}",
        project_id=project_id,
        file_role=kind,
        format=destination.suffix.removeprefix(".") if destination.is_file() else "dir",
        path=str(destination),
        size_bytes=_path_size(destination),
        sha256=_path_hash(destination),
        created_at=datetime.now(UTC),
        metadata_json={
            "source_path": str(source),
            "source": "multiqc_import",
            "run_id": run_id,
        },
    )


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


async def _replace_files(
    database_url: str,
    run_id: str,
    files: list[FileAsset],
    file_links: list[FileLink],
    *,
    project_id: str,
) -> None:
    store = SQLModelGoodomicsStore(database_url)
    try:
        await store.ensure_schema()
        async with store.session() as session:
            await store.replace_run_file_catalog(
                session,
                run_id,
                files,
                file_links,
                project_id,
            )
    finally:
        await store.dispose()
