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

from goodomics.report.html import render_report
from goodomics.schemas.models import Metric, Run, Sample
from goodomics.server.db.models import (
    CohortRecord,
    QCPolicyRecord,
    ReportRecord,
    ReportTemplateRecord,
    ReportTemplateRevisionRecord,
)
from goodomics.storage.sqlalchemy import (
    ArtifactRecord,
    MetricRecord,
    RunRecord,
    SampleRecord,
    metadata,
)

router = APIRouter(prefix="/api/v1")
JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class RunCreate(SQLModel):
    run_id: str | None = None
    project: str | None = None
    assay: str | None = None
    samples: list[Sample] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)


class RunPatch(SQLModel):
    project: str | None = None
    assay: str | None = None


class RunPageRead(SQLModel):
    items: list[Run]
    total: int
    limit: int
    offset: int


class FileRead(SQLModel):
    id: int
    file_id: str | None = None
    run_id: str
    kind: str = "file"
    path: str
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


EDITABLE_TABLES: dict[str, tuple[type[SQLModel], str, set[str]]] = {
    "runs": (RunRecord, "run_id", {"project", "assay"}),
    "samples": (SampleRecord, "sample_id", {"sample_name", "metadata_json"}),
    "metrics": (MetricRecord, "id", {"sample_id", "name", "value", "unit"}),
    "files": (ArtifactRecord, "id", {"kind", "path", "source_path"}),
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


@router.get("/runs", response_model=RunPageRead)
async def list_runs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RunPageRead:
    await _ensure_schema(request)
    async with _session(request) as session:
        total = int((await session.exec(select(func.count()).select_from(RunRecord))).one())
        rows = (
            await session.exec(
                select(RunRecord)
                .order_by(cast(Any, RunRecord.created_at).desc(), RunRecord.run_id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    return RunPageRead(
        items=[
            Run(
                run_id=row.run_id,
                project=row.project,
                assay=row.assay,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/runs", response_model=Run, status_code=201)
async def create_run(payload: RunCreate, request: Request) -> Run:
    run = Run(
        run_id=payload.run_id or _new_id("run"),
        project=payload.project,
        assay=payload.assay,
        samples=payload.samples,
        metrics=payload.metrics,
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


@router.get("/runs/{run_id}/metrics", response_model=list[Metric])
async def list_run_metrics(run_id: str, request: Request) -> list[Metric]:
    return await request.app.state.store.list_metrics(run_id)


@router.get("/runs/{run_id}/files", response_model=list[FileRead])
async def list_run_files(run_id: str, request: Request) -> list[FileRead]:
    await _ensure_schema(request)
    async with _session(request) as session:
        rows = (
            await session.exec(select(ArtifactRecord).where(ArtifactRecord.run_id == run_id))
        ).all()
    return [_file_from_artifact(row) for row in rows]


@router.get(
    "/runs/{run_id}/analytics/metrics",
    response_model=list[AnalyticsMetricRead],
)
async def list_run_analytics_metrics(run_id: str, request: Request) -> list[AnalyticsMetricRead]:
    await get_run(run_id, request)
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
        for metric in request.app.state.analytics_store.list_metric_values(run_id)
    ]


@router.get(
    "/runs/{run_id}/analytics/payloads",
    response_model=list[AnalyticsPayloadRead],
)
async def list_run_analytics_payloads(run_id: str, request: Request) -> list[AnalyticsPayloadRead]:
    await get_run(run_id, request)
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
        for payload in request.app.state.analytics_store.list_profile_payloads(run_id)
    ]


@router.get("/files/{file_id}/content")
async def get_file_content(file_id: str, request: Request) -> FileResponse:
    return await _file_content_response(file_id, request)


async def _file_content_response(file_id: str, request: Request) -> FileResponse:
    await _ensure_schema(request)
    async with _session(request) as session:
        row = (
            await session.exec(
                select(ArtifactRecord).where(ArtifactRecord.artifact_id == file_id)
            )
        ).first()
        if row is None and file_id.isdigit():
            row = await session.get(ArtifactRecord, int(file_id))
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")
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
async def export_report_template_json(template_id: str, request: Request) -> dict[str, Any]:
    template = await get_report_template(template_id, request)
    return _template_export(template)


@router.post("/reports/render", response_model=ReportRead, status_code=201)
async def render_standalone_report(payload: ReportRenderRequest, request: Request) -> ReportRead:
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
async def patch_cohort(cohort_id: str, payload: CohortPatch, request: Request) -> CohortRead:
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
async def patch_qc_policy(policy_id: str, payload: QCPolicyPatch, request: Request) -> QCPolicyRead:
    values = payload.model_dump(exclude_unset=True) | {"updated_at": datetime.now(UTC)}
    await _patch_values(request, QCPolicyRecord, "policy_id", policy_id, values)
    row = await _get_row(request, QCPolicyRecord, "policy_id", policy_id)
    return QCPolicyRead.model_validate(row.model_dump())


@router.get("/database/tables", response_model=list[DatabaseTableRead])
async def list_database_tables() -> list[DatabaseTableRead]:
    return [DatabaseTableRead(name=name, editable=True) for name in sorted(EDITABLE_TABLES)]


@router.get("/database/summary", response_model=DatabaseSummaryRead)
async def get_database_summary(request: Request) -> DatabaseSummaryRead:
    control_counts = await _control_table_counts(request)
    analytics_counts = request.app.state.analytics_store.row_counts()
    return DatabaseSummaryRead(
        sqlite_size_bytes=_sqlite_size_bytes(request.app.state.settings.database_url),
        duckdb_size_bytes=request.app.state.analytics_store.database_size_bytes(),
        file_size_bytes=_path_size(Path(request.app.state.settings.artifact_root)),
        total_runs=control_counts.get("runs", 0),
        total_samples=control_counts.get("samples", 0),
        total_scalar_metrics=analytics_counts.get("sample_metric_numeric", 0)
        + analytics_counts.get("sample_metric_string", 0),
        total_payloads=analytics_counts.get("profile_payloads", 0),
        control_tables=[
            TableCountRead(name=name, rows=count) for name, count in sorted(control_counts.items())
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
    async with _engine(request).begin() as connection:
        await connection.run_sync(metadata.create_all)


def _engine(request: Request):
    return request.app.state.store._get_engine()


def _session(request: Request) -> AsyncSession:
    return AsyncSession(_engine(request))


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


async def _control_table_counts(request: Request) -> dict[str, int]:
    await _ensure_schema(request)
    async with _session(request) as session:
        return {
            name: int(
                (
                    await session.exec(
                        select(func.count()).select_from(model)  # type: ignore[arg-type]
                    )
                ).one()
            )
            for name, (model, _, _) in EDITABLE_TABLES.items()
        }


async def _insert_values(request: Request, model: type[SQLModel], values: dict[str, Any]) -> None:
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
            await session.exec(select(model).where(getattr(model, primary_key) == key_value))
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


def _coerce_json_values(model: type[SQLModel], values: dict[str, JsonValue]) -> dict[str, Any]:
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
    if isinstance(row, ArtifactRecord) and "artifact_id" in data:
        data["file_id"] = data.pop("artifact_id")
    return data


def _file_from_artifact(row: ArtifactRecord) -> FileRead:
    data = row.model_dump()
    data["file_id"] = data.pop("artifact_id", None)
    return FileRead.model_validate(data)


def _model_field_name(model: type[SQLModel], requested_name: str) -> str:
    if requested_name in model.model_fields:
        return requested_name
    if requested_name == "metadata" and "metadata_json" in model.model_fields:
        return "metadata_json"
    return requested_name


def _coerce_primary_key_value(model: type[SQLModel], primary_key: str, value: str) -> Any:
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
