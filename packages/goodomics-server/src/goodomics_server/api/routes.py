from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import yaml
from fastapi import APIRouter, HTTPException, Request, Response
from goodomics.report.html import render_report
from goodomics.schemas.models import Metric, Run, Sample
from goodomics.storage.sqlalchemy import (
    artifacts_table,
    metadata,
    metrics_table,
    runs_table,
    samples_table,
)
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select, update
from sqlalchemy.sql.schema import Column, Table

from goodomics_server.db.models import (
    cohorts_table,
    qc_policies_table,
    report_template_revisions_table,
    report_templates_table,
    reports_table,
)

router = APIRouter(prefix="/api/v1")
JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class RunCreate(BaseModel):
    run_id: str | None = None
    project: str | None = None
    assay: str | None = None
    samples: list[Sample] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)


class RunPatch(BaseModel):
    project: str | None = None
    assay: str | None = None


class ArtifactRead(BaseModel):
    id: int
    run_id: str
    path: str


class ReportTemplateBase(BaseModel):
    name: str
    description: str | None = None
    config: dict[str, JsonValue] = Field(default_factory=dict)


class ReportTemplateCreate(ReportTemplateBase):
    template_id: str | None = None


class ReportTemplatePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, JsonValue] | None = None


class ReportTemplateRead(ReportTemplateBase):
    template_id: str
    created_at: datetime
    updated_at: datetime


class ReportRenderRequest(BaseModel):
    results: str = "."
    report_id: str | None = None
    run_id: str | None = None
    template_id: str | None = None
    title: str = "Goodomics Report"


class ReportRead(BaseModel):
    report_id: str
    run_id: str | None = None
    template_id: str | None = None
    title: str
    html: str
    created_at: datetime


class CohortCreate(BaseModel):
    cohort_id: str | None = None
    name: str
    description: str | None = None
    filters: dict[str, JsonValue] = Field(default_factory=dict)


class CohortPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    filters: dict[str, JsonValue] | None = None


class CohortRead(BaseModel):
    cohort_id: str
    name: str
    description: str | None = None
    filters: dict[str, JsonValue]
    updated_at: datetime


class QCPolicyCreate(BaseModel):
    policy_id: str | None = None
    name: str
    thresholds: dict[str, JsonValue] = Field(default_factory=dict)


class QCPolicyPatch(BaseModel):
    name: str | None = None
    thresholds: dict[str, JsonValue] | None = None


class QCPolicyRead(BaseModel):
    policy_id: str
    name: str
    thresholds: dict[str, JsonValue]
    updated_at: datetime


class DatabaseTableRead(BaseModel):
    name: str
    editable: bool


class DatabaseRowPatch(BaseModel):
    values: dict[str, JsonValue]
    audit_note: str | None = None


