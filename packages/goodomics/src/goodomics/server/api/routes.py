from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_args, get_origin
from uuid import uuid4

import yaml
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, or_
from sqlmodel import Field, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.projects import (
    DEFAULT_PROJECT_ID,
    analytics_path_for_project,
    display_name_from_slug,
    is_project_id,
    new_project_id,
    validate_project_slug,
)
from goodomics.report.html import render_report, render_report_result
from goodomics.schemas.models import Run, Sample
from goodomics.server.ai import (
    AIProviderNotConfigured,
    ChatMessage,
    ChatResult,
)
from goodomics.server.db.models import (
    CohortRecord,
    InsightRecord,
    InsightResultCacheRecord,
    InsightRevisionRecord,
    QCPolicyRecord,
    RenderedReportRecord,
    ReportRecord,
    ReportResultCacheRecord,
    ReportRevisionRecord,
)
from goodomics.server.insights import execute_insight, execute_report
from goodomics.storage.duckdb import SERIALIZERS_BY_TABLE, DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataImportRecord,
    DataProfileRecord,
    FileLinkRecord,
    FileRecord,
    ProjectRecord,
    QCDecisionRecord,
    RunRecord,
    RunSampleRecord,
    SampleRecord,
    SampleSetMemberRecord,
    SampleSetRecord,
    SubjectRecord,
    get_record_by_field,
    get_record_where,
)

router = APIRouter(prefix="/api/v1")
JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class RunCreate(SQLModel):
    run_id: str | None = None
    project_id: str | None = None
    project: str | None = None
    assay: str | None = None
    samples: list[Sample] = Field(default_factory=list)


class RunPatch(SQLModel):
    project: str | None = None
    assay: str | None = None


class RunPageRead(SQLModel):
    items: list[Run]
    total: int
    limit: int
    offset: int


class SampleListItemRead(SQLModel):
    sample_id: str
    project_id: str | None = None
    subject_id: str | None = None
    sample_name: str | None = None
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict)
    run_count: int = 0
    latest_run_id: str | None = None
    latest_run_name: str | None = None
    latest_run_created_at: datetime | None = None


class SamplePageRead(SQLModel):
    items: list[SampleListItemRead]
    total: int
    limit: int
    offset: int


class SampleRunRead(SQLModel):
    run_id: str
    project_id: str | None = None
    name: str | None = None
    run_kind: str
    assay: str | None = None
    pipeline_name: str | None = None
    pipeline_version: str | None = None
    status: str
    created_at: datetime
    run_sample_id: str
    run_sample_status: str


class ProjectCreate(SQLModel):
    name: str
    slug: str | None = None
    description: str | None = None
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict)


