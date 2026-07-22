"""FastAPI routes for the Goodomics server API.

This module owns the HTTP boundary for the dashboard and local server. Route
handlers validate request models, enforce project scoping, delegate analytical
work to the metadata/DuckDB stores, and translate internal SQLModel records into
JSON-ready API shapes.

The lower helpers intentionally keep database details close to the routes that
need them: public IDs are resolved from internal integer keys, project-specific
analytics stores are selected, and database-preview endpoints are constrained by
the shared metadata registry.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast, get_args, get_origin
from uuid import uuid4

import yaml
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlmodel import SQLModel, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.analysis import GENERIC_ANALYSIS, analysis_method, resolve_analysis_type
from goodomics.projects import (
    DEFAULT_PROJECT_ID,
    analytics_path_for_project,
    display_name_from_slug,
    is_project_id,
    new_project_id,
    validate_project_slug,
)
from goodomics.report.html import render_report, render_report_result
from goodomics.schemas.models import Run, RunSample, Sample
from goodomics.server.ai import (
    AIProviderNotConfigured,
    ChatMessage,
    ChatResult,
)
from goodomics.server.auth import (
    Principal,
    authorize_api_request,
    authorized_project_pks,
    project_permissions,
    require_project_permission,
    seed_project_roles,
)
from goodomics.server.db.metadata import EDITABLE_TABLES, METADATA_TABLES
from goodomics.server.db.models import (
    InsightRecord,
    InsightResultCacheRecord,
    InsightRevisionRecord,
    QCPolicyRecord,
    RenderedReportRecord,
    ReportRecord,
    ReportResultCacheRecord,
    ReportRevisionRecord,
)
from goodomics.server.insight_capabilities import insight_capabilities
from goodomics.server.insights import (
    execute_insight,
    execute_report,
    normalize_insight_config,
    validate_and_explain_config,
)
from goodomics.server.rate_limits import principal_rate_key
from goodomics.storage.duckdb import SERIALIZERS_BY_TABLE, DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    AnalysisMethodRecord,
    AnalysisTypeRecord,
    DataContractAnalysisTypeRecord,
    DataContractFieldRecord,
    DataContractRecord,
    DataImportRecord,
    FileLinkRecord,
    FileRecord,
    ProjectRecord,
    RunContractRecord,
    RunRecord,
    RunSampleRecord,
    SampleGroupMemberRecord,
    SampleGroupRecord,
    SampleRecord,
    SubjectRecord,
    get_record_by_field,
    get_record_where,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize_api_request)])
JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
UPLOAD_FILE = File(...)


# Request/response schemas are kept near the routes that use them so FastAPI's
# generated OpenAPI schema stays aligned with the HTTP surface. They use
# Pydantic directly because they are HTTP DTOs, not SQL table records.
class RunCreate(BaseModel):
    """Payload for creating a run through the API."""

    run_id: str | None = None
    project_id: str | None = None
    project: str | None = None
    analysis_type_id: str = GENERIC_ANALYSIS
    method_id: str = "goodomics-api"
    method_version: str | None = None
    method_kind: Literal[
        "workflow", "tool", "algorithm", "notebook", "benchmark", "script", "importer"
    ] = "script"
    samples: list[Sample] = Field(default_factory=list)


class RunPatch(BaseModel):
    """Fields that can be patched on an existing run."""

    project: str | None = None
    analysis_type_id: str | None = None
    method_id: str | None = None
    method_version: str | None = None


class RunPageRead(BaseModel):
    """Paginated run list response."""

    items: list[Run]
    total: int
    limit: int
    offset: int


class SampleListItemRead(BaseModel):
    """Compact sample row used in paginated project sample lists."""

    sample_id: str
    project_id: str | None = None
    subject_id: str | None = None
    sample_name: str | None = None
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict)
    run_count: int = 0
    latest_run_id: str | None = None
    latest_run_name: str | None = None
    latest_run_created_at: datetime | None = None


class SamplePageRead(BaseModel):
    """Paginated sample list response."""

    items: list[SampleListItemRead]
    total: int
    limit: int
    offset: int


class SampleRunRead(BaseModel):
    """Run membership for a sample, including run-sample status."""

    run_id: str
    project_id: str | None = None
    name: str | None = None
    run_kind: str
    analysis_type_id: str
    method_id: str
    method_version: str | None = None
    status: str
    created_at: datetime
    run_sample_id: str
    run_sample_status: str


class RunSampleListItemRead(BaseModel):
    """Compact run/sample link row used by project-scoped pickers."""

    run_sample_id: str
    run_id: str
    run_name: str | None = None
    sample_id: str
    sample_name: str | None = None
    subject_id: str | None = None
    role: str | None = None
    status: str
    created_at: datetime


class RunSamplePageRead(BaseModel):
    """Paginated project run/sample link list response."""

    items: list[RunSampleListItemRead]
    total: int
    limit: int
    offset: int


class ProjectCreate(BaseModel):
    """Payload for creating a project."""

    name: str
    slug: str | None = None
    description: str | None = None
    visibility: Literal["private", "public"] = "private"
    default_storage_location: str | None = None
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict)


class ProjectPatch(BaseModel):
    """Fields that can be patched on an existing project."""

    name: str | None = None
    slug: str | None = None
    description: str | None = None
    default_report_id: str | None = None
    visibility: Literal["private", "public"] | None = None
    default_storage_location: str | None = None
    metadata_json: dict[str, JsonValue] | None = None


class ProjectRead(BaseModel):
    """Project response enriched with dashboard summary counts."""

    project_id: str
    slug: str | None = None
    name: str
    description: str | None = None
    default_report_id: str | None = None
    visibility: Literal["private", "public"] = "private"
    default_storage_location: str | None = None
    metadata_json: dict[str, JsonValue]
    created_at: datetime
    run_count: int = 0
    sample_count: int = 0
    subject_count: int = 0
    file_count: int = 0
    file_size_bytes: int = 0
    latest_activity_at: datetime | None = None


class SearchResultRead(BaseModel):
    """A lightweight result from the global sample/run search endpoint."""

    kind: str
    project_id: str | None = None
    project_name: str | None = None
    run_id: str | None = None
    sample_id: str | None = None
    sample_name: str | None = None


class FileRead(BaseModel):
    """File metadata plus the metadata link explaining why it is in scope."""

    file_id: str
    project_id: str | None = None
    data_import_id: str | None = None
    run_id: str | None = None
    run_sample_id: str | None = None
    sample_id: str | None = None
    data_contract_id: str | None = None
    association_scope: str = "direct_run"
    association_reason: str | None = None
    kind: str = "file"
    path: str | None = None
    uri: str | None = None
    storage_location: str | None = None
    object_key: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    source_path: str | None = None
    created_at: datetime | None = None


class SavedInsightBase(BaseModel):
    """Shared fields for saved insight create/read payloads."""

    name: str
    description: str | None = None
    config: dict[str, JsonValue] = Field(default_factory=dict)


class SavedInsightCreate(SavedInsightBase):
    """Payload for creating a saved insight."""

    insight_id: str | None = None
    project_id: str | None = None


class SavedInsightPatch(BaseModel):
    """Fields that can be patched on an existing saved insight."""

    name: str | None = None
    description: str | None = None
    config: dict[str, JsonValue] | None = None


class SavedInsightRead(SavedInsightBase):
    """Saved insight response with stable ID and timestamps."""

    insight_id: str
    url_slug: str
    project_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SavedReportBase(BaseModel):
    """Shared fields for saved report create/read payloads."""

    name: str
    description: str | None = None
    config: dict[str, JsonValue] = Field(default_factory=dict)


class SavedReportCreate(SavedReportBase):
    """Payload for creating a saved report."""

    report_id: str | None = None
    project_id: str | None = None


class SavedReportPatch(BaseModel):
    """Fields that can be patched on an existing saved report."""

    name: str | None = None
    description: str | None = None
    config: dict[str, JsonValue] | None = None


class SavedReportRead(SavedReportBase):
    """Saved report response with stable ID and timestamps."""

    report_id: str
    url_slug: str
    project_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ReportRenderRequest(BaseModel):
    """Payload for rendering a saved or standalone HTML report."""

    results: str = "."
    rendered_report_id: str | None = None
    report_id: str | None = None
    run_id: str | None = None
    project_id: str | None = None
    name: str = "Goodomics Report"
    refresh: bool = False


class RenderedReportRead(BaseModel):
    """Persisted rendered report HTML and its source metadata."""

    rendered_report_id: str
    project_id: str | None = None
    run_id: str | None = None
    report_id: str | None = None
    name: str
    html: str
    created_at: datetime


class InsightExecuteRequest(BaseModel):
    """Payload for executing an ad hoc or saved insight."""

    config: dict[str, JsonValue] | None = None
    name: str | None = None
    description: str | None = None
    project_id: str | None = None
    refresh: bool = False


class ReportExecuteRequest(BaseModel):
    """Payload for executing a saved report."""

    project_id: str | None = None
    refresh: bool = False


class InsightResultRead(BaseModel):
    """Envelope for an executed insight result payload."""

    result: dict[str, JsonValue]


class ReportResultRead(BaseModel):
    """Envelope for an executed report result payload."""

    result: dict[str, JsonValue]


class InsightValidationRequest(BaseModel):
    """Payload for validating and explaining a draft insight config."""

    config: dict[str, JsonValue] = Field(default_factory=dict)


class InsightValidationRead(BaseModel):
    """Shared validation/explanation response for UI and AI insight drafting."""

    valid: bool
    messages: list[dict[str, JsonValue]]
    normalized_config: dict[str, JsonValue]
    explanation: str
    capabilities_version: int = 1


class SampleGroupRead(BaseModel):
    """Canonical sample-group context option."""

    sample_group_id: str
    url_slug: str
    project_id: str | None = None
    name: str
    kind: str
    description: str | None = None
    definition_json: dict[str, JsonValue] = Field(default_factory=dict)
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    member_count: int = 0


class SampleGroupPageRead(BaseModel):
    """Paginated sample-group list response."""

    items: list[SampleGroupRead]
    total: int
    limit: int
    offset: int


class SampleGroupCreate(BaseModel):
    """Payload for creating a project-scoped sample group."""

    name: str
    description: str | None = None
    kind: str = "sample_group"
    sample_ids: list[str] = Field(default_factory=list)


class SampleGroupPatch(BaseModel):
    """Fields that can be patched on a sample group."""

    name: str | None = None
    description: str | None = None
    kind: str | None = None
    metadata_json: dict[str, JsonValue] | None = None


class SampleGroupMemberRead(BaseModel):
    """Sample/run link member displayed in a sample group."""

    run_sample_id: str
    sample_id: str
    sample_name: str | None = None
    subject_id: str | None = None
    run_id: str
    run_name: str | None = None
    status: str


class SampleGroupMemberPageRead(BaseModel):
    """Paginated sample-group member response."""

    items: list[SampleGroupMemberRead]
    total: int
    limit: int
    offset: int


class SampleGroupMembersAdd(BaseModel):
    """Payload for adding stable samples to a sample group."""

    sample_ids: list[str]


class SampleGroupMembersRemove(BaseModel):
    """Payload for removing sample/run links from a sample group."""

    run_sample_ids: list[str]


class QCPolicyCreate(BaseModel):
    """Payload for creating a QC policy definition."""

    policy_id: str | None = None
    name: str
    thresholds: dict[str, JsonValue] = Field(default_factory=dict)


class QCPolicyPatch(BaseModel):
    """Fields that can be patched on an existing QC policy."""

    name: str | None = None
    thresholds: dict[str, JsonValue] | None = None


class QCPolicyRead(BaseModel):
    """Saved QC policy response."""

    policy_id: str
    project_id: str
    name: str
    thresholds: dict[str, JsonValue]
    updated_at: datetime


class DatabaseTableRead(BaseModel):
    """Summary row for a metadata or analytics table in the database browser."""

    name: str
    store: str = "metadata"
    rows: int = 0
    columns: list[str] = Field(default_factory=list)
    editable: bool = False


class DatabaseTablePageRead(BaseModel):
    """Paginated preview of rows from one database table."""

    name: str
    store: str
    columns: list[str]
    rows: list[dict[str, JsonValue]]
    total: int
    limit: int
    offset: int
    sort_by: str | None = None
    sort_direction: str | None = None


class DataContractFieldRead(BaseModel):
    """Queryable field exposed by a data contract."""

    field_id: str
    field_role: str
    entity_scope: str | None = None
    display_name: str
    value_type: str
    unit: str | None = None
    direction: str | None = None
    description: str | None = None
    priority: str | None = None
    primary_table: str | None = None
    physical_tables: dict[str, JsonValue] = Field(default_factory=dict)
    query_ref: dict[str, JsonValue] = Field(default_factory=dict)
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict)


class DataContractRead(BaseModel):
    """Data contract contract plus fields available to insight builders."""

    data_contract_id: str
    name: str
    data_type: str
    compatible_analysis_type_ids: list[str] = Field(default_factory=list)
    intrinsic_producer_families: dict[str, JsonValue] = Field(default_factory=dict)
    entity_grain: str | None = None
    value_semantics: str | None = None
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    last_profiled_at: datetime | None = None
    source_fingerprint: str | None = None
    query_modes: dict[str, JsonValue] = Field(default_factory=dict)
    description: str | None = None
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict)
    fields: list[DataContractFieldRead] = Field(default_factory=list)


class ContractResultOptionsRead(BaseModel):
    """Bounded result-scope options compatible with one data contract."""

    analysis_types: list[dict[str, str]] = Field(default_factory=list)
    methods: list[dict[str, str]] = Field(default_factory=list)
    method_versions: list[str] = Field(default_factory=list)
    runs: list[dict[str, str]] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)


class AnalyticsMetricRead(BaseModel):
    """Scalar analytical metric read from the DuckDB analytics store."""

    run_id: int | str
    data_contract_id: int | str
    run_sample_id: int | str | None = None
    sample_id: int | str | None = None
    field_id: int | str
    value_type: str
    value: float | str | bool | dict[str, Any] | list[Any] | None = None
    source_file_id: int | str | None = None
    source_observation_id: str | None = None
    source_observation_label: str | None = None
    source_observation_metadata_json: dict[str, JsonValue] = Field(default_factory=dict)


class AnalyticsResultPayloadRead(BaseModel):
    """Logical non-scalar result payload read from the analytics store."""

    run_id: int | str
    data_contract_id: int | str
    run_sample_id: int | str | None = None
    sample_id: int | str | None = None
    field_id: int | str
    payload_name: str
    payload_kind: str
    storage_format: str
    payload_schema_json: dict[str, Any] = Field(
        default_factory=dict,
        alias="schema_json",
    )
    data_json: JsonValue
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    source_file_id: int | str | None = None
    source_observation_id: str | None = None
    source_observation_label: str | None = None
    source_observation_metadata_json: dict[str, JsonValue] = Field(default_factory=dict)
    source_hash: str | None = None


class TableCountRead(BaseModel):
    """Row-count summary for one database table."""

    name: str
    rows: int


class DatabaseSummaryRead(BaseModel):
    """Storage and table-count summary for the local Goodomics database."""

    sqlite_size_bytes: int
    duckdb_size_bytes: int
    file_size_bytes: int
    total_runs: int
    total_samples: int
    total_scalar_metrics: int
    total_payloads: int
    metadata_tables: list[TableCountRead]
    analytics_tables: list[TableCountRead]


class DatabaseRowPatch(BaseModel):
    """Patch payload for the constrained database editor endpoint."""

    values: dict[str, JsonValue]
    audit_note: str | None = None


class AIChatRequest(BaseModel):
    """Chat request passed to the configured AI provider."""

    messages: list[ChatMessage]
    project_id: str | None = None
    conversation_id: str | None = None


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a minimal liveness response for server health checks."""

    return {"status": "ok"}


