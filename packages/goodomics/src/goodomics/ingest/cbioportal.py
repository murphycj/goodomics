"""Ingest orchestration for cBioPortal studies into catalog and analytics stores."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from goodomics.parsers.cbioportal import parse_cbioportal_study
from goodomics.projects import analytics_path_for_project
from goodomics.storage.analytics_resolution import (
    resolve_analytics_batch_catalog_ids,
    resolve_catalog_id,
)
from goodomics.storage.database import DEFAULT_DATABASE_URL
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    SQLModelGoodomicsStore,
    catalog_id_maps_from_records,
)


@dataclass(frozen=True)
class CbioPortalIngestResult:
    """Summary of one cBioPortal ingest execution across SQL and DuckDB writes."""

    data_import_id: str
    runs_ingested: int
    profiles_ingested: int
    subjects_ingested: int
    samples_ingested: int
    run_samples_ingested: int
    files_registered: int
    sample_sets_ingested: int
    bulk_loads: int
    database_url: str
    analytics_path: Path


def ingest_cbioportal_study(
    root: Path,
    *,
    data_import_id: str | None = None,
    project: str | None = None,
    assay: str | None = None,
    database_url: str = DEFAULT_DATABASE_URL,
    analytics_path: Path | None = None,
    show_progress: bool = False,
    console: Console | None = None,
) -> CbioPortalIngestResult:
    """Parse a cBioPortal study and persist catalog plus analytical records."""

    progress = _new_progress(console) if show_progress else None
    task_id: TaskID | None = None
    if progress is not None:
        progress.start()
        task_id = progress.add_task("Preparing cBioPortal import", total=None)

    def update_progress(description: str, *, completed: int | None = None) -> None:
        if progress is not None and task_id is not None:
            progress.update(task_id, description=description, completed=completed)

    try:
        update_progress("Resolving project")
        catalog_store = SQLModelGoodomicsStore(database_url)
        project_record = asyncio.run(catalog_store.ensure_project(project))
        resolved_data_import_id = (
            f"{_study_identifier(root)}:{uuid4().hex[:12]}"
            if data_import_id is None
            else data_import_id
        )

        update_progress("Parsing cBioPortal study", completed=1)
        parsed = parse_cbioportal_study(
            root,
            data_import_id=resolved_data_import_id,
            project_id=project_record.project_id,
            assay=assay,
        )
        total_steps = 4 + len(parsed.bulk_loads)
        if progress is not None and task_id is not None:
            progress.update(task_id, total=total_steps, completed=2)

        update_progress("Writing SQL catalog metadata", completed=2)
        catalog_result = asyncio.run(
            catalog_store.replace_runs_catalog(
                parsed.all_runs,
                data_import=parsed.data_import,
                subjects=parsed.subjects,
                samples=parsed.samples,
                run_samples=parsed.run_samples,
                data_profiles=parsed.data_profiles,
                data_profile_fields=parsed.data_profile_fields,
                files=parsed.files,
                file_links=parsed.file_links,
                sample_sets=parsed.sample_sets,
                sample_set_members=parsed.sample_set_members,
            )
        )
        update_progress("Writing DuckDB analytical batch", completed=3)

        resolved_analytics_path = analytics_path or analytics_path_for_project(
            Path(".goodomics"), project_record.project_id
        )
        catalog_id_maps = catalog_id_maps_from_records(catalog_result)
        resolved_batch = resolve_analytics_batch_catalog_ids(
            parsed.analytics_batch,
            catalog_id_maps,
        )
        resolved_bulk_loads = [
            bulk_load.resolve_catalog_ids(catalog_id_maps)
            for bulk_load in parsed.bulk_loads
        ]
        resolved_staged_loads = [
            staged_load.resolve_catalog_ids(catalog_id_maps)
            for staged_load in parsed.staged_loads
        ]
        resolved_replace_run_ids = [
            resolve_catalog_id("run_id", run_id, catalog_id_maps)
            for run_id in [
                resolved_data_import_id,
                *[run.run_id for run in parsed.all_runs],
            ]
        ]

        def bulk_load_progress(
            bulk_load: Any,
            index: int,
            total: int,
        ) -> None:
            update_progress(
                f"Loading DuckDB rows: {_bulk_load_label(bulk_load)}",
                completed=4 + index,
            )

        DuckDBAnalyticsStore(resolved_analytics_path).write_batch_with_bulk_loads(
            resolved_batch,
            resolved_bulk_loads,
            staged_loads=resolved_staged_loads,
            replace_run_ids=resolved_replace_run_ids,
            bulk_load_progress=bulk_load_progress if progress is not None else None,
        )
        update_progress("cBioPortal ingest complete", completed=total_steps)
        return CbioPortalIngestResult(
            data_import_id=resolved_data_import_id,
            runs_ingested=len(parsed.all_runs),
            profiles_ingested=len(parsed.data_profiles),
            subjects_ingested=len(parsed.subjects),
            samples_ingested=len(parsed.samples),
            run_samples_ingested=len(parsed.run_samples),
            files_registered=len(parsed.files),
            sample_sets_ingested=len(parsed.sample_sets),
            bulk_loads=len(parsed.bulk_loads),
            database_url=database_url,
            analytics_path=resolved_analytics_path,
        )
    finally:
        if progress is not None:
            progress.stop()


def _new_progress(console: Console | None) -> Progress:
    return Progress(
        SpinnerColumn(),
        BarColumn(bar_width=40),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        _ClippedDescriptionColumn(width=80),
        console=console,
    )


class _ClippedDescriptionColumn(ProgressColumn):
    def __init__(self, *, width: int) -> None:
        super().__init__()
        self.width = width

    def render(self, task: Any) -> Text:
        text = task.description
        if len(text) > self.width:
            text = f"{text[: self.width - 3]}..."
        return Text(text, style="progress.description")


def _bulk_load_label(bulk_load: Any) -> str:
    profile = getattr(bulk_load, "profile", None)
    profile_name = getattr(profile, "name", None)
    path = getattr(bulk_load, "path", None)
    path_name = Path(path).name if path is not None else type(bulk_load).__name__
    return f"{profile_name or type(bulk_load).__name__} ({path_name})"


def _study_identifier(root: Path) -> str:
    meta_path = root / "meta_study.txt"
    if meta_path.exists():
        with meta_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("cancer_study_identifier:"):
                    return line.split(":", 1)[1].strip() or root.name
    return root.name