EDITABLE_TABLES: dict[str, tuple[Table, str, set[str]]] = {
    "runs": (runs_table, "run_id", {"project", "assay"}),
    "samples": (samples_table, "id", {"sample_id", "metadata"}),
    "metrics": (metrics_table, "id", {"sample_id", "name", "value", "unit"}),
    "artifacts": (artifacts_table, "id", {"path"}),
    "report_templates": (
        report_templates_table,
        "template_id",
        {"name", "description", "config"},
    ),
    "reports": (reports_table, "report_id", {"title"}),
    "cohorts": (cohorts_table, "cohort_id", {"name", "description", "filters"}),
    "qc_policies": (qc_policies_table, "policy_id", {"name", "thresholds"}),
}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/runs", response_model=list[Run])
async def list_runs(request: Request) -> list[Run]:
    await _ensure_schema(request)
    async with _engine(request).connect() as connection:
        rows = (await connection.execute(select(runs_table))).mappings().all()
    return [
        Run(
            run_id=str(row["run_id"]),
            project=_optional_str(row, "project"),
            assay=_optional_str(row, "assay"),
            created_at=row["created_at"],
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
        async with _engine(request).begin() as connection:
            result = await connection.execute(
                update(runs_table).where(runs_table.c.run_id == run_id).values(**values)
            )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Run not found")
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
    async with _engine(request).connect() as connection:
        rows = (
            await connection.execute(
                select(artifacts_table).where(artifacts_table.c.run_id == run_id)
            )
        ).mappings().all()
    return [ArtifactRead.model_validate(dict(row)) for row in rows]


@router.get("/report-templates", response_model=list[ReportTemplateRead])
async def list_report_templates(request: Request) -> list[ReportTemplateRead]:
    await _ensure_schema(request)
    async with _engine(request).connect() as connection:
        rows = (await connection.execute(select(report_templates_table))).mappings().all()
    return [_template_from_row(row) for row in rows]


@router.post("/report-templates", response_model=ReportTemplateRead, status_code=201)
async def create_report_template(
    payload: ReportTemplateCreate, request: Request
) -> ReportTemplateRead:
    await _ensure_schema(request)
    now = datetime.now(UTC)
    template_id = payload.template_id or _new_id("template")
    values = payload.model_dump(exclude={"template_id"}) | {
        "template_id": template_id,
        "created_at": now,
        "updated_at": now,
    }
    async with _engine(request).begin() as connection:
        await connection.execute(insert(report_templates_table).values(**values))
        await connection.execute(
            insert(report_template_revisions_table).values(
                template_id=template_id,
                config=payload.config,
                created_at=now,
            )
        )
    return await get_report_template(template_id, request)


@router.get("/report-templates/{template_id}", response_model=ReportTemplateRead)
async def get_report_template(template_id: str, request: Request) -> ReportTemplateRead:
    await _ensure_schema(request)
    async with _engine(request).connect() as connection:
        row = (
            await connection.execute(
                select(report_templates_table).where(
                    report_templates_table.c.template_id == template_id
                )
            )
        ).mappings().first()
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
        values["updated_at"] = datetime.now(UTC)
        async with _engine(request).begin() as connection:
            result = await connection.execute(
                update(report_templates_table)
                .where(report_templates_table.c.template_id == template_id)
                .values(**values)
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Report template not found")
            if "config" in values:
                await connection.execute(
                    insert(report_template_revisions_table).values(
                        template_id=template_id,
                        config=values["config"],
                        created_at=values["updated_at"],
                    )
                )
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
    values = {
        "report_id": report_id,
        "run_id": payload.run_id,
        "template_id": payload.template_id,
        "title": payload.title,
        "html": html,
        "created_at": created_at,
    }
    async with _engine(request).begin() as connection:
        await connection.execute(
            delete(reports_table).where(reports_table.c.report_id == report_id)
        )
        await connection.execute(insert(reports_table).values(**values))
    return ReportRead(**values)


@router.get("/reports/{report_id}", response_model=ReportRead)
async def get_report(report_id: str, request: Request) -> ReportRead:
    await _ensure_schema(request)
    async with _engine(request).connect() as connection:
        row = (
            await connection.execute(
                select(reports_table).where(reports_table.c.report_id == report_id)
            )
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportRead.model_validate(dict(row))


@router.get("/reports/{report_id}/export.html")
async def export_report_html(report_id: str, request: Request) -> Response:
    report = await get_report(report_id, request)
    return Response(content=report.html, media_type="text/html")


@router.get("/cohorts", response_model=list[CohortRead])
async def list_cohorts(request: Request) -> list[CohortRead]:
    rows = await _list_table(request, cohorts_table)
    return [CohortRead.model_validate(dict(row)) for row in rows]


@router.post("/cohorts", response_model=CohortRead, status_code=201)
async def create_cohort(payload: CohortCreate, request: Request) -> CohortRead:
    now = datetime.now(UTC)
    values = payload.model_dump(exclude={"cohort_id"}) | {
        "cohort_id": payload.cohort_id or _new_id("cohort"),
        "updated_at": now,
    }
    await _insert_values(request, cohorts_table, values)
    return CohortRead(**values)


@router.patch("/cohorts/{cohort_id}", response_model=CohortRead)
async def patch_cohort(cohort_id: str, payload: CohortPatch, request: Request) -> CohortRead:
    values = payload.model_dump(exclude_unset=True) | {"updated_at": datetime.now(UTC)}
    await _patch_values(request, cohorts_table, cohorts_table.c.cohort_id, cohort_id, values)
    row = await _get_row(request, cohorts_table, cohorts_table.c.cohort_id, cohort_id)
    return CohortRead.model_validate(dict(row))


@router.get("/qc-policies", response_model=list[QCPolicyRead])
async def list_qc_policies(request: Request) -> list[QCPolicyRead]:
    rows = await _list_table(request, qc_policies_table)
    return [QCPolicyRead.model_validate(dict(row)) for row in rows]


@router.post("/qc-policies", response_model=QCPolicyRead, status_code=201)
async def create_qc_policy(payload: QCPolicyCreate, request: Request) -> QCPolicyRead:
    now = datetime.now(UTC)
    values = payload.model_dump(exclude={"policy_id"}) | {
        "policy_id": payload.policy_id or _new_id("policy"),
        "updated_at": now,
    }
    await _insert_values(request, qc_policies_table, values)
    return QCPolicyRead(**values)


@router.patch("/qc-policies/{policy_id}", response_model=QCPolicyRead)
async def patch_qc_policy(
    policy_id: str, payload: QCPolicyPatch, request: Request
) -> QCPolicyRead:
    values = payload.model_dump(exclude_unset=True) | {"updated_at": datetime.now(UTC)}
    await _patch_values(
        request, qc_policies_table, qc_policies_table.c.policy_id, policy_id, values
    )
    row = await _get_row(request, qc_policies_table, qc_policies_table.c.policy_id, policy_id)
    return QCPolicyRead.model_validate(dict(row))


@router.get("/database/tables", response_model=list[DatabaseTableRead])
async def list_database_tables() -> list[DatabaseTableRead]:
    return [DatabaseTableRead(name=name, editable=True) for name in sorted(EDITABLE_TABLES)]


@router.get("/database/tables/{table_name}/rows")
async def list_database_rows(table_name: str, request: Request) -> list[dict[str, Any]]:
    table, _, _ = _editable_table(table_name)
    rows = await _list_table(request, table)
    return [_jsonable_row(row) for row in rows]


@router.patch("/database/tables/{table_name}/rows/{row_id}")
async def patch_database_row(
    table_name: str, row_id: str, payload: DatabaseRowPatch, request: Request
) -> dict[str, Any]:
    table, primary_key, allowed = _editable_table(table_name)
    disallowed = set(payload.values) - allowed
    if disallowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported editable columns: {', '.join(sorted(disallowed))}",
        )
    values = _coerce_json_values(payload.values)
    await _patch_values(request, table, table.c[primary_key], row_id, values)
    row = await _get_row(request, table, table.c[primary_key], row_id)
    return _jsonable_row(row)


async def _ensure_schema(request: Request) -> None:
    async with _engine(request).begin() as connection:
        await connection.run_sync(metadata.create_all)


def _engine(request: Request):
    return request.app.state.store._get_engine()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _optional_str(row: Any, key: str) -> str | None:
    value = row[key]
    return value if isinstance(value, str) else None


def _template_from_row(row: Any) -> ReportTemplateRead:
    return ReportTemplateRead.model_validate(dict(row))


def _template_export(template: ReportTemplateRead) -> dict[str, Any]:
    return {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "config": template.config,
    }


async def _list_table(request: Request, table: Table) -> list[Any]:
    await _ensure_schema(request)
    async with _engine(request).connect() as connection:
        return (await connection.execute(select(table))).mappings().all()


async def _insert_values(request: Request, table: Table, values: dict[str, Any]) -> None:
    await _ensure_schema(request)
    async with _engine(request).begin() as connection:
        await connection.execute(insert(table).values(**values))


async def _patch_values(
    request: Request, table: Table, column: Column[Any], row_id: str, values: dict[str, Any]
) -> None:
    await _ensure_schema(request)
    async with _engine(request).begin() as connection:
        result = await connection.execute(update(table).where(column == row_id).values(**values))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Row not found")


async def _get_row(request: Request, table: Table, column: Column[Any], row_id: str) -> Any:
    await _ensure_schema(request)
    async with _engine(request).connect() as connection:
        row = (await connection.execute(select(table).where(column == row_id))).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Row not found")
    return row


def _editable_table(table_name: str) -> tuple[Table, str, set[str]]:
    table_config = EDITABLE_TABLES.get(table_name)
    if table_config is None:
        raise HTTPException(status_code=404, detail="Editable table not found")
    return table_config


def _coerce_json_values(values: dict[str, JsonValue]) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    for key, value in values.items():
        if key in {"config", "filters", "thresholds", "metadata", "value"}:
            coerced[key] = json.loads(json.dumps(value))
        else:
            coerced[key] = value
    return coerced


def _jsonable_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data