@router.post("/ai/chat", response_model=ChatResult)
async def chat_with_ai(payload: AIChatRequest, request: Request) -> ChatResult:
    """Send chat messages to the configured AI provider after scope checks."""

    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    key = principal_rate_key(request)
    limiter = request.app.state.rate_limiter
    await limiter.check("ai", key, request.app.state.settings.rate_limits.ai)
    await limiter.check(
        "ai-installation",
        "installation",
        request.app.state.settings.rate_limits.ai_installation,
    )
    try:
        async with limiter.concurrent(
            "ai", key, request.app.state.settings.rate_limits.ai_concurrent
        ):
            return await request.app.state.ai_chat.chat(
                payload.messages,
                project_id=payload.project_id,
                conversation_id=payload.conversation_id,
            )
    except AIProviderNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(request: Request) -> list[ProjectRead]:
    """List projects, creating the default project on first use."""

    await _ensure_default_project(request)

    async with _session_context(request) as session:
        statement = select(ProjectRecord).order_by(
            cast(Any, ProjectRecord.created_at), ProjectRecord.name
        )
        visible = await authorized_project_pks(
            session,
            cast(Principal, request.state.principal),
            request.app.state.settings,
        )
        if visible is not None:
            statement = statement.where(cast(Any, ProjectRecord.id).in_(visible))
        rows = (await session.exec(statement)).all()

        return [await _project_read(row, session=session) for row in rows]


@router.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project(payload: ProjectCreate, request: Request) -> ProjectRead:
    """Create a project with a validated unique slug."""
    slug = validate_project_slug(payload.slug or payload.name)

    # Validate the default storage location if provided.
    if (
        payload.default_storage_location is not None
        and payload.default_storage_location
        not in request.app.state.settings.storage.locations
    ):
        raise HTTPException(status_code=400, detail="Unknown storage location")

    async with _session_context(request) as session:
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
            visibility=payload.visibility,
            default_storage_location=payload.default_storage_location,
            metadata_json=json.loads(json.dumps(payload.metadata_json)),
            created_at=datetime.now(UTC),
        )
        session.add(project)
        await session.flush()

        # Seed the default project roles for the new project.
        roles = await seed_project_roles(session, project)
        principal = cast(Principal, request.state.principal)
        if principal.kind == "user" and principal.user_pk is not None:
            from goodomics.server.db.models import ProjectMembershipRecord

            session.add(
                ProjectMembershipRecord(
                    membership_id=f"mem_{uuid4().hex[:20]}",
                    project_id=cast(int, project.id),
                    user_id=principal.user_pk,
                    role_id=cast(int, roles["Owner"].id),
                    created_at=datetime.now(UTC),
                )
            )
        await session.commit()
        await session.refresh(project)
        return await _project_read(project, session=session)


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, request: Request) -> ProjectRead:
    """Return one project by public project ID."""

    return await _get_project_read(request, project_id)


@router.get("/projects/{project_id}/runs/{run_id}", response_model=Run)
async def get_project_run(
    project_id: str,
    run_id: str,
    request: Request,
) -> Run:
    """Return a run only if it belongs to the requested project."""

    return await _get_project_run(request, project_id, run_id)


@router.get("/projects/{project_id}/runs/{run_id}/samples", response_model=list[Sample])
async def list_project_run_samples(
    project_id: str,
    run_id: str,
    request: Request,
) -> list[Sample]:
    """Return samples attached to a project-scoped run."""

    run = await _get_project_run(request, project_id, run_id)
    return run.samples


@router.get("/projects/{project_id}/run-samples", response_model=RunSamplePageRead)
async def list_project_run_sample_links(
    project_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=255),
) -> RunSamplePageRead:
    """List project run/sample links for picker-style filters."""

    return await _list_project_run_sample_links(
        request,
        project_id=project_id,
        limit=limit,
        offset=offset,
        search=search,
    )


@router.get("/projects/{project_id}/runs/{run_id}/files", response_model=list[FileRead])
async def list_project_run_files(
    project_id: str,
    run_id: str,
    request: Request,
) -> list[FileRead]:
    """Return files linked to a project-scoped run."""

    await _get_project_run(request, project_id, run_id)
    return await _list_run_files(run_id, request, project_id=project_id)


@router.get("/projects/{project_id}/files", response_model=list[FileRead])
async def list_project_files(project_id: str, request: Request) -> list[FileRead]:
    """List managed and referenced files linked to a project."""

    project = await _require_project(request, project_id)

    async with _session_context(request) as session:
        rows = (
            await session.exec(
                select(FileRecord, FileLinkRecord)
                .join(
                    FileLinkRecord, cast(Any, FileLinkRecord.file_id) == FileRecord.id
                )
                .where(FileLinkRecord.project_id == project.id)
                .order_by(FileRecord.file_id)
            )
        ).all()

        return [
            await _file_from_rows_public(
                session,
                file,
                link,
                association_scope="project",
                association_reason="File linked to this project.",
            )
            for file, link in rows
        ]


@router.post("/projects/{project_id}/files", response_model=FileRead, status_code=201)
async def upload_project_file(
    project_id: str,
    request: Request,
    upload: UploadFile = UPLOAD_FILE,
    object_key: str | None = Form(default=None),
    storage_location: str | None = Form(default=None),
    file_role: str = Form(default="upload"),
) -> FileRead:
    """Upload a managed file to a project's selected named location."""

    project = await _require_project(request, project_id)

    # Determine the storage location for the uploaded file,
    # falling back to the project's default location or the global default.
    location = (
        storage_location
        or project.default_storage_location
        or request.app.state.settings.storage.default_location
    )
    key = object_key or (
        f"{project_id}/{uuid4().hex}/{Path(upload.filename or 'upload').name}"
    )

    try:
        file_store = request.app.state.file_stores.get(location)
        metadata = file_store.upload(key, upload.file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # create a new FileRecord with the current timestamp
    now = datetime.now(UTC)
    row = FileRecord(
        file_id=_new_id("file"),
        project_id=project.id,
        storage_location=location,
        object_key=key,
        file_role=file_role,
        format=Path(upload.filename or "").suffix.lstrip(".") or None,
        size_bytes=metadata.size_bytes,
        sha256=metadata.sha256,
        created_at=now,
        metadata_json={"original_filename": upload.filename},
    )
    async with _session_context(request) as session:
        session.add(row)
        await session.flush()
        link = FileLinkRecord(
            file_id=cast(int, row.id),
            project_id=project.id,
            link_role="project_file",
        )
        session.add(link)
        await session.commit()
        await session.refresh(row)
        await session.refresh(link)

        return await _file_from_rows_public(
            session,
            row,
            link,
            association_scope="project",
            association_reason="Managed project upload.",
        )


@router.delete("/projects/{project_id}/files/{file_id}", status_code=204)
async def delete_project_file(project_id: str, file_id: str, request: Request) -> None:
    """Delete a managed project file after removing its final metadata link."""

    project = await _require_project(request, project_id)

    async with _session_context(request) as session:
        # Retrieve the file record for the given file_id and project,
        # ensuring it exists before deletion.
        row = (
            await session.exec(
                select(FileRecord)
                .join(
                    FileLinkRecord, cast(Any, FileLinkRecord.file_id) == FileRecord.id
                )
                .where(
                    FileRecord.file_id == file_id,
                    FileLinkRecord.project_id == project.id,
                )
            )
        ).first()

        if row is None:
            raise HTTPException(status_code=404, detail="File not found")
        links = (
            await session.exec(
                select(FileLinkRecord).where(FileLinkRecord.file_id == row.id)
            )
        ).all()

        # delete project-specific links for the file
        project_links = [link for link in links if link.project_id == project.id]

        for link in project_links:
            await session.delete(link)
        if len(project_links) == len(links):
            if row.storage_location and row.object_key:
                request.app.state.file_stores.get(row.storage_location).delete(
                    row.object_key
                )
            await session.delete(row)
        await session.commit()


@router.get(
    "/projects/{project_id}/runs/{run_id}/analytics/metrics",
    response_model=list[AnalyticsMetricRead],
)
async def list_project_run_analytics_metrics(
    project_id: str,
    run_id: str,
    request: Request,
) -> list[AnalyticsMetricRead]:
    """Return scalar analytical metrics for a project-scoped run."""

    run = await _get_project_run_record(request, project_id, run_id)
    return _analytics_metric_reads(
        _analytics_store_for_project(request, project_id).list_metric_values(run.id)
    )


@router.get(
    "/projects/{project_id}/runs/{run_id}/analytics/payloads",
    response_model=list[AnalyticsResultPayloadRead],
)
async def list_project_run_analytics_payloads(
    project_id: str,
    run_id: str,
    request: Request,
) -> list[AnalyticsResultPayloadRead]:
    """Return result payloads for a project-scoped run."""

    run = await _get_project_run_record(request, project_id, run_id)
    return _analytics_payload_reads(
        _analytics_store_for_project(request, project_id).list_result_payloads(run.id)
    )


@router.get("/projects/{project_id}/files/{file_id}/content")
async def get_project_file_content(
    project_id: str,
    file_id: str,
    request: Request,
) -> Response:
    """Stream a stored file only if it is linked to the requested project."""

    return await _file_content_response(file_id, request, project_id=project_id)


@router.get("/projects/{project_id}/samples", response_model=SamplePageRead)
async def list_project_samples(
    project_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=255),
) -> SamplePageRead:
    """List samples in a project with run summary metadata."""

    await _require_project(request, project_id)
    return await _list_samples(
        request,
        project_id=project_id,
        limit=limit,
        offset=offset,
        search=search,
    )


