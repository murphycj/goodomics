"""Catalog identifier resolution helpers for analytics ingest record batches."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from goodomics.schemas.models import AnalyticsIngestBatch

CATALOG_COLUMNS_BY_BATCH_FIELD: dict[str, frozenset[str]] = {
    "entity_attributes": frozenset({"data_profile_id", "field_id"}),
    "sample_metrics": frozenset(
        {"data_profile_id", "run_id", "run_sample_id", "sample_id", "field_id"}
    ),
    "feature_value_numeric": frozenset(
        {"data_profile_id", "run_id", "run_sample_id", "sample_id"}
    ),
    "feature_call": frozenset(
        {"data_profile_id", "run_id", "run_sample_id", "sample_id"}
    ),
    "sample_interval_values": frozenset(
        {"data_profile_id", "run_id", "run_sample_id", "sample_id"}
    ),
    "copy_number_segments": frozenset(
        {"data_profile_id", "run_id", "run_sample_id", "sample_id"}
    ),
    "variant_annotations": frozenset({"data_profile_id"}),
    "variant_transcript_annotations": frozenset({"data_profile_id"}),
    "sample_variant_calls": frozenset(
        {"data_profile_id", "run_id", "run_sample_id", "sample_id"}
    ),
    "sample_structural_variant_calls": frozenset(
        {"data_profile_id", "run_id", "run_sample_id", "sample_id"}
    ),
    "timeline_events": frozenset({"subject_id", "sample_id", "run_sample_id"}),
    "profile_payloads": frozenset({"data_profile_id", "run_id", "run_sample_id"}),
    "gene_alteration_state": frozenset(
        {"run_sample_id", "sample_id", "subject_id", "data_profile_id"}
    ),
    "cohort_summaries": frozenset({"sample_set_id", "data_profile_id"}),
    "tool_versions": frozenset({"run_id"}),
    "data_sources": frozenset({"run_id", "run_sample_id", "sample_id"}),
}


def resolve_analytics_batch_catalog_ids(
    batch: AnalyticsIngestBatch,
    catalog_id_maps: Mapping[str, Mapping[Any, int]],
) -> AnalyticsIngestBatch:
    """Return a storage-ready batch with SQL-owned labels replaced by int IDs."""

    values = batch.model_dump()
    for field_name, columns in CATALOG_COLUMNS_BY_BATCH_FIELD.items():
        records = getattr(batch, field_name)
        values[field_name] = [
            _resolve_record_catalog_ids(record, columns, catalog_id_maps)
            for record in records
        ]
    return AnalyticsIngestBatch.model_validate(values)


def resolve_catalog_id(
    column: str,
    value: Any,
    catalog_id_maps: Mapping[str, Mapping[Any, int]],
) -> int | None:
    """Resolve a catalog identifier from label form to SQL integer id."""

    if value is None or isinstance(value, int):
        return value
    column_map = catalog_id_maps.get(column, {})
    identifier = column_map.get(value)
    if identifier is None:
        identifier = column_map.get(str(value))
    if identifier is None:
        raise ValueError(
            f"No SQL catalog integer id found for {column}={value!r}. "
            "Resolve catalog IDs before writing analytics rows to DuckDB."
        )
    return int(identifier)


def _resolve_record_catalog_ids(
    record: Any,
    columns: frozenset[str],
    catalog_id_maps: Mapping[str, Mapping[Any, int]],
) -> Any:
    updates: dict[str, int | None] = {}
    for column in columns:
        value = _record_value(record, column)
        if value is not None and not isinstance(value, int):
            updates[column] = resolve_catalog_id(column, value, catalog_id_maps)
    if not updates:
        return record
    if isinstance(record, BaseModel):
        return record.model_copy(update=updates)
    if isinstance(record, Mapping):
        return dict(record) | updates
    for key, value in updates.items():
        setattr(record, key, value)
    return record


def _record_value(record: Any, column: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(column)
    if isinstance(record, BaseModel):
        extra = record.model_extra or {}
        if column in extra:
            return extra[column]
        if column in type(record).model_fields:
            return getattr(record, column)
        return None
    return getattr(record, column, None)
