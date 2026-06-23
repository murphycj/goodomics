from __future__ import annotations

import asyncio
import hashlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.parsers.multiqc import (
    MultiQCOutput,
    discover_multiqc_outputs,
    parse_multiqc_bundle,
    parse_multiqc_outputs,
)
from goodomics.projects import analytics_path_for_project
from goodomics.schemas.models import Run, Sample
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    SQLModelGoodomicsStore,
    StoredFileMetadata,
)


@dataclass(frozen=True)
class MultiQCIngestResult:
    run_id: str
    outputs_found: int
    metrics_ingested: int
    payloads_ingested: int
    files_stored: int
    database_url: str
    analytics_path: Path
    file_root: Path


def default_run_id(results: Path) -> str:
    name = results.resolve().name if results.name else "run"
    return name or f"run-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


def default_run_id_for_output(output: MultiQCOutput) -> str:
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
    assay: str | None = None,
    database_url: str = "sqlite+aiosqlite:///.goodomics/goodomics.db",
    analytics_path: Path | None = None,
    file_root: Path = Path(".goodomics/files"),
) -> list[MultiQCIngestResult]:
    outputs = discover_multiqc_outputs(results)
    if not outputs:
        raise ValueError(f"No MultiQC output found under {results}")
    if run_id is not None or len(outputs) == 1:
        return [
            ingest_multiqc(
                results,
                run_id=run_id,
                project=project,
                assay=assay,
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
            assay=assay,
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
    assay: str | None = None,
    database_url: str = "sqlite+aiosqlite:///.goodomics/goodomics.db",
    analytics_path: Path | None = None,
    file_root: Path = Path(".goodomics/files"),
) -> MultiQCIngestResult:
    resolved_run_id = run_id or default_run_id(results)
    parsed = parse_multiqc_bundle(results, run_id=resolved_run_id)
    if not parsed.outputs:
        raise ValueError(f"No MultiQC output found under {results}")

    return _save_multiqc_parse_result(
        parsed,
        run_id=resolved_run_id,
        project=project,
        assay=assay,
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )


def _ingest_multiqc_outputs(
    outputs: list[MultiQCOutput],
    *,
    run_id: str,
    project: str | None,
    assay: str | None,
    database_url: str,
    analytics_path: Path | None,
    file_root: Path,
) -> MultiQCIngestResult:
    parsed = parse_multiqc_outputs(outputs, run_id=run_id)
    return _save_multiqc_parse_result(
        parsed,
        run_id=run_id,
        project=project,
        assay=assay,
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )


def _save_multiqc_parse_result(
    parsed: Any,
    *,
    run_id: str,
    project: str | None,
    assay: str | None,
    database_url: str,
    analytics_path: Path | None,
    file_root: Path,
) -> MultiQCIngestResult:
    _ensure_sqlite_parent(database_url)
    file_root.mkdir(parents=True, exist_ok=True)

    control_store = SQLModelGoodomicsStore(database_url)
    project_record = asyncio.run(control_store.ensure_project(project))
    resolved_analytics_path = analytics_path or analytics_path_for_project(
        Path(".goodomics"), project_record.project_id
    )
    run = Run(
        run_id=run_id,
        project_id=project_record.project_id,
        project=project_record.slug,
        assay=assay,
        samples=[
            Sample(sample_id=sample_id, project_id=project_record.project_id)
            for sample_id in sorted(parsed.sample_ids)
        ],
    )
    asyncio.run(control_store.save_run(run))

    files = _copy_multiqc_files(
        parsed.outputs,
        run_id=run_id,
        file_root=file_root,
    )
    asyncio.run(_replace_files(database_url, run_id, files))

    DuckDBAnalyticsStore(resolved_analytics_path).replace_run_data(
        run_id,
        parsed.to_batch(run_id=run_id),
    )

    return MultiQCIngestResult(
        run_id=run_id,
        outputs_found=len(parsed.outputs),
        metrics_ingested=len(parsed.metrics),
        payloads_ingested=len(parsed.payloads),
        files_stored=len(files),
        database_url=database_url,
        analytics_path=resolved_analytics_path,
        file_root=file_root,
    )


def _copy_multiqc_files(
    outputs: list[MultiQCOutput],
    *,
    run_id: str,
    file_root: Path,
) -> list[StoredFileMetadata]:
    destination_root = file_root / run_id / "multiqc"
    if destination_root.exists():
        shutil.rmtree(destination_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    files: list[StoredFileMetadata] = []
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
                kind="multiqc_data",
                source=output.data_dir,
                destination=data_destination,
            )
        )
    return files


def _file_metadata(
    *,
    run_id: str,
    kind: str,
    source: Path,
    destination: Path,
) -> StoredFileMetadata:
    return StoredFileMetadata(
        file_id=f"{run_id}:{kind}:{destination.name}",
        run_id=run_id,
        kind=kind,
        path=str(destination),
        size_bytes=_path_size(destination),
        sha256=_path_hash(destination),
        source_path=str(source),
        created_at=datetime.now(UTC),
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


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if database_url.startswith(prefix):
        db_path = Path(database_url.removeprefix(prefix))
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)


async def _replace_files(
    database_url: str,
    run_id: str,
    files: list[StoredFileMetadata],
) -> None:
    engine = create_async_engine(database_url)
    try:
        store = SQLModelGoodomicsStore(database_url, engine=engine)
        await store.ensure_schema()
        async with AsyncSession(engine) as session:
            await store.replace_files(session, run_id, files)
    finally:
        await engine.dispose()