@router.get("/projects/{project_id}/samples/{sample_id}", response_model=Sample)
async def get_project_sample(
    project_id: str,
    sample_id: str,
    request: Request,
) -> Sample:
    """Return a sample that belongs to, or was processed in, the project."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
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
                    .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
                    .where(
                        RunRecord.project_id == project.id,
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
    """List runs in which a project sample appears."""

    await _require_project(request, project_id)
    async with _session_context(request) as session:
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
    """Return files from the latest run for a project sample."""

    await _require_project(request, project_id)
    async with _session_context(request) as session:
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
    """Return files for a specific project sample/run pairing."""

    await _require_project(request, project_id)
    async with _session_context(request) as session:
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
    """Return scalar metrics for a specific project sample/run pairing."""

    await _require_project(request, project_id)
    async with _session_context(request) as session:
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
    """Patch project metadata and validate default-report ownership."""
    values = payload.model_dump(exclude_unset=True)
    async with _session_context(request) as session:
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

        if "visibility" in values and values["visibility"] is not None:
            row.visibility = values["visibility"]

        if "default_storage_location" in values:
            location = values["default_storage_location"]
            if (
                location is not None
                and location not in request.app.state.settings.storage.locations
            ):
                raise HTTPException(status_code=400, detail="Unknown storage location")
            row.default_storage_location = location

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
    search: str = Query(default="", max_length=255),
) -> RunPageRead:
    """List runs in one project."""

    await _require_project(request, project_id)
    return await _list_runs(
        request,
        project_id=project_id,
        limit=limit,
        offset=offset,
        search=search,
    )


@router.get("/search", response_model=list[SearchResultRead])
async def search_samples(
    request: Request,
    q: str = Query(default="", max_length=255),
    project_id: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
) -> list[SearchResultRead]:
    """Search samples first, then fill remaining slots with matching runs."""
    project_pk: int | None = None
    if project_id is not None:
        project = await _require_project(request, project_id)
        project_pk = project.id
    term = q.strip().lower()
    if not term:
        return []
    pattern = f"%{term}%"
    async with _session_context(request) as session:
        visible = await authorized_project_pks(
            session,
            cast(Principal, request.state.principal),
            request.app.state.settings,
        )
        sample_statement = select(SampleRecord).where(
            (func.lower(SampleRecord.sample_id).like(pattern))
            | (func.lower(SampleRecord.sample_name).like(pattern))
        )
        if project_id is not None:
            sample_statement = sample_statement.where(
                SampleRecord.project_id == project_pk
            )
        elif visible is not None:
            sample_statement = sample_statement.where(
                cast(Any, SampleRecord.project_id).in_(visible)
            )
        sample_rows = (await session.exec(sample_statement.limit(limit))).all()

        run_statement = select(RunRecord).where(
            (func.lower(RunRecord.run_id).like(pattern))
            | (func.lower(RunRecord.name).like(pattern))
        )
        if project_id is not None:
            run_statement = run_statement.where(RunRecord.project_id == project_pk)
        elif visible is not None:
            run_statement = run_statement.where(
                cast(Any, RunRecord.project_id).in_(visible)
            )
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
    search: str = Query(default="", max_length=255),
) -> RunPageRead:
    """List runs globally or within one project."""

    return await _list_runs(
        request,
        project_id=project_id,
        limit=limit,
        offset=offset,
        search=search,
    )


@router.post("/runs", response_model=Run, status_code=201)
async def create_run(payload: RunCreate, request: Request) -> Run:
    """Create a run through the storage abstraction used by ingest code."""

    project = await request.app.state.store.ensure_project_with_session(
        _session(request), payload.project_id or payload.project
    )
    project_row = await _require_project(request, project.project_id)
    await require_project_permission(
        request, _session(request), project_row, "data.ingest"
    )

    run = Run(
        run_id=payload.run_id or _new_id("run"),
        project_id=project.project_id,
        project=project.slug,
        analysis_type_id=payload.analysis_type_id,
        method_id=payload.method_id,
        method_version=payload.method_version,
        samples=[
            sample.model_copy(
                update={"project_id": sample.project_id or project.project_id}
            )
            for sample in payload.samples
        ],
    )
    await request.app.state.store.replace_run_metadata(
        run,
        analysis_types=[resolve_analysis_type(payload.analysis_type_id)],
        analysis_methods=[
            analysis_method(
                payload.method_id,
                name=payload.method_id,
                method_kind=payload.method_kind,
            )
        ],
        samples=run.samples,
        run_samples=[
            RunSample(
                run_sample_id=f"{run.run_id}:{sample.sample_id}",
                run_id=run.run_id,
                sample_id=sample.sample_id,
            )
            for sample in run.samples
        ],
        session=_session(request),
    )
    return run


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(run_id: str, request: Request) -> Run:
    """Return a run by public run ID."""

    run = await request.app.state.store.get_run(run_id, session=_session(request))

    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.project_id is not None:
        await _require_project(request, run.project_id)

    return run


@router.patch("/runs/{run_id}", response_model=Run)
async def patch_run(run_id: str, payload: RunPatch, request: Request) -> Run:
    """Patch editable run fields in the SQL metadata store."""
    values = payload.model_dump(exclude_unset=True)
    if values:
        async with _session_context(request) as session:
            row = await get_record_by_field(
                session, RunRecord, RunRecord.run_id, run_id
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Run not found")
            if "analysis_type_id" in values:
                analysis_type = await get_record_where(
                    session,
                    AnalysisTypeRecord,
                    AnalysisTypeRecord.analysis_type_id
                    == values.pop("analysis_type_id"),
                    AnalysisTypeRecord.project_id == row.project_id,
                )
                if analysis_type is None:
                    raise HTTPException(status_code=422, detail="Unknown analysis type")
                if analysis_type.id is None:
                    raise HTTPException(status_code=500, detail="Invalid analysis type")
                row.analysis_type_id = analysis_type.id
            if "method_id" in values:
                method = await get_record_where(
                    session,
                    AnalysisMethodRecord,
                    AnalysisMethodRecord.method_id == values.pop("method_id"),
                    AnalysisMethodRecord.project_id == row.project_id,
                )
                if method is None:
                    raise HTTPException(
                        status_code=422, detail="Unknown analysis method"
                    )
                if method.id is None:
                    raise HTTPException(
                        status_code=500, detail="Invalid analysis method"
                    )
                row.method_id = method.id
            for key, value in values.items():
                setattr(row, key, value)
            session.add(row)
            await session.commit()
    return await get_run(run_id, request)


@router.get("/runs/{run_id}/samples", response_model=list[Sample])
async def list_run_samples(run_id: str, request: Request) -> list[Sample]:
    """Return samples attached to a run."""

    run = await get_run(run_id, request)
    return run.samples


@router.get("/runs/{run_id}/files", response_model=list[FileRead])
async def list_run_files(run_id: str, request: Request) -> list[FileRead]:
    """Return files linked directly or indirectly to a run."""

    return await _list_run_files(run_id, request)


async def _list_run_files(
    run_id: str, request: Request, *, project_id: str | None = None
) -> list[FileRead]:
    """Resolve files linked to a run and its originating data import."""
    async with _session_context(request) as session:
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
        # Direct links are files explicitly associated with this run.
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
            # Import-level files are source files that produced the run but were
            # not linked to the run row directly.
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
    """Return scalar analytics metrics for a run."""

    run = await _get_run_record(request, run_id)
    project_id = await _project_public_id_for_pk(request, run.project_id)
    analytics_store = _analytics_store_for_project(request, project_id)
    return _analytics_metric_reads(analytics_store.list_metric_values(run.id))


@router.get(
    "/runs/{run_id}/analytics/payloads",
    response_model=list[AnalyticsResultPayloadRead],
)
async def list_run_analytics_payloads(
    run_id: str, request: Request
) -> list[AnalyticsResultPayloadRead]:
    """Return result payloads for a run."""

    run = await _get_run_record(request, run_id)
    project_id = await _project_public_id_for_pk(request, run.project_id)
    analytics_store = _analytics_store_for_project(request, project_id)
    return _analytics_payload_reads(analytics_store.list_result_payloads(run.id))


@router.get("/contracts", response_model=list[DataContractRead])
async def list_data_contracts(
    request: Request,
    project_id: str | None = Query(default=None),
) -> list[DataContractRead]:
    """List data contracts for a project, or all contracts when unscoped."""

    project: ProjectRecord | None = None
    if project_id is not None:
        project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        project_pk = project.id if project is not None else None
        statement = select(DataContractRecord)
        if project_pk is not None:
            if project and project.project_id == DEFAULT_PROJECT_ID:
                contract_project_id = cast(Any, DataContractRecord.project_id)
                statement = statement.where(
                    or_(
                        contract_project_id == project_pk,
                        contract_project_id.is_(None),
                    )
                )
            else:
                statement = statement.where(DataContractRecord.project_id == project_pk)
        statement = statement.order_by(DataContractRecord.name)
        contracts = list((await session.exec(statement)).all())
        if project_pk is not None:
            contracts = _prefer_project_contract_rows(contracts, project_pk)
        fields_by_contract = await _fields_by_contract(session, contracts)
        compatibility = await _contract_analysis_type_labels(session, contracts)
    return [
        _data_contract_read(
            contract,
            fields_by_contract.get(contract.id, []),
            compatibility.get(contract.id, []),
        )
        for contract in contracts
    ]


@router.get("/contracts/{data_contract_id:path}", response_model=DataContractRead)
async def get_data_contract(
    data_contract_id: str,
    request: Request,
    project_id: str | None = Query(default=None),
) -> DataContractRead:
    """Return one data contract for a project, or an unscoped match."""

    project: ProjectRecord | None = None
    if project_id is not None:
        project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        project_pk = project.id if project is not None else None
        statement = select(DataContractRecord).where(
            DataContractRecord.data_contract_id == data_contract_id
        )
        if project_pk is not None:
            if project and project.project_id == DEFAULT_PROJECT_ID:
                contract_project_id = cast(Any, DataContractRecord.project_id)
                statement = statement.where(
                    or_(
                        contract_project_id == project_pk,
                        contract_project_id.is_(None),
                    )
                )
            else:
                statement = statement.where(DataContractRecord.project_id == project_pk)
        contracts = list((await session.exec(statement)).all())
        if project_pk is not None:
            contracts = _prefer_project_contract_rows(contracts, project_pk)
        contract = contracts[0] if contracts else None
        if contract is None:
            raise HTTPException(status_code=404, detail="Data contract not found")
        fields_by_contract = await _fields_by_contract(session, [contract])
        compatibility = await _contract_analysis_type_labels(session, [contract])
    return _data_contract_read(
        contract,
        fields_by_contract.get(contract.id, []),
        compatibility.get(contract.id, []),
    )


@router.get(
    "/contract-result-options/{data_contract_id:path}",
    response_model=ContractResultOptionsRead,
)
async def get_contract_result_options(
    data_contract_id: str,
    request: Request,
    project_id: str = Query(...),
) -> ContractResultOptionsRead:
    """Return compatible methods, versions, runs, and statuses for a contract."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        contract = (
            await session.exec(
                select(DataContractRecord).where(
                    DataContractRecord.data_contract_id == data_contract_id,
                    DataContractRecord.project_id == project.id,
                )
            )
        ).first()
        if contract is None:
            raise HTTPException(status_code=404, detail="Data contract not found")
        rows = list(
            (
                await session.exec(
                    select(
                        RunContractRecord,
                        RunRecord,
                        AnalysisTypeRecord,
                        AnalysisMethodRecord,
                    )
                    .join(
                        RunRecord,
                        cast(Any, RunRecord.id) == RunContractRecord.run_id,
                    )
                    .join(
                        AnalysisTypeRecord,
                        cast(Any, AnalysisTypeRecord.id) == RunRecord.analysis_type_id,
                    )
                    .join(
                        AnalysisMethodRecord,
                        cast(Any, AnalysisMethodRecord.id) == RunRecord.method_id,
                    )
                    .where(
                        RunContractRecord.data_contract_id == contract.id,
                        RunRecord.project_id == project.id,
                    )
                    .limit(500)
                )
            ).all()
        )
    analysis_types = {
        analysis_type.analysis_type_id: analysis_type.name
        for _, _, analysis_type, _ in rows
    }
    methods = {method.method_id: method.name for _, _, _, method in rows}
    return ContractResultOptionsRead(
        analysis_types=[
            {"id": identifier, "name": name}
            for identifier, name in sorted(analysis_types.items())
        ],
        methods=[
            {"id": identifier, "name": name}
            for identifier, name in sorted(methods.items())
        ],
        method_versions=sorted(
            {
                str(occurrence.producer_version or run.method_version)
                for occurrence, run, _, _ in rows
                if occurrence.producer_version or run.method_version
            }
        ),
        runs=[
            {"id": run.run_id, "name": run.name or run.run_id} for _, run, _, _ in rows
        ],
        statuses=sorted(
            {
                value
                for occurrence, run, _, _ in rows
                for value in (run.status, occurrence.status)
            }
        ),
    )


@router.get("/files/{file_id}/content")
async def get_file_content(file_id: str, request: Request) -> Response:
    """Stream a stored file by public file ID."""

    return await _file_content_response(file_id, request)


# TODO: handle large files differently
async def _file_content_response(
    file_id: str,
    request: Request,
    *,
    project_id: str | None = None,
) -> Response:
    """Validate file visibility and return a FastAPI file response."""
    async with _session_context(request) as session:
        row = await get_record_by_field(
            session, FileRecord, FileRecord.file_id, file_id
        )

        if row is not None and project_id is not None:
            # Ensure the file is linked to the specified project.
            # If no link exists, treat the file as not found.
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
        elif row is not None:
            # If no project ID is provided, check if the file has any
            # project link and enforce project access if necessary.
            link = (
                await session.exec(
                    select(FileLinkRecord).where(FileLinkRecord.file_id == row.id)
                )
            ).first()
            if link is not None and link.project_id is not None:
                linked_project_id = await _public_label(
                    session, ProjectRecord, "project_id", link.project_id
                )
                if linked_project_id is not None:
                    await _require_project(request, linked_project_id)

    if row is None:
        raise HTTPException(status_code=404, detail="File not found")

    # If the file has a storage location and object key, attempt to retrieve
    # the file from the storage backend. Otherwise, check if the file
    # has a local path and serve it from the filesystem.
    if row.storage_location and row.object_key:
        try:
            store = request.app.state.file_stores.get(row.storage_location)
            metadata = store.metadata(row.object_key)
        except (FileNotFoundError, ValueError):
            raise HTTPException(
                status_code=404, detail="Stored file not found"
            ) from None
        return StreamingResponse(
            store.iter_bytes(row.object_key),
            media_type=metadata.content_type or "application/octet-stream",
            headers={
                "Content-Length": str(metadata.size_bytes),
                "Content-Disposition": (
                    f'attachment; filename="{Path(row.object_key).name}"'
                ),
            },
        )

    if row.path is None:
        raise HTTPException(status_code=404, detail="Stored file not found")

    # Only serve files whose metadata row points at an existing local file.
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
    """List saved insights globally or for one project."""

    if project_id is not None:
        await _require_project(request, project_id)

    async with _session_context(request) as session:
        statement = select(InsightRecord)
        if project_id is not None:
            statement = statement.where(InsightRecord.project_id == project_id)
        else:
            visible = await _authorized_project_labels(request, session)
            if visible is not None:
                statement = statement.where(
                    cast(Any, InsightRecord.project_id).in_(visible)
                )
        rows = (await session.exec(statement)).all()

    return [_saved_insight_read(row) for row in rows]