class ProjectPatch(SQLModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    default_report_id: str | None = None
    metadata_json: dict[str, JsonValue] | None = None


class ProjectRead(SQLModel):
    project_id: str
    slug: str | None = None
    name: str
    description: str | None = None
    default_report_id: str | None = None
    metadata_json: dict[str, JsonValue]
    created_at: datetime
    run_count: int = 0
    sample_count: int = 0
    subject_count: int = 0
    file_count: int = 0
    file_size_bytes: int = 0
    latest_activity_at: datetime | None = None


class SearchResultRead(SQLModel):
    kind: str
    project_id: str | None = None
    project_name: str | None = None
    run_id: str | None = None
    sample_id: str | None = None
    sample_name: str | None = None


class FileRead(SQLModel):
    file_id: str
    project_id: str | None = None
    data_import_id: str | None = None
    run_id: str | None = None
    run_sample_id: str | None = None
    sample_id: str | None = None
    data_profile_id: str | None = None
    association_scope: str = "direct_run"
    association_reason: str | None = None
    kind: str = "file"
    path: str | None = None
    uri: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    source_path: str | None = None
    created_at: datetime | None = None


class SavedInsightBase(SQLModel):
    name: str
    description: str | None = None
    config: dict[str, JsonValue] = Field(default_factory=dict)


class SavedInsightCreate(SavedInsightBase):
    insight_id: str | None = None
    project_id: str | None = None


class SavedInsightPatch(SQLModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, JsonValue] | None = None


class SavedInsightRead(SavedInsightBase):
    insight_id: str
    project_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SavedReportBase(SQLModel):
    name: str
    description: str | None = None
    config: dict[str, JsonValue] = Field(default_factory=dict)


class SavedReportCreate(SavedReportBase):
    report_id: str | None = None
    project_id: str | None = None


class SavedReportPatch(SQLModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, JsonValue] | None = None


class SavedReportRead(SavedReportBase):
    report_id: str
    project_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ReportRenderRequest(SQLModel):
    results: str = "."
    rendered_report_id: str | None = None
    report_id: str | None = None
    run_id: str | None = None
    project_id: str | None = None
    title: str = "Goodomics Report"
    refresh: bool = False


class RenderedReportRead(SQLModel):
    rendered_report_id: str
    project_id: str | None = None
    run_id: str | None = None
    report_id: str | None = None
    title: str
    html: str
    created_at: datetime


class InsightExecuteRequest(SQLModel):
    config: dict[str, JsonValue] | None = None
    project_id: str | None = None
    refresh: bool = False


class ReportExecuteRequest(SQLModel):
    project_id: str | None = None
    refresh: bool = False


class InsightResultRead(SQLModel):
    result: dict[str, JsonValue]


class ReportResultRead(SQLModel):
    result: dict[str, JsonValue]


class CohortCreate(SQLModel):
    cohort_id: str | None = None
    name: str
    description: str | None = None
    filters: dict[str, JsonValue] = Field(default_factory=dict)


class CohortPatch(SQLModel):
    name: str | None = None
    description: str | None = None
    filters: dict[str, JsonValue] | None = None


class CohortRead(SQLModel):
    cohort_id: str
    name: str
    description: str | None = None
    filters: dict[str, JsonValue]
    updated_at: datetime


class QCPolicyCreate(SQLModel):
    policy_id: str | None = None
    name: str
    thresholds: dict[str, JsonValue] = Field(default_factory=dict)


class QCPolicyPatch(SQLModel):
    name: str | None = None
    thresholds: dict[str, JsonValue] | None = None


class QCPolicyRead(SQLModel):
    policy_id: str
    name: str
    thresholds: dict[str, JsonValue]
    updated_at: datetime


class DatabaseTableRead(SQLModel):
    name: str
    store: str = "catalog"
    rows: int = 0
    columns: list[str] = Field(default_factory=list)
    editable: bool = False


class DatabaseTablePageRead(SQLModel):
    name: str
    store: str
    columns: list[str]
    rows: list[dict[str, JsonValue]]
    total: int
    limit: int
    offset: int
    sort_by: str | None = None
    sort_direction: str | None = None


class AnalyticsMetricRead(SQLModel):
    run_id: int | str
    data_profile_id: int | str
    run_sample_id: int | str | None = None
    sample_id: int | str | None = None
    metric_id: int | str
    value: float | str
    source_file_id: int | str | None = None


class AnalyticsPayloadRead(SQLModel):
    run_id: int | str
    data_profile_id: int | str
    run_sample_id: int | str | None = None
    payload_name: str
    payload_kind: str
    storage_format: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    source_file_id: int | str | None = None
    source_hash: str | None = None


class TableCountRead(SQLModel):
    name: str
    rows: int


class DatabaseSummaryRead(SQLModel):
    sqlite_size_bytes: int
    duckdb_size_bytes: int
    file_size_bytes: int
    total_runs: int
    total_samples: int
    total_scalar_metrics: int
    total_payloads: int
    control_tables: list[TableCountRead]
    analytics_tables: list[TableCountRead]


class DatabaseRowPatch(SQLModel):
    values: dict[str, JsonValue]
    audit_note: str | None = None


class AIChatRequest(SQLModel):
    messages: list[ChatMessage]
    project_id: str | None = None
    conversation_id: str | None = None


CATALOG_TABLES: dict[str, tuple[type[SQLModel], str]] = {
    "projects": (ProjectRecord, "project_id"),
    "subjects": (SubjectRecord, "subject_id"),
    "samples": (SampleRecord, "sample_id"),
    "runs": (RunRecord, "run_id"),
    "run_samples": (RunSampleRecord, "run_sample_id"),
    "data_imports": (DataImportRecord, "data_import_id"),
    "data_profiles": (DataProfileRecord, "data_profile_id"),
    "files": (FileRecord, "file_id"),
    "file_links": (FileLinkRecord, "id"),
    "sample_sets": (SampleSetRecord, "sample_set_id"),
    "sample_set_members": (SampleSetMemberRecord, "id"),
    "qc_decisions": (QCDecisionRecord, "id"),
    "insights": (InsightRecord, "insight_id"),
    "insight_revisions": (InsightRevisionRecord, "id"),
    "reports": (ReportRecord, "report_id"),
    "report_revisions": (ReportRevisionRecord, "id"),
    "rendered_reports": (RenderedReportRecord, "rendered_report_id"),
    "insight_result_cache": (InsightResultCacheRecord, "cache_id"),
    "report_result_cache": (ReportResultCacheRecord, "cache_id"),
    "cohorts": (CohortRecord, "cohort_id"),
    "qc_policies": (QCPolicyRecord, "policy_id"),
}

EDITABLE_TABLES: dict[str, tuple[type[SQLModel], str, set[str]]] = {
    "projects": (
        ProjectRecord,
        "project_id",
        {"name", "slug", "description", "default_report_id", "metadata_json"},
    ),
    "runs": (RunRecord, "run_id", {"project", "assay"}),
    "samples": (SampleRecord, "sample_id", {"sample_name", "metadata_json"}),
    "files": (FileRecord, "file_id", {"file_role", "path", "uri", "metadata_json"}),
    "insights": (
        InsightRecord,
        "insight_id",
        {"name", "description", "config"},
    ),
    "reports": (ReportRecord, "report_id", {"name", "description", "config"}),
    "rendered_reports": (RenderedReportRecord, "rendered_report_id", {"title"}),
    "cohorts": (CohortRecord, "cohort_id", {"name", "description", "filters"}),
    "qc_policies": (QCPolicyRecord, "policy_id", {"name", "thresholds"}),
}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/ai/chat", response_model=ChatResult)
async def chat_with_ai(payload: AIChatRequest, request: Request) -> ChatResult:
    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    try:
        return await request.app.state.ai_chat.chat(
            payload.messages,
            project_id=payload.project_id,
            conversation_id=payload.conversation_id,
        )
    except AIProviderNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(request: Request) -> list[ProjectRead]:
    await _ensure_default_project(request)
    await _ensure_schema(request)
    async with _session(request) as session:
        rows = (
            await session.exec(
                select(ProjectRecord).order_by(
                    cast(Any, ProjectRecord.created_at), ProjectRecord.name
                )
            )
        ).all()
        return [await _project_read(row, session=session) for row in rows]


@router.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project(payload: ProjectCreate, request: Request) -> ProjectRead:
    await _ensure_schema(request)
    slug = validate_project_slug(payload.slug or payload.name)
    async with _session(request) as session:
        existing = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.slug, slug
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Project slug already exists")
        project = ProjectRecord(
            project_id=_new_project_id(),
            slug=slug,
            name=payload.name.strip() or display_name_from_slug(slug),
            description=payload.description,
            metadata_json=json.loads(json.dumps(payload.metadata_json)),
            created_at=datetime.now(UTC),
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return await _project_read(project, session=session)


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, request: Request) -> ProjectRead:
    return await _get_project_read(request, project_id)


@router.get("/projects/{project_id}/runs/{run_id}", response_model=Run)
async def get_project_run(
    project_id: str,
    run_id: str,
    request: Request,
) -> Run:
    return await _get_project_run(request, project_id, run_id)


@router.get("/projects/{project_id}/runs/{run_id}/samples", response_model=list[Sample])
async def list_project_run_samples(
    project_id: str,
    run_id: str,
    request: Request,
) -> list[Sample]:
    run = await _get_project_run(request, project_id, run_id)
    return run.samples


@router.get("/projects/{project_id}/runs/{run_id}/files", response_model=list[FileRead])
async def list_project_run_files(
    project_id: str,
    run_id: str,
    request: Request,
) -> list[FileRead]:
    await _get_project_run(request, project_id, run_id)
    return await _list_run_files(run_id, request, project_id=project_id)


@router.get(
    "/projects/{project_id}/runs/{run_id}/analytics/metrics",
    response_model=list[AnalyticsMetricRead],
)
async def list_project_run_analytics_metrics(
    project_id: str,
    run_id: str,
    request: Request,
) -> list[AnalyticsMetricRead]:
    run = await _get_project_run_record(request, project_id, run_id)
    return _analytics_metric_reads(
        _analytics_store_for_project(request, project_id).list_metric_values(run.id)
    )


@router.get(
    "/projects/{project_id}/runs/{run_id}/analytics/payloads",
    response_model=list[AnalyticsPayloadRead],
)
async def list_project_run_analytics_payloads(
    project_id: str,
    run_id: str,
    request: Request,
) -> list[AnalyticsPayloadRead]:
    run = await _get_project_run_record(request, project_id, run_id)
    return _analytics_payload_reads(
        _analytics_store_for_project(request, project_id).list_profile_payloads(run.id)
    )


@router.get("/projects/{project_id}/files/{file_id}/content")
async def get_project_file_content(
    project_id: str,
    file_id: str,
    request: Request,
) -> FileResponse:
    return await _file_content_response(file_id, request, project_id=project_id)


@router.get("/projects/{project_id}/samples", response_model=SamplePageRead)
async def list_project_samples(
    project_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SamplePageRead:
    await _require_project(request, project_id)
    return await _list_samples(
        request,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )


@router.get("/projects/{project_id}/samples/{sample_id}", response_model=Sample)
async def get_project_sample(
    project_id: str,
    sample_id: str,
    request: Request,
) -> Sample:
    project = await _require_project(request, project_id)
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await get_record_where(
            session,
            SampleRecord,
            SampleRecord.project_id == project.id,
            SampleRecord.sample_id == sample_id,
        )
        if row is None:
            row = (
                await session.exec(
                    select(SampleRecord)
                    .join(
                        RunSampleRecord,
                        cast(Any, RunSampleRecord.sample_id) == SampleRecord.id,
                    )
                    .where(
                        RunSampleRecord.project_id == project.id,
                        SampleRecord.sample_id == sample_id,
                    )
                )
            ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Sample not found")
        sample = await _sample_from_row_public(session, row)
    return sample


@router.get(
    "/projects/{project_id}/samples/{sample_id}/runs",
    response_model=list[SampleRunRead],
)
async def list_project_sample_runs(
    project_id: str,
    sample_id: str,
    request: Request,
) -> list[SampleRunRead]:
    await _require_project(request, project_id)
    await _ensure_schema(request)
    async with _session(request) as session:
        await _require_project_sample(session, project_id, sample_id)
        rows = await _sample_run_rows(session, project_id, sample_id)
        return [
            await _sample_run_from_rows_public(session, run, run_sample)
            for run, run_sample in rows
        ]


@router.get(
    "/projects/{project_id}/samples/{sample_id}/files",
    response_model=list[FileRead],
)
async def list_project_sample_files(
    project_id: str,
    sample_id: str,
    request: Request,
) -> list[FileRead]:
    await _require_project(request, project_id)
    await _ensure_schema(request)
    async with _session(request) as session:
        await _require_project_sample(session, project_id, sample_id)
        latest = await _latest_sample_run(session, project_id, sample_id)
    if latest is None:
        return []
    run, _ = latest
    return await _list_run_files(run.run_id, request, project_id=project_id)


@router.get(
    "/projects/{project_id}/samples/{sample_id}/runs/{run_id}/files",
    response_model=list[FileRead],
)
async def list_project_sample_run_files(
    project_id: str,
    sample_id: str,
    run_id: str,
    request: Request,
) -> list[FileRead]:
    await _require_project(request, project_id)
    await _ensure_schema(request)
    async with _session(request) as session:
        await _get_sample_run_link(session, project_id, sample_id, run_id)
    return await _list_run_files(run_id, request, project_id=project_id)


@router.get(
    "/projects/{project_id}/samples/{sample_id}/runs/{run_id}/analytics/metrics",
    response_model=list[AnalyticsMetricRead],
)
async def list_project_sample_run_analytics_metrics(
    project_id: str,
    sample_id: str,
    run_id: str,
    request: Request,
) -> list[AnalyticsMetricRead]:
    await _require_project(request, project_id)
    await _ensure_schema(request)
    async with _session(request) as session:
        run, run_sample = await _get_sample_run_link(
            session, project_id, sample_id, run_id
        )
    metrics = _analytics_store_for_project(request, project_id).list_metric_values(
        run.id,
        run_sample_id=run_sample.id,
    )
    return _analytics_metric_reads(metrics)


@router.patch("/projects/{project_id}", response_model=ProjectRead)
async def patch_project(
    project_id: str, payload: ProjectPatch, request: Request
) -> ProjectRead:
    await _ensure_schema(request)
    values = payload.model_dump(exclude_unset=True)
    async with _session(request) as session:
        row = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.project_id, project_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if "slug" in values and values["slug"] is not None:
            slug = validate_project_slug(str(values["slug"]))
            existing = await get_record_by_field(
                session, ProjectRecord, ProjectRecord.slug, slug
            )
            if existing is not None and existing.project_id != project_id:
                raise HTTPException(
                    status_code=409, detail="Project slug already exists"
                )
            row.slug = slug
        if "name" in values and values["name"] is not None:
            row.name = str(values["name"]).strip() or row.name
        if "description" in values:
            row.description = values["description"]
        if "default_report_id" in values:
            default_report_id = values["default_report_id"]
            if default_report_id is not None:
                report = await session.get(ReportRecord, str(default_report_id))
                if report is None or report.project_id not in {None, project_id}:
                    raise HTTPException(
                        status_code=404, detail="Default report not found"
                    )
            row.default_report_id = default_report_id
        if "metadata_json" in values and values["metadata_json"] is not None:
            row.metadata_json = json.loads(json.dumps(values["metadata_json"]))
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return await _project_read(row, session=session)


@router.get("/projects/{project_id}/runs", response_model=RunPageRead)
async def list_project_runs(
    project_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RunPageRead:
    await _require_project(request, project_id)
    return await _list_runs(request, project_id=project_id, limit=limit, offset=offset)


@router.get("/search", response_model=list[SearchResultRead])
async def search_samples(
    request: Request,
    q: str = Query(default="", max_length=255),
    project_id: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
) -> list[SearchResultRead]:
    await _ensure_schema(request)
    project_pk: int | None = None
    if project_id is not None:
        project = await _require_project(request, project_id)
        project_pk = project.id
    term = q.strip().lower()
    if not term:
        return []
    pattern = f"%{term}%"
    async with _session(request) as session:
        sample_statement = select(SampleRecord).where(
            (func.lower(SampleRecord.sample_id).like(pattern))
            | (func.lower(SampleRecord.sample_name).like(pattern))
        )
        if project_id is not None:
            sample_statement = sample_statement.where(
                SampleRecord.project_id == project_pk
            )
        sample_rows = (await session.exec(sample_statement.limit(limit))).all()

        run_statement = select(RunRecord).where(
            (func.lower(RunRecord.run_id).like(pattern))
            | (func.lower(RunRecord.name).like(pattern))
        )
        if project_id is not None:
            run_statement = run_statement.where(RunRecord.project_id == project_pk)
        remaining = max(limit - len(sample_rows), 0)
        run_rows = (
            (await session.exec(run_statement.limit(remaining))).all()
            if remaining
            else []
        )
        project_ids = {
            row.project_id
            for row in [*run_rows, *sample_rows]
            if row.project_id is not None
        }
        project_rows: dict[int, ProjectRecord] = {}
        if project_ids:
            project_rows = {
                int(project.id): project
                for project in (
                    await session.exec(
                        select(ProjectRecord).where(
                            cast(Any, ProjectRecord.id).in_(project_ids)
                        )
                    )
                ).all()
                if project.id is not None
            }
    return [
        SearchResultRead(
            kind="sample",
            project_id=(
                project_rows[row.project_id].project_id
                if row.project_id in project_rows
                else None
            ),
            project_name=(
                project_rows[row.project_id].name
                if row.project_id in project_rows
                else None
            ),
            sample_id=row.sample_id,
            sample_name=row.sample_name,
        )
        for row in sample_rows
    ] + [
        SearchResultRead(
            kind="run",
            project_id=(
                project_rows[row.project_id].project_id
                if row.project_id in project_rows
                else None
            ),
            project_name=(
                project_rows[row.project_id].name
                if row.project_id in project_rows
                else None
            ),
            run_id=row.run_id,
        )
        for row in run_rows
    ]


@router.get("/runs", response_model=RunPageRead)
async def list_runs(
    request: Request,
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RunPageRead:
    return await _list_runs(request, project_id=project_id, limit=limit, offset=offset)


@router.post("/runs", response_model=Run, status_code=201)
async def create_run(payload: RunCreate, request: Request) -> Run:
    project = await request.app.state.store.ensure_project(
        payload.project_id or payload.project
    )
    run = Run(
        run_id=payload.run_id or _new_id("run"),
        project_id=project.project_id,
        project=project.slug,
        assay=payload.assay,
        samples=[
            sample.model_copy(
                update={"project_id": sample.project_id or project.project_id}
            )
            for sample in payload.samples
        ],
    )
    await request.app.state.store.save_run(run)
    return run


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(run_id: str, request: Request) -> Run:
    run = await request.app.state.store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.patch("/runs/{run_id}", response_model=Run)
async def patch_run(run_id: str, payload: RunPatch, request: Request) -> Run:
    await _ensure_schema(request)
    values = payload.model_dump(exclude_unset=True)
    if values:
        async with _session(request) as session:
            row = await get_record_by_field(
                session, RunRecord, RunRecord.run_id, run_id
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Run not found")
            for key, value in values.items():
                setattr(row, key, value)
            session.add(row)
            await session.commit()
    return await get_run(run_id, request)


@router.get("/runs/{run_id}/samples", response_model=list[Sample])
async def list_run_samples(run_id: str, request: Request) -> list[Sample]:
    run = await get_run(run_id, request)
    return run.samples


@router.get("/runs/{run_id}/files", response_model=list[FileRead])
async def list_run_files(run_id: str, request: Request) -> list[FileRead]:
    return await _list_run_files(run_id, request)


async def _list_run_files(
    run_id: str, request: Request, *, project_id: str | None = None
) -> list[FileRead]:
    await _ensure_schema(request)
    async with _session(request) as session:
        run = await get_record_by_field(session, RunRecord, RunRecord.run_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        project_pk: int | None = None
        if project_id is not None:
            project = await get_record_by_field(
                session, ProjectRecord, ProjectRecord.project_id, project_id
            )
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            project_pk = project.id
        if project_pk is not None and run.project_id != project_pk:
            raise HTTPException(status_code=404, detail="Run not found")
        direct_statement = (
            select(FileRecord, FileLinkRecord)
            .join(FileLinkRecord, cast(Any, FileLinkRecord.file_id) == FileRecord.id)
            .where(FileLinkRecord.run_id == run.id)
            .order_by(FileRecord.file_id)
        )
        if project_pk is not None:
            direct_statement = direct_statement.where(
                FileLinkRecord.project_id == project_pk
            )
        rows: list[FileRead] = []
        for file, link in (await session.exec(direct_statement)).all():
            rows.append(
                await _file_from_rows_public(
                    session,
                    file,
                    link,
                    association_scope="direct_run",
                    association_reason="File directly linked to this run.",
                )
            )
        if run.data_import_id is not None:
            import_statement = (
                select(FileRecord, FileLinkRecord)
                .join(
                    FileLinkRecord,
                    cast(Any, FileLinkRecord.file_id) == FileRecord.id,
                )
                .where(
                    FileLinkRecord.data_import_id == run.data_import_id,
                    cast(Any, FileLinkRecord.run_id).is_(None),
                )
                .order_by(FileRecord.file_id)
            )
            if project_pk is not None:
                import_statement = import_statement.where(
                    FileLinkRecord.project_id == project_pk
                )
            for file, link in (await session.exec(import_statement)).all():
                rows.append(
                    await _file_from_rows_public(
                        session,
                        file,
                        link,
                        association_scope="data_import",
                        association_reason=(
                            "Source file from the data import that produced this run."
                        ),
                    )
                )
    return _dedupe_file_reads(rows)


@router.get(
    "/runs/{run_id}/analytics/metrics",
    response_model=list[AnalyticsMetricRead],
)
async def list_run_analytics_metrics(
    run_id: str, request: Request
) -> list[AnalyticsMetricRead]:
    run = await _get_run_record(request, run_id)
    project_id = await _project_public_id_for_pk(request, run.project_id)
    analytics_store = _analytics_store_for_project(request, project_id)
    return _analytics_metric_reads(analytics_store.list_metric_values(run.id))


@router.get(
    "/runs/{run_id}/analytics/payloads",
    response_model=list[AnalyticsPayloadRead],
)
async def list_run_analytics_payloads(
    run_id: str, request: Request
) -> list[AnalyticsPayloadRead]:
    run = await _get_run_record(request, run_id)
    project_id = await _project_public_id_for_pk(request, run.project_id)
    analytics_store = _analytics_store_for_project(request, project_id)
    return _analytics_payload_reads(analytics_store.list_profile_payloads(run.id))


@router.get("/files/{file_id}/content")
async def get_file_content(file_id: str, request: Request) -> FileResponse:
    return await _file_content_response(file_id, request)


async def _file_content_response(
    file_id: str,
    request: Request,
    *,
    project_id: str | None = None,
) -> FileResponse:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await get_record_by_field(
            session, FileRecord, FileRecord.file_id, file_id
        )
        if row is not None and project_id is not None:
            project_pk = await _project_pk(request, project_id, session=session)
            link = (
                await session.exec(
                    select(FileLinkRecord).where(
                        FileLinkRecord.file_id == row.id,
                        FileLinkRecord.project_id == project_pk,
                    )
                )
            ).first()
            if link is None:
                row = None
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")
    if row.path is None:
        raise HTTPException(status_code=404, detail="Stored file not found")
    path = Path(row.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found")
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Stored path is not a file")
    return FileResponse(path)


@router.get("/insights", response_model=list[SavedInsightRead])
async def list_insights(
    request: Request,
    project_id: str | None = Query(default=None),
) -> list[SavedInsightRead]:
    await _ensure_schema(request)
    if project_id is not None:
        await _require_project(request, project_id)
    async with _session(request) as session:
        statement = select(InsightRecord)
        if project_id is not None:
            statement = statement.where(InsightRecord.project_id == project_id)
        rows = (await session.exec(statement)).all()
    return [SavedInsightRead.model_validate(row.model_dump()) for row in rows]


@router.post("/insights", response_model=SavedInsightRead, status_code=201)
async def create_insight(
    payload: SavedInsightCreate, request: Request
) -> SavedInsightRead:
    await _ensure_schema(request)
    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    now = datetime.now(UTC)
    insight_id = payload.insight_id or _new_id("insight")
    async with _session(request) as session:
        insight = InsightRecord(
            insight_id=insight_id,
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            config=payload.config,
            created_at=now,
            updated_at=now,
        )
        revision = InsightRevisionRecord(
            insight_id=insight_id,
            config=payload.config,
            created_at=now,
        )
        session.add(insight)
        session.add(revision)
        await session.commit()
    return await get_insight(insight_id, request)


@router.get("/insights/{insight_id}", response_model=SavedInsightRead)
async def get_insight(insight_id: str, request: Request) -> SavedInsightRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await session.get(InsightRecord, insight_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    return SavedInsightRead.model_validate(row.model_dump())


@router.patch("/insights/{insight_id}", response_model=SavedInsightRead)
async def patch_insight(
    insight_id: str, payload: SavedInsightPatch, request: Request
) -> SavedInsightRead:
    await _ensure_schema(request)
    values = payload.model_dump(exclude_unset=True)
    if values:
        async with _session(request) as session:
            insight = await session.get(InsightRecord, insight_id)
            if insight is None:
                raise HTTPException(status_code=404, detail="Insight not found")
            updated_at = datetime.now(UTC)
            for key, value in values.items():
                setattr(insight, key, value)
            insight.updated_at = updated_at
            session.add(insight)
            if "config" in values:
                session.add(
                    InsightRevisionRecord(
                        insight_id=insight_id,
                        config=values["config"],
                        created_at=updated_at,
                    )
                )
            await session.commit()
    return await get_insight(insight_id, request)


@router.get("/insights/{insight_id}/export.yaml")
async def export_insight_yaml(insight_id: str, request: Request) -> Response:
    insight = await get_insight(insight_id, request)
    body = yaml.safe_dump(_saved_insight_export(insight), sort_keys=False)
    return Response(content=body, media_type="application/yaml")


@router.get("/insights/{insight_id}/export.json")
async def export_insight_json(insight_id: str, request: Request) -> dict[str, Any]:
    insight = await get_insight(insight_id, request)
    return _saved_insight_export(insight)


@router.post("/insights/execute", response_model=InsightResultRead)
async def execute_adhoc_insight(
    payload: InsightExecuteRequest, request: Request
) -> InsightResultRead:
    await _ensure_schema(request)
    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    analytics_store = _analytics_store_for_project(request, payload.project_id)
    try:
        async with _session(request) as session:
            result = await execute_insight(
                session=session,
                analytics_store=analytics_store,
                project_id=payload.project_id,
                config=payload.config or {},
                refresh=payload.refresh,
            )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return InsightResultRead(result=result)


@router.post("/insights/{insight_id}/execute", response_model=InsightResultRead)
async def execute_saved_insight(
    insight_id: str,
    payload: InsightExecuteRequest,
    request: Request,
) -> InsightResultRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        insight = await session.get(InsightRecord, insight_id)
        if insight is None:
            raise HTTPException(status_code=404, detail="Insight not found")
        project_id = payload.project_id or insight.project_id
        if project_id is not None:
            await _require_project(request, project_id)
        analytics_store = _analytics_store_for_project(request, project_id)
        try:
            result = await execute_insight(
                session=session,
                analytics_store=analytics_store,
                project_id=project_id,
                insight=insight,
                config=payload.config,
                refresh=payload.refresh,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return InsightResultRead(result=result)


@router.get("/reports", response_model=list[SavedReportRead])
async def list_reports(
    request: Request,
    project_id: str | None = Query(default=None),
) -> list[SavedReportRead]:
    await _ensure_schema(request)
    if project_id is not None:
        await _require_project(request, project_id)
    async with _session(request) as session:
        statement = select(ReportRecord)
        if project_id is not None:
            statement = statement.where(ReportRecord.project_id == project_id)
        rows = (await session.exec(statement)).all()
    return [SavedReportRead.model_validate(row.model_dump()) for row in rows]


@router.post("/reports", response_model=SavedReportRead, status_code=201)
async def create_report(
    payload: SavedReportCreate, request: Request
) -> SavedReportRead:
    await _ensure_schema(request)
    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    now = datetime.now(UTC)
    report_id = payload.report_id or _new_id("report")
    async with _session(request) as session:
        report = ReportRecord(
            report_id=report_id,
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            config=payload.config,
            created_at=now,
            updated_at=now,
        )
        revision = ReportRevisionRecord(
            report_id=report_id,
            config=payload.config,
            created_at=now,
        )
        session.add(report)
        session.add(revision)
        await session.commit()
    return await get_saved_report(report_id, request)


@router.post("/reports/render", response_model=RenderedReportRead, status_code=201)
async def render_standalone_report(
    payload: ReportRenderRequest, request: Request
) -> RenderedReportRead:
    await _ensure_schema(request)
    rendered_report_id = payload.rendered_report_id or _new_id("rendered_report")
    created_at = datetime.now(UTC)
    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    if payload.report_id is not None:
        async with _session(request) as session:
            report = await session.get(ReportRecord, payload.report_id)
            if report is None:
                raise HTTPException(status_code=404, detail="Report not found")
            project_id = payload.project_id or report.project_id
            insights = await _report_insights(session, report)
            analytics_store = _analytics_store_for_project(request, project_id)
            result = await execute_report(
                session=session,
                analytics_store=analytics_store,
                project_id=project_id,
                report=report,
                insights=insights,
                refresh=payload.refresh,
            )
            html = render_report_result(result)
            title = report.name
    else:
        project_id = payload.project_id
        html = render_report(payload.results, title=payload.title)
        title = payload.title
    values = RenderedReportRecord(
        rendered_report_id=rendered_report_id,
        project_id=project_id,
        run_id=payload.run_id,
        report_id=payload.report_id,
        title=title,
        html=html,
        created_at=created_at,
    )
    async with _session(request) as session:
        existing = await session.get(RenderedReportRecord, rendered_report_id)
        if existing is not None:
            await session.delete(existing)
        session.add(values)
        await session.commit()
    return RenderedReportRead(
        rendered_report_id=rendered_report_id,
        project_id=project_id,
        run_id=payload.run_id,
        report_id=payload.report_id,
        title=title,
        html=html,
        created_at=created_at,
    )


@router.get("/reports/{report_id}", response_model=SavedReportRead)
async def get_saved_report(report_id: str, request: Request) -> SavedReportRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await session.get(ReportRecord, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return SavedReportRead.model_validate(row.model_dump())


@router.patch("/reports/{report_id}", response_model=SavedReportRead)
async def patch_report(
    report_id: str, payload: SavedReportPatch, request: Request
) -> SavedReportRead:
    await _ensure_schema(request)
    values = payload.model_dump(exclude_unset=True)
    if values:
        async with _session(request) as session:
            report = await session.get(ReportRecord, report_id)
            if report is None:
                raise HTTPException(status_code=404, detail="Report not found")
            updated_at = datetime.now(UTC)
            for key, value in values.items():
                setattr(report, key, value)
            report.updated_at = updated_at
            session.add(report)
            if "config" in values:
                session.add(
                    ReportRevisionRecord(
                        report_id=report_id,
                        config=values["config"],
                        created_at=updated_at,
                    )
                )
            await session.commit()
    return await get_saved_report(report_id, request)


@router.get("/reports/{report_id}/export.yaml")
async def export_report_yaml(report_id: str, request: Request) -> Response:
    report = await get_saved_report(report_id, request)
    body = yaml.safe_dump(_saved_report_export(report), sort_keys=False)
    return Response(content=body, media_type="application/yaml")


@router.get("/reports/{report_id}/export.json")
async def export_report_json(report_id: str, request: Request) -> dict[str, Any]:
    report = await get_saved_report(report_id, request)
    return _saved_report_export(report)


@router.post("/reports/{report_id}/execute", response_model=ReportResultRead)
async def execute_saved_report(
    report_id: str,
    payload: ReportExecuteRequest,
    request: Request,
) -> ReportResultRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        report = await session.get(ReportRecord, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        project_id = payload.project_id or report.project_id
        if project_id is not None:
            await _require_project(request, project_id)
        insights = await _report_insights(session, report)
        analytics_store = _analytics_store_for_project(request, project_id)
        try:
            result = await execute_report(
                session=session,
                analytics_store=analytics_store,
                project_id=project_id,
                report=report,
                insights=insights,
                refresh=payload.refresh,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return ReportResultRead(result=result)


@router.get("/rendered-reports/{rendered_report_id}", response_model=RenderedReportRead)
async def get_rendered_report(
    rendered_report_id: str, request: Request
) -> RenderedReportRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await session.get(RenderedReportRecord, rendered_report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Rendered report not found")
    return RenderedReportRead.model_validate(row.model_dump())


@router.get("/rendered-reports/{rendered_report_id}/export.html")
async def export_rendered_report_html(
    rendered_report_id: str, request: Request
) -> Response:
    report = await get_rendered_report(rendered_report_id, request)
    return Response(content=report.html, media_type="text/html")


@router.get("/cohorts", response_model=list[CohortRead])
async def list_cohorts(request: Request) -> list[CohortRead]:
    rows = await _list_table(request, CohortRecord)
    return [CohortRead.model_validate(row.model_dump()) for row in rows]


@router.post("/cohorts", response_model=CohortRead, status_code=201)
async def create_cohort(payload: CohortCreate, request: Request) -> CohortRead:
    now = datetime.now(UTC)
    values = payload.model_dump(exclude={"cohort_id"}) | {
        "cohort_id": payload.cohort_id or _new_id("cohort"),
        "updated_at": now,
    }
    await _insert_values(request, CohortRecord, values)
    return CohortRead(**values)


@router.patch("/cohorts/{cohort_id}", response_model=CohortRead)
async def patch_cohort(
    cohort_id: str, payload: CohortPatch, request: Request
) -> CohortRead:
    values = payload.model_dump(exclude_unset=True) | {"updated_at": datetime.now(UTC)}
    await _patch_values(request, CohortRecord, "cohort_id", cohort_id, values)
    row = await _get_row(request, CohortRecord, "cohort_id", cohort_id)
    return CohortRead.model_validate(row.model_dump())


@router.get("/qc-policies", response_model=list[QCPolicyRead])
async def list_qc_policies(request: Request) -> list[QCPolicyRead]:
    rows = await _list_table(request, QCPolicyRecord)
    return [QCPolicyRead.model_validate(row.model_dump()) for row in rows]


@router.post("/qc-policies", response_model=QCPolicyRead, status_code=201)
async def create_qc_policy(payload: QCPolicyCreate, request: Request) -> QCPolicyRead:
    now = datetime.now(UTC)
    values = payload.model_dump(exclude={"policy_id"}) | {
        "policy_id": payload.policy_id or _new_id("policy"),
        "updated_at": now,
    }
    await _insert_values(request, QCPolicyRecord, values)
    return QCPolicyRead(**values)


@router.patch("/qc-policies/{policy_id}", response_model=QCPolicyRead)
async def patch_qc_policy(
    policy_id: str, payload: QCPolicyPatch, request: Request
) -> QCPolicyRead:
    values = payload.model_dump(exclude_unset=True) | {"updated_at": datetime.now(UTC)}
    await _patch_values(request, QCPolicyRecord, "policy_id", policy_id, values)
    row = await _get_row(request, QCPolicyRecord, "policy_id", policy_id)
    return QCPolicyRead.model_validate(row.model_dump())


@router.get("/database/tables", response_model=list[DatabaseTableRead])
async def list_database_tables(
    request: Request,
    project_id: str | None = Query(default=None),
) -> list[DatabaseTableRead]:
    if project_id is not None:
        await _require_project(request, project_id)
    catalog_counts = await _control_table_counts(request, project_id=project_id)
    analytics_store = _analytics_store_for_project(request, project_id)
    analytics_counts = analytics_store.row_counts()
    return [
        DatabaseTableRead(
            name=name,
            store="catalog",
            rows=catalog_counts.get(name, 0),
            columns=_catalog_columns(model),
            editable=name in EDITABLE_TABLES,
        )
        for name, (model, _) in sorted(CATALOG_TABLES.items())
    ] + [
        DatabaseTableRead(
            name=name,
            store="analytics",
            rows=analytics_counts.get(name, 0),
            columns=list(serializer.columns),
            editable=False,
        )
        for name, serializer in sorted(SERIALIZERS_BY_TABLE.items())
    ]


@router.get("/database/summary", response_model=DatabaseSummaryRead)
async def get_database_summary(
    request: Request,
    project_id: str | None = Query(default=None),
) -> DatabaseSummaryRead:
    if project_id is not None:
        await _require_project(request, project_id)
    control_counts = await _control_table_counts(request, project_id=project_id)
    analytics_store = _analytics_store_for_project(request, project_id)
    analytics_counts = analytics_store.row_counts()
    return DatabaseSummaryRead(
        sqlite_size_bytes=_sqlite_size_bytes(request.app.state.settings.database_url),
        duckdb_size_bytes=analytics_store.database_size_bytes(),
        file_size_bytes=_path_size(Path(request.app.state.settings.file_root)),
        total_runs=control_counts.get("runs", 0),
        total_samples=control_counts.get("samples", 0),
        total_scalar_metrics=analytics_counts.get("sample_metric_numeric", 0)
        + analytics_counts.get("sample_metric_string", 0),
        total_payloads=analytics_counts.get("profile_payloads", 0),
        control_tables=[
            TableCountRead(name=name, rows=count)
            for name, count in sorted(control_counts.items())
        ],
        analytics_tables=[
            TableCountRead(name=name, rows=count)
            for name, count in sorted(analytics_counts.items())
        ],
    )


@router.get("/database/tables/{table_name}/rows")
async def list_database_rows(table_name: str, request: Request) -> list[dict[str, Any]]:
    model, _, _ = _editable_table(table_name)
    rows = await _list_table(request, model)
    return [_jsonable_row(row) for row in rows]


@router.get(
    "/database/{store}/tables/{table_name}/rows",
    response_model=DatabaseTablePageRead,
)
async def preview_database_table(
    store: str,
    table_name: str,
    request: Request,
    project_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort_by: str | None = Query(default=None),
    sort_direction: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> DatabaseTablePageRead:
    if project_id is not None:
        await _require_project(request, project_id)
    if store == "catalog":
        return await _catalog_table_page(
            request,
            table_name,
            project_id=project_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
    if store == "analytics":
        analytics_store = _analytics_store_for_project(request, project_id)
        try:
            columns, rows, total = analytics_store.preview_table(
                table_name,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_direction=cast(Any, sort_direction),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="Analytical table not found"
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return DatabaseTablePageRead(
            name=table_name,
            store=store,
            columns=columns,
            rows=cast(list[dict[str, JsonValue]], rows),
            total=total,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_direction=sort_direction if sort_by is not None else None,
        )
    raise HTTPException(status_code=404, detail="Database store not found")


@router.patch("/database/tables/{table_name}/rows/{row_id}")
async def patch_database_row(
    table_name: str, row_id: str, payload: DatabaseRowPatch, request: Request
) -> dict[str, Any]:
    model, primary_key, allowed = _editable_table(table_name)
    disallowed = set(payload.values) - allowed
    if disallowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported editable columns: {', '.join(sorted(disallowed))}",
        )
    values = _coerce_json_values(model, payload.values)
    await _patch_values(request, model, primary_key, row_id, values)
    row = await _get_row(request, model, primary_key, row_id)
    return _jsonable_row(row)


async def _ensure_schema(request: Request) -> None:
    await request.app.state.store.ensure_schema()


def _engine(request: Request):
    return request.app.state.store._get_engine()


def _session(request: Request) -> AsyncSession:
    return AsyncSession(_engine(request))


async def _ensure_default_project(request: Request) -> ProjectRead:
    project = await request.app.state.store.ensure_default_project()
    return await _get_project_read(request, project.project_id)


async def _require_project(request: Request, project_id: str) -> ProjectRecord:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.project_id, project_id
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


async def _get_project_read(request: Request, project_id: str) -> ProjectRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.project_id, project_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return await _project_read(row, session=session)


async def _get_project_run(request: Request, project_id: str, run_id: str) -> Run:
    await _require_project(request, project_id)
    run = await request.app.state.store.get_run(run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


async def _get_run_record(request: Request, run_id: str) -> RunRecord:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await get_record_by_field(session, RunRecord, RunRecord.run_id, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


async def _get_project_run_record(
    request: Request, project_id: str, run_id: str
) -> RunRecord:
    project = await _require_project(request, project_id)
    row = await _get_run_record(request, run_id)
    if row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


async def _project_read(
    row: ProjectRecord,
    *,
    session: AsyncSession,
) -> ProjectRead:
    run_count = int(
        (
            await session.exec(
                select(func.count())
                .select_from(RunRecord)
                .where(RunRecord.project_id == row.id)
            )
        ).one()
    )
    sample_count = int(
        (
            await session.exec(
                select(func.count())
                .select_from(SampleRecord)
                .where(SampleRecord.project_id == row.id)
            )
        ).one()
    )
    subject_count = int(
        (
            await session.exec(
                select(func.count())
                .select_from(SubjectRecord)
                .where(SubjectRecord.project_id == row.id)
            )
        ).one()
    )
    latest_activity_at = (
        await session.exec(
            select(func.max(RunRecord.created_at)).where(RunRecord.project_id == row.id)
        )
    ).one()
    file_rows = (
        await session.exec(
            select(FileRecord)
            .join(
                FileLinkRecord,
                cast(Any, FileLinkRecord.file_id) == FileRecord.id,
            )
            .where(FileLinkRecord.project_id == row.id)
            .distinct()
        )
    ).all()
    file_count = len(file_rows)
    file_size_bytes = sum(file.size_bytes or 0 for file in file_rows)
    data = row.model_dump()
    return ProjectRead(
        **data,
        run_count=run_count,
        sample_count=sample_count,
        subject_count=subject_count,
        file_count=file_count,
        file_size_bytes=file_size_bytes,
        latest_activity_at=latest_activity_at,
    )


async def _list_samples(
    request: Request,
    *,
    project_id: str,
    limit: int,
    offset: int,
) -> SamplePageRead:
    await _ensure_schema(request)
    project = await _require_project(request, project_id)
    project_pk = project.id
    latest_run_subquery = (
        select(
            cast(Any, RunSampleRecord.sample_id).label("sample_id"),
            func.max(RunRecord.created_at).label("latest_run_created_at"),
        )
        .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
        .where(
            RunSampleRecord.project_id == project_pk,
            RunRecord.project_id == project_pk,
        )
        .group_by(cast(Any, RunSampleRecord.sample_id))
        .subquery()
    )
    run_count_subquery = (
        select(
            cast(Any, RunSampleRecord.sample_id).label("sample_id"),
            func.count(func.distinct(RunSampleRecord.run_id)).label("run_count"),
        )
        .where(RunSampleRecord.project_id == project_pk)
        .group_by(cast(Any, RunSampleRecord.sample_id))
        .subquery()
    )
    async with _session(request) as session:
        total = int(
            (
                await session.exec(
                    select(func.count())
                    .select_from(SampleRecord)
                    .where(SampleRecord.project_id == project_pk)
                )
            ).one()
        )
        statement = (
            select(
                SampleRecord,
                run_count_subquery.c.run_count,
                latest_run_subquery.c.latest_run_created_at,
            )
            .outerjoin(
                run_count_subquery,
                cast(Any, SampleRecord.id) == run_count_subquery.c.sample_id,
            )
            .outerjoin(
                latest_run_subquery,
                cast(Any, SampleRecord.id) == latest_run_subquery.c.sample_id,
            )
            .where(SampleRecord.project_id == project_pk)
            .order_by(
                cast(Any, latest_run_subquery.c.latest_run_created_at).desc(),
                SampleRecord.sample_id,
            )
        )
        rows = (await session.exec(statement.offset(offset).limit(limit))).all()
        items: list[SampleListItemRead] = []
        for sample_row, run_count, latest_run_created_at in rows:
            latest_run = await _latest_sample_run(
                session, project_id, sample_row.sample_id
            )
            items.append(
                await _sample_list_item_from_row_public(
                    session,
                    sample_row,
                    run_count=int(run_count or 0),
                    latest_run=latest_run[0] if latest_run is not None else None,
                    latest_run_created_at=latest_run_created_at,
                )
            )
    return SamplePageRead(items=items, total=total, limit=limit, offset=offset)


async def _require_project_sample(
    session: AsyncSession,
    project_id: str,
    sample_id: str,
) -> SampleRecord:
    project = await get_record_by_field(
        session, ProjectRecord, ProjectRecord.project_id, project_id
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    row = await get_record_where(
        session,
        SampleRecord,
        SampleRecord.project_id == project.id,
        SampleRecord.sample_id == sample_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return row


async def _sample_run_rows(
    session: AsyncSession,
    project_id: str,
    sample_id: str,
) -> list[tuple[RunRecord, RunSampleRecord]]:
    project = await get_record_by_field(
        session, ProjectRecord, ProjectRecord.project_id, project_id
    )
    sample = await get_record_by_field(
        session, SampleRecord, SampleRecord.sample_id, sample_id
    )
    if project is None or sample is None:
        return []
    rows = (
        await session.exec(
            select(RunRecord, RunSampleRecord)
            .join(
                RunSampleRecord,
                cast(Any, RunSampleRecord.run_id) == RunRecord.id,
            )
            .where(
                RunRecord.project_id == project.id,
                RunSampleRecord.project_id == project.id,
                RunSampleRecord.sample_id == sample.id,
            )
            .order_by(
                cast(Any, RunRecord.created_at).desc(),
                cast(Any, RunRecord.run_id).desc(),
            )
        )
    ).all()
    return [(run, run_sample) for run, run_sample in rows]


async def _latest_sample_run(
    session: AsyncSession,
    project_id: str,
    sample_id: str,
) -> tuple[RunRecord, RunSampleRecord] | None:
    rows = await _sample_run_rows(session, project_id, sample_id)
    return rows[0] if rows else None


async def _get_sample_run_link(
    session: AsyncSession,
    project_id: str,
    sample_id: str,
    run_id: str,
) -> tuple[RunRecord, RunSampleRecord]:
    project = await get_record_by_field(
        session, ProjectRecord, ProjectRecord.project_id, project_id
    )
    sample = await get_record_by_field(
        session, SampleRecord, SampleRecord.sample_id, sample_id
    )
    if project is None or sample is None:
        raise HTTPException(status_code=404, detail="Sample run not found")
    row = (
        await session.exec(
            select(RunRecord, RunSampleRecord)
            .join(
                RunSampleRecord,
                cast(Any, RunSampleRecord.run_id) == RunRecord.id,
            )
            .where(
                RunRecord.project_id == project.id,
                RunRecord.run_id == run_id,
                RunSampleRecord.project_id == project.id,
                RunSampleRecord.sample_id == sample.id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Sample run not found")
    return row


async def _list_runs(
    request: Request,
    *,
    project_id: str | None,
    limit: int,
    offset: int,
) -> RunPageRead:
    await _ensure_schema(request)
    project_pk: int | None = None
    if project_id is not None:
        project = await _require_project(request, project_id)
        project_pk = project.id
    async with _session(request) as session:
        count_statement = select(func.count()).select_from(RunRecord)
        rows_statement = select(RunRecord).order_by(
            cast(Any, RunRecord.created_at).desc(), RunRecord.run_id
        )
        if project_pk is not None:
            count_statement = count_statement.where(RunRecord.project_id == project_pk)
            rows_statement = rows_statement.where(RunRecord.project_id == project_pk)
        total = int((await session.exec(count_statement)).one())
        rows = (await session.exec(rows_statement.offset(offset).limit(limit))).all()
        items = [await _run_from_row_public(session, row) for row in rows]
    return RunPageRead(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


async def _run_from_row_public(session: AsyncSession, row: RunRecord) -> Run:
    return Run(
        run_id=row.run_id,
        project_id=await _public_label(
            session, ProjectRecord, "project_id", row.project_id
        ),
        data_import_id=await _public_label(
            session, DataImportRecord, "data_import_id", row.data_import_id
        ),
        project=row.project,
        name=row.name,
        run_kind=row.run_kind,
        assay=row.assay,
        pipeline_name=row.pipeline_name,
        pipeline_version=row.pipeline_version,
        parameters_json=row.parameters_json,
        started_at=row.started_at,
        ended_at=row.ended_at,
        status=row.status,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
    )


async def _sample_from_row_public(
    session: AsyncSession,
    row: SampleRecord,
) -> Sample:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Sample(
        sample_id=row.sample_id,
        project_id=await _public_label(
            session, ProjectRecord, "project_id", row.project_id
        ),
        subject_id=await _public_label(
            session, SubjectRecord, "subject_id", row.subject_id
        ),
        sample_name=row.sample_name,
        metadata_json=metadata_dict,
    )


async def _sample_list_item_from_row_public(
    session: AsyncSession,
    row: SampleRecord,
    *,
    run_count: int,
    latest_run: RunRecord | None,
    latest_run_created_at: datetime | None,
) -> SampleListItemRead:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return SampleListItemRead(
        sample_id=row.sample_id,
        project_id=await _public_label(
            session, ProjectRecord, "project_id", row.project_id
        ),
        subject_id=await _public_label(
            session, SubjectRecord, "subject_id", row.subject_id
        ),
        sample_name=row.sample_name,
        metadata_json=metadata_dict,
        run_count=run_count,
        latest_run_id=latest_run.run_id if latest_run is not None else None,
        latest_run_name=latest_run.name if latest_run is not None else None,
        latest_run_created_at=latest_run_created_at,
    )


async def _sample_run_from_rows_public(
    session: AsyncSession,
    run: RunRecord,
    run_sample: RunSampleRecord,
) -> SampleRunRead:
    return SampleRunRead(
        run_id=run.run_id,
        project_id=await _public_label(
            session, ProjectRecord, "project_id", run.project_id
        ),
        name=run.name,
        run_kind=run.run_kind,
        assay=run.assay,
        pipeline_name=run.pipeline_name,
        pipeline_version=run.pipeline_version,
        status=run.status,
        created_at=run.created_at,
        run_sample_id=run_sample.run_sample_id,
        run_sample_status=run_sample.status,
    )


def _analytics_metric_reads(metrics: list[Any]) -> list[AnalyticsMetricRead]:
    return [
        AnalyticsMetricRead(
            run_id=metric.run_id,
            data_profile_id=metric.data_profile_id,
            run_sample_id=metric.run_sample_id,
            sample_id=metric.sample_id,
            metric_id=metric.metric_id,
            value=metric.value,
            source_file_id=metric.source_file_id,
        )
        for metric in metrics
    ]


def _analytics_payload_reads(payloads: list[Any]) -> list[AnalyticsPayloadRead]:
    return [
        AnalyticsPayloadRead(
            run_id=payload.run_id,
            data_profile_id=payload.data_profile_id,
            run_sample_id=payload.run_sample_id,
            payload_name=payload.payload_name,
            payload_kind=payload.payload_kind,
            storage_format=payload.storage_format,
            columns=_payload_columns(payload.metadata_json),
            rows=_payload_rows(payload.metadata_json),
            row_count=payload.row_count or len(_payload_rows(payload.metadata_json)),
            source_file_id=payload.source_file_id,
            source_hash=_payload_source_hash(payload.metadata_json),
        )
        for payload in payloads
    ]


def _analytics_store_for_project(
    request: Request, project_id: str | None
) -> DuckDBAnalyticsStore:
    settings = request.app.state.settings
    if settings.analytics_path:
        return DuckDBAnalyticsStore(settings.analytics_path)
    return DuckDBAnalyticsStore(
        analytics_path_for_project(
            settings.analytics_root, project_id or DEFAULT_PROJECT_ID
        )
    )


def _new_project_id() -> str:
    project_id = new_project_id()
    if not is_project_id(project_id):
        raise RuntimeError("Generated invalid project id")
    return project_id


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _payload_columns(metadata_json: dict[str, Any]) -> list[str]:
    columns = metadata_json.get("columns")
    return [str(column) for column in columns] if isinstance(columns, list) else []


def _payload_rows(metadata_json: dict[str, Any]) -> list[dict[str, Any]]:
    rows = metadata_json.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _payload_source_hash(metadata_json: dict[str, Any]) -> str | None:
    source_hash = metadata_json.get("source_hash")
    return source_hash if isinstance(source_hash, str) else None


def _saved_insight_export(insight: SavedInsightRead) -> dict[str, Any]:
    return {
        "insight_id": insight.insight_id,
        "project_id": insight.project_id,
        "name": insight.name,
        "description": insight.description,
        "config": insight.config,
    }


def _saved_report_export(report: SavedReportRead) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "project_id": report.project_id,
        "name": report.name,
        "description": report.description,
        "config": report.config,
    }


async def _report_insights(
    session: AsyncSession, report: ReportRecord
) -> list[InsightRecord]:
    items = report.config.get("items") if isinstance(report.config, dict) else None
    insight_ids: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("insight_id"), str):
                insight_ids.append(item["insight_id"])
    if not insight_ids:
        return []
    rows = (
        await session.exec(
            select(InsightRecord).where(
                cast(Any, InsightRecord.insight_id).in_(insight_ids)
            )
        )
    ).all()
    by_id = {row.insight_id: row for row in rows}
    return [by_id[insight_id] for insight_id in insight_ids if insight_id in by_id]


async def _list_table(request: Request, model: type[SQLModel]) -> list[SQLModel]:
    await _ensure_schema(request)
    async with _session(request) as session:
        return list((await session.exec(select(model))).all())


async def _catalog_table_page(
    request: Request,
    table_name: str,
    *,
    project_id: str | None,
    limit: int,
    offset: int,
    sort_by: str | None,
    sort_direction: str,
) -> DatabaseTablePageRead:
    model, primary_key = _catalog_table(table_name)
    columns = _catalog_columns(model)
    order_column_name = sort_by or primary_key
    if order_column_name not in model.model_fields:
        raise HTTPException(
            status_code=400, detail=f"Unknown column: {order_column_name}"
        )
    project_pk = await _project_pk(request, project_id)
    project_run_ids = await _project_run_ids(request, project_id)
    model_any = cast(Any, model)
    count_statement = select(func.count()).select_from(model)  # type: ignore[arg-type]
    row_statement = select(model)
    if (
        project_pk is not None
        and table_name == "data_profiles"
        and "project_id" in model.model_fields
    ):
        count_statement = count_statement.where(
            or_(model_any.project_id == project_pk, model_any.project_id.is_(None))
        )
        row_statement = row_statement.where(
            or_(model_any.project_id == project_pk, model_any.project_id.is_(None))
        )
    elif project_pk is not None and "project_id" in model.model_fields:
        count_statement = count_statement.where(model_any.project_id == project_pk)
        row_statement = row_statement.where(model_any.project_id == project_pk)
    elif project_run_ids is not None and "run_id" in model.model_fields:
        count_statement = count_statement.where(model_any.run_id.in_(project_run_ids))
        row_statement = row_statement.where(model_any.run_id.in_(project_run_ids))
    order_column = getattr(model, order_column_name)
    if sort_direction == "desc":
        order_column = order_column.desc()
    row_statement = row_statement.order_by(order_column).offset(offset).limit(limit)
    await _ensure_schema(request)
    async with _session(request) as session:
        total = int((await session.exec(count_statement)).one())
        rows = list((await session.exec(row_statement)).all())
    return DatabaseTablePageRead(
        name=table_name,
        store="catalog",
        columns=columns,
        rows=cast(list[dict[str, JsonValue]], [_jsonable_row(row) for row in rows]),
        total=total,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_direction=sort_direction if sort_by is not None else None,
    )


async def _control_table_counts(
    request: Request, project_id: str | None = None
) -> dict[str, int]:
    await _ensure_schema(request)
    async with _session(request) as session:
        counts: dict[str, int] = {}
        project_pk = await _project_pk(request, project_id, session=session)
        project_run_ids = await _project_run_ids(request, project_id, session=session)
        for name, (model, _) in CATALOG_TABLES.items():
            statement = select(func.count()).select_from(model)  # type: ignore[arg-type]
            model_any = cast(Any, model)
            if (
                project_pk is not None
                and name == "data_profiles"
                and "project_id" in model.model_fields
            ):
                statement = statement.where(
                    or_(
                        model_any.project_id == project_pk,
                        model_any.project_id.is_(None),
                    )
                )
            elif project_pk is not None and "project_id" in model.model_fields:
                statement = statement.where(model_any.project_id == project_pk)
            elif project_run_ids is not None and "run_id" in model.model_fields:
                statement = statement.where(model_any.run_id.in_(project_run_ids))
            counts[name] = int((await session.exec(statement)).one())
        return counts


async def _project_run_ids(
    request: Request,
    project_id: str | None,
    *,
    session: AsyncSession | None = None,
) -> list[int] | None:
    if project_id is None:
        return None
    own_session = False
    if session is None:
        await _ensure_schema(request)
        session = _session(request)
        own_session = True
    try:
        project_pk = await _project_pk(request, project_id, session=session)
        if project_pk is None:
            return []
        run_ids = (
            await session.exec(
                select(RunRecord.id).where(RunRecord.project_id == project_pk)
            )
        ).all()
        return [int(run_id) for run_id in run_ids if run_id is not None]
    finally:
        if own_session:
            await session.close()


async def _project_pk(
    request: Request,
    project_id: str | None,
    *,
    session: AsyncSession | None = None,
) -> int | None:
    if project_id is None:
        return None
    own_session = False
    if session is None:
        await _ensure_schema(request)
        session = _session(request)
        own_session = True
    try:
        project = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.project_id, project_id
        )
        return project.id if project is not None else None
    finally:
        if own_session:
            await session.close()


async def _project_public_id_for_pk(
    request: Request,
    project_pk: int | None,
) -> str | None:
    if project_pk is None:
        return None
    await _ensure_schema(request)
    async with _session(request) as session:
        project = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.id, project_pk
        )
    return project.project_id if project is not None else None


async def _insert_values(
    request: Request, model: type[SQLModel], values: dict[str, Any]
) -> None:
    await _ensure_schema(request)
    async with _session(request) as session:
        session.add(model.model_validate(values))
        await session.commit()


async def _patch_values(
    request: Request,
    model: type[SQLModel],
    primary_key: str,
    row_id: str,
    values: dict[str, Any],
) -> None:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await _get_row(request, model, primary_key, row_id, session=session)
        for key, value in values.items():
            setattr(row, key, value)
        session.add(row)
        await session.commit()


async def _get_row(
    request: Request,
    model: type[SQLModel],
    primary_key: str,
    row_id: str,
    *,
    session: AsyncSession | None = None,
) -> SQLModel:
    await _ensure_schema(request)
    own_session = False
    if session is None:
        session = _session(request)
        own_session = True
    try:
        key_value: Any = _coerce_primary_key_value(model, primary_key, row_id)
        row = (
            await session.exec(
                select(model).where(getattr(model, primary_key) == key_value)
            )
        ).first()
    finally:
        if own_session:
            await session.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Row not found")
    return row


def _editable_table(table_name: str) -> tuple[type[SQLModel], str, set[str]]:
    table_config = EDITABLE_TABLES.get(table_name)
    if table_config is None:
        raise HTTPException(status_code=404, detail="Editable table not found")
    return table_config


def _catalog_table(table_name: str) -> tuple[type[SQLModel], str]:
    table_config = CATALOG_TABLES.get(table_name)
    if table_config is None:
        raise HTTPException(status_code=404, detail="Catalog table not found")
    return table_config


def _catalog_columns(model: type[SQLModel]) -> list[str]:
    return list(model.model_fields)


def _coerce_json_values(
    model: type[SQLModel], values: dict[str, JsonValue]
) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    for key, value in values.items():
        field_name = _model_field_name(model, key)
        if key in {"config", "filters", "thresholds", "metadata", "value"}:
            coerced[field_name] = json.loads(json.dumps(value))
        else:
            coerced[field_name] = value
    return coerced


def _jsonable_row(row: SQLModel) -> dict[str, Any]:
    data = row.model_dump(mode="json")
    if isinstance(row, SampleRecord) and "metadata_json" in data:
        data["metadata"] = data.pop("metadata_json")
    return data


async def _file_from_rows_public(
    session: AsyncSession,
    file: FileRecord,
    link: FileLinkRecord | None = None,
    *,
    association_scope: str = "direct_run",
    association_reason: str | None = None,
) -> FileRead:
    if link is None:
        return _file_from_rows(
            file,
            link,
            association_scope=association_scope,
            association_reason=association_reason,
        )
    project_id = await _public_label(
        session, ProjectRecord, "project_id", link.project_id
    )
    data_import_id = await _public_label(
        session, DataImportRecord, "data_import_id", link.data_import_id
    )
    run_id = await _public_label(session, RunRecord, "run_id", link.run_id)
    run_sample_id = await _public_label(
        session, RunSampleRecord, "run_sample_id", link.run_sample_id
    )
    sample_id = await _public_label(session, SampleRecord, "sample_id", link.sample_id)
    data_profile_id = await _public_label(
        session, DataProfileRecord, "data_profile_id", link.data_profile_id
    )
    metadata_value = file.metadata_json
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    source_path = metadata.get("source_path")
    return FileRead(
        file_id=file.file_id,
        project_id=project_id,
        data_import_id=data_import_id,
        run_id=run_id,
        run_sample_id=run_sample_id,
        sample_id=sample_id,
        data_profile_id=data_profile_id,
        association_scope=association_scope,
        association_reason=association_reason,
        kind=file.file_role,
        path=file.path,
        uri=file.uri,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        source_path=source_path if isinstance(source_path, str) else None,
        created_at=file.created_at,
    )


async def _public_label(
    session: AsyncSession,
    model: type[SQLModel],
    label_name: str,
    identifier: int | None,
) -> str | None:
    if identifier is None:
        return None
    row = await get_record_by_field(session, model, cast(Any, model).id, identifier)
    if row is None:
        return None
    label = getattr(row, label_name)
    return str(label) if label is not None else None


def _file_from_rows(
    file: FileRecord,
    link: FileLinkRecord | None = None,
    *,
    association_scope: str = "direct_run",
    association_reason: str | None = None,
) -> FileRead:
    metadata_value = file.metadata_json
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    source_path = metadata.get("source_path")
    return FileRead(
        file_id=file.file_id,
        project_id=str(file.project_id) if file.project_id is not None else None,
        data_import_id=(
            str(link.data_import_id)
            if link is not None and link.data_import_id is not None
            else None
        ),
        run_id=(
            str(link.run_id) if link is not None and link.run_id is not None else None
        ),
        run_sample_id=(
            str(link.run_sample_id)
            if link is not None and link.run_sample_id is not None
            else None
        ),
        sample_id=(
            str(link.sample_id)
            if link is not None and link.sample_id is not None
            else None
        ),
        data_profile_id=(
            str(link.data_profile_id)
            if link is not None and link.data_profile_id is not None
            else None
        ),
        association_scope=association_scope,
        association_reason=association_reason,
        kind=file.file_role,
        path=file.path,
        uri=file.uri,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        source_path=source_path if isinstance(source_path, str) else None,
        created_at=file.created_at,
    )


def _dedupe_file_reads(files: list[FileRead]) -> list[FileRead]:
    by_file_id: dict[str, FileRead] = {}
    for file in files:
        existing = by_file_id.get(file.file_id)
        if existing is None or _file_read_rank(file) > _file_read_rank(existing):
            by_file_id[file.file_id] = file
    return sorted(by_file_id.values(), key=lambda item: item.file_id)


def _file_read_rank(file: FileRead) -> tuple[int, int]:
    scope_rank = {"direct_run": 3, "direct_sample": 3, "data_import": 2}.get(
        file.association_scope,
        1,
    )
    profile_rank = 1 if file.data_profile_id is not None else 0
    return scope_rank, profile_rank


def _model_field_name(model: type[SQLModel], requested_name: str) -> str:
    if requested_name in model.model_fields:
        return requested_name
    if requested_name == "metadata" and "metadata_json" in model.model_fields:
        return "metadata_json"
    return requested_name


def _coerce_primary_key_value(
    model: type[SQLModel], primary_key: str, value: str
) -> Any:
    field_info = model.model_fields.get(primary_key)
    if field_info is None:
        return value
    annotation = field_info.annotation
    if annotation is int:
        return int(value)
    if get_origin(annotation) is not None and int in get_args(annotation):
        return int(value)
    return value


def _sqlite_size_bytes(database_url: str) -> int:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return 0
    path_value = database_url.removeprefix(prefix)
    if path_value == ":memory:":
        return 0
    path = Path(path_value)
    return path.stat().st_size if path.exists() else 0


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
