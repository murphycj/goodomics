"""Shared registry for SQL catalog tables exposed by the server.

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
    SampleRecord,
    SampleSetMemberRecord,
    SampleSetRecord,
    SubjectRecord,
)


@dataclass(frozen=True)
class CatalogTable:
    """Server exposure policy for one SQL catalog table."""

    model: type[SQLModel]
    row_id_field: str
    queryable: bool = False
    editable_fields: frozenset[str] = field(default_factory=frozenset)


def _table_name(model: type[SQLModel]) -> str:
    table_name = getattr(model, "__tablename__", None)
    if not isinstance(table_name, str):
        raise RuntimeError(f"Catalog model has no __tablename__: {model!r}")
    return table_name


def _editable(*fields: str) -> frozenset[str]:
    return frozenset(fields)


# The registry is explicit about which SQLModel classes the server exposes, but
# derives table-name keys from each model to avoid string/model drift.
CATALOG_TABLE_REGISTRY: dict[str, CatalogTable] = {
    _table_name(entry.model): entry
    for entry in (
        CatalogTable(
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
        CatalogTable(SubjectRecord, "subject_id", queryable=True),
        CatalogTable(
            SampleRecord,
            "sample_id",
            queryable=True,
            editable_fields=_editable("sample_name", "metadata_json"),
        ),
        CatalogTable(
            RunRecord,
            "run_id",
            queryable=True,
            editable_fields=_editable("project", "method_version", "status"),
        ),
        CatalogTable(AnalysisTypeRecord, "analysis_type_id", queryable=True),
        CatalogTable(AnalysisMethodRecord, "method_id", queryable=True),
        CatalogTable(RunSampleRecord, "run_sample_id", queryable=True),
        CatalogTable(RunRelationshipRecord, "id", queryable=True),
        CatalogTable(DataImportRecord, "data_import_id", queryable=True),
        CatalogTable(DataContractRecord, "data_contract_id", queryable=True),
        CatalogTable(DataContractAnalysisTypeRecord, "id", queryable=True),
        CatalogTable(RunContractRecord, "run_contract_id", queryable=True),
        CatalogTable(RunContractSampleRecord, "id", queryable=True),
        CatalogTable(DataContractFieldRecord, "id", queryable=True),
        CatalogTable(
            FileRecord,
            "file_id",
            queryable=True,
            editable_fields=_editable("file_role", "path", "uri", "metadata_json"),
        ),
        CatalogTable(FileLinkRecord, "id", queryable=True),
        CatalogTable(SampleSetRecord, "sample_set_id", queryable=True),
        CatalogTable(SampleSetMemberRecord, "id", queryable=True),
        CatalogTable(QCDecisionRecord, "id", queryable=True),
        CatalogTable(
            InsightRecord,
            "insight_id",
            queryable=True,
            editable_fields=_editable("name", "description", "config"),
        ),
        CatalogTable(InsightRevisionRecord, "id"),
        CatalogTable(
            ReportRecord,
            "report_id",
            queryable=True,
            editable_fields=_editable("name", "description", "config"),
        ),
        CatalogTable(ReportRevisionRecord, "id"),
        CatalogTable(
            RenderedReportRecord,
            "rendered_report_id",
            editable_fields=_editable("title"),
        ),
        CatalogTable(InsightResultCacheRecord, "cache_id"),
        CatalogTable(ReportResultCacheRecord, "cache_id"),
        CatalogTable(
            QCPolicyRecord,
            "policy_id",
            editable_fields=_editable("name", "thresholds"),
        ),
    )
}

# API routes use the broad catalog table set for browsing database contents.
CATALOG_TABLES: dict[str, tuple[type[SQLModel], str]] = {
    name: (entry.model, entry.row_id_field)
    for name, entry in CATALOG_TABLE_REGISTRY.items()
}

# Insight/report builder queries use a narrower allowlist so internal cache and
# revision tables are not exposed as normal analytical sources.
CATALOG_MODELS: dict[str, type[SQLModel]] = {
    name: entry.model
    for name, entry in CATALOG_TABLE_REGISTRY.items()
    if entry.queryable
}

EDITABLE_TABLES: dict[str, tuple[type[SQLModel], str, set[str]]] = {
    name: (entry.model, entry.row_id_field, set(entry.editable_fields))
    for name, entry in CATALOG_TABLE_REGISTRY.items()
    if entry.editable_fields
}