@router.get("/insights/capabilities")
async def get_insight_capabilities() -> dict[str, JsonValue]:
    """Return the server-owned insight/report builder capabilities."""

    return insight_capabilities()


@router.post("/insights/validate", response_model=InsightValidationRead)
async def validate_insight_config(
    payload: InsightValidationRequest,
) -> InsightValidationRead:
    """Validate and explain a draft insight config without executing it."""

    return InsightValidationRead.model_validate(
        validate_and_explain_config(payload.config)
    )


@router.post("/insights", response_model=SavedInsightRead, status_code=201)
async def create_insight(
    payload: SavedInsightCreate, request: Request
) -> SavedInsightRead:
    """Create a saved insight and its initial revision."""
    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    now = datetime.now(UTC)
    insight_id = payload.insight_id or _new_id("insight")
    config = normalize_insight_config(payload.config)
    async with _session_context(request) as session:
        insight = InsightRecord(
            insight_id=insight_id,
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            config=config,
            created_at=now,
            updated_at=now,
            created_by_user_id=getattr(request.state.principal, "user_pk", None),
            updated_by_user_id=getattr(request.state.principal, "user_pk", None),
        )
        revision = InsightRevisionRecord(
            insight_id=insight_id,
            config=config,
            created_at=now,
        )
        session.add(insight)
        session.add(revision)
        await session.commit()
    return await get_insight(insight_id, request)


@router.get("/insights/{insight_ref}", response_model=SavedInsightRead)
async def get_insight(insight_ref: str, request: Request) -> SavedInsightRead:
    """Return a saved insight by ID or stable URL slug."""

    async with _session_context(request) as session:
        row = await _get_insight_by_ref(session, insight_ref)

    if row is None:
        raise HTTPException(status_code=404, detail="Insight not found")

    if row.project_id is not None:
        project = await _require_project(request, row.project_id)
        await require_project_permission(
            request, _session(request), project, "insight.read"
        )

    return _saved_insight_read(row)


@router.patch("/insights/{insight_ref}", response_model=SavedInsightRead)
async def patch_insight(
    insight_ref: str, payload: SavedInsightPatch, request: Request
) -> SavedInsightRead:
    """Patch a saved insight and record a revision when config changes."""
    values = payload.model_dump(exclude_unset=True)
    if isinstance(values.get("config"), dict):
        values["config"] = normalize_insight_config(values["config"])

    if values:
        async with _session_context(request) as session:
            insight = await _get_insight_by_ref(session, insight_ref)

            if insight is None:
                raise HTTPException(status_code=404, detail="Insight not found")

            if insight.project_id is not None:
                project = await _require_project(request, insight.project_id)
                await require_project_permission(
                    request, _session(request), project, "insight.edit"
                )

            insight_id = insight.insight_id
            updated_at = datetime.now(UTC)
            for key, value in values.items():
                setattr(insight, key, value)
            insight.updated_at = updated_at
            insight.updated_by_user_id = getattr(
                request.state.principal, "user_pk", None
            )
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
    return await get_insight(insight_ref, request)


@router.delete("/insights/{insight_ref}", status_code=204)
async def delete_insight(insight_ref: str, request: Request) -> Response:
    """Delete a saved insight, its revisions, and cached results."""

    async with _session_context(request) as session:
        insight = await _get_insight_by_ref(session, insight_ref)

        if insight is None:
            raise HTTPException(status_code=404, detail="Insight not found")

        if insight.project_id is not None:
            project = await _require_project(request, insight.project_id)
            await require_project_permission(
                request, _session(request), project, "insight.delete"
            )

        insight_id = insight.insight_id
        insight_revision_id = cast(Any, InsightRevisionRecord.insight_id)
        insight_cache_id = cast(Any, InsightResultCacheRecord.insight_id)
        await session.exec(
            delete(InsightRevisionRecord).where(insight_revision_id == insight_id)
        )
        await session.exec(
            delete(InsightResultCacheRecord).where(insight_cache_id == insight_id)
        )
        await session.delete(insight)
        await session.commit()

    return Response(status_code=204)


@router.get("/insights/{insight_ref}/export.yaml")
async def export_insight_yaml(insight_ref: str, request: Request) -> Response:
    """Export a saved insight as portable YAML."""

    insight = await get_insight(insight_ref, request)
    body = yaml.safe_dump(_saved_insight_export(insight), sort_keys=False)
    return Response(content=body, media_type="application/yaml")


@router.get("/insights/{insight_ref}/export.json")
async def export_insight_json(insight_ref: str, request: Request) -> dict[str, Any]:
    """Export a saved insight as portable JSON."""

    insight = await get_insight(insight_ref, request)
    return _saved_insight_export(insight)


@router.post("/insights/execute", response_model=InsightResultRead)
async def execute_adhoc_insight(
    payload: InsightExecuteRequest, request: Request
) -> InsightResultRead:
    """Execute an insight config that has not been saved."""
    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    analytics_store = _analytics_store_for_project(request, payload.project_id)
    try:
        async with _session_context(request) as session:
            result = await execute_insight(
                session=session,
                analytics_store=analytics_store,
                project_id=payload.project_id,
                config=payload.config or {},
                name=payload.name,
                description=payload.description,
                refresh=payload.refresh,
                persist_results=await _may_persist_results(request, payload.project_id),
            )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return InsightResultRead(result=result)


@router.post("/insights/{insight_ref}/execute", response_model=InsightResultRead)
async def execute_saved_insight(
    insight_ref: str,
    payload: InsightExecuteRequest,
    request: Request,
) -> InsightResultRead:
    """Execute a saved insight, optionally overriding its config."""
    async with _session_context(request) as session:
        insight = await _get_insight_by_ref(session, insight_ref)
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
                persist_results=await _may_persist_results(request, project_id),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return InsightResultRead(result=result)


@router.get("/reports", response_model=list[SavedReportRead])
async def list_reports(
    request: Request,
    project_id: str | None = Query(default=None),
) -> list[SavedReportRead]:
    """List saved reports globally or for one project."""
    if project_id is not None:
        await _require_project(request, project_id)

    async with _session_context(request) as session:
        statement = select(ReportRecord)

        if project_id is not None:
            statement = statement.where(ReportRecord.project_id == project_id)
        else:
            visible = await _authorized_project_labels(request, session)

            if visible is not None:
                statement = statement.where(
                    cast(Any, ReportRecord.project_id).in_(visible)
                )
        rows = (await session.exec(statement)).all()
    return [_saved_report_read(row) for row in rows]


@router.post("/reports", response_model=SavedReportRead, status_code=201)
async def create_report(
    payload: SavedReportCreate, request: Request
) -> SavedReportRead:
    """Create a saved report and its initial revision."""
    if payload.project_id is not None:
        await _require_project(request, payload.project_id)
    now = datetime.now(UTC)
    report_id = payload.report_id or _new_id("report")
    async with _session_context(request) as session:
        report = ReportRecord(
            report_id=report_id,
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            config=payload.config,
            created_at=now,
            updated_at=now,
            created_by_user_id=getattr(request.state.principal, "user_pk", None),
            updated_by_user_id=getattr(request.state.principal, "user_pk", None),
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
    """Render and persist either a saved report or filesystem report output."""
    rendered_report_id = payload.rendered_report_id or _new_id("rendered_report")
    created_at = datetime.now(UTC)

    if payload.project_id is not None:
        await _require_project(request, payload.project_id)

    if payload.report_id is not None:
        # Saved-report rendering executes the report model and stores the final
        # offline HTML so it can be viewed/exported later.
        async with _session_context(request) as session:
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
                persist_results=await _may_persist_results(request, project_id),
            )
            html = render_report_result(result)
            name = report.name
    else:
        # Standalone rendering preserves the older CLI-style path where a report
        # is rendered from a results directory instead of a saved report config.
        project_id = payload.project_id
        html = render_report(payload.results, name=payload.name)
        name = payload.name

    values = RenderedReportRecord(
        rendered_report_id=rendered_report_id,
        project_id=project_id,
        run_id=payload.run_id,
        report_id=payload.report_id,
        name=name,
        html=html,
        created_at=created_at,
    )

    if await _may_persist_results(request, project_id):
        async with _session_context(request) as session:
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
        name=name,
        html=html,
        created_at=created_at,
    )


@router.get("/reports/{report_ref}", response_model=SavedReportRead)
async def get_saved_report(report_ref: str, request: Request) -> SavedReportRead:
    """Return a saved report by ID or stable URL slug."""
    async with _session_context(request) as session:
        row = await _get_report_by_ref(session, report_ref)

    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")

    if row.project_id is not None:
        project = await _require_project(request, row.project_id)
        await require_project_permission(
            request, _session(request), project, "report.read"
        )

    return _saved_report_read(row)


@router.patch("/reports/{report_ref}", response_model=SavedReportRead)
async def patch_report(
    report_ref: str, payload: SavedReportPatch, request: Request
) -> SavedReportRead:
    """Patch a saved report and record a revision when config changes."""
    values = payload.model_dump(exclude_unset=True)

    if values:
        async with _session_context(request) as session:
            report = await _get_report_by_ref(session, report_ref)

            if report is None:
                raise HTTPException(status_code=404, detail="Report not found")

            if report.project_id is not None:
                project = await _require_project(request, report.project_id)
                await require_project_permission(
                    request, _session(request), project, "report.edit"
                )

            report_id = report.report_id
            updated_at = datetime.now(UTC)
            for key, value in values.items():
                setattr(report, key, value)
            report.updated_at = updated_at
            report.updated_by_user_id = getattr(
                request.state.principal, "user_pk", None
            )
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

    return await get_saved_report(report_ref, request)


@router.delete("/reports/{report_ref}", status_code=204)
async def delete_report(report_ref: str, request: Request) -> Response:
    """Delete a saved report, its revisions, cached results, and default pointer."""
    async with _session_context(request) as session:
        report = await _get_report_by_ref(session, report_ref)

        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")

        if report.project_id is not None:
            project = await _require_project(request, report.project_id)
            await require_project_permission(
                request, _session(request), project, "report.delete"
            )

        report_id = report.report_id
        default_project_rows = (
            await session.exec(
                select(ProjectRecord).where(
                    ProjectRecord.default_report_id == report_id
                )
            )
        ).all()

        for project_row in default_project_rows:
            project_row.default_report_id = None
            session.add(project_row)

        report_revision_id = cast(Any, ReportRevisionRecord.report_id)
        report_cache_id = cast(Any, ReportResultCacheRecord.report_id)

        await session.exec(
            delete(ReportRevisionRecord).where(report_revision_id == report_id)
        )
        await session.exec(
            delete(ReportResultCacheRecord).where(report_cache_id == report_id)
        )
        await session.delete(report)
        await session.commit()

    return Response(status_code=204)


@router.get("/reports/{report_ref}/export.yaml")
async def export_report_yaml(report_ref: str, request: Request) -> Response:
    """Export a saved report as portable YAML."""

    report = await get_saved_report(report_ref, request)
    body = yaml.safe_dump(_saved_report_export(report), sort_keys=False)
    return Response(content=body, media_type="application/yaml")


@router.get("/reports/{report_ref}/export.json")
async def export_report_json(report_ref: str, request: Request) -> dict[str, Any]:
    """Export a saved report as portable JSON."""

    report = await get_saved_report(report_ref, request)
    return _saved_report_export(report)


@router.post("/reports/{report_ref}/execute", response_model=ReportResultRead)
async def execute_saved_report(
    report_ref: str,
    payload: ReportExecuteRequest,
    request: Request,
) -> ReportResultRead:
    """Execute a saved report and return its structured result payload."""
    async with _session_context(request) as session:
        report = await _get_report_by_ref(session, report_ref)
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
                persist_results=await _may_persist_results(request, project_id),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return ReportResultRead(result=result)


