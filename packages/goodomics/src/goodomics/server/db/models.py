# pyright: reportAssignmentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

INITIAL_TABLES = (
    "runs",
    "samples",
    "qc_decisions",
    "report_templates",
    "report_template_revisions",
    "reports",
    "cohorts",
    "qc_policies",
)


class ReportTemplateRecord(SQLModel, table=True):
    __tablename__ = "report_templates"

    template_id: str = Field(primary_key=True, max_length=255)
    name: str = Field(max_length=255)
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime
    updated_at: datetime


class ReportTemplateRevisionRecord(SQLModel, table=True):
    __tablename__ = "report_template_revisions"

    id: int | None = Field(default=None, primary_key=True)
    template_id: str = Field(foreign_key="report_templates.template_id", max_length=255)
    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class ReportRecord(SQLModel, table=True):
    __tablename__ = "reports"

    report_id: str = Field(primary_key=True, max_length=255)
    run_id: str | None = Field(default=None, max_length=255)
    template_id: str | None = Field(default=None, max_length=255)
    title: str = Field(max_length=255)
    html: str
    created_at: datetime


class CohortRecord(SQLModel, table=True):
    __tablename__ = "cohorts"

    cohort_id: str = Field(primary_key=True, max_length=255)
    name: str = Field(max_length=255)
    description: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    updated_at: datetime


class QCPolicyRecord(SQLModel, table=True):
    __tablename__ = "qc_policies"

    policy_id: str = Field(primary_key=True, max_length=255)
    name: str = Field(max_length=255)
    thresholds: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    updated_at: datetime


SERVER_TABLES: dict[str, Any] = {
    record.__tablename__: record.__table__
    for record in (
        ReportTemplateRecord,
        ReportTemplateRevisionRecord,
        ReportRecord,
        CohortRecord,
        QCPolicyRecord,
    )
}

server_metadata = SQLModel.metadata
