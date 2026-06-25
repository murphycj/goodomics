from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_args, get_origin
from uuid import uuid4

import yaml
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func
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
from goodomics.report.html import render_report
from goodomics.schemas.models import Run, Sample
from goodomics.server.ai import (
    AIProviderNotConfigured,
    ChatMessage,
    ChatResult,
)
from goodomics.server.db.models import (
    CohortRecord,
    QCPolicyRecord,
    ReportRecord,
    ReportTemplateRecord,
    ReportTemplateRevisionRecord,
)
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    FileLinkRecord,
    FileRecord,
    ProjectRecord,
    RunRecord,
    RunSampleRecord,
    SampleRecord,
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
    metadata_json: dict[str, JsonValue] | None = None


class ProjectRead(SQLModel):
    project_id: str
    slug: str | None = None
    name: str
    description: str | None = None
    metadata_json: dict[str, JsonValue]
    created_at: datetime
    run_count: int = 0
    sample_count: int = 0
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
    run_id: str | None = None
    kind: str = "file"
    path: str | None = None
    uri: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    source_path: str | None = None
    created_at: datetime | None = None


class ReportTemplateBase(SQLModel):
    name: str
    description: str | None = None
    config: dict[str, JsonValue] = Field(default_factory=dict)


class ReportTemplateCreate(ReportTemplateBase):
    template_id: str | None = None


class ReportTemplatePatch(SQLModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, JsonValue] | None = None


class ReportTemplateRead(ReportTemplateBase):
    template_id: str
    created_at: datetime
    updated_at: datetime


class ReportRenderRequest(SQLModel):
    results: str = "."
    report_id: str | None = None
    run_id: str | None = None
    template_id: str | None = None
    title: str = "Goodomics Report"


class ReportRead(SQLModel):
    report_id: str
    run_id: str | None = None
    template_id: str | None = None
    title: str
    html: str
    created_at: datetime


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
    editable: bool


class AnalyticsMetricRead(SQLModel):
    run_id: str
    data_profile_key: str
    run_sample_key: str | None = None
    sample_key: str | None = None
    metric_key: str
    value: float | str
    source_file_id: str | None = None


class AnalyticsPayloadRead(SQLModel):
    run_id: str
    data_profile_key: str
    run_sample_key: str | None = None
    payload_name: str
    payload_kind: str
    storage_format: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    source_file_id: str | None = None
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


