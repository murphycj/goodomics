"""Routing helpers for dispatching ingest calls and formatting CLI output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from goodomics.sources import SourceSpec, get_source
from goodomics.storage.database import resolve_database_url


@dataclass(frozen=True)
class IngestRouteResult:
    """Resolved ingest route and payload returned by the selected source handler."""

    ingest_type: str
    source: SourceSpec
    payload: Any


def run_ingest(
    results: Path,
    *,
    ingest_type: str,
    project: str | None,
    analysis_type_id: str | None,
    run_id: str | None,
    database_url: str | None,
    analytics_path: Path | None,
    file_root: Path,
    console: Console | None = None,
    show_progress: bool = False,
) -> IngestRouteResult:
    """Resolve and execute the configured ingest source for provided results path."""

    source = get_source(str(ingest_type))
    resolved_database_url = resolve_database_url(database_url)
    # SourceSpec owns the callable's keyword contract, which lets built-ins keep
    # their historical parameter names while routing through one registry path.
    kwargs = {
        "project": project,
        "analysis_type_id": analysis_type_id,
        "database_url": resolved_database_url,
        "analytics_path": analytics_path,
        "file_root": file_root,
        "console": console,
        "show_progress": show_progress,
    }
    if run_id is not None:
        kwargs[source.run_id_parameter] = run_id
    callable_kwargs = {
        key: value
        for key, value in kwargs.items()
        if key in source.ingest_parameters and value is not None
    }
    return IngestRouteResult(
        ingest_type=source.key,
        source=source,
        payload=source.load_ingest()(results, **callable_kwargs),
    )


def print_ingest_result(result: IngestRouteResult, console: Console) -> None:
    """Render ingest output with source printer or generic structured fallback."""

    printer = result.source.load_result_printer()
    if printer is None:
        # Third-party sources can omit custom printers and still get a useful
        # structured CLI echo while they are being developed.
        console.print({"source": result.ingest_type, "result": result.payload})
        return
    printer(result.payload, console)


def print_multiqc_ingest_results(results_ingested: Any, console: Console) -> None:
    """Print a human-readable summary for one or many MultiQC ingest results."""

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


def print_cbioportal_ingest_result(result: Any, console: Console) -> None:
    """Print a human-readable summary for a completed cBioPortal ingest result."""

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
            "contracts_ingested": result.contracts_ingested,
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
