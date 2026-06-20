from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, get_args, get_origin
from uuid import uuid4

import yaml
from fastapi import APIRouter, HTTPException, Request, Response
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


class ArtifactRead(SQLModel):
    id: int
    run_id: str
    path: str


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


class DatabaseRowPatch(SQLModel):
    values: dict[str, JsonValue]
    audit_note: str | None = None


EDITABLE_TABLES: dict[str, tuple[type[SQLModel], str, set[str]]] = {
    "runs": (RunRecord, "run_id", {"project", "assay"}),
    "samples": (SampleRecord, "id", {"sample_id", "metadata"}),
    "metrics": (MetricRecord, "id", {"sample_id", "name", "value", "unit"}),
    "artifacts": (ArtifactRecord, "id", {"path"}),
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


@router.get("/runs", response_model=list[Run])
async def list_runs(request: Request) -> list[Run]:
    await _ensure_schema(request)
    async with _session(request) as session:
        rows = (await session.exec(select(RunRecord))).all()
    return [
        Run(
            run_id=row.run_id,
            project=row.project,
            assay=row.assay,
            created_at=row.created_at,
        )
        for row in rows
    ]


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


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactRead])
async def list_run_artifacts(run_id: str, request: Request) -> list[ArtifactRead]:
    await _ensure_schema(request)
    async with _session(request) as session:
        rows = (
            await session.exec(
                select(ArtifactRecord).where(ArtifactRecord.run_id == run_id)
            )
        ).all()
    return [ArtifactRead.model_validate(row.model_dump()) for row in rows]


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
