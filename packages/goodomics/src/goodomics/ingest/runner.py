from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from rich.console import Console

from goodomics.ingest.cbioportal import CbioPortalIngestResult, ingest_cbioportal_study
from goodomics.ingest.multiqc import MultiQCIngestResult, ingest_multiqc_runs
from goodomics.storage.database import resolve_database_url


class IngestType(StrEnum):
    multiqc = "multiqc"
    cbioportal = "cbioportal"


@dataclass(frozen=True)
class IngestRouteResult:
    ingest_type: IngestType
    payload: list[MultiQCIngestResult] | CbioPortalIngestResult


def run_ingest(
    results: Path,
    *,
    ingest_type: IngestType | str,
    project: str | None,
    assay: str | None,
    run_id: str | None,
    database_url: str | None,
    analytics_path: Path | None,
    file_root: Path,
    console: Console | None = None,
    show_progress: bool = False,
) -> IngestRouteResult:
    resolved_ingest_type = IngestType(ingest_type)
    resolved_database_url = resolve_database_url(database_url)
    if resolved_ingest_type == IngestType.cbioportal:
        return IngestRouteResult(
            ingest_type=resolved_ingest_type,
            payload=ingest_cbioportal_study(
                results,
                project=project,
                assay=assay,
                data_import_id=run_id,
                database_url=resolved_database_url,
                analytics_path=analytics_path,
                show_progress=show_progress,
                console=console,
            ),
        )

    return IngestRouteResult(
        ingest_type=resolved_ingest_type,
        payload=ingest_multiqc_runs(
            results,
            project=project,
            assay=assay,
            run_id=run_id,
            database_url=resolved_database_url,
            analytics_path=analytics_path,
            file_root=file_root,
        ),
    )


def print_ingest_result(result: IngestRouteResult, console: Console) -> None:
    if result.ingest_type == IngestType.cbioportal:
        _print_cbioportal_ingest_result(
            cast(CbioPortalIngestResult, result.payload),
            console,
        )
        return
    _print_multiqc_ingest_results(
        cast(list[MultiQCIngestResult], result.payload),
        console,
    )


def _print_multiqc_ingest_results(
    results_ingested: list[MultiQCIngestResult],
    console: Console,
) -> None:
    if len(results_ingested) == 1:
        result = results_ingested[0]
        console.print(f"Ingested run [bold]{result.run_id}[/bold]")
    else:
        console.print(f"Ingested [bold]{len(results_ingested)}[/bold] runs")
    for result in results_ingested:
        console.print(
            {
                "run_id": result.run_id,
                "data_import_id": result.data_import_id,
                "outputs_found": result.outputs_found,
                "metrics_ingested": result.metrics_ingested,
                "payloads_ingested": result.payloads_ingested,
                "files_stored": result.files_stored,
                "database_url": result.database_url,
                "analytics_path": str(result.analytics_path),
                "file_root": str(result.file_root),
            }
        )


def _print_cbioportal_ingest_result(
    result: CbioPortalIngestResult,
    console: Console,
) -> None:
    if result.runs_ingested == 1:
        console.print(
            f"Ingested cBioPortal import [bold]{result.data_import_id}[/bold]"
        )
    else:
        console.print(
            f"Ingested [bold]{result.runs_ingested}[/bold] cBioPortal sample runs"
        )
    console.print(
        {
            "data_import_id": result.data_import_id,
            "runs_ingested": result.runs_ingested,
            "profiles_ingested": result.profiles_ingested,
            "subjects_ingested": result.subjects_ingested,
            "samples_ingested": result.samples_ingested,
            "run_samples_ingested": result.run_samples_ingested,
            "files_registered": result.files_registered,
            "sample_sets_ingested": result.sample_sets_ingested,
            "bulk_loads": result.bulk_loads,
            "database_url": result.database_url,
            "analytics_path": str(result.analytics_path),
        }
    )