EDITABLE_TABLES: dict[str, tuple[type[SQLModel], str, set[str]]] = {
    "projects": (
        ProjectRecord,
        "project_id",
        {"name", "slug", "description", "metadata_json"},
    ),
    "runs": (RunRecord, "run_id", {"project", "assay"}),
    "samples": (SampleRecord, "sample_id", {"sample_name", "metadata_json"}),
    "files": (FileRecord, "file_id", {"file_role", "path", "uri", "metadata_json"}),
    "report_templates": (
        ReportTemplateRecord,
        "template_id",
        {"name", "description", "config"},
    ),
    "reports": (ReportRecord, "report_id", {"title"}),
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
        existing = (
            await session.exec(select(ProjectRecord).where(ProjectRecord.slug == slug))
        ).first()
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
    run = await _get_project_run(request, project_id, run_id)
    return _analytics_metric_reads(
        _analytics_store_for_project(request, run.project_id).list_metric_values(run_id)
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
    run = await _get_project_run(request, project_id, run_id)
    return _analytics_payload_reads(
        _analytics_store_for_project(request, run.project_id).list_profile_payloads(
            run_id
        )
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
    await _require_project(request, project_id)
    await _ensure_schema(request)
    async with _session(request) as session:
        row = (
            await session.exec(
                select(SampleRecord).where(
                    SampleRecord.project_id == project_id,
                    SampleRecord.sample_id == sample_id,
                )
            )
        ).first()
        if row is None:
            row = (
                await session.exec(
                    select(SampleRecord)
                    .join(
                        RunSampleRecord,
                        cast(Any, RunSampleRecord.sample_id) == SampleRecord.sample_id,
                    )
                    .where(
                        RunSampleRecord.project_id == project_id,
                        RunSampleRecord.sample_id == sample_id,
                    )
                )
            ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return _sample_from_row(row)


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
    return [_sample_run_from_rows(run, run_sample) for run, run_sample in rows]


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
        _, run_sample = await _get_sample_run_link(
            session, project_id, sample_id, run_id
        )
    metrics = _analytics_store_for_project(request, project_id).list_metric_values(
        run_id,
        sample_key=sample_id,
        run_sample_key=run_sample.run_sample_id,
    )
    return _analytics_metric_reads(metrics)


@router.patch("/projects/{project_id}", response_model=ProjectRead)
async def patch_project(
    project_id: str, payload: ProjectPatch, request: Request
) -> ProjectRead:
    await _ensure_schema(request)
    values = payload.model_dump(exclude_unset=True)
    async with _session(request) as session:
        row = await session.get(ProjectRecord, project_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if "slug" in values and values["slug"] is not None:
            slug = validate_project_slug(str(values["slug"]))
            existing = (
                await session.exec(
                    select(ProjectRecord).where(
                        ProjectRecord.slug == slug,
                        ProjectRecord.project_id != project_id,
                    )
                )
            ).first()
            if existing is not None:
                raise HTTPException(
                    status_code=409, detail="Project slug already exists"
                )
            row.slug = slug
        if "name" in values and values["name"] is not None:
            row.name = str(values["name"]).strip() or row.name
        if "description" in values:
            row.description = values["description"]
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
    if project_id is not None:
        await _require_project(request, project_id)
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
                SampleRecord.project_id == project_id
            )
        sample_rows = (await session.exec(sample_statement.limit(limit))).all()

        run_statement = select(RunRecord).where(
            (func.lower(RunRecord.run_id).like(pattern))
            | (func.lower(RunRecord.name).like(pattern))
        )
        if project_id is not None:
            run_statement = run_statement.where(RunRecord.project_id == project_id)
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
        project_rows: dict[str, ProjectRecord] = {}
        if project_ids:
            project_rows = {
                project.project_id: project
                for project in (
                    await session.exec(
                        select(ProjectRecord).where(
                            cast(Any, ProjectRecord.project_id).in_(project_ids)
                        )
                    )
                ).all()
            }
    return [
        SearchResultRead(
            kind="sample",
            project_id=row.project_id,
            project_name=project_rows[row.project_id].name
            if row.project_id in project_rows
            else None,
            sample_id=row.sample_id,
            sample_name=row.sample_name,
        )
        for row in sample_rows
    ] + [
        SearchResultRead(
            kind="run",
            project_id=row.project_id,
            project_name=project_rows[row.project_id].name
            if row.project_id in project_rows
            else None,
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
            row = await session.get(RunRecord, run_id)
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
    statement = (
        select(FileRecord, FileLinkRecord)
        .join(FileLinkRecord, cast(Any, FileLinkRecord.file_id) == FileRecord.file_id)
        .where(FileLinkRecord.run_id == run_id)
        .order_by(FileRecord.file_id)
    )
    if project_id is not None:
        statement = statement.where(FileLinkRecord.project_id == project_id)
    async with _session(request) as session:
        rows = (await session.exec(statement)).all()
    return [_file_from_rows(file, link) for file, link in rows]


@router.get(
    "/runs/{run_id}/analytics/metrics",
    response_model=list[AnalyticsMetricRead],
)
async def list_run_analytics_metrics(
    run_id: str, request: Request
) -> list[AnalyticsMetricRead]:
    run = await get_run(run_id, request)
    analytics_store = _analytics_store_for_project(request, run.project_id)
    return _analytics_metric_reads(analytics_store.list_metric_values(run_id))


@router.get(
    "/runs/{run_id}/analytics/payloads",
    response_model=list[AnalyticsPayloadRead],
)
async def list_run_analytics_payloads(
    run_id: str, request: Request
) -> list[AnalyticsPayloadRead]:
    run = await get_run(run_id, request)
    analytics_store = _analytics_store_for_project(request, run.project_id)
    return _analytics_payload_reads(analytics_store.list_profile_payloads(run_id))


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
        row = await session.get(FileRecord, file_id)
        if row is not None and project_id is not None:
            link = (
                await session.exec(
                    select(FileLinkRecord).where(
                        FileLinkRecord.file_id == file_id,
                        FileLinkRecord.project_id == project_id,
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


@router.get("/report-templates", response_model=list[ReportTemplateRead])
async def list_report_templates(request: Request) -> list[ReportTemplateRead]:
    await _ensure_schema(request)
    async with _session(request) as session:
        rows = (await session.exec(select(ReportTemplateRecord))).all()
    return [_template_from_row(row) for row in rows]


@router.post("/report-templates", response_model=ReportTemplateRead, status_code=201)
async def create_report_template(
    payload: ReportTemplateCreate, request: Request
) -> ReportTemplateRead:
    await _ensure_schema(request)
    now = datetime.now(UTC)
    template_id = payload.template_id or _new_id("template")
    async with _session(request) as session:
        template = ReportTemplateRecord(
            template_id=template_id,
            name=payload.name,
            description=payload.description,
            config=payload.config,
            created_at=now,
            updated_at=now,
        )
        revision = ReportTemplateRevisionRecord(
            template_id=template_id,
            config=payload.config,
            created_at=now,
        )
        session.add(template)
        session.add(revision)
        await session.commit()
    return await get_report_template(template_id, request)


@router.get("/report-templates/{template_id}", response_model=ReportTemplateRead)
async def get_report_template(template_id: str, request: Request) -> ReportTemplateRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await session.get(ReportTemplateRecord, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Report template not found")
    return _template_from_row(row)


@router.patch("/report-templates/{template_id}", response_model=ReportTemplateRead)
async def patch_report_template(
    template_id: str, payload: ReportTemplatePatch, request: Request
) -> ReportTemplateRead:
    await _ensure_schema(request)
    values = payload.model_dump(exclude_unset=True)
    if values:
        async with _session(request) as session:
            template = await session.get(ReportTemplateRecord, template_id)
            if template is None:
                raise HTTPException(status_code=404, detail="Report template not found")
            updated_at = datetime.now(UTC)
            for key, value in values.items():
                setattr(template, key, value)
            template.updated_at = updated_at
            session.add(template)
            if "config" in values:
                session.add(
                    ReportTemplateRevisionRecord(
                        template_id=template_id,
                        config=values["config"],
                        created_at=updated_at,
                    )
                )
            await session.commit()
    return await get_report_template(template_id, request)


@router.get("/report-templates/{template_id}/export.yaml")
async def export_report_template_yaml(template_id: str, request: Request) -> Response:
    template = await get_report_template(template_id, request)
    body = yaml.safe_dump(_template_export(template), sort_keys=False)
    return Response(content=body, media_type="application/yaml")


@router.get("/report-templates/{template_id}/export.json")
async def export_report_template_json(
    template_id: str, request: Request
) -> dict[str, Any]:
    template = await get_report_template(template_id, request)
    return _template_export(template)


@router.post("/reports/render", response_model=ReportRead, status_code=201)
async def render_standalone_report(
    payload: ReportRenderRequest, request: Request
) -> ReportRead:
    await _ensure_schema(request)
    report_id = payload.report_id or _new_id("report")
    html = render_report(payload.results, title=payload.title)
    created_at = datetime.now(UTC)
    values = ReportRecord(
        report_id=report_id,
        run_id=payload.run_id,
        template_id=payload.template_id,
        title=payload.title,
        html=html,
        created_at=created_at,
    )
    async with _session(request) as session:
        existing = await session.get(ReportRecord, report_id)
        if existing is not None:
            await session.delete(existing)
        session.add(values)
        await session.commit()
    return ReportRead(
        report_id=report_id,
        run_id=payload.run_id,
        template_id=payload.template_id,
        title=payload.title,
        html=html,
        created_at=created_at,
    )


@router.get("/reports/{report_id}", response_model=ReportRead)
async def get_report(report_id: str, request: Request) -> ReportRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await session.get(ReportRecord, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportRead.model_validate(row.model_dump())


@router.get("/reports/{report_id}/export.html")
async def export_report_html(report_id: str, request: Request) -> Response:
    report = await get_report(report_id, request)
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
async def list_database_tables() -> list[DatabaseTableRead]:
    return [
        DatabaseTableRead(name=name, editable=True) for name in sorted(EDITABLE_TABLES)
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
        row = await session.get(ProjectRecord, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


async def _get_project_read(request: Request, project_id: str) -> ProjectRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = await session.get(ProjectRecord, project_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return await _project_read(row, session=session)


async def _get_project_run(request: Request, project_id: str, run_id: str) -> Run:
    await _require_project(request, project_id)
    run = await request.app.state.store.get_run(run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


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
                .where(RunRecord.project_id == row.project_id)
            )
        ).one()
    )
    sample_count = int(
        (
            await session.exec(
                select(func.count())
                .select_from(SampleRecord)
                .where(SampleRecord.project_id == row.project_id)
            )
        ).one()
    )
    latest_activity_at = (
        await session.exec(
            select(func.max(RunRecord.created_at)).where(
                RunRecord.project_id == row.project_id
            )
        )
    ).one()
    file_rows = (
        await session.exec(
            select(FileRecord)
            .join(
                FileLinkRecord,
                cast(Any, FileLinkRecord.file_id) == FileRecord.file_id,
            )
            .where(FileLinkRecord.project_id == row.project_id)
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
    latest_run_subquery = (
        select(
            cast(Any, RunSampleRecord.sample_id).label("sample_id"),
            func.max(RunRecord.created_at).label("latest_run_created_at"),
        )
        .join(RunRecord, cast(Any, RunRecord.run_id) == RunSampleRecord.run_id)
        .where(
            RunSampleRecord.project_id == project_id,
            RunRecord.project_id == project_id,
        )
        .group_by(RunSampleRecord.sample_id)
        .subquery()
    )
    run_count_subquery = (
        select(
            cast(Any, RunSampleRecord.sample_id).label("sample_id"),
            func.count(func.distinct(RunSampleRecord.run_id)).label("run_count"),
        )
        .where(RunSampleRecord.project_id == project_id)
        .group_by(RunSampleRecord.sample_id)
        .subquery()
    )
    async with _session(request) as session:
        total = int(
            (
                await session.exec(
                    select(func.count())
                    .select_from(SampleRecord)
                    .where(SampleRecord.project_id == project_id)
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
                cast(Any, SampleRecord.sample_id) == run_count_subquery.c.sample_id,
            )
            .outerjoin(
                latest_run_subquery,
                cast(Any, SampleRecord.sample_id) == latest_run_subquery.c.sample_id,
            )
            .where(SampleRecord.project_id == project_id)
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
                _sample_list_item_from_row(
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
    row = (
        await session.exec(
            select(SampleRecord).where(
                SampleRecord.project_id == project_id,
                SampleRecord.sample_id == sample_id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return row


async def _sample_run_rows(
    session: AsyncSession,
    project_id: str,
    sample_id: str,
) -> list[tuple[RunRecord, RunSampleRecord]]:
    rows = (
        await session.exec(
            select(RunRecord, RunSampleRecord)
            .join(
                RunSampleRecord,
                cast(Any, RunSampleRecord.run_id) == RunRecord.run_id,
            )
            .where(
                RunRecord.project_id == project_id,
                RunSampleRecord.project_id == project_id,
                RunSampleRecord.sample_id == sample_id,
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
    row = (
        await session.exec(
            select(RunRecord, RunSampleRecord)
            .join(
                RunSampleRecord,
                cast(Any, RunSampleRecord.run_id) == RunRecord.run_id,
            )
            .where(
                RunRecord.project_id == project_id,
                RunRecord.run_id == run_id,
                RunSampleRecord.project_id == project_id,
                RunSampleRecord.sample_id == sample_id,
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
    if project_id is not None:
        await _require_project(request, project_id)
    async with _session(request) as session:
        count_statement = select(func.count()).select_from(RunRecord)
        rows_statement = select(RunRecord).order_by(
            cast(Any, RunRecord.created_at).desc(), RunRecord.run_id
        )
        if project_id is not None:
            count_statement = count_statement.where(RunRecord.project_id == project_id)
            rows_statement = rows_statement.where(RunRecord.project_id == project_id)
        total = int((await session.exec(count_statement)).one())
        rows = (await session.exec(rows_statement.offset(offset).limit(limit))).all()
    return RunPageRead(
        items=[_run_from_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _run_from_row(row: RunRecord) -> Run:
    return Run(
        run_id=row.run_id,
        project_id=row.project_id,
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


def _sample_from_row(row: SampleRecord) -> Sample:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Sample(
        sample_id=row.sample_id,
        project_id=row.project_id,
        subject_id=row.subject_id,
        sample_name=row.sample_name,
        metadata_json=metadata_dict,
    )


def _sample_list_item_from_row(
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
        project_id=row.project_id,
        subject_id=row.subject_id,
        sample_name=row.sample_name,
        metadata_json=metadata_dict,
        run_count=run_count,
        latest_run_id=latest_run.run_id if latest_run is not None else None,
        latest_run_name=latest_run.name if latest_run is not None else None,
        latest_run_created_at=latest_run_created_at,
    )


def _sample_run_from_rows(run: RunRecord, run_sample: RunSampleRecord) -> SampleRunRead:
    return SampleRunRead(
        run_id=run.run_id,
        project_id=run.project_id,
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
            data_profile_key=metric.data_profile_key,
            run_sample_key=metric.run_sample_key,
            sample_key=metric.sample_key,
            metric_key=metric.metric_key,
            value=metric.value,
            source_file_id=metric.source_file_id,
        )
        for metric in metrics
    ]


def _analytics_payload_reads(payloads: list[Any]) -> list[AnalyticsPayloadRead]:
    return [
        AnalyticsPayloadRead(
            run_id=payload.run_id,
            data_profile_key=payload.data_profile_key,
            run_sample_key=payload.run_sample_key,
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


def _template_from_row(row: ReportTemplateRecord) -> ReportTemplateRead:
    return ReportTemplateRead.model_validate(row.model_dump())


def _template_export(template: ReportTemplateRead) -> dict[str, Any]:
    return {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "config": template.config,
    }


async def _list_table(request: Request, model: type[SQLModel]) -> list[SQLModel]:
    await _ensure_schema(request)
    async with _session(request) as session:
        return list((await session.exec(select(model))).all())


async def _control_table_counts(
    request: Request, project_id: str | None = None
) -> dict[str, int]:
    await _ensure_schema(request)
    async with _session(request) as session:
        counts: dict[str, int] = {}
        project_run_ids: list[str] | None = None
        if project_id is not None:
            project_run_ids = list(
                (
                    await session.exec(
                        select(RunRecord.run_id).where(
                            RunRecord.project_id == project_id
                        )
                    )
                ).all()
            )
        for name, (model, _, _) in EDITABLE_TABLES.items():
            statement = select(func.count()).select_from(model)  # type: ignore[arg-type]
            model_any = cast(Any, model)
            if project_id is not None and "project_id" in model.model_fields:
                statement = statement.where(model_any.project_id == project_id)
            elif project_run_ids is not None and "run_id" in model.model_fields:
                statement = statement.where(model_any.run_id.in_(project_run_ids))
            counts[name] = int((await session.exec(statement)).one())
        return counts


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


def _file_from_rows(file: FileRecord, link: FileLinkRecord | None = None) -> FileRead:
    metadata_value = file.metadata_json
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    source_path = metadata.get("source_path")
    return FileRead(
        file_id=file.file_id,
        project_id=file.project_id,
        run_id=link.run_id if link is not None else None,
        kind=file.file_role,
        path=file.path,
        uri=file.uri,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        source_path=source_path if isinstance(source_path, str) else None,
        created_at=file.created_at,
    )


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
