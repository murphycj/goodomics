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
    "insights",
    "insight_revisions",
    "reports",
    "report_revisions",
    "rendered_reports",
    "insight_result_cache",
    "report_result_cache",
    "cohorts",
    "qc_policies",
)


class InsightRecord(SQLModel, table=True):
    __tablename__ = "insights"

    insight_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    name: str = Field(max_length=255)
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime
    updated_at: datetime


class InsightRevisionRecord(SQLModel, table=True):
    __tablename__ = "insight_revisions"

    id: int | None = Field(default=None, primary_key=True)
    insight_id: str = Field(foreign_key="insights.insight_id", max_length=255)
    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class ReportRecord(SQLModel, table=True):
    __tablename__ = "reports"

    report_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    name: str = Field(max_length=255)
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime
    updated_at: datetime


class ReportRevisionRecord(SQLModel, table=True):
    __tablename__ = "report_revisions"

    id: int | None = Field(default=None, primary_key=True)
    report_id: str = Field(foreign_key="reports.report_id", max_length=255)
    config: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class RenderedReportRecord(SQLModel, table=True):
    __tablename__ = "rendered_reports"

    rendered_report_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    run_id: str | None = Field(default=None, max_length=255)
    report_id: str | None = Field(default=None, max_length=255, index=True)
    title: str = Field(max_length=255)
    html: str
    created_at: datetime


class InsightResultCacheRecord(SQLModel, table=True):
    __tablename__ = "insight_result_cache"

    cache_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    insight_id: str | None = Field(default=None, max_length=255, index=True)
    spec_hash: str = Field(max_length=64, index=True)
    source_fingerprint: str = Field(max_length=64, index=True)
    result: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class ReportResultCacheRecord(SQLModel, table=True):
    __tablename__ = "report_result_cache"

    cache_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    report_id: str | None = Field(default=None, max_length=255, index=True)
    spec_hash: str = Field(max_length=64, index=True)
    source_fingerprint: str = Field(max_length=64, index=True)
    result: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
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
        InsightRecord,
        InsightRevisionRecord,
        ReportRecord,
        ReportRevisionRecord,
        RenderedReportRecord,
        InsightResultCacheRecord,
        ReportResultCacheRecord,
        CohortRecord,
        QCPolicyRecord,
    )
}

server_metadata = SQLModel.metadata