@router.get("/rendered-reports/{rendered_report_id}", response_model=RenderedReportRead)
async def get_rendered_report(
    rendered_report_id: str, request: Request
) -> RenderedReportRead:
    """Return a persisted rendered report."""
    async with _session_context(request) as session:
        row = await session.get(RenderedReportRecord, rendered_report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Rendered report not found")
    return RenderedReportRead.model_validate(row.model_dump())


@router.get("/rendered-reports/{rendered_report_id}/export.html")
async def export_rendered_report_html(
    rendered_report_id: str, request: Request
) -> Response:
    """Export persisted report HTML."""

    report = await get_rendered_report(rendered_report_id, request)
    return Response(content=report.html, media_type="text/html")


@router.get(
    "/projects/{project_id}/sample-groups",
    response_model=SampleGroupPageRead,
)
async def list_project_sample_groups(
    project_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=255),
    kind: str | None = Query(default=None, max_length=64),
) -> SampleGroupPageRead:
    """List project sample groups with search, counts, and pagination."""

    return await _list_project_sample_groups(
        request,
        project_id=project_id,
        limit=limit,
        offset=offset,
        search=search,
        kind=kind,
    )


@router.post(
    "/projects/{project_id}/sample-groups",
    response_model=SampleGroupRead,
    status_code=201,
)
async def create_project_sample_group(
    project_id: str,
    payload: SampleGroupCreate,
    request: Request,
) -> SampleGroupRead:
    """Create a project-scoped sample group."""

    project = await _require_project(request, project_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Sample group name is required")
    kind = payload.kind.strip() or "sample_group"
    now = datetime.now(UTC)
    async with _session_context(request) as session:
        row = SampleGroupRecord(
            sample_group_id=_new_id("sample-group"),
            project_id=project.id,
            name=name,
            kind=kind,
            description=payload.description,
            definition_json={"source": "dashboard"},
            created_at=now,
            updated_at=now,
            metadata_json={},
        )
        session.add(row)
        await session.flush()
        await _add_sample_group_members_by_sample_id(
            session,
            project,
            row,
            payload.sample_ids,
        )
        await session.commit()
        await session.refresh(row)
        return await _sample_group_read(session, row)


@router.get(
    "/projects/{project_id}/sample-groups/{sample_group_id}",
    response_model=SampleGroupRead,
)
async def get_project_sample_group(
    project_id: str,
    sample_group_id: str,
    request: Request,
) -> SampleGroupRead:
    """Return one project-scoped sample group with its member count."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        row = await _require_project_sample_group(session, project, sample_group_id)
        return await _sample_group_read(session, row, project_id=project.project_id)


@router.patch(
    "/projects/{project_id}/sample-groups/{sample_group_id}",
    response_model=SampleGroupRead,
)
async def patch_project_sample_group(
    project_id: str,
    sample_group_id: str,
    payload: SampleGroupPatch,
    request: Request,
) -> SampleGroupRead:
    """Patch a project-scoped sample group."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        row = await _require_project_sample_group(session, project, sample_group_id)
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                raise HTTPException(
                    status_code=400,
                    detail="Sample group name is required",
                )
            row.name = name
        if payload.description is not None:
            row.description = payload.description
        if payload.kind is not None:
            row.kind = payload.kind.strip() or "sample_group"
        if payload.metadata_json is not None:
            row.metadata_json = payload.metadata_json
        row.updated_at = datetime.now(UTC)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return await _sample_group_read(session, row)


@router.delete(
    "/projects/{project_id}/sample-groups/{sample_group_id}",
    status_code=204,
)
async def delete_project_sample_group(
    project_id: str,
    sample_group_id: str,
    request: Request,
) -> Response:
    """Delete a project-scoped sample group and its members."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        row = await _require_project_sample_group(session, project, sample_group_id)
        if row.id is not None:
            sample_group_member_id = cast(Any, SampleGroupMemberRecord.sample_group_id)
            await session.exec(
                delete(SampleGroupMemberRecord).where(sample_group_member_id == row.id)
            )
        await session.delete(row)
        await session.commit()
    return Response(status_code=204)


@router.get(
    "/projects/{project_id}/sample-groups/{sample_group_id}/members",
    response_model=SampleGroupMemberPageRead,
)
async def list_project_sample_group_members(
    project_id: str,
    sample_group_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=255),
) -> SampleGroupMemberPageRead:
    """List sample/run link members for one sample group."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        row = await _require_project_sample_group(session, project, sample_group_id)
        return await _sample_group_members_page(
            session,
            project,
            row,
            limit=limit,
            offset=offset,
            search=search,
        )


@router.post(
    "/projects/{project_id}/sample-groups/{sample_group_id}/members",
    response_model=SampleGroupRead,
)
async def add_project_sample_group_members(
    project_id: str,
    sample_group_id: str,
    payload: SampleGroupMembersAdd,
    request: Request,
) -> SampleGroupRead:
    """Add samples to a sample group by resolving their latest sample/run link."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        row = await _require_project_sample_group(session, project, sample_group_id)
        await _add_sample_group_members_by_sample_id(
            session,
            project,
            row,
            payload.sample_ids,
        )
        await session.commit()
        await session.refresh(row)
        return await _sample_group_read(session, row)


@router.delete(
    "/projects/{project_id}/sample-groups/{sample_group_id}/members",
    response_model=SampleGroupRead,
)
async def remove_project_sample_group_members(
    project_id: str,
    sample_group_id: str,
    payload: SampleGroupMembersRemove,
    request: Request,
) -> SampleGroupRead:
    """Remove sample/run link members from a sample group."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        row = await _require_project_sample_group(session, project, sample_group_id)
        await _remove_sample_group_members_by_run_sample_id(
            session,
            project,
            row,
            payload.run_sample_ids,
        )
        await session.commit()
        await session.refresh(row)
        return await _sample_group_read(session, row)


@router.get("/sample-groups", response_model=list[SampleGroupRead])
async def list_sample_groups(
    request: Request,
    project_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
) -> list[SampleGroupRead]:
    """List canonical sample groups used for filtering and comparison."""
    project_pk: int | None = None
    if project_id is not None:
        project = await _require_project(request, project_id)
        project_pk = project.id
    async with _session_context(request) as session:
        statement = select(SampleGroupRecord)
        if project_pk is not None:
            statement = statement.where(SampleGroupRecord.project_id == project_pk)
        if kind is not None:
            statement = statement.where(SampleGroupRecord.kind == kind)
        rows = (await session.exec(statement.order_by(SampleGroupRecord.name))).all()
        counts: dict[int, int] = {}
        sample_group_ids = [row.id for row in rows if row.id is not None]
        if sample_group_ids:
            sample_group_member_id = cast(Any, SampleGroupMemberRecord.sample_group_id)
            member_id = cast(Any, SampleGroupMemberRecord.id)
            count_rows = (
                await session.exec(
                    select(
                        sample_group_member_id,
                        func.count(member_id),
                    )
                    .where(sample_group_member_id.in_(sample_group_ids))
                    .group_by(sample_group_member_id)
                )
            ).all()
            counts = {int(row[0]): int(row[1]) for row in count_rows}
        return [
            await _sample_group_read(
                session,
                row,
                member_count=counts.get(int(row.id or 0), 0),
            )
            for row in rows
        ]


@router.get("/projects/{project_id}/qc-policies", response_model=list[QCPolicyRead])
async def list_qc_policies(project_id: str, request: Request) -> list[QCPolicyRead]:
    """List project-owned QC policy definitions."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        rows = (
            await session.exec(
                select(QCPolicyRecord)
                .where(QCPolicyRecord.project_id == project.id)
                .order_by(QCPolicyRecord.name)
            )
        ).all()
    return [_qc_policy_read(row, project_id) for row in rows]


@router.post(
    "/projects/{project_id}/qc-policies",
    response_model=QCPolicyRead,
    status_code=201,
)
async def create_qc_policy(
    project_id: str, payload: QCPolicyCreate, request: Request
) -> QCPolicyRead:
    """Create a project-owned QC policy definition."""

    project = await _require_project(request, project_id)
    row = QCPolicyRecord(
        policy_id=payload.policy_id or _new_id("policy"),
        project_id=cast(int, project.id),
        name=payload.name,
        thresholds=json.loads(json.dumps(payload.thresholds)),
        updated_at=datetime.now(UTC),
    )
    async with _session_context(request) as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return _qc_policy_read(row, project_id)


@router.patch(
    "/projects/{project_id}/qc-policies/{policy_id}", response_model=QCPolicyRead
)
async def patch_qc_policy(
    project_id: str, policy_id: str, payload: QCPolicyPatch, request: Request
) -> QCPolicyRead:
    """Patch a project-owned QC policy definition."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        row = (
            await session.exec(
                select(QCPolicyRecord).where(
                    QCPolicyRecord.project_id == project.id,
                    QCPolicyRecord.policy_id == policy_id,
                )
            )
        ).first()

        if row is None:
            raise HTTPException(status_code=404, detail="QC policy not found")
        values = payload.model_dump(exclude_unset=True)

        if "name" in values:
            row.name = values["name"]

        if "thresholds" in values:
            row.thresholds = json.loads(json.dumps(values["thresholds"]))

        row.updated_at = datetime.now(UTC)
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return _qc_policy_read(row, project_id)


def _qc_policy_read(row: QCPolicyRecord, project_id: str) -> QCPolicyRead:
    return QCPolicyRead(
        policy_id=row.policy_id,
        project_id=project_id,
        name=row.name,
        thresholds=row.thresholds,
        updated_at=row.updated_at,
    )


