"""Lazy disposable dataset and field profiling over authoritative analytical rows."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.schemas.models import DataContract, DataContractField
from goodomics.semantic import BUILT_IN_ADAPTERS
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataContractFieldProfileRecord,
    DataContractFieldRecord,
    DataContractProfileRecord,
    DataContractRecord,
    DataShapeRecord,
    DataShapeVersionRecord,
    ProjectRecord,
)


async def ensure_minimal_profile(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project: ProjectRecord,
    contract: DataContractRecord,
) -> DataContractProfileRecord:
    """Return a current lazy profile, recomputing only after fingerprint change."""

    if project.id is None or contract.id is None:
        raise ValueError("Profiling requires persisted project and contract records.")
    shape_version = await session.get(
        DataShapeVersionRecord, contract.data_shape_version_id
    )
    if shape_version is None:
        raise ValueError("Contract shape version not found.")
    shape = await session.get(DataShapeRecord, shape_version.data_shape_id)
    if shape is None:
        raise ValueError("Contract shape not found.")
    contract_model = DataContract(
        data_contract_id=contract.data_contract_id,
        name=contract.name,
        data_shape_id=shape.data_shape_id,
        data_shape_version=shape_version.version,
        shape_bindings_json=contract.shape_bindings_json,
        search_tags=contract.search_tags_json,
        description=contract.description,
        metadata_json=contract.metadata_json,
    )
    adapter = BUILT_IN_ADAPTERS.get(shape_version.adapter_key)
    relation = adapter.relation(contract_model)
    managed = shape.data_shape_id == "records"
    if managed:
        relation_table, _ = analytics_store.managed_record_relation(
            contract_pk=contract.id
        )
    else:
        relation_table = relation.table
    analytics_store.ensure_schema()
    _, count_rows = analytics_store.query_rows(
        f"SELECT count(*) AS row_count FROM {relation_table} "
        + ("" if managed else "WHERE data_contract_id = ?"),
        parameters=[] if managed else [contract.id],
        limit=1,
    )
    row_count = int(count_rows[0]["row_count"] if count_rows else 0)
    stat = analytics_store.path.stat() if analytics_store.path.exists() else None
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "contract": contract.data_contract_id,
                "shape": [shape.data_shape_id, shape_version.version],
                "row_count": row_count,
                "store_size": stat.st_size if stat is not None else 0,
                "store_mtime_ns": stat.st_mtime_ns if stat is not None else 0,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = (
        await session.exec(
            select(DataContractProfileRecord).where(
                DataContractProfileRecord.project_id == project.id,
                DataContractProfileRecord.data_contract_id == contract.id,
            )
        )
    ).first()
    if existing is not None and existing.source_fingerprint == fingerprint:
        return existing
    identity = next(
        (
            column
            for column in relation.identity_columns
            if column in _table_columns(analytics_store, relation_table)
        ),
        None,
    )
    distinct_count: int | None = None
    if identity is not None:
        _, distinct_rows = analytics_store.query_rows(
            f"SELECT count(DISTINCT {identity}) AS n FROM {relation_table} "
            + ("" if managed else "WHERE data_contract_id = ?"),
            parameters=[] if managed else [contract.id],
            limit=1,
        )
        distinct_count = int(distinct_rows[0]["n"] if distinct_rows else 0)
    if existing is None:
        existing = DataContractProfileRecord(
            project_id=project.id,
            data_contract_id=contract.id,
            source_fingerprint=fingerprint,
            profiled_at=datetime.now(UTC),
            row_count=row_count,
            distinct_entity_count=distinct_count,
        )
    else:
        existing.source_fingerprint = fingerprint
        existing.profiled_at = datetime.now(UTC)
        existing.row_count = row_count
        existing.distinct_entity_count = distinct_count
    session.add(existing)
    await _replace_field_profiles(
        session=session,
        analytics_store=analytics_store,
        project=project,
        contract=contract,
        contract_model=contract_model,
        adapter_key=shape_version.adapter_key,
        fingerprint=fingerprint,
        managed=managed,
    )
    await session.commit()
    await session.refresh(existing)
    return existing


async def _replace_field_profiles(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project: ProjectRecord,
    contract: DataContractRecord,
    contract_model: DataContract,
    adapter_key: str,
    fingerprint: str,
    managed: bool,
) -> None:
    """Replace bounded field profiles after a dataset fingerprint changes."""

    fields = (
        await session.exec(
            select(DataContractFieldRecord).where(
                DataContractFieldRecord.data_contract_id == contract.id
            )
        )
    ).all()
    field_pks = [field.id for field in fields if field.id is not None]
    if field_pks:
        await session.exec(
            delete(DataContractFieldProfileRecord).where(
                cast(Any, DataContractFieldProfileRecord.project_id) == project.id,
                cast(Any, DataContractFieldProfileRecord.data_contract_field_id).in_(
                    field_pks
                ),
            )
        )
    adapter = BUILT_IN_ADAPTERS.get(adapter_key)
    now = datetime.now(UTC)
    profiles: list[DataContractFieldProfileRecord] = []
    for field in fields:
        if field.id is None:
            continue
        public_field = DataContractField(
            data_contract_id=contract.data_contract_id,
            field_id=field.field_id,
            display_name=field.display_name,
            purpose=cast(Any, field.purpose),
            scalar_type=cast(Any, field.scalar_type),
            semantic_type=field.semantic_type,
            unit=field.unit,
            direction=field.direction,
            description=field.description,
            priority=field.priority,
            domain_tags=field.domain_tags_json,
            metadata_json=field.metadata_json,
        )
        relation = adapter.relation(contract_model, public_field)
        if managed:
            relation_table, managed_columns = analytics_store.managed_record_relation(
                contract_pk=cast(int, contract.id), field_ids=[field.field_id]
            )
            value_column = managed_columns[field.field_id]
            predicate = "TRUE"
            parameters = []
        else:
            relation_table = relation.table
            value_column = _value_column(relation.table, field.scalar_type)
            predicate = "data_contract_id = ?"
            parameters = [contract.id]
        if not managed and relation.field_column is not None:
            predicate += f" AND {relation.field_column} = ?"
            parameters.append(field.id)
        numeric = field.scalar_type in {"numeric", "integer"}
        aggregates = (
            f", min({value_column}) AS minimum, max({value_column}) AS maximum"
            if numeric
            else ""
        )
        _, summary_rows = analytics_store.query_rows(
            f"SELECT count(*) FILTER (WHERE {value_column} IS NULL) "
            f"AS missing{aggregates} "
            f"FROM {relation_table} WHERE {predicate}",
            parameters=parameters,
            limit=1,
        )
        summary = summary_rows[0] if summary_rows else {}
        top_values: list[dict[str, Any]] = []
        distinct_count: int | None = None
        if field.scalar_type in {"string", "categorical", "boolean"}:
            _, distinct_rows = analytics_store.query_rows(
                f"SELECT count(DISTINCT {value_column}) AS count "
                f"FROM {relation_table} WHERE {predicate}",
                parameters=parameters,
                limit=1,
            )
            _, value_rows = analytics_store.query_rows(
                f"SELECT {value_column} AS value, count(*) AS count "
                f"FROM {relation_table} "
                f"WHERE {predicate} AND {value_column} IS NOT NULL "
                f"GROUP BY {value_column} ORDER BY count DESC, value LIMIT 20",
                parameters=parameters,
                limit=20,
            )
            top_values = value_rows
            distinct_count = int(distinct_rows[0]["count"] if distinct_rows else 0)
        profiles.append(
            DataContractFieldProfileRecord(
                project_id=cast(int, project.id),
                data_contract_field_id=field.id,
                source_fingerprint=fingerprint,
                profiled_at=now,
                missing_value_count=int(summary.get("missing") or 0),
                numeric_minimum=summary.get("minimum"),
                numeric_maximum=summary.get("maximum"),
                categorical_distinct_count=distinct_count,
                top_values_json={"values": top_values},
            )
        )
    session.add_all(profiles)


def _table_columns(analytics_store: DuckDBAnalyticsStore, table: str) -> set[str]:
    """Return trusted table columns for identity profiling."""

    return set(analytics_store.table_columns(table))


def _value_column(table: str, scalar_type: str) -> str:
    """Return the canonical typed value column for a trusted relation."""

    if table == "feature_value_numeric":
        return "value"
    if table == "result_payloads":
        return "data_json"
    return {
        "numeric": "value_numeric",
        "integer": "value_numeric",
        "string": "value_string",
        "categorical": "value_string",
        "boolean": "value_boolean",
        "date": "value_datetime",
        "datetime": "value_datetime",
        "json": "value_json",
    }.get(scalar_type, "value_string")
