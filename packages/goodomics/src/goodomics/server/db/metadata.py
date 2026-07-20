"""Shared registry for SQL metadata tables exposed by the server.

The SQLModel record classes are defined in the storage and server model modules.
This module describes how the server is allowed to expose those records to API
routes and insight/report query builders. Keeping the policy here avoids each
caller maintaining a separate table-name mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import SQLModel

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
    QCDecisionRecord,
    RunContractRecord,
    RunContractSampleRecord,
    RunRecord,
    RunRelationshipRecord,
    RunSampleRecord,
    SampleGroupMemberRecord,
    SampleGroupRecord,
    SampleRecord,
    SubjectRecord,
)


@dataclass(frozen=True)
class MetadataTable:
    """Server exposure policy for one SQL metadata table."""

    model: type[SQLModel]
    row_id_field: str
    queryable: bool = False
    editable_fields: frozenset[str] = field(default_factory=frozenset)


def _table_name(model: type[SQLModel]) -> str:
    table_name = getattr(model, "__tablename__", None)
    if not isinstance(table_name, str):
        raise RuntimeError(f"Metadata model has no __tablename__: {model!r}")
    return table_name


def _editable(*fields: str) -> frozenset[str]:
    return frozenset(fields)


# The registry is explicit about which SQLModel classes the server exposes, but
# derives table-name keys from each model to avoid string/model drift.
METADATA_TABLE_REGISTRY: dict[str, MetadataTable] = {
    _table_name(entry.model): entry
    for entry in (
        MetadataTable(
            ProjectRecord,
            "project_id",
            queryable=True,
            editable_fields=_editable(
                "name",
                "slug",
                "description",
                "default_report_id",
                "metadata_json",
            ),
        ),
        MetadataTable(SubjectRecord, "subject_id", queryable=True),
        MetadataTable(
            SampleRecord,
            "sample_id",
            queryable=True,
            editable_fields=_editable("sample_name", "metadata_json"),
        ),
        MetadataTable(
            RunRecord,
            "run_id",
            queryable=True,
            editable_fields=_editable("project", "method_version", "status"),
        ),
        MetadataTable(AnalysisTypeRecord, "analysis_type_id", queryable=True),
        MetadataTable(AnalysisMethodRecord, "method_id", queryable=True),
        MetadataTable(RunSampleRecord, "run_sample_id", queryable=True),
        MetadataTable(RunRelationshipRecord, "id", queryable=True),
        MetadataTable(DataImportRecord, "data_import_id", queryable=True),
        MetadataTable(DataContractRecord, "data_contract_id", queryable=True),
        MetadataTable(DataContractAnalysisTypeRecord, "id", queryable=True),
        MetadataTable(RunContractRecord, "run_contract_id", queryable=True),
        MetadataTable(RunContractSampleRecord, "id", queryable=True),
        MetadataTable(DataContractFieldRecord, "id", queryable=True),
        MetadataTable(
            FileRecord,
            "file_id",
            queryable=True,
            editable_fields=_editable("file_role", "path", "uri", "metadata_json"),
        ),
        MetadataTable(FileLinkRecord, "id", queryable=True),
        MetadataTable(SampleGroupRecord, "sample_group_id", queryable=True),
        MetadataTable(SampleGroupMemberRecord, "id", queryable=True),
        MetadataTable(QCDecisionRecord, "id", queryable=True),
        MetadataTable(
            InsightRecord,
            "insight_id",
            queryable=True,
            editable_fields=_editable("name", "description", "config"),
        ),
        MetadataTable(InsightRevisionRecord, "id"),
        MetadataTable(
            ReportRecord,
            "report_id",
            queryable=True,
            editable_fields=_editable("name", "description", "config"),
        ),
        MetadataTable(ReportRevisionRecord, "id"),
        MetadataTable(
            RenderedReportRecord,
            "rendered_report_id",
            editable_fields=_editable("title"),
        ),
        MetadataTable(InsightResultCacheRecord, "cache_id"),
        MetadataTable(ReportResultCacheRecord, "cache_id"),
        MetadataTable(
            QCPolicyRecord,
            "policy_id",
            editable_fields=_editable("name", "thresholds"),
        ),
    )
}

# API routes use the broad metadata table set for browsing database contents.
METADATA_TABLES: dict[str, tuple[type[SQLModel], str]] = {
    name: (entry.model, entry.row_id_field)
    for name, entry in METADATA_TABLE_REGISTRY.items()
}

# Insight/report builder queries use a narrower allowlist so internal cache and
# revision tables are not exposed as normal analytical sources.
METADATA_MODELS: dict[str, type[SQLModel]] = {
    name: entry.model
    for name, entry in METADATA_TABLE_REGISTRY.items()
    if entry.queryable
}

EDITABLE_TABLES: dict[str, tuple[type[SQLModel], str, set[str]]] = {
    name: (entry.model, entry.row_id_field, set(entry.editable_fields))
    for name, entry in METADATA_TABLE_REGISTRY.items()
    if entry.editable_fields
}
