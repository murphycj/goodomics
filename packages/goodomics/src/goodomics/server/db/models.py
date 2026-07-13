# pyright: reportAssignmentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, UniqueConstraint
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
    "qc_policies",
    "users",
    "installation_state",
    "project_roles",
    "project_role_permissions",
    "project_memberships",
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
    created_by_user_id: int | None = Field(default=None, foreign_key="users.id")
    updated_by_user_id: int | None = Field(default=None, foreign_key="users.id")


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
    created_by_user_id: int | None = Field(default=None, foreign_key="users.id")
    updated_by_user_id: int | None = Field(default=None, foreign_key="users.id")


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


class QCPolicyRecord(SQLModel, table=True):
    __tablename__ = "qc_policies"

    id: int | None = Field(default=None, primary_key=True)
    policy_id: str = Field(max_length=255, unique=True, index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    name: str = Field(max_length=255)
    thresholds: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    updated_at: datetime


class UserRecord(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(max_length=64, unique=True, index=True)
    email: str = Field(max_length=320, unique=True, index=True)
    password_hash: str
    display_name: str = Field(max_length=255)
    is_active: bool = Field(default=True, index=True)
    is_admin: bool = Field(default=False, index=True)
    must_change_password: bool = False
    auth_version: int = 1
    created_at: datetime
    updated_at: datetime


class InstallationStateRecord(SQLModel, table=True):
    """Durable singleton recording that first-run administrator setup completed."""

    __tablename__ = "installation_state"

    state_key: str = Field(primary_key=True, max_length=64)
    setup_completed_at: datetime
    setup_completed_by_user_id: str = Field(max_length=64)


class ProjectRoleRecord(SQLModel, table=True):
    __tablename__ = "project_roles"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_roles_project_name"),
    )

    id: int | None = Field(default=None, primary_key=True)
    role_id: str = Field(max_length=64, unique=True, index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    name: str = Field(max_length=255)
    description: str | None = None
    is_builtin: bool = False


class ProjectRolePermissionRecord(SQLModel, table=True):
    __tablename__ = "project_role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission", name="uq_project_role_permissions_role_permission"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    role_id: int = Field(foreign_key="project_roles.id", index=True)
    permission: str = Field(max_length=128, index=True)


class ProjectMembershipRecord(SQLModel, table=True):
    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", name="uq_project_memberships_project_user"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    membership_id: str = Field(max_length=64, unique=True, index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    role_id: int = Field(foreign_key="project_roles.id", index=True)
    created_at: datetime


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
        QCPolicyRecord,
        UserRecord,
        InstallationStateRecord,
        ProjectRoleRecord,
        ProjectRolePermissionRecord,
        ProjectMembershipRecord,
    )
}

server_metadata = SQLModel.metadata