@router.get("/database/tables", response_model=list[DatabaseTableRead])
async def list_database_tables(
    request: Request,
    project_id: str | None = Query(default=None),
) -> list[DatabaseTableRead]:
    """List metadata and analytics tables available to the database browser."""

    if project_id is not None:
        await _require_project(request, project_id)
    metadata_counts = await _metadata_table_counts(request, project_id=project_id)
    analytics_store = _analytics_store_for_project(request, project_id)
    analytics_counts = analytics_store.row_counts()
    return [
        DatabaseTableRead(
            name=name,
            store="metadata",
            rows=metadata_counts.get(name, 0),
            columns=_metadata_columns(model),
            editable=name in EDITABLE_TABLES,
        )
        for name, (model, _) in sorted(METADATA_TABLES.items())
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
    """Return storage sizes and row counts for the local database."""

    if project_id is not None:
        await _require_project(request, project_id)
    metadata_counts = await _metadata_table_counts(request, project_id=project_id)
    analytics_store = _analytics_store_for_project(request, project_id)
    analytics_counts = analytics_store.row_counts()
    return DatabaseSummaryRead(
        sqlite_size_bytes=_sqlite_size_bytes(request.app.state.settings.database_url),
        duckdb_size_bytes=analytics_store.database_size_bytes(),
        file_size_bytes=_path_size(Path(request.app.state.settings.file_root)),
        total_runs=metadata_counts.get("runs", 0),
        total_samples=metadata_counts.get("samples", 0),
        total_scalar_metrics=analytics_counts.get("sample_metrics", 0),
        total_payloads=analytics_counts.get("result_payloads", 0),
        metadata_tables=[
            TableCountRead(name=name, rows=count)
            for name, count in sorted(metadata_counts.items())
        ],
        analytics_tables=[
            TableCountRead(name=name, rows=count)
            for name, count in sorted(analytics_counts.items())
        ],
    )


@router.get("/database/tables/{table_name}/rows")
async def list_database_rows(table_name: str, request: Request) -> list[dict[str, Any]]:
    """List rows from an editable metadata table."""

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
    """Preview paginated rows from a metadata or analytics table."""

    if project_id is not None:
        await _require_project(request, project_id)
    if store == "metadata":
        return await _metadata_table_page(
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
    """Patch one row in a registry-approved editable metadata table."""

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


async def _may_persist_results(request: Request, project_id: str | None) -> bool:
    """
    Return whether execution may write cache or rendered-report rows.
    Do not want unauthorized users to persist results, only local
    or admin principals, or those with project-specific permissions.
    """

    principal = cast(Principal, request.state.principal)
    if principal.kind == "local" or principal.is_admin:
        return True
    if project_id is None:
        return False
    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        permissions = await project_permissions(
            session, principal, project, request.app.state.settings
        )
    return "result.persist" in permissions


def _session(request: Request) -> AsyncSession:
    """Return the request-scoped SQL session created by FastAPI."""

    return cast(AsyncSession, request.state.db_session)


@asynccontextmanager
async def _session_context(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield the request session without closing it before the response completes."""

    yield _session(request)


async def _ensure_default_project(request: Request) -> ProjectRead:
    """Create and return the default project used by first-run dashboards."""

    project = await request.app.state.store.ensure_project_with_session(
        _session(request), DEFAULT_PROJECT_ID
    )
    async with _session_context(request) as session:
        row = (
            await session.exec(
                select(ProjectRecord).where(
                    ProjectRecord.project_id == project.project_id
                )
            )
        ).one()
        await seed_project_roles(session, row)
        await session.commit()

    return await _get_project_read(request, project.project_id)


async def _require_project(request: Request, project_id: str) -> ProjectRecord:
    """Return a project row or raise a 404 HTTP error."""
    async with _session_context(request) as session:
        row = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.project_id, project_id
        )
        if row is not None:
            await seed_project_roles(session, row)
            await session.commit()
            await session.refresh(row)

    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_project_permission(request, _session(request), row, "project.read")

    return row


async def _authorized_project_labels(
    request: Request, session: AsyncSession
) -> set[str] | None:
    visible = await authorized_project_pks(
        session,
        cast(Principal, request.state.principal),
        request.app.state.settings,
    )

    if visible is None:
        return None

    rows = (
        await session.exec(
            select(ProjectRecord.project_id).where(
                cast(Any, ProjectRecord.id).in_(visible)
            )
        )
    ).all()

    return {str(value) for value in rows}


async def _get_project_read(request: Request, project_id: str) -> ProjectRead:
    """Return an enriched project response by public project ID."""
    async with _session_context(request) as session:
        row = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.project_id, project_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return await _project_read(row, session=session)


async def _list_project_sample_groups(
    request: Request,
    *,
    project_id: str,
    limit: int,
    offset: int,
    search: str = "",
    kind: str | None = None,
) -> SampleGroupPageRead:
    """List project sample groups with member counts."""

    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        filters: list[Any] = [SampleGroupRecord.project_id == project.id]
        if kind:
            filters.append(SampleGroupRecord.kind == kind)
        term = search.strip().lower()
        if term:
            pattern = f"%{term}%"
            filters.append(
                or_(
                    func.lower(SampleGroupRecord.sample_group_id).like(pattern),
                    func.lower(SampleGroupRecord.name).like(pattern),
                    func.lower(SampleGroupRecord.kind).like(pattern),
                    func.lower(SampleGroupRecord.description).like(pattern),
                )
            )
        total = int(
            (
                await session.exec(
                    select(func.count()).select_from(SampleGroupRecord).where(*filters)
                )
            ).one()
        )
        rows = (
            await session.exec(
                select(SampleGroupRecord)
                .where(*filters)
                .order_by(
                    cast(Any, SampleGroupRecord.updated_at).desc(),
                    SampleGroupRecord.name,
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
        counts = await _sample_group_member_counts(
            session,
            [row.id for row in rows if row.id is not None],
        )
        return SampleGroupPageRead(
            items=[
                await _sample_group_read(
                    session,
                    row,
                    member_count=counts.get(int(row.id or 0), 0),
                    project_id=project.project_id,
                )
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )


async def _sample_group_read(
    session: AsyncSession,
    row: SampleGroupRecord,
    *,
    member_count: int | None = None,
    project_id: str | None = None,
) -> SampleGroupRead:
    """Convert a sample-group metadata row into a dashboard/API response."""

    row_id = int(row.id or 0)
    count = (
        member_count
        if member_count is not None
        else (await _sample_group_member_counts(session, [row_id])).get(row_id, 0)
    )
    definition_json = (
        row.definition_json if isinstance(row.definition_json, dict) else {}
    )
    metadata_json = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return SampleGroupRead(
        sample_group_id=row.sample_group_id,
        url_slug=_sample_group_url_slug(row),
        project_id=(
            project_id
            if project_id is not None
            else await _public_label(
                session,
                ProjectRecord,
                "project_id",
                row.project_id,
            )
        ),
        name=row.name,
        kind=row.kind,
        description=row.description,
        definition_json=definition_json,
        metadata_json=metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
        member_count=count,
    )


async def _sample_group_member_counts(
    session: AsyncSession,
    sample_group_ids: list[int],
) -> dict[int, int]:
    """Return member counts keyed by internal sample-group primary key."""

    if not sample_group_ids:
        return {}
    sample_group_member_id = cast(Any, SampleGroupMemberRecord.sample_group_id)
    member_id = cast(Any, SampleGroupMemberRecord.id)
    count_rows = (
        await session.exec(
            select(
                sample_group_member_id,
                func.count(member_id),
            )
            .where(sample_group_member_id.in_(sample_group_ids))
            .group_by(sample_group_member_id)
        )
    ).all()
    return {int(row[0]): int(row[1]) for row in count_rows}


async def _require_project_sample_group(
    session: AsyncSession,
    project: ProjectRecord,
    sample_group_ref: str,
) -> SampleGroupRecord:
    """Return a sample group only when it belongs to the project."""

    row = await _get_project_sample_group_by_ref(session, project, sample_group_ref)
    if row is None:
        raise HTTPException(status_code=404, detail="Sample group not found")
    return row


async def _get_project_sample_group_by_ref(
    session: AsyncSession,
    project: ProjectRecord,
    sample_group_ref: str,
) -> SampleGroupRecord | None:
    """Resolve a sample group by raw sample-group ID or readable URL slug."""

    row = await get_record_where(
        session,
        SampleGroupRecord,
        SampleGroupRecord.project_id == project.id,
        SampleGroupRecord.sample_group_id == sample_group_ref,
    )
    if row is not None:
        return row
    url_key = _sample_group_url_key_from_slug(sample_group_ref)
    if not url_key:
        return None
    rows = (
        await session.exec(
            select(SampleGroupRecord).where(SampleGroupRecord.project_id == project.id)
        )
    ).all()
    return next(
        (
            candidate
            for candidate in rows
            if _sample_group_url_key(candidate) == url_key
        ),
        None,
    )


def _saved_insight_read(row: InsightRecord) -> SavedInsightRead:
    values = row.model_dump()
    values["url_slug"] = _saved_entity_url_slug(
        row.insight_id,
        row.name,
        prefix="ins",
        fallback="insight",
    )
    return SavedInsightRead.model_validate(values)


def _saved_report_read(row: ReportRecord) -> SavedReportRead:
    values = row.model_dump()
    values["url_slug"] = _saved_entity_url_slug(
        row.report_id,
        row.name,
        prefix="rep",
        fallback="report",
    )
    return SavedReportRead.model_validate(values)


async def _get_insight_by_ref(
    session: AsyncSession,
    insight_ref: str,
) -> InsightRecord | None:
    row = await session.get(InsightRecord, insight_ref)
    if row is not None:
        return row
    url_key = _saved_entity_url_key_from_slug(insight_ref, prefix="ins")
    if not url_key:
        return None
    rows = (await session.exec(select(InsightRecord))).all()
    return next(
        (
            candidate
            for candidate in rows
            if _saved_entity_url_key(candidate.insight_id, prefix="ins") == url_key
        ),
        None,
    )


async def _get_report_by_ref(
    session: AsyncSession,
    report_ref: str,
) -> ReportRecord | None:
    row = await session.get(ReportRecord, report_ref)
    if row is not None:
        return row
    url_key = _saved_entity_url_key_from_slug(report_ref, prefix="rep")
    if not url_key:
        return None
    rows = (await session.exec(select(ReportRecord))).all()
    return next(
        (
            candidate
            for candidate in rows
            if _saved_entity_url_key(candidate.report_id, prefix="rep") == url_key
        ),
        None,
    )


def _saved_entity_url_slug(
    entity_id: str,
    name: str,
    *,
    prefix: str,
    fallback: str,
) -> str:
    """Return a stable readable URL segment for an insight or report."""

    return (
        f"{_saved_entity_url_key(entity_id, prefix=prefix)}-"
        f"{_slugify_url_part(name, fallback=fallback)}"
    )


def _saved_entity_url_key(entity_id: str, *, prefix: str) -> str:
    digest = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:10]}"


def _saved_entity_url_key_from_slug(value: str, *, prefix: str) -> str | None:
    match = re.match(rf"^({re.escape(prefix)}_[0-9a-f]{{10}})(?:-|$)", value)
    return match.group(1) if match else None


def _sample_group_url_slug(row: SampleGroupRecord) -> str:
    """Return a stable readable URL segment for a sample group."""

    name_slug = _slugify_url_part(row.name, fallback="sample-group")
    return f"{_sample_group_url_key(row)}-{name_slug}"


def _sample_group_url_key(row: SampleGroupRecord) -> str:
    digest = hashlib.sha256(row.sample_group_id.encode("utf-8")).hexdigest()
    return f"sg_{digest[:10]}"


def _sample_group_url_key_from_slug(value: str) -> str | None:
    match = re.match(r"^(sg_[0-9a-f]{10})(?:-|$)", value)
    return match.group(1) if match else None


def _slugify_url_part(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


async def _sample_group_members_page(
    session: AsyncSession,
    project: ProjectRecord,
    sample_group: SampleGroupRecord,
    *,
    limit: int,
    offset: int,
    search: str = "",
) -> SampleGroupMemberPageRead:
    """List display-ready members for a sample group."""

    filters: list[Any] = [
        SampleGroupMemberRecord.sample_group_id == sample_group.id,
        RunRecord.project_id == project.id,
    ]
    term = search.strip().lower()
    if term:
        pattern = f"%{term}%"
        filters.append(
            or_(
                func.lower(SampleRecord.sample_id).like(pattern),
                func.lower(SampleRecord.sample_name).like(pattern),
                func.lower(RunRecord.run_id).like(pattern),
                func.lower(RunRecord.name).like(pattern),
                cast(Any, SampleRecord.subject_id).in_(
                    select(SubjectRecord.id).where(
                        func.lower(SubjectRecord.subject_id).like(pattern)
                    )
                ),
            )
        )
    count_statement = (
        select(func.count())
        .select_from(SampleGroupMemberRecord)
        .join(
            RunSampleRecord,
            cast(Any, RunSampleRecord.id) == SampleGroupMemberRecord.run_sample_id,
        )
        .join(SampleRecord, cast(Any, SampleRecord.id) == RunSampleRecord.sample_id)
        .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
        .where(*filters)
    )
    total = int((await session.exec(count_statement)).one())
    rows = (
        await session.exec(
            select(
                RunSampleRecord,
                SampleRecord,
                RunRecord,
                cast(Any, SubjectRecord.subject_id),
            )
            .select_from(SampleGroupMemberRecord)
            .join(
                RunSampleRecord,
                cast(Any, RunSampleRecord.id) == SampleGroupMemberRecord.run_sample_id,
            )
            .join(SampleRecord, cast(Any, SampleRecord.id) == RunSampleRecord.sample_id)
            .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
            .join(
                SubjectRecord,
                cast(Any, SubjectRecord.id) == SampleRecord.subject_id,
                isouter=True,
            )
            .where(*filters)
            .order_by(SampleRecord.sample_id, cast(Any, RunRecord.created_at).desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return SampleGroupMemberPageRead(
        items=[
            _sample_group_member_read(run_sample, sample, run, subject_id)
            for run_sample, sample, run, subject_id in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def _sample_group_member_read(
    run_sample: RunSampleRecord,
    sample: SampleRecord,
    run: RunRecord,
    subject_id: str | None,
) -> SampleGroupMemberRead:
    """Convert joined sample-group member rows to the public API shape."""

    return SampleGroupMemberRead(
        run_sample_id=run_sample.run_sample_id,
        sample_id=sample.sample_id,
        sample_name=sample.sample_name,
        subject_id=subject_id,
        run_id=run.run_id,
        run_name=run.name,
        status=run.status,
    )


async def _add_sample_group_members_by_sample_id(
    session: AsyncSession,
    project: ProjectRecord,
    sample_group: SampleGroupRecord,
    sample_ids: list[str],
) -> None:
    """Resolve stable sample labels to latest run-sample rows and add members."""

    requested_sample_ids = _unique_nonempty(sample_ids)
    if not requested_sample_ids:
        return
    latest_run_samples: list[RunSampleRecord] = []
    unresolved: list[str] = []
    project_id = project.project_id
    for sample_id in requested_sample_ids:
        await _require_project_sample(session, project_id, sample_id)
        latest = await _latest_sample_run(session, project_id, sample_id)
        if latest is None:
            unresolved.append(sample_id)
            continue
        latest_run_samples.append(latest[1])
    if unresolved:
        raise HTTPException(
            status_code=400,
            detail=(
                "Samples must have at least one run/sample link before they "
                f"can be added to a group: {', '.join(unresolved)}"
            ),
        )
    run_sample_pks = [
        int(row.id)
        for row in latest_run_samples
        if row.id is not None and row.sample_id is not None
    ]
    if not run_sample_pks or sample_group.id is None:
        return
    existing = (
        await session.exec(
            select(SampleGroupMemberRecord.run_sample_id).where(
                SampleGroupMemberRecord.sample_group_id == sample_group.id,
                cast(Any, SampleGroupMemberRecord.run_sample_id).in_(run_sample_pks),
            )
        )
    ).all()
    existing_pks = {int(row) for row in existing}
    new_members = [
        SampleGroupMemberRecord(
            sample_group_id=sample_group.id,
            run_sample_id=run_sample_pk,
        )
        for run_sample_pk in run_sample_pks
        if run_sample_pk not in existing_pks
    ]
    if not new_members:
        return
    session.add_all(new_members)
    sample_group.updated_at = datetime.now(UTC)
    session.add(sample_group)
    await session.flush()


async def _remove_sample_group_members_by_run_sample_id(
    session: AsyncSession,
    project: ProjectRecord,
    sample_group: SampleGroupRecord,
    run_sample_ids: list[str],
) -> None:
    """Remove sample/run link labels from a sample group."""

    requested_run_sample_ids = _unique_nonempty(run_sample_ids)
    if not requested_run_sample_ids or sample_group.id is None:
        return
    run_samples = (
        await session.exec(
            select(RunSampleRecord)
            .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
            .where(
                RunRecord.project_id == project.id,
                cast(Any, RunSampleRecord.run_sample_id).in_(requested_run_sample_ids),
            )
        )
    ).all()
    found_ids = {row.run_sample_id for row in run_samples}
    missing = [
        run_sample_id
        for run_sample_id in requested_run_sample_ids
        if run_sample_id not in found_ids
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Run samples are not in this project: {', '.join(missing)}",
        )
    run_sample_pks = [int(row.id) for row in run_samples if row.id is not None]
    members = (
        await session.exec(
            select(SampleGroupMemberRecord).where(
                SampleGroupMemberRecord.sample_group_id == sample_group.id,
                cast(Any, SampleGroupMemberRecord.run_sample_id).in_(run_sample_pks),
            )
        )
    ).all()
    if not members:
        return
    for member in members:
        await session.delete(member)
    sample_group.updated_at = datetime.now(UTC)
    session.add(sample_group)
    await session.flush()


def _unique_nonempty(values: list[str]) -> list[str]:
    """Return unique, stripped non-empty values while preserving order."""

    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


async def _get_project_run(request: Request, project_id: str, run_id: str) -> Run:
    """Return a public run model after checking project ownership."""

    await _require_project(request, project_id)
    run = await request.app.state.store.get_run(run_id, session=_session(request))
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


async def _get_run_record(request: Request, run_id: str) -> RunRecord:
    """Return the SQL metadata row for a run."""
    async with _session_context(request) as session:
        row = await get_record_by_field(session, RunRecord, RunRecord.run_id, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if row.project_id is not None:
        async with _session_context(request) as session:
            project = await session.get(ProjectRecord, row.project_id)
        if project is not None:
            await require_project_permission(
                request, _session(request), project, "data.read"
            )
    return row


async def _get_project_run_record(
    request: Request, project_id: str, run_id: str
) -> RunRecord:
    """Return a run metadata row after checking project ownership."""

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
    """Build a project response with derived counts and latest activity."""

    # Project cards need summary numbers, but those counts are not stored on the
    # project row. Compute them in the same session to keep the response current.
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
    search: str = "",
) -> SamplePageRead:
    """List samples with latest-run and run-count summary columns."""
    project = await _require_project(request, project_id)
    project_pk = project.id
    # These subqueries avoid returning every run_sample link just to show summary
    # data in the sample table.
    latest_run_subquery = (
        select(
            cast(Any, RunSampleRecord.sample_id).label("sample_id"),
            func.max(RunRecord.created_at).label("latest_run_created_at"),
        )
        .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
        .where(
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
        .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
        .where(RunRecord.project_id == project_pk)
        .group_by(cast(Any, RunSampleRecord.sample_id))
        .subquery()
    )
    async with _session_context(request) as session:
        sample_filters: list[Any] = [SampleRecord.project_id == project_pk]
        term = search.strip().lower()
        if term:
            pattern = f"%{term}%"
            sample_filters.append(
                or_(
                    func.lower(SampleRecord.sample_id).like(pattern),
                    func.lower(SampleRecord.sample_name).like(pattern),
                    cast(Any, SampleRecord.subject_id).in_(
                        select(SubjectRecord.id).where(
                            func.lower(SubjectRecord.subject_id).like(pattern)
                        )
                    ),
                )
            )
        total = int(
            (
                await session.exec(
                    select(func.count())
                    .select_from(SampleRecord)
                    .where(*sample_filters)
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
            .where(*sample_filters)
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


async def _list_project_run_sample_links(
    request: Request,
    *,
    project_id: str,
    limit: int,
    offset: int,
    search: str = "",
) -> RunSamplePageRead:
    """List project-scoped run/sample links with picker-friendly labels."""
    project = await _require_project(request, project_id)
    async with _session_context(request) as session:
        filters: list[Any] = [RunRecord.project_id == project.id]
        term = search.strip().lower()
        if term:
            pattern = f"%{term}%"
            filters.append(
                or_(
                    func.lower(RunSampleRecord.run_sample_id).like(pattern),
                    func.lower(RunRecord.run_id).like(pattern),
                    func.lower(RunRecord.name).like(pattern),
                    func.lower(SampleRecord.sample_id).like(pattern),
                    func.lower(SampleRecord.sample_name).like(pattern),
                    func.lower(SubjectRecord.subject_id).like(pattern),
                )
            )
        base = (
            select(RunSampleRecord)
            .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
            .join(SampleRecord, cast(Any, SampleRecord.id) == RunSampleRecord.sample_id)
            .outerjoin(
                SubjectRecord,
                cast(Any, SubjectRecord.id) == SampleRecord.subject_id,
            )
            .where(*filters)
        )
        total = int(
            (
                await session.exec(select(func.count()).select_from(base.subquery()))
            ).one()
        )
        rows = (
            await session.exec(
                select(RunSampleRecord, RunRecord, SampleRecord, SubjectRecord)
                .join(RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id)
                .join(
                    SampleRecord,
                    cast(Any, SampleRecord.id) == RunSampleRecord.sample_id,
                )
                .outerjoin(
                    SubjectRecord,
                    cast(Any, SubjectRecord.id) == SampleRecord.subject_id,
                )
                .where(*filters)
                .order_by(
                    cast(Any, RunRecord.created_at).desc(),
                    RunSampleRecord.run_sample_id,
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
        items = [
            RunSampleListItemRead(
                run_sample_id=run_sample.run_sample_id,
                run_id=run.run_id,
                run_name=run.name,
                sample_id=sample.sample_id,
                sample_name=sample.sample_name,
                subject_id=subject.subject_id if subject is not None else None,
                role=run_sample.role,
                status=run.status,
                created_at=run.created_at,
            )
            for run_sample, run, sample, subject in rows
        ]
    return RunSamplePageRead(items=items, total=total, limit=limit, offset=offset)


async def _require_project_sample(
    session: AsyncSession,
    project_id: str,
    sample_id: str,
) -> SampleRecord:
    """Return a sample row only when it belongs to the project."""

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
    """Return run/run_sample rows for a sample in reverse run order."""

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
    """Return the latest run/run_sample pair for a project sample."""

    rows = await _sample_run_rows(session, project_id, sample_id)
    return rows[0] if rows else None


async def _get_sample_run_link(
    session: AsyncSession,
    project_id: str,
    sample_id: str,
    run_id: str,
) -> tuple[RunRecord, RunSampleRecord]:
    """Return the metadata link proving a sample belongs to a run."""

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
    search: str = "",
) -> RunPageRead:
    """List runs with optional project scoping and pagination."""
    project_pk: int | None = None
    if project_id is not None:
        project = await _require_project(request, project_id)
        project_pk = project.id
    async with _session_context(request) as session:
        count_statement = select(func.count()).select_from(RunRecord)
        rows_statement = select(RunRecord).order_by(
            cast(Any, RunRecord.created_at).desc(), RunRecord.run_id
        )
        if project_pk is not None:
            count_statement = count_statement.where(RunRecord.project_id == project_pk)
            rows_statement = rows_statement.where(RunRecord.project_id == project_pk)
        else:
            visible = await authorized_project_pks(
                session,
                cast(Principal, request.state.principal),
                request.app.state.settings,
            )
            if visible is not None:
                count_statement = count_statement.where(
                    cast(Any, RunRecord.project_id).in_(visible)
                )
                rows_statement = rows_statement.where(
                    cast(Any, RunRecord.project_id).in_(visible)
                )
        term = search.strip().lower()
        if term:
            pattern = f"%{term}%"
            run_filter = or_(
                func.lower(RunRecord.run_id).like(pattern),
                func.lower(RunRecord.name).like(pattern),
                func.lower(RunRecord.status).like(pattern),
            )
            count_statement = count_statement.where(run_filter)
            rows_statement = rows_statement.where(run_filter)
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
    """Convert a run metadata row into the public SDK/API run model."""

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
        analysis_type_id=cast(
            str,
            await _public_label(
                session, AnalysisTypeRecord, "analysis_type_id", row.analysis_type_id
            ),
        ),
        method_id=cast(
            str,
            await _public_label(
                session, AnalysisMethodRecord, "method_id", row.method_id
            ),
        ),
        method_version=row.method_version,
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
    """Convert a sample metadata row into the public SDK/API sample model."""

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
    """Convert a sample row plus summary values into a list item."""

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
    """Convert joined run/run_sample rows into a sample-run response."""

    return SampleRunRead(
        run_id=run.run_id,
        project_id=await _public_label(
            session, ProjectRecord, "project_id", run.project_id
        ),
        name=run.name,
        run_kind=run.run_kind,
        analysis_type_id=cast(
            str,
            await _public_label(
                session, AnalysisTypeRecord, "analysis_type_id", run.analysis_type_id
            ),
        ),
        method_id=cast(
            str,
            await _public_label(
                session, AnalysisMethodRecord, "method_id", run.method_id
            ),
        ),
        method_version=run.method_version,
        status=run.status,
        created_at=run.created_at,
        run_sample_id=run_sample.run_sample_id,
        run_sample_status=run.status,
    )


def _analytics_metric_reads(metrics: list[Any]) -> list[AnalyticsMetricRead]:
    """Convert DuckDB metric rows into API response models."""

    return [
        AnalyticsMetricRead(
            run_id=metric.run_id,
            data_contract_id=metric.data_contract_id,
            run_sample_id=metric.run_sample_id,
            sample_id=metric.sample_id,
            field_id=metric.field_id,
            value_type=metric.value_type,
            value=_sample_metric_value(metric),
            source_file_id=metric.source_file_id,
            source_observation_id=metric.source_observation_id,
            source_observation_label=metric.source_observation_label,
            source_observation_metadata_json=metric.source_observation_metadata_json,
        )
        for metric in metrics
    ]


def _sample_metric_value(metric: Any) -> JsonValue:
    """Pick the typed value column for a DuckDB metric row."""

    if getattr(metric, "value_type", None) == "numeric":
        return metric.value_numeric
    if getattr(metric, "value_type", None) == "json":
        return metric.value_json
    return metric.value_string


def _analytics_payload_reads(payloads: list[Any]) -> list[AnalyticsResultPayloadRead]:
    """Convert DuckDB payload rows into API response models."""

    return [
        AnalyticsResultPayloadRead(
            run_id=payload.run_id,
            data_contract_id=payload.data_contract_id,
            run_sample_id=payload.run_sample_id,
            sample_id=payload.sample_id,
            field_id=payload.field_id,
            payload_name=payload.payload_name,
            payload_kind=payload.payload_kind,
            storage_format=payload.storage_format,
            schema_json=payload.payload_schema_json,
            data_json=payload.data_json,
            columns=payload.columns,
            rows=payload.rows,
            row_count=payload.row_count or len(payload.rows),
            source_file_id=payload.source_file_id,
            source_observation_id=payload.source_observation_id,
            source_observation_label=payload.source_observation_label,
            source_observation_metadata_json=(payload.source_observation_metadata_json),
            source_hash=_payload_source_hash(payload.metadata_json),
        )
        for payload in payloads
    ]


def _analytics_store_for_project(
    request: Request, project_id: str | None
) -> DuckDBAnalyticsStore:
    """Return the DuckDB store for a project or configured global path."""

    settings = request.app.state.settings
    if settings.analytics_path:
        return request.app.state.analytics_stores.get(settings.analytics_path)
    return request.app.state.analytics_stores.get(
        analytics_path_for_project(
            settings.analytics_root, project_id or DEFAULT_PROJECT_ID
        )
    )


def _new_project_id() -> str:
    """Generate and validate a public project ID."""

    project_id = new_project_id()
    if not is_project_id(project_id):
        raise RuntimeError("Generated invalid project id")
    return project_id


def _new_id(prefix: str) -> str:
    """Generate a short stable-enough local API ID with a prefix."""

    return f"{prefix}-{uuid4().hex[:12]}"


def _payload_source_hash(metadata_json: dict[str, Any]) -> str | None:
    """Extract the optional source hash from payload metadata."""

    source_hash = metadata_json.get("source_hash")
    return source_hash if isinstance(source_hash, str) else None


def _saved_insight_export(insight: SavedInsightRead) -> dict[str, Any]:
    """Build the portable saved-insight export document."""

    return {
        "insight_id": insight.insight_id,
        "project_id": insight.project_id,
        "name": insight.name,
        "description": insight.description,
        "config": insight.config,
    }


def _saved_report_export(report: SavedReportRead) -> dict[str, Any]:
    """Build the portable saved-report export document."""

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
    """Load report insight dependencies in template order."""

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
    # Preserve the order in report.config["items"] so rendered reports match the
    # builder/template order instead of database return order.
    return [by_id[insight_id] for insight_id in insight_ids if insight_id in by_id]


async def _list_table(request: Request, model: type[SQLModel]) -> list[SQLModel]:
    """Return all rows from a registered SQLModel table."""
    async with _session_context(request) as session:
        return list((await session.exec(select(model))).all())


async def _metadata_table_page(
    request: Request,
    table_name: str,
    *,
    project_id: str | None,
    limit: int,
    offset: int,
    sort_by: str | None,
    sort_direction: str,
) -> DatabaseTablePageRead:
    """Preview one metadata table with safe sorting and project scoping."""

    model, primary_key = _metadata_table(table_name)
    columns = _metadata_columns(model)
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
    # Most metadata tables scope directly by project_id. A few tables either
    # include global rows or only reference runs, so each case is handled
    # explicitly instead of assuming a universal schema.
    if (
        project_pk is not None
        and table_name == "data_contracts"
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
    async with _session_context(request) as session:
        total = int((await session.exec(count_statement)).one())
        rows = list((await session.exec(row_statement)).all())
    return DatabaseTablePageRead(
        name=table_name,
        store="metadata",
        columns=columns,
        rows=cast(list[dict[str, JsonValue]], [_jsonable_row(row) for row in rows]),
        total=total,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_direction=sort_direction if sort_by is not None else None,
    )


async def _metadata_table_counts(
    request: Request, project_id: str | None = None
) -> dict[str, int]:
    """Count rows in each registered metadata table."""
    async with _session_context(request) as session:
        counts: dict[str, int] = {}
        project_pk = await _project_pk(request, project_id, session=session)
        project_run_ids = await _project_run_ids(request, project_id, session=session)
        for name, (model, _) in METADATA_TABLES.items():
            statement = select(func.count()).select_from(model)  # type: ignore[arg-type]
            model_any = cast(Any, model)
            # Count with the same scoping rules used by table previews so the
            # database summary and browser rows agree.
            if (
                project_pk is not None
                and name == "data_contracts"
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
    """Return internal run primary keys for project-scoped joins."""

    if project_id is None:
        return None
    own_session = False
    if session is None:
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
    """Resolve a public project ID to its internal SQL primary key."""

    if project_id is None:
        return None
    own_session = False
    if session is None:
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
    """Resolve an internal project primary key to its public project ID."""

    if project_pk is None:
        return None
    async with _session_context(request) as session:
        project = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.id, project_pk
        )
    return project.project_id if project is not None else None


async def _insert_values(
    request: Request, model: type[SQLModel], values: dict[str, Any]
) -> None:
    """Insert one SQLModel row after schema initialization."""
    async with _session_context(request) as session:
        session.add(model.model_validate(values))
        await session.commit()


async def _patch_values(
    request: Request,
    model: type[SQLModel],
    primary_key: str,
    row_id: str,
    values: dict[str, Any],
) -> None:
    """Patch one SQLModel row addressed by a registered primary key field."""
    async with _session_context(request) as session:
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
    """Return a SQLModel row by public row ID, opening a session if needed."""
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
    """Return edit policy for a table or raise a 404 HTTP error."""

    table_config = EDITABLE_TABLES.get(table_name)
    if table_config is None:
        raise HTTPException(status_code=404, detail="Editable table not found")
    return table_config


def _metadata_table(table_name: str) -> tuple[type[SQLModel], str]:
    """Return metadata browse policy for a table or raise a 404 HTTP error."""

    table_config = METADATA_TABLES.get(table_name)
    if table_config is None:
        raise HTTPException(status_code=404, detail="Metadata table not found")
    return table_config


def _metadata_columns(model: type[SQLModel]) -> list[str]:
    """Return public column names for a SQLModel metadata model."""

    return list(model.model_fields)


def _coerce_json_values(
    model: type[SQLModel], values: dict[str, JsonValue]
) -> dict[str, Any]:
    """Coerce database-editor JSON values into SQLModel field names/values."""

    coerced: dict[str, Any] = {}
    for key, value in values.items():
        field_name = _model_field_name(model, key)
        if key in {"config", "filters", "thresholds", "metadata", "value"}:
            coerced[field_name] = json.loads(json.dumps(value))
        else:
            coerced[field_name] = value
    return coerced


def _jsonable_row(row: SQLModel) -> dict[str, Any]:
    """Convert a SQLModel row into a JSON-friendly database-browser row."""

    data = row.model_dump(mode="json")
    if isinstance(row, SampleRecord) and "metadata_json" in data:
        data["metadata"] = data.pop("metadata_json")
    return data


async def _fields_by_contract(
    session: AsyncSession,
    contracts: list[DataContractRecord],
) -> dict[int | None, list[DataContractFieldRecord]]:
    """Load data-contract fields grouped by contract primary key."""

    contract_ids = [contract.id for contract in contracts if contract.id is not None]
    if not contract_ids:
        return {}
    rows = (
        await session.exec(
            select(DataContractFieldRecord)
            .where(
                cast(Any, DataContractFieldRecord.data_contract_id).in_(contract_ids)
            )
            .order_by(
                DataContractFieldRecord.field_role, DataContractFieldRecord.field_id
            )
        )
    ).all()
    grouped: dict[int | None, list[DataContractFieldRecord]] = {}
    for row in rows:
        grouped.setdefault(row.data_contract_id, []).append(row)
    return grouped


async def _contract_analysis_type_labels(
    session: AsyncSession,
    contracts: list[DataContractRecord],
) -> dict[int | None, list[str]]:
    """Load compatible controlled analysis-type labels by contract."""

    contract_ids = [contract.id for contract in contracts if contract.id is not None]
    if not contract_ids:
        return {}
    rows = (
        await session.exec(
            select(DataContractAnalysisTypeRecord, AnalysisTypeRecord)
            .join(
                AnalysisTypeRecord,
                cast(Any, AnalysisTypeRecord.id)
                == DataContractAnalysisTypeRecord.analysis_type_id,
            )
            .where(
                cast(Any, DataContractAnalysisTypeRecord.data_contract_id).in_(
                    contract_ids
                )
            )
        )
    ).all()
    grouped: dict[int | None, list[str]] = {}
    for association, analysis_type in rows:
        grouped.setdefault(association.data_contract_id, []).append(
            analysis_type.analysis_type_id
        )
    return grouped


def _prefer_project_contract_rows(
    contracts: list[DataContractRecord],
    project_pk: int,
) -> list[DataContractRecord]:
    """Deduplicate contract labels, preferring project-owned rows over legacy nulls."""

    by_label: dict[str, DataContractRecord] = {}
    for contract in contracts:
        existing = by_label.get(contract.data_contract_id)
        if existing is None or contract.project_id == project_pk:
            by_label[contract.data_contract_id] = contract
    return list(by_label.values())


def _data_contract_read(
    contract: DataContractRecord,
    fields: list[DataContractFieldRecord],
    compatible_analysis_type_ids: list[str] | None = None,
) -> DataContractRead:
    """Convert a data contract definition row into its API response model."""

    field_reads = [_data_contract_field_read(field) for field in fields]
    if not field_reads:
        # Some analytics tables are queryable even when no field rows were
        # materialized. Surface synthetic fields so the insight builder can
        # still present usable metric/attribute choices.
        field_reads = _synthetic_contract_fields(contract)
    return DataContractRead(
        data_contract_id=contract.data_contract_id,
        name=contract.name,
        data_type=contract.data_type,
        compatible_analysis_type_ids=compatible_analysis_type_ids or [],
        intrinsic_producer_families=dict(contract.intrinsic_producer_families_json),
        entity_grain=contract.entity_grain,
        value_semantics=contract.value_semantics,
        summary=dict(contract.summary_json),
        last_profiled_at=contract.last_profiled_at,
        source_fingerprint=contract.source_fingerprint,
        query_modes=dict(contract.query_modes_json),
        description=contract.description,
        metadata_json=dict(contract.metadata_json),
        fields=field_reads,
    )


def _synthetic_contract_fields(
    contract: DataContractRecord,
) -> list[DataContractFieldRead]:
    """Return field descriptors for contract tables without field rows."""

    table = _default_field_table_for_contract(contract)
    fields = {
        "feature_value_numeric": [
            ("value", "measure", "Value", "numeric", "value"),
        ],
        "feature_call": [
            ("call_code", "attribute", "Call code", "string", "call_code"),
            ("call_rank", "measure", "Call rank", "numeric", "call_rank"),
        ],
        "copy_number_segments": [
            ("segment_mean", "measure", "Segment mean", "numeric", "segment_mean"),
            ("num_probes", "measure", "Number of probes", "numeric", "num_probes"),
        ],
        "sample_variant_calls": [
            (
                "allele_fraction",
                "measure",
                "Allele fraction",
                "numeric",
                "allele_fraction",
            ),
            ("genotype", "attribute", "Genotype", "string", "genotype"),
            ("filter", "attribute", "Filter", "string", "filter"),
        ],
        "sample_structural_variant_calls": [
            ("call_status", "attribute", "Call status", "string", "call_status"),
            (
                "split_read_count",
                "measure",
                "Split read count",
                "numeric",
                "split_read_count",
            ),
            (
                "paired_end_read_count",
                "measure",
                "Paired-end read count",
                "numeric",
                "paired_end_read_count",
            ),
        ],
        "result_payloads": [
            ("payload_kind", "attribute", "Payload kind", "string", "payload_kind"),
            ("payload_name", "attribute", "Payload name", "string", "payload_name"),
            ("schema_json", "attribute", "Payload schema", "json", "schema_json"),
            (
                "source_observation_id",
                "attribute",
                "Source observation",
                "string",
                "source_observation_id",
            ),
            (
                "source_observation_label",
                "attribute",
                "Source observation label",
                "string",
                "source_observation_label",
            ),
        ],
    }.get(table or "", [])
    return [
        DataContractFieldRead(
            field_id=field_id,
            field_role=field_role,
            entity_scope=contract.entity_grain,
            display_name=display_name,
            value_type=value_type,
            unit=contract.unit if value_type == "numeric" else None,
            direction=None,
            description=contract.description,
            priority=None,
            primary_table=table,
            physical_tables={"tables": [table]} if table else {},
            query_ref={
                "table": table,
                "value_column": value_column,
                "synthetic": True,
            },
            summary=dict(contract.summary_json),
            metadata_json={"synthetic": True},
        )
        for field_id, field_role, display_name, value_type, value_column in fields
    ]


def _data_contract_field_read(field: DataContractFieldRecord) -> DataContractFieldRead:
    """Convert a data contract field definition into its API response model."""

    return DataContractFieldRead(
        field_id=field.field_id,
        field_role=field.field_role,
        entity_scope=field.entity_scope,
        display_name=field.display_name,
        value_type=field.value_type,
        unit=field.unit,
        direction=field.direction,
        description=field.description,
        priority=field.priority,
        primary_table=field.primary_table,
        physical_tables=dict(field.physical_tables_json),
        query_ref=dict(field.query_ref_json),
        summary=dict(field.summary_json),
        metadata_json=dict(field.metadata_json),
    )


def _default_field_table_for_contract(contract: DataContractRecord) -> str | None:
    return {
        "entity_attributes": "entity_attributes",
        "feature_matrix": "feature_value_numeric",
        "feature_calls": "feature_call",
        "copy_number_segments": "copy_number_segments",
        "small_variants": "sample_variant_calls",
        "structural_variants": "sample_structural_variant_calls",
        "result_payload": "result_payloads",
    }.get(contract.data_type)


async def _file_from_rows_public(
    session: AsyncSession,
    file: FileRecord,
    link: FileLinkRecord | None = None,
    *,
    association_scope: str = "direct_run",
    association_reason: str | None = None,
) -> FileRead:
    """Convert a file/link pair using public labels instead of SQL IDs."""

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
    data_contract_id = await _public_label(
        session, DataContractRecord, "data_contract_id", link.data_contract_id
    )
    # source_path is parser/ingest provenance stored inside metadata_json; keep
    # it as a first-class response field because the dashboard displays it often.
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
        data_contract_id=data_contract_id,
        association_scope=association_scope,
        association_reason=association_reason,
        kind=file.file_role,
        path=file.path,
        uri=file.uri,
        storage_location=file.storage_location,
        object_key=file.object_key,
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
    """Resolve an internal integer foreign key to a public string label."""

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
    """Convert file/link rows without resolving foreign keys to public labels."""

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
        data_contract_id=(
            str(link.data_contract_id)
            if link is not None and link.data_contract_id is not None
            else None
        ),
        association_scope=association_scope,
        association_reason=association_reason,
        kind=file.file_role,
        path=file.path,
        uri=file.uri,
        storage_location=file.storage_location,
        object_key=file.object_key,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        source_path=source_path if isinstance(source_path, str) else None,
        created_at=file.created_at,
    )


def _dedupe_file_reads(files: list[FileRead]) -> list[FileRead]:
    """Keep one file response per file ID, preferring the strongest link."""

    by_file_id: dict[str, FileRead] = {}
    for file in files:
        existing = by_file_id.get(file.file_id)
        if existing is None or _file_read_rank(file) > _file_read_rank(existing):
            by_file_id[file.file_id] = file
    return sorted(by_file_id.values(), key=lambda item: item.file_id)


def _file_read_rank(file: FileRead) -> tuple[int, int]:
    """Rank file associations so direct/contract-aware links win deduping."""

    scope_rank = {"direct_run": 3, "direct_sample": 3, "data_import": 2}.get(
        file.association_scope,
        1,
    )
    contract_rank = 1 if file.data_contract_id is not None else 0
    return scope_rank, contract_rank


def _model_field_name(model: type[SQLModel], requested_name: str) -> str:
    """Map API-facing aliases to SQLModel field names."""

    if requested_name in model.model_fields:
        return requested_name
    if requested_name == "metadata" and "metadata_json" in model.model_fields:
        return "metadata_json"
    return requested_name


def _coerce_primary_key_value(
    model: type[SQLModel], primary_key: str, value: str
) -> Any:
    """Coerce route path row IDs to the model primary-key type."""

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
    """Return the SQLite database file size when the URL points at a file."""

    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return 0
    path_value = database_url.removeprefix(prefix)
    if path_value == ":memory:":
        return 0
    path = Path(path_value)
    return path.stat().st_size if path.exists() else 0


def _path_size(path: Path) -> int:
    """Return recursive file size for a file or directory path."""

    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
