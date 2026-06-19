from __future__ import annotations

from goodomics.storage.sqlalchemy import metadata
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, MetaData, String, Table, Text
from sqlalchemy.sql.schema import Column

INITIAL_TABLES = (
    "runs",
    "samples",
    "metrics",
    "artifacts",
    "qc_decisions",
    "report_templates",
    "report_template_revisions",
    "reports",
    "cohorts",
    "qc_policies",
)

report_templates_table = Table(
    "report_templates",
    metadata,
    Column("template_id", String(length=255), primary_key=True),
    Column("name", String(length=255), nullable=False),
    Column("description", Text, nullable=True),
    Column("config", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

report_template_revisions_table = Table(
    "report_template_revisions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "template_id",
        ForeignKey("report_templates.template_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("config", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

reports_table = Table(
    "reports",
    metadata,
    Column("report_id", String(length=255), primary_key=True),
    Column("run_id", String(length=255), nullable=True),
    Column("template_id", String(length=255), nullable=True),
    Column("title", String(length=255), nullable=False),
    Column("html", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

cohorts_table = Table(
    "cohorts",
    metadata,
    Column("cohort_id", String(length=255), primary_key=True),
    Column("name", String(length=255), nullable=False),
    Column("description", Text, nullable=True),
    Column("filters", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

qc_policies_table = Table(
    "qc_policies",
    metadata,
    Column("policy_id", String(length=255), primary_key=True),
    Column("name", String(length=255), nullable=False),
    Column("thresholds", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

SERVER_TABLES: dict[str, Table] = {
    table.name: table
    for table in (
        report_templates_table,
        report_template_revisions_table,
        reports_table,
        cohorts_table,
        qc_policies_table,
    )
}

# Re-export the shared metadata so server imports make the database-backed additions explicit.
server_metadata: MetaData = metadata
