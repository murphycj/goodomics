"""DuckDB analytical storage registry, serializers, and ingest write helpers."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import UnionType
from typing import Any, Literal, TypeVar, Union, get_args, get_origin

import duckdb
from pydantic import BaseModel

from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    CohortSummary,
    CopyNumberSegment,
    DataSource,
    EntityAttribute,
    Feature,
    FeatureAlias,
    FeatureCall,
    FeatureSet,
    FeatureSetMember,
    FeatureValueNumeric,
    GeneAlterationState,
    GenomicInterval,
    ResultPayload,
    SampleIntervalValue,
    SampleMetric,
    SampleStructuralVariantCall,
    SampleVariantCall,
    StructuralVariantEvent,
    TimelineEvent,
    ToolVersion,
    Variant,
    VariantAnnotation,
    VariantTranscriptAnnotation,
)

RecordT = TypeVar("RecordT", bound=BaseModel)


@dataclass(frozen=True)
class AnalyticalTableSerializer:
    """Mapping between one analytical batch field, model schema, and DuckDB table."""

    table_name: str
    """Physical DuckDB table name for this analytical record type."""

    model_type: type[BaseModel]
    """Pydantic model class that defines public columns and value types."""

    order_by: str
    """Default sort expression used when creating deterministic sorted views."""

    batch_field: str | None = None
    """Optional `AnalyticsIngestBatch` field name; defaults to `table_name`."""

    run_column: str | None = None
    """Run-scoped column used for replace-by-run writes, if applicable."""

    unique_columns: tuple[str, ...] = ()
    """Natural-key columns used to upsert non-run-scoped reference data."""

    column_types: dict[str, str] = field(default_factory=dict)
    """Optional per-column SQL type overrides for physical table creation."""

    @property
    def resolved_batch_field(self) -> str:
        """Return the `AnalyticsIngestBatch` field name for this serializer."""

        return self.batch_field or self.table_name

    @property
    def columns(self) -> tuple[str, ...]:
        """Return public column names derived from the model field definitions."""

        return tuple(
            _field_column_name(field_name, field_info)
            for field_name, field_info in self.model_type.model_fields.items()
        )

    @property
    def column_sql(self) -> tuple[str, ...]:
        """Return SQL column definitions for table creation."""

        sql: list[str] = []
        for field_name, field_info in self.model_type.model_fields.items():
            column = _field_column_name(field_name, field_info)
            db_type = self.column_types.get(
                column,
                _duckdb_type_for_field(field_info.annotation, column),
            )
            sql.append(f"{column} {db_type}")
        return tuple(sql)

    @property
    def create_sql(self) -> str:
        """Build the `CREATE TABLE` statement for the serializer table."""

        columns = ",\n                    ".join(self.column_sql)
        return f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    {columns}
                )
                """

    def create_table(self, connection: duckdb.DuckDBPyConnection) -> None:
        """Create the backing table, using integer-keyed behavior when configured."""

        integer_table = INTEGER_KEYED_TABLES.get(self.table_name)
        if integer_table is not None:
            integer_table.create_table(connection)
            return
        connection.execute(self.create_sql)

    def create_sorted_view(self, connection: duckdb.DuckDBPyConnection) -> None:
        """Create a deterministic sorted view for stable read/query ordering."""

        # Sorted views give API/query callers deterministic row order without
        # requiring every query to remember the table-specific ORDER BY clause.
        view_name = f"{self.table_name}_sorted"
        integer_table = INTEGER_KEYED_TABLES.get(self.table_name)
        columns = (
            _column_list(integer_table.physical_columns)
            if integer_table is not None
            else "*"
        )
        order_by = (
            _physical_order_by(integer_table, self.order_by)
            if integer_table is not None
            else self.order_by
        )
        connection.execute(f"DROP VIEW IF EXISTS {view_name}")
        connection.execute(
            f"CREATE VIEW {view_name} AS SELECT {columns} FROM {self.table_name} "
            f"ORDER BY {order_by}"
        )

    def delete_run(
        self, connection: duckdb.DuckDBPyConnection, run_id: Any | None
    ) -> None:
        """Delete run-scoped rows for one run identifier when supported."""

        if run_id is None or self.run_column is None:
            return
        integer_table = INTEGER_KEYED_TABLES.get(self.table_name)
        if integer_table is not None:
            integer_table.delete_run(connection, run_id)
            return
        connection.execute(
            f"DELETE FROM {self.table_name} WHERE {self.run_column} = ?", [run_id]
        )

    def delete_unique_values(
        self,
        connection: duckdb.DuckDBPyConnection,
        records: Sequence[Any],
    ) -> None:
        """Delete rows matching natural-key values extracted from incoming records."""

        # Reference tables like features or metric definitions are not scoped to
        # a single run, so replacement is based on their configured natural key.
        if not records or not self.unique_columns:
            return
        values = {
            tuple(_field_value(record, column) for column in self.unique_columns)
            for record in records
        }
        where = " AND ".join(
            f"{column} IS NOT DISTINCT FROM ?" for column in self.unique_columns
        )
        integer_table = INTEGER_KEYED_TABLES.get(self.table_name)
        if integer_table is not None:
            _delete_integer_table_unique_values(
                connection,
                integer_table,
                self.unique_columns,
                records,
            )
            return
        connection.executemany(
            f"DELETE FROM {self.table_name} WHERE {where}",
            [tuple(value) for value in values],
        )

    def insert_records(
        self,
        connection: duckdb.DuckDBPyConnection,
        records: Sequence[Any],
    ) -> None:
        """Insert validated records into either public or integer-keyed storage."""

        if not records:
            return
        if self.table_name in INTEGER_KEYED_TABLES:
            insert_public_rows(
                connection,
                self.table_name,
                self.columns,
                [
                    tuple(
                        _to_db_value(_field_value(record, column))
                        for column in self.columns
                    )
                    for record in records
                ],
            )
            return
        placeholders = ", ".join("?" for _ in self.columns)
        columns = ", ".join(self.columns)
        connection.executemany(
            f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})",
            [
                tuple(
                    _to_db_value(_field_value(record, column))
                    for column in self.columns
                )
                for record in records
            ],
        )

    def records_from_batch(self, batch: AnalyticsIngestBatch) -> list[Any]:
        """Extract and validate table-specific records from an ingest batch."""

        # The batch field name and model type are paired here, which lets the
        # write loop handle every analytical table with the same code path.
        raw_records = getattr(batch, self.resolved_batch_field)
        if self.table_name in INTEGER_KEYED_TABLES:
            return list(raw_records)
        return [self.model_type.model_validate(record) for record in raw_records]


# SERIALIZERS is the DuckDB analytical schema registry. Adding a new analytical
# table generally means adding a Pydantic model/list field to AnalyticsIngestBatch
# and then adding one serializer entry here for table-specific behavior.
SERIALIZERS: tuple[AnalyticalTableSerializer, ...] = (
    AnalyticalTableSerializer(
        "entity_attributes",
        EntityAttribute,
        "entity_scope, entity_id, field_id",
        unique_columns=(
            "entity_scope",
            "entity_id",
            "field_id",
            "data_contract_id",
        ),
    ),
    AnalyticalTableSerializer(
        "sample_metrics",
        SampleMetric,
        "data_contract_id, run_id, run_sample_id, field_id, source_observation_id",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "features",
        Feature,
        "feature_type, feature_id",
        unique_columns=("feature_id",),
    ),
    AnalyticalTableSerializer(
        "feature_aliases",
        FeatureAlias,
        "feature_id, alias",
        unique_columns=("feature_id", "alias", "namespace"),
    ),
    AnalyticalTableSerializer(
        "feature_sets",
        FeatureSet,
        "feature_set_type, feature_set_id",
        unique_columns=("feature_set_id",),
    ),
    AnalyticalTableSerializer(
        "feature_set_members",
        FeatureSetMember,
        "feature_set_id, feature_id",
        unique_columns=("feature_set_id", "feature_id"),
    ),
    AnalyticalTableSerializer(
        "feature_value_numeric",
        FeatureValueNumeric,
        "data_contract_id, feature_id, run_sample_id",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "feature_call",
        FeatureCall,
        "data_contract_id, feature_id, call_code, run_sample_id",
        run_column="run_id",
        column_types={
            "call_rank": "INTEGER",
        },
    ),
    AnalyticalTableSerializer(
        "genomic_intervals",
        GenomicInterval,
        "genome_build, contig, start_pos, end_pos",
        unique_columns=("interval_id",),
    ),
    AnalyticalTableSerializer(
        "sample_interval_values",
        SampleIntervalValue,
        "data_contract_id, run_sample_id, interval_id",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "copy_number_segments",
        CopyNumberSegment,
        "data_contract_id, run_sample_id, contig, start_pos",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "variants",
        Variant,
        "genome_build, contig, pos, end_pos, variant_id",
        unique_columns=("variant_id",),
    ),
    AnalyticalTableSerializer(
        "variant_annotations",
        VariantAnnotation,
        "variant_id, data_contract_id, feature_id",
        unique_columns=(
            "data_contract_id",
            "variant_id",
            "feature_id",
            "consequence",
        ),
    ),
    AnalyticalTableSerializer(
        "variant_transcript_annotations",
        VariantTranscriptAnnotation,
        "variant_id, transcript_feature_id",
        unique_columns=("data_contract_id", "variant_id", "transcript_feature_id"),
    ),
    AnalyticalTableSerializer(
        "sample_variant_calls",
        SampleVariantCall,
        "data_contract_id, run_sample_id, variant_id",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "structural_variant_events",
        StructuralVariantEvent,
        "structural_variant_id",
        unique_columns=("structural_variant_id",),
    ),
    AnalyticalTableSerializer(
        "sample_structural_variant_calls",
        SampleStructuralVariantCall,
        "data_contract_id, run_sample_id, structural_variant_id",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "timeline_events",
        TimelineEvent,
        "subject_id, event_type, start_time",
        unique_columns=("event_id",),
    ),
    AnalyticalTableSerializer(
        "result_payloads",
        ResultPayload,
        "data_contract_id, run_id, run_sample_id, payload_name",
        run_column="run_id",
        unique_columns=("payload_id",),
    ),
    AnalyticalTableSerializer(
        "gene_alteration_state",
        GeneAlterationState,
        "feature_id, alteration_type, data_contract_id, run_sample_id",
    ),
    AnalyticalTableSerializer(
        "cohort_summaries",
        CohortSummary,
        "sample_set_id, data_contract_id, field_id, feature_id",
        unique_columns=(
            "sample_set_id",
            "data_contract_id",
            "field_id",
            "feature_id",
        ),
    ),
    AnalyticalTableSerializer(
        "tool_versions",
        ToolVersion,
        "run_id, tool",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "data_sources",
        DataSource,
        "run_id, sample_id, tool, module",
        run_column="run_id",
    ),
)

SERIALIZERS_BY_FIELD = {
    serializer.resolved_batch_field: serializer for serializer in SERIALIZERS
}
SERIALIZERS_BY_TABLE = {serializer.table_name: serializer for serializer in SERIALIZERS}
# These derived registries keep lookup code explicit: fetch/validation starts
# from a table name, while replacement needs only the run-scoped subset.
RUN_SCOPED_TABLES = tuple(
    serializer for serializer in SERIALIZERS if serializer.run_column is not None
)
ANALYTICS_TABLES = tuple(serializer.table_name for serializer in SERIALIZERS)


@dataclass(frozen=True)
class DuckDBDimension:
    """Dimension table metadata for converting public labels to integer IDs."""

    table_name: str
    """Dimension table name."""

    id_column: str
    """Integer identifier column stored by fact tables."""

    label_column: str
    """Public label column resolved from and to API-facing IDs."""

    storage_column: str | None = None
    """Optional fact-table column name when it differs from `id_column`."""

    @property
    def physical_column(self) -> str:
        """Return the stored integer ID column name used in fact tables."""

        return self.storage_column or self.id_column

    @property
    def create_sql(self) -> str:
        """Build the `CREATE TABLE` statement for this dimension table."""

        return f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                {self.id_column} BIGINT PRIMARY KEY,
                {self.label_column} TEXT UNIQUE
            )
            """


CATALOG_ID_COLUMNS = frozenset(
    {
        "project_id",
        "data_contract_id",
        "run_id",
        "run_sample_id",
        "sample_id",
        "sample_set_id",
        "subject_id",
    }
)


DIMENSIONS_BY_COLUMN: dict[str, DuckDBDimension] = {
    "feature_id": DuckDBDimension("dim_features", "feature_id", "feature_label"),
    "transcript_feature_id": DuckDBDimension(
        "dim_features", "feature_id", "feature_label", "transcript_feature_id"
    ),
    "gene_feature_id": DuckDBDimension(
        "dim_features", "feature_id", "feature_label", "gene_feature_id"
    ),
    "site1_feature_id": DuckDBDimension(
        "dim_features", "feature_id", "feature_label", "site1_feature_id"
    ),
    "site2_feature_id": DuckDBDimension(
        "dim_features", "feature_id", "feature_label", "site2_feature_id"
    ),
    "source_file_id": DuckDBDimension(
        "dim_files", "source_file_id", "source_file_label"
    ),
    "field_id": DuckDBDimension("dim_fields", "field_id", "field_label"),
    "variant_id": DuckDBDimension("dim_variants", "variant_id", "variant_label"),
    "interval_id": DuckDBDimension("dim_intervals", "interval_id", "interval_label"),
    "feature_set_id": DuckDBDimension(
        "dim_feature_sets", "feature_set_id", "feature_set_label"
    ),
    "structural_variant_id": DuckDBDimension(
        "dim_structural_variants",
        "structural_variant_id",
        "structural_variant_label",
    ),
    "event_id": DuckDBDimension("dim_events", "event_id", "event_label"),
    "payload_id": DuckDBDimension("dim_payloads", "payload_id", "payload_label"),
}
DIMENSIONS = tuple(dict.fromkeys(DIMENSIONS_BY_COLUMN.values()))


@dataclass(frozen=True)
class IntegerKeyedTableDefinition:
    """Configuration for a fact table that stores integer foreign-key columns."""

    table_name: str
    """Physical table name."""

    serializer: AnalyticalTableSerializer
    """Serializer describing public schema and write behavior for this table."""

    dimensions: Mapping[str, DuckDBDimension]
    """Public columns resolved through dimension tables."""

    catalog_columns: frozenset[str] = frozenset()
    """Public columns already resolved to SQL integer catalog IDs before write."""

    @property
    def physical_columns(self) -> tuple[str, ...]:
        """Return physical stored column names aligned with serializer columns."""

        return tuple(
            (
                self.dimensions[column].physical_column
                if column in self.dimensions
                else column
            )
            for column in self.serializer.columns
        )

    def create_table(self, connection: duckdb.DuckDBPyConnection) -> None:
        """Create the physical table and drop stale sorted views first."""

        _drop_view_if_exists(connection, self.table_name)
        connection.execute(self.create_sql)

    @property
    def create_sql(self) -> str:
        """Build the physical `CREATE TABLE` statement for this table."""

        columns = ",\n                    ".join(
            self._physical_column_sql(column) for column in self.serializer.columns
        )
        return f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    {columns}
                )
                """

    def _physical_column_sql(self, public_column: str) -> str:
        dimension = self.dimensions.get(public_column)
        if dimension is not None or public_column in self.catalog_columns:
            physical_column = (
                dimension.physical_column if dimension is not None else public_column
            )
            return f"{_quote_identifier(physical_column)} BIGINT"
        field_name = _field_name_for_column(self.serializer.model_type, public_column)
        field_info = self.serializer.model_type.model_fields[field_name]
        db_type = self.serializer.column_types.get(
            public_column,
            _duckdb_type_for_field(field_info.annotation, public_column),
        )
        return f"{_quote_identifier(public_column)} {db_type}"

    def readable_select_sql(self, columns: Sequence[str] | None = None) -> str:
        """Build a select statement that joins dimensions back to public labels."""

        requested_columns = tuple(columns or self.serializer.columns)
        select_columns: list[str] = []
        joins: list[str] = []
        for index, column in enumerate(self.serializer.columns):
            dimension = self.dimensions.get(column)
            if dimension is None:
                if column in requested_columns:
                    select_columns.append(f"stored.{_quote_identifier(column)}")
                continue
            alias = f"dim_{index}"
            joins.append(
                f"LEFT JOIN {dimension.table_name} {alias} "
                f"ON stored.{_quote_identifier(dimension.physical_column)} = "
                f"{alias}.{_quote_identifier(dimension.id_column)}"
            )
            if column in requested_columns:
                select_columns.append(
                    f"{alias}.{_quote_identifier(dimension.label_column)} "
                    f"AS {_quote_identifier(column)}"
                )
        return f"""
            SELECT {", ".join(select_columns)}
            FROM {self.table_name} stored
            {" ".join(joins)}
            """

    def delete_run(self, connection: duckdb.DuckDBPyConnection, run_id: str) -> None:
        """Delete rows for one run from this integer-keyed table."""

        if "run_id" in self.catalog_columns:
            connection.execute(
                f"""
                DELETE FROM {self.table_name}
                WHERE {_quote_identifier("run_id")} = ?
                """,
                [run_id],
            )
            return
        run_dimension = self.dimensions.get("run_id")
        if run_dimension is None:
            return
        connection.execute(
            f"""
            DELETE FROM {self.table_name}
            WHERE {_quote_identifier(run_dimension.physical_column)} IN (
                SELECT {_quote_identifier(run_dimension.id_column)}
                FROM {run_dimension.table_name}
                WHERE {_quote_identifier(run_dimension.label_column)} = ?
            )
            """,
            [run_id],
        )


def _integer_id_dimensions(*columns: str) -> dict[str, DuckDBDimension]:
    return {
        column: DIMENSIONS_BY_COLUMN[column]
        for column in columns
        if column in DIMENSIONS_BY_COLUMN
    }


def _catalog_id_columns(*columns: str) -> frozenset[str]:
    return frozenset(column for column in columns if column in CATALOG_ID_COLUMNS)


INTEGER_KEYED_TABLES: dict[str, IntegerKeyedTableDefinition] = {
    table: IntegerKeyedTableDefinition(
        table_name=table,
        serializer=SERIALIZERS_BY_TABLE[table],
        dimensions=_integer_id_dimensions(*columns),
        catalog_columns=_catalog_id_columns(*columns),
    )
    for table, columns in {
        "entity_attributes": (
            "entity_id",
            "field_id",
            "data_contract_id",
            "source_file_id",
        ),
        "sample_metrics": (
            "data_contract_id",
            "run_id",
            "run_sample_id",
            "sample_id",
            "field_id",
            "source_file_id",
        ),
        "feature_aliases": ("feature_id",),
        "feature_set_members": ("feature_set_id", "feature_id"),
        "feature_value_numeric": (
            "data_contract_id",
            "run_id",
            "run_sample_id",
            "sample_id",
            "feature_id",
            "source_file_id",
        ),
        "feature_call": (
            "data_contract_id",
            "run_id",
            "run_sample_id",
            "sample_id",
            "feature_id",
            "source_file_id",
        ),
        "genomic_intervals": ("feature_id",),
        "sample_interval_values": (
            "data_contract_id",
            "run_id",
            "run_sample_id",
            "sample_id",
            "interval_id",
            "source_file_id",
        ),
        "copy_number_segments": (
            "data_contract_id",
            "run_id",
            "run_sample_id",
            "sample_id",
            "source_file_id",
        ),
        "variant_annotations": (
            "data_contract_id",
            "variant_id",
            "feature_id",
        ),
        "variant_transcript_annotations": (
            "data_contract_id",
            "variant_id",
            "transcript_feature_id",
            "gene_feature_id",
        ),
        "sample_variant_calls": (
            "data_contract_id",
            "run_id",
            "run_sample_id",
            "sample_id",
            "variant_id",
            "source_file_id",
        ),
        "structural_variant_events": (
            "structural_variant_id",
            "site1_feature_id",
            "site2_feature_id",
        ),
        "sample_structural_variant_calls": (
            "data_contract_id",
            "run_id",
            "run_sample_id",
            "sample_id",
            "structural_variant_id",
            "source_file_id",
        ),
        "timeline_events": (
            "event_id",
            "subject_id",
            "sample_id",
            "run_sample_id",
        ),
        "result_payloads": (
            "payload_id",
            "data_contract_id",
            "run_id",
            "run_sample_id",
            "sample_id",
            "field_id",
            "source_file_id",
        ),
        "gene_alteration_state": (
            "run_sample_id",
            "sample_id",
            "subject_id",
            "feature_id",
            "data_contract_id",
            "source_event_id",
        ),
        "cohort_summaries": (
            "sample_set_id",
            "data_contract_id",
            "field_id",
            "feature_id",
        ),
        "tool_versions": ("run_id", "source_file_id"),
        "data_sources": ("run_id", "run_sample_id", "sample_id"),
    }.items()
}


class DuckDBAnalyticsStore:
    """DuckDB-backed analytical store with replace-oriented ingest operations."""

    path: Path
    """Path to the project analytics DuckDB file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(self.path))
        connection.execute("SET preserve_insertion_order=false")
        return connection

    def ensure_schema(self) -> None:
        """Create/refresh analytical tables, dimensions, and sorted views."""

        with self._connect() as connection:
            for serializer in SERIALIZERS:
                connection.execute(
                    f"DROP VIEW IF EXISTS {serializer.table_name}_sorted"
                )
            for dimension in DIMENSIONS:
                connection.execute(dimension.create_sql)
            # The registry is the source of truth for physical DuckDB tables.
            for serializer in SERIALIZERS:
                serializer.create_table(connection)
                serializer.create_sorted_view(connection)
            self._create_derived_views(connection)

    def write_batch(
        self,
        batch: AnalyticsIngestBatch,
        *,
        replace_run_id: Any | None = None,
        replace_run_ids: Sequence[Any] | None = None,
        refresh_derived: bool = True,
    ) -> None:
        """Write an ingest batch, optionally replacing existing data for run IDs."""

        validated = AnalyticsIngestBatch.model_validate(batch)
        run_ids_to_replace = list(replace_run_ids or [])
        if replace_run_id is not None:
            run_ids_to_replace.append(replace_run_id)
        self.ensure_schema()
        with self._connect() as connection:
            connection.begin()
            try:
                for run_id in dict.fromkeys(run_ids_to_replace):
                    # Replacing a run clears only tables that carry run-scoped
                    # observations; shared definitions/features are refreshed by
                    # natural key deletion below.
                    for serializer in RUN_SCOPED_TABLES:
                        serializer.delete_run(connection, run_id)

                for serializer in SERIALIZERS:
                    records = serializer.records_from_batch(validated)
                    # Non-run tables are dimensions/reference data. Delete the
                    # incoming natural keys first so imports stay idempotent.
                    if serializer.run_column is None:
                        serializer.delete_unique_values(connection, records)
                    serializer.insert_records(connection, records)

                if refresh_derived:
                    refresh_run_id = (
                        replace_run_id
                        if replace_run_id is not None and not replace_run_ids
                        else None
                    )
                    self._refresh_gene_alteration_state(
                        connection, run_id=refresh_run_id
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def write_batch_with_bulk_loads(
        self,
        batch: AnalyticsIngestBatch,
        bulk_loads: Sequence[Any],
        *,
        staged_loads: Sequence[Any] | None = None,
        replace_run_id: Any | None = None,
        replace_run_ids: Sequence[Any] | None = None,
        bulk_load_progress: Callable[[Any, int, int], None] | None = None,
    ) -> None:
        """Write a batch plus staged/bulk loaders in one coordinated workflow."""

        self.write_batch(
            batch,
            replace_run_id=replace_run_id,
            replace_run_ids=replace_run_ids,
            refresh_derived=False,
        )
        staged_loads = tuple(staged_loads or ())
        if not bulk_loads and not staged_loads:
            with self._connect() as connection:
                refresh_run_id = (
                    replace_run_id
                    if replace_run_id is not None and not replace_run_ids
                    else None
                )
                self._refresh_gene_alteration_state(connection, run_id=refresh_run_id)
            return

        self.ensure_schema()
        with self._connect() as connection:
            loads = [*staged_loads, *bulk_loads]
            use_transaction = not any(
                bool(getattr(load, "requires_autocommit", False)) for load in loads
            )
            if use_transaction:
                connection.begin()
            try:
                for staged_load in staged_loads:
                    staged_load.load(connection)
                total_bulk_loads = len(bulk_loads)
                for index, bulk_load in enumerate(bulk_loads):
                    if bulk_load_progress is not None:
                        bulk_load_progress(bulk_load, index, total_bulk_loads)
                    bulk_load.load(connection)
                refresh_run_id = (
                    replace_run_id
                    if replace_run_id is not None and not replace_run_ids
                    else None
                )
                self._refresh_gene_alteration_state(connection, run_id=refresh_run_id)
                if use_transaction:
                    connection.commit()
            except Exception:
                if use_transaction:
                    connection.rollback()
                raise

    def replace_run_data(
        self,
        run_id: Any,
        batch: AnalyticsIngestBatch | None = None,
        *,
        metrics: Sequence[SampleMetric] | None = None,
        payloads: Sequence[ResultPayload] | None = None,
        tool_versions: Sequence[ToolVersion] | None = None,
        data_sources: Sequence[DataSource] | None = None,
    ) -> None:
        """Replace one run's analytical rows using a batch or selected table slices."""

        if batch is None:
            batch = AnalyticsIngestBatch(
                sample_metrics=list(metrics or []),
                result_payloads=list(payloads or []),
                tool_versions=list(tool_versions or []),
                data_sources=list(data_sources or []),
            )
        self.write_batch(
            batch,
            replace_run_id=run_id,
            refresh_derived=True,
        )

    def fetch_records(
        self, table_name: str, model_type: type[RecordT], *, run_id: Any | None = None
    ) -> list[RecordT]:
        """Fetch and validate records from one analytical table."""

        serializer = SERIALIZERS_BY_TABLE[table_name]
        if not self.path.exists():
            return []
        self.ensure_schema()
        query = f"SELECT {_column_list(serializer.columns)} FROM {table_name}"
        parameters: list[Any] = []
        if run_id is not None and serializer.run_column is not None:
            integer_table = INTEGER_KEYED_TABLES.get(table_name)
            if (
                integer_table is not None
                and serializer.run_column in integer_table.dimensions
            ):
                dimension = integer_table.dimensions[serializer.run_column]
                query += (
                    f" WHERE {_quote_identifier(serializer.run_column)} IN ("
                    f"SELECT {_quote_identifier(dimension.id_column)} "
                    f"FROM {dimension.table_name} "
                    f"WHERE {_quote_identifier(dimension.label_column)} = ?)"
                )
            else:
                query += f" WHERE {_quote_identifier(serializer.run_column)} = ?"
            parameters.append(run_id)
        query += f" ORDER BY {_quote_order_by(serializer.order_by)}"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            model_type.model_validate(
                {
                    column: _from_db_value(column, value)
                    for column, value in zip(serializer.columns, row, strict=True)
                }
            )
            for row in rows
        ]

    def list_metric_values(
        self,
        run_id: Any,
        *,
        sample_id: Any | None = None,
        run_sample_id: Any | None = None,
    ) -> list[SampleMetric]:
        """List sample metrics for a run, with optional sample/run-sample filtering."""

        values = self.fetch_records("sample_metrics", SampleMetric, run_id=run_id)
        if sample_id is None and run_sample_id is None:
            return values
        resolved_sample_id = sample_id
        resolved_run_sample_id = run_sample_id
        return [
            value
            for value in values
            if (
                resolved_sample_id is not None and value.sample_id == resolved_sample_id
            )
            or (
                resolved_run_sample_id is not None
                and value.run_sample_id == resolved_run_sample_id
            )
        ]

    def list_result_payloads(self, run_id: Any) -> list[ResultPayload]:
        """List result payload rows for a run."""

        return self.fetch_records("result_payloads", ResultPayload, run_id=run_id)

    def row_counts(self) -> dict[str, int]:
        """Return row counts for each registered analytical table."""

        if not self.path.exists():
            return {table: 0 for table in ANALYTICS_TABLES}
        self.ensure_schema()
        with self._connect() as connection:
            counts: dict[str, int] = {}
            for table in ANALYTICS_TABLES:
                result = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(result[0]) if result is not None else 0
            return counts

    def preview_table(
        self,
        table_name: str,
        *,
        limit: int,
        offset: int = 0,
        sort_by: str | None = None,
        sort_direction: Literal["asc", "desc"] = "asc",
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        """Return a paginated preview for one analytical table."""

        serializer = SERIALIZERS_BY_TABLE[table_name]
        integer_table = INTEGER_KEYED_TABLES.get(table_name)
        columns = list(
            integer_table.physical_columns
            if integer_table is not None
            else serializer.columns
        )
        if not self.path.exists():
            return columns, [], 0
        self.ensure_schema()
        order_by = (
            _physical_order_by(integer_table, serializer.order_by)
            if integer_table is not None
            else serializer.order_by
        )
        if sort_by is not None:
            if sort_by not in columns:
                raise ValueError(f"Unknown analytical table column: {sort_by}")
            direction = "DESC" if sort_direction == "desc" else "ASC"
            order_by = f"{_quote_identifier(sort_by)} {direction}"
        query = (
            f"SELECT {_column_list(columns)} FROM {table_name} "
            f"ORDER BY {order_by} LIMIT ? OFFSET ?"
        )
        with self._connect() as connection:
            total_result = connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()
            rows = connection.execute(query, [limit, offset]).fetchall()
        total = int(total_result[0]) if total_result is not None else 0
        return (
            columns,
            [
                {
                    column: _from_db_value(column, value)
                    for column, value in zip(columns, row, strict=True)
                }
                for row in rows
            ],
            total,
        )

    def query_rows(
        self,
        query: str,
        *,
        parameters: Sequence[Any] = (),
        limit: int = 1000,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Execute a bounded read-only query and return JSON-serializable rows."""

        if not self.path.exists():
            return [], []
        self.ensure_schema()
        bounded_query = f"SELECT * FROM ({query}) AS goodomics_query LIMIT ?"
        with self._connect() as connection:
            cursor = connection.execute(
                bounded_query, [*parameters, min(max(limit, 1), 100000)]
            )
            columns = [description[0] for description in cursor.description or []]
            rows = cursor.fetchall()
        return (
            columns,
            [
                {
                    column: _from_db_value(column, value)
                    for column, value in zip(columns, row, strict=True)
                }
                for row in rows
            ],
        )

    def database_size_bytes(self) -> int:
        """Return on-disk DuckDB file size in bytes when present."""

        return self.path.stat().st_size if self.path.exists() else 0

    def _create_derived_views(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(f"""
            CREATE OR REPLACE VIEW sample_metric_numeric_by_metric AS
            SELECT
                data_contract_id,
                run_id,
                run_sample_id,
                sample_id,
                field_id,
                source_file_id,
                source_observation_id,
                source_observation_label,
                source_observation_metadata_json,
                value_numeric AS value
            FROM sample_metrics
            WHERE value_type = 'numeric'
            ORDER BY {
            _physical_order_by(
                INTEGER_KEYED_TABLES["sample_metrics"],
                "data_contract_id, field_id, source_observation_id, "
                "value_numeric, run_sample_id",
            )
        }
            """)
        connection.execute(f"""
            CREATE OR REPLACE VIEW feature_value_numeric_by_sample AS
            SELECT *
            FROM feature_value_numeric
            ORDER BY {
            _physical_order_by(
                INTEGER_KEYED_TABLES["feature_value_numeric"],
                "data_contract_id, run_sample_id, feature_id",
            )
        }
            """)
        connection.execute(f"""
            CREATE OR REPLACE VIEW feature_call_by_sample AS
            SELECT *
            FROM feature_call
            ORDER BY {
            _physical_order_by(
                INTEGER_KEYED_TABLES["feature_call"],
                "data_contract_id, run_sample_id, feature_id",
            )
        }
            """)
        connection.execute(f"""
            CREATE OR REPLACE VIEW sample_variant_calls_by_variant AS
            SELECT *
            FROM sample_variant_calls
            ORDER BY {
            _physical_order_by(
                INTEGER_KEYED_TABLES["sample_variant_calls"],
                "data_contract_id, variant_id, run_sample_id",
            )
        }
            """)
        connection.execute(f"""
            CREATE OR REPLACE VIEW copy_number_segments_by_region AS
            SELECT *
            FROM copy_number_segments
            ORDER BY genome_build, contig, start_pos, end_pos,
                {
            _physical_order_by(
                INTEGER_KEYED_TABLES["copy_number_segments"],
                "data_contract_id, run_sample_id",
            )
        }
            """)
        connection.execute(f"""
            CREATE OR REPLACE VIEW gene_alteration_state_by_sample AS
            SELECT *
            FROM gene_alteration_state
            ORDER BY {
            _physical_order_by(
                INTEGER_KEYED_TABLES["gene_alteration_state"],
                "run_sample_id, feature_id, alteration_type",
            )
        }
            """)

    def _refresh_gene_alteration_state(
        self, connection: duckdb.DuckDBPyConnection, *, run_id: Any | None
    ) -> None:
        integer_table = INTEGER_KEYED_TABLES["gene_alteration_state"]
        sample_variant_calls = "SELECT * FROM sample_variant_calls"
        feature_call = "SELECT * FROM feature_call"
        sample_structural_variant_calls = (
            "SELECT * FROM sample_structural_variant_calls"
        )
        variant_annotations = "SELECT * FROM variant_annotations"
        structural_variant_events = "SELECT * FROM structural_variant_events"
        if run_id is None:
            connection.execute(f"DELETE FROM {integer_table.table_name}")
            svc_run_filter = "WHERE TRUE"
            feature_call_run_filter = "WHERE TRUE"
            sv_run_filter = "WHERE TRUE"
            parameters: list[str] = []
        else:
            connection.execute(
                f"""
                DELETE FROM {integer_table.table_name}
                WHERE run_sample_id IN (
                    SELECT DISTINCT run_sample_id
                    FROM ({sample_variant_calls})
                    WHERE run_id = ?
                    UNION
                    SELECT DISTINCT run_sample_id
                    FROM ({feature_call})
                    WHERE run_id = ?
                    UNION
                    SELECT DISTINCT run_sample_id
                    FROM ({sample_structural_variant_calls})
                    WHERE run_id = ?
                )
                """,
                [run_id, run_id, run_id],
            )
            svc_run_filter = "WHERE svc.run_id = ?"
            feature_call_run_filter = "WHERE run_id = ?"
            sv_run_filter = "WHERE ssvc.run_id = ?"
            parameters = [run_id]

        insert_storage_select(
            connection,
            "gene_alteration_state",
            SERIALIZERS_BY_TABLE["gene_alteration_state"].columns,
            f"""
            SELECT
                svc.run_sample_id,
                svc.sample_id,
                NULL AS subject_id,
                va.feature_id,
                svc.data_contract_id,
                'mutation' AS alteration_type,
                va.consequence AS alteration_subtype,
                TRUE AS is_altered,
                svc.allele_fraction AS value_numeric,
                svc.genotype AS value_string,
                NULL AS driver_status,
                'sample_variant_calls' AS source_table,
                CAST(svc.variant_id AS TEXT) AS source_event_id
            FROM ({sample_variant_calls}) svc
            LEFT JOIN ({variant_annotations}) va ON svc.variant_id = va.variant_id
            {svc_run_filter}
            AND va.feature_id IS NOT NULL
            """,
            parameters,
        )
        insert_storage_select(
            connection,
            "gene_alteration_state",
            SERIALIZERS_BY_TABLE["gene_alteration_state"].columns,
            f"""
            SELECT
                run_sample_id,
                sample_id,
                NULL AS subject_id,
                feature_id,
                data_contract_id,
                'feature_call' AS alteration_type,
                call_code AS alteration_subtype,
                TRUE AS is_altered,
                score AS value_numeric,
                call_code AS value_string,
                NULL AS driver_status,
                'feature_call' AS source_table,
                source_event_id
            FROM ({feature_call})
            {feature_call_run_filter}
            AND (
                call_rank IS DISTINCT FROM 0
                OR lower(call_code) NOT IN (
                    '0', 'diploid', 'neutral', 'absent', 'none', 'na'
                )
            )
            """,
            parameters,
        )
        insert_storage_select(
            connection,
            "gene_alteration_state",
            SERIALIZERS_BY_TABLE["gene_alteration_state"].columns,
            f"""
            SELECT
                ssvc.run_sample_id,
                ssvc.sample_id,
                NULL AS subject_id,
                sve.site1_feature_id AS feature_id,
                ssvc.data_contract_id,
                'sv' AS alteration_type,
                sve.event_class AS alteration_subtype,
                TRUE AS is_altered,
                NULL AS value_numeric,
                ssvc.call_status AS value_string,
                NULL AS driver_status,
                'sample_structural_variant_calls' AS source_table,
                CAST(ssvc.structural_variant_id AS TEXT) AS source_event_id
            FROM ({sample_structural_variant_calls}) ssvc
            JOIN ({structural_variant_events}) sve
                ON ssvc.structural_variant_id = sve.structural_variant_id
            {sv_run_filter}
            AND sve.site1_feature_id IS NOT NULL
            """,
            parameters,
        )
        insert_storage_select(
            connection,
            "gene_alteration_state",
            SERIALIZERS_BY_TABLE["gene_alteration_state"].columns,
            f"""
            SELECT
                ssvc.run_sample_id,
                ssvc.sample_id,
                NULL AS subject_id,
                sve.site2_feature_id AS feature_id,
                ssvc.data_contract_id,
                'sv' AS alteration_type,
                sve.event_class AS alteration_subtype,
                TRUE AS is_altered,
                NULL AS value_numeric,
                ssvc.call_status AS value_string,
                NULL AS driver_status,
                'sample_structural_variant_calls' AS source_table,
                CAST(ssvc.structural_variant_id AS TEXT) AS source_event_id
            FROM ({sample_structural_variant_calls}) ssvc
            JOIN ({structural_variant_events}) sve
                ON ssvc.structural_variant_id = sve.structural_variant_id
            {sv_run_filter}
            AND sve.site2_feature_id IS NOT NULL
            AND (
                sve.site1_feature_id IS NULL
                OR sve.site2_feature_id != sve.site1_feature_id
            )
            """,
            parameters,
        )


def insert_public_rows(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> None:
    """Insert rows expressed with public IDs/labels into the target table."""

    if not rows:
        return
    integer_table = INTEGER_KEYED_TABLES.get(table_name)
    if integer_table is None:
        placeholders = ", ".join("?" for _ in columns)
        insert_sql = (
            f"INSERT INTO {table_name} ({_column_list(columns)}) "
            f"VALUES ({placeholders})"
        )
        connection.executemany(
            insert_sql,
            [tuple(_to_db_value(value) for value in row) for row in rows],
        )
        return
    dimension_maps = _ensure_integer_id_dimensions(
        connection, integer_table, columns, rows
    )
    physical_rows = [
        _physical_storage_row(
            integer_table,
            columns,
            row,
            dimension_maps,
        )
        for row in rows
    ]
    placeholders = ", ".join("?" for _ in integer_table.physical_columns)
    connection.executemany(
        f"""
        INSERT INTO {integer_table.table_name}
            ({_column_list(integer_table.physical_columns)})
        VALUES ({placeholders})
        """,
        physical_rows,
    )


def insert_storage_select(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Sequence[str],
    select_sql: str,
    parameters: Sequence[Any] | None = None,
) -> None:
    """Insert rows from a select query that already yields storage-form columns."""

    column_sql = _column_list(columns)
    connection.execute(
        f"INSERT INTO {table_name} ({column_sql}) SELECT {column_sql} "
        f"FROM ({select_sql})",
        list(parameters or []),
    )


def insert_public_select(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Sequence[str],
    select_sql: str,
    parameters: Sequence[Any] | None = None,
    *,
    upsert_dimensions: bool = True,
) -> None:
    """Insert rows from a public-label select query into storage tables."""

    integer_table = INTEGER_KEYED_TABLES.get(table_name)
    column_sql = _column_list(columns)
    if integer_table is None:
        connection.execute(
            f"INSERT INTO {table_name} ({column_sql}) SELECT {column_sql} "
            f"FROM ({select_sql})",
            list(parameters or []),
        )
        return
    if upsert_dimensions:
        upsert_public_dimensions_select(
            connection,
            table_name,
            columns,
            select_sql,
            parameters,
        )
    select_columns = [
        _storage_select_column(integer_table, column, index, source_alias="source")
        for index, column in enumerate(columns)
    ]
    joins = [
        _id_resolution_join(
            integer_table,
            column,
            index,
            source_alias="source",
        )
        for index, column in enumerate(columns)
        if column in integer_table.dimensions
    ]
    connection.execute(
        f"""
        INSERT INTO {integer_table.table_name}
            ({_column_list(integer_table.physical_columns)})
        SELECT {", ".join(select_columns)}
        FROM ({select_sql}) source
        {" ".join(joins)}
        """,
        list(parameters or []),
    )


def upsert_public_dimensions_select(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Sequence[str],
    select_sql: str,
    parameters: Sequence[Any] | None = None,
    *,
    dimension_columns: Sequence[str] | None = None,
) -> None:
    """Upsert dimension labels referenced by a public select query."""

    integer_table = INTEGER_KEYED_TABLES.get(table_name)
    if integer_table is None:
        return
    requested = set(dimension_columns or columns)
    for column, dimension in integer_table.dimensions.items():
        if column in columns and column in requested:
            _upsert_dimension_from_select(
                connection,
                dimension,
                select_sql,
                column,
                list(parameters or []),
            )


def insert_public_parquet(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Sequence[str],
    path: Path | str,
    *,
    upsert_dimensions: bool = True,
) -> None:
    """Insert rows from a parquet file whose columns use public labels."""

    column_sql = _column_list(columns)
    insert_public_select(
        connection,
        table_name,
        columns,
        f"SELECT {column_sql} FROM read_parquet(?)",
        [str(path)],
        upsert_dimensions=upsert_dimensions,
    )


def delete_public_select(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Sequence[str],
    select_sql: str,
    parameters: Sequence[Any] | None = None,
) -> None:
    """Delete rows matching records produced by a public select query."""

    integer_table = INTEGER_KEYED_TABLES.get(table_name)
    if integer_table is None:
        where = " AND ".join(
            _delete_public_select_predicate(column) for column in columns
        )
        connection.execute(
            f"""
            DELETE FROM {table_name}
            WHERE EXISTS (
                SELECT 1
                FROM ({select_sql}) source
                WHERE {where}
            )
            """,
            list(parameters or []),
        )
        return
    stage = "_goodomics_delete_select_stage"
    connection.execute(f"DROP TABLE IF EXISTS {stage}")
    connection.execute(
        f"CREATE TEMP TABLE {stage} AS SELECT {_column_list(columns)} "
        f"FROM ({select_sql})",
        list(parameters or []),
    )
    _delete_integer_table_stage(connection, integer_table, columns, stage)
    connection.execute(f"DROP TABLE IF EXISTS {stage}")


def delete_public_parquet(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Sequence[str],
    path: Path | str,
) -> None:
    """Delete rows matching records loaded from a parquet file."""

    column_sql = _column_list(columns)
    delete_public_select(
        connection,
        table_name,
        columns,
        f"SELECT {column_sql} FROM read_parquet(?)",
        [str(path)],
    )


def delete_public_rows(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> None:
    """Delete rows matching public-label row tuples."""

    if not rows:
        return
    integer_table = INTEGER_KEYED_TABLES.get(table_name)
    if integer_table is None:
        where = " AND ".join(
            f"{_quote_identifier(column)} IS NOT DISTINCT FROM ?" for column in columns
        )
        connection.executemany(
            f"DELETE FROM {table_name} WHERE {where}",
            [tuple(row) for row in rows],
        )
        return
    stage = "_goodomics_delete_rows_stage"
    connection.execute(f"DROP TABLE IF EXISTS {stage}")
    connection.execute(f"CREATE TEMP TABLE {stage} ({_text_stage_columns(columns)})")
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {stage} VALUES ({placeholders})",
        [
            tuple(None if value is None else str(_to_db_value(value)) for value in row)
            for row in rows
        ],
    )
    _delete_integer_table_stage(connection, integer_table, columns, stage)
    connection.execute(f"DROP TABLE IF EXISTS {stage}")


def _delete_integer_table_unique_values(
    connection: duckdb.DuckDBPyConnection,
    integer_table: IntegerKeyedTableDefinition,
    unique_columns: Sequence[str],
    records: Sequence[Any],
) -> None:
    values = {
        tuple(
            _stage_delete_value(
                integer_table,
                column,
                _to_db_value(_field_value(record, column)),
            )
            for column in unique_columns
        )
        for record in records
    }
    if not values:
        return
    stage = "_goodomics_delete_stage"
    connection.execute(f"DROP TABLE IF EXISTS {stage}")
    connection.execute(
        f"CREATE TEMP TABLE {stage} ({_text_stage_columns(unique_columns)})"
    )
    placeholders = ", ".join("?" for _ in unique_columns)
    connection.executemany(
        f"INSERT INTO {stage} VALUES ({placeholders})",
        [
            tuple(None if value is None else str(value) for value in row)
            for row in values
        ],
    )
    _delete_integer_table_stage(connection, integer_table, unique_columns, stage)
    connection.execute(f"DROP TABLE IF EXISTS {stage}")


def _delete_integer_table_stage(
    connection: duckdb.DuckDBPyConnection,
    integer_table: IntegerKeyedTableDefinition,
    columns: Sequence[str],
    stage: str,
) -> None:
    joins = [
        _delete_id_resolution_join(integer_table, column, index)
        for index, column in enumerate(columns)
        if column in integer_table.dimensions
    ]
    predicates = [
        _delete_unique_predicate(integer_table, column, index)
        for index, column in enumerate(columns)
    ]
    connection.execute(f"""
        DELETE FROM {integer_table.table_name} AS stored
        WHERE EXISTS (
            SELECT 1
            FROM {stage} stage
            {" ".join(joins)}
            WHERE {" AND ".join(predicates)}
        )
        """)


def _ensure_integer_id_dimensions(
    connection: duckdb.DuckDBPyConnection,
    integer_table: IntegerKeyedTableDefinition,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> dict[str, dict[Any, int | None]]:
    dimensions: dict[str, DuckDBDimension] = {
        column: integer_table.dimensions[column]
        for column in columns
        if column in integer_table.dimensions
    }
    values_by_column: dict[str, set[Any]] = {column: set() for column in dimensions}
    for row in rows:
        for column, value in zip(columns, row, strict=True):
            if (
                column in values_by_column
                and value is not None
                and not isinstance(value, int)
            ):
                values_by_column[column].add(_to_db_value(value))
    for column, values in values_by_column.items():
        _upsert_dimension_values(connection, dimensions[column], values)
    return {
        column: _dimension_map(connection, dimension, values_by_column[column])
        for column, dimension in dimensions.items()
    }


def _upsert_dimension_values(
    connection: duckdb.DuckDBPyConnection,
    dimension: DuckDBDimension,
    values: set[Any],
) -> None:
    if not values:
        return
    stage = "_goodomics_dimension_values"
    connection.execute(f"DROP TABLE IF EXISTS {stage}")
    connection.execute(f"CREATE TEMP TABLE {stage}(value TEXT)")
    connection.executemany(
        f"INSERT INTO {stage} VALUES (?)",
        [(str(value),) for value in sorted(values, key=str)],
    )
    _upsert_dimension_from_stage(connection, dimension, stage, "value")
    connection.execute(f"DROP TABLE IF EXISTS {stage}")


def _dimension_map(
    connection: duckdb.DuckDBPyConnection,
    dimension: DuckDBDimension,
    values: set[Any],
) -> dict[Any, int | None]:
    if not values:
        return {}
    stage = "_goodomics_lookup_values"
    connection.execute(f"DROP TABLE IF EXISTS {stage}")
    connection.execute(f"CREATE TEMP TABLE {stage}(value TEXT)")
    connection.executemany(
        f"INSERT INTO {stage} VALUES (?)",
        [(str(value),) for value in sorted(values, key=str)],
    )
    rows = connection.execute(f"""
        SELECT {_quote_identifier(dimension.label_column)},
               {_quote_identifier(dimension.id_column)}
        FROM {dimension.table_name}
        WHERE {_quote_identifier(dimension.label_column)} IN (
            SELECT value FROM {stage}
        )
        """).fetchall()
    connection.execute(f"DROP TABLE IF EXISTS {stage}")
    return {label: int(identifier) for label, identifier in rows}


def _dimension_id_for_label(
    connection: duckdb.DuckDBPyConnection,
    dimension: DuckDBDimension,
    label: str,
) -> int | None:
    row = connection.execute(
        f"""
        SELECT {_quote_identifier(dimension.id_column)}
        FROM {dimension.table_name}
        WHERE {_quote_identifier(dimension.label_column)} = ?
        """,
        [label],
    ).fetchone()
    return int(row[0]) if row is not None else None


def _physical_storage_row(
    integer_table: IntegerKeyedTableDefinition,
    columns: Sequence[str],
    row: Sequence[Any],
    dimension_maps: Mapping[str, Mapping[Any, int | None]],
) -> tuple[Any, ...]:
    values = dict(zip(columns, row, strict=True))
    physical: list[Any] = []
    for column in integer_table.serializer.columns:
        if column in integer_table.dimensions:
            raw = _to_db_value(values.get(column))
            if raw is None or isinstance(raw, int):
                physical.append(raw)
            else:
                physical.append(dimension_maps[column].get(str(raw)))
        elif column in integer_table.catalog_columns:
            physical.append(_catalog_storage_value(column, values.get(column)))
        else:
            physical.append(_to_db_value(values.get(column)))
    return tuple(physical)


def _catalog_storage_value(column: str, value: Any) -> int | None:
    value = _to_db_value(value)
    if value is None or isinstance(value, int):
        return value
    raise ValueError(
        f"Expected integer SQL catalog id for {column}, got {value!r}. "
        "Resolve catalog IDs before writing analytics rows to DuckDB."
    )


def _stage_delete_value(
    integer_table: IntegerKeyedTableDefinition,
    column: str,
    value: Any,
) -> Any:
    if column not in integer_table.catalog_columns:
        return value
    return _catalog_storage_value(column, value)


def _storage_select_column(
    integer_table: IntegerKeyedTableDefinition,
    column: str,
    index: int,
    *,
    source_alias: str = "stage",
) -> str:
    dimension = integer_table.dimensions.get(column)
    if dimension is not None:
        return f"dim_{index}.{_quote_identifier(dimension.id_column)}"
    if column in integer_table.catalog_columns:
        stage_column = f"{source_alias}.{_quote_identifier(column)}"
        return f"CAST({stage_column} AS BIGINT)"
    return f"{source_alias}.{_quote_identifier(column)}"


def _id_resolution_join(
    integer_table: IntegerKeyedTableDefinition,
    column: str,
    index: int,
    *,
    source_alias: str = "stage",
) -> str:
    dimension = integer_table.dimensions.get(column)
    if dimension is not None:
        return (
            f"LEFT JOIN {dimension.table_name} dim_{index} "
            f"ON {source_alias}.{_quote_identifier(column)} = "
            f"dim_{index}.{_quote_identifier(dimension.label_column)}"
        )
    raise ValueError(f"No DuckDB dimension configured for {column!r}")


def _delete_id_resolution_join(
    integer_table: IntegerKeyedTableDefinition, column: str, index: int
) -> str:
    dimension = integer_table.dimensions.get(column)
    if dimension is not None:
        return (
            f"LEFT JOIN {dimension.table_name} dim_{index} "
            f"ON CAST(stage.{_quote_identifier(column)} AS TEXT) = "
            f"dim_{index}.{_quote_identifier(dimension.label_column)}"
        )
    raise ValueError(f"No DuckDB dimension configured for {column!r}")


def _delete_unique_predicate(
    integer_table: IntegerKeyedTableDefinition, column: str, index: int
) -> str:
    dimension = integer_table.dimensions.get(column)
    if dimension is not None:
        stored_column = f"stored.{_quote_identifier(dimension.physical_column)}"
        dimension_column = f"dim_{index}.{_quote_identifier(dimension.id_column)}"
        return f"{stored_column} IS NOT DISTINCT FROM {dimension_column}"
    if column in integer_table.catalog_columns:
        stored_column = f"stored.{_quote_identifier(column)}"
        stage_column = f"stage.{_quote_identifier(column)}"
        resolved_column = f"CAST({stage_column} AS BIGINT)"
        return f"{stored_column} IS NOT DISTINCT FROM {resolved_column}"
    return (
        f"CAST(stored.{_quote_identifier(column)} AS TEXT) IS NOT DISTINCT FROM "
        f"CAST(stage.{_quote_identifier(column)} AS TEXT)"
    )


def _delete_public_select_predicate(column: str) -> str:
    quoted_column = _quote_identifier(column)
    return f"{quoted_column} IS NOT DISTINCT FROM source.{quoted_column}"


def _upsert_dimension_from_stage(
    connection: duckdb.DuckDBPyConnection,
    dimension: DuckDBDimension,
    stage_table: str,
    stage_column: str,
) -> None:
    connection.execute(f"""
        INSERT INTO {dimension.table_name} (
            {_quote_identifier(dimension.id_column)},
            {_quote_identifier(dimension.label_column)}
        )
        WITH incoming AS (
            SELECT DISTINCT CAST({_quote_identifier(stage_column)} AS TEXT) AS value
            FROM {stage_table}
            WHERE {_quote_identifier(stage_column)} IS NOT NULL
        ),
        new_values AS (
            SELECT incoming.value
            FROM incoming
            LEFT JOIN {dimension.table_name} dim
                ON incoming.value = dim.{_quote_identifier(dimension.label_column)}
            WHERE dim.{_quote_identifier(dimension.label_column)} IS NULL
        ),
        base AS (
            SELECT coalesce(max({_quote_identifier(dimension.id_column)}), 0) AS max_id
            FROM {dimension.table_name}
        )
        SELECT
            base.max_id + row_number() OVER (ORDER BY new_values.value),
            new_values.value
        FROM new_values, base
        """)


def _upsert_dimension_from_select(
    connection: duckdb.DuckDBPyConnection,
    dimension: DuckDBDimension,
    select_sql: str,
    column: str,
    parameters: Sequence[Any],
) -> None:
    quoted_column = _quote_identifier(column)
    connection.execute(
        f"""
        INSERT INTO {dimension.table_name} (
            {_quote_identifier(dimension.id_column)},
            {_quote_identifier(dimension.label_column)}
        )
        WITH incoming AS (
            SELECT DISTINCT CAST(source.{quoted_column} AS TEXT) AS value
            FROM ({select_sql}) source
            WHERE source.{quoted_column} IS NOT NULL
        ),
        new_values AS (
            SELECT incoming.value
            FROM incoming
            LEFT JOIN {dimension.table_name} dim
                ON incoming.value = dim.{_quote_identifier(dimension.label_column)}
            WHERE dim.{_quote_identifier(dimension.label_column)} IS NULL
        ),
        base AS (
            SELECT coalesce(max({_quote_identifier(dimension.id_column)}), 0) AS max_id
            FROM {dimension.table_name}
        )
        SELECT
            base.max_id + row_number() OVER (ORDER BY new_values.value),
            new_values.value
        FROM new_values, base
        """,
        list(parameters),
    )


def validate_records(
    table_name: str,
    records: Iterable[dict[str, Any] | BaseModel],
) -> list[BaseModel]:
    """Validate records against the registered model for an analytical table."""

    serializer = SERIALIZERS_BY_TABLE[table_name]
    return [serializer.model_type.model_validate(record) for record in records]


def _field_column_name(field_name: str, field_info: Any) -> str:
    return str(field_info.alias or field_name)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _drop_view_if_exists(connection: duckdb.DuckDBPyConnection, view_name: str) -> None:
    row = connection.execute(
        """
        SELECT table_type
        FROM information_schema.tables
        WHERE table_schema = current_schema()
        AND table_name = ?
        """,
        [view_name],
    ).fetchone()
    if row is not None and str(row[0]).upper() == "VIEW":
        connection.execute(f"DROP VIEW {_quote_identifier(view_name)}")


def _column_list(columns: Sequence[str]) -> str:
    return ", ".join(_quote_identifier(column) for column in columns)


def _quote_order_by(order_by: str) -> str:
    clauses: list[str] = []
    for raw_clause in order_by.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        parts = clause.split()
        column = parts[0]
        suffix = " ".join(parts[1:])
        quoted_column = _quote_identifier(column)
        clauses.append(f"{quoted_column} {suffix}" if suffix else quoted_column)
    return ", ".join(clauses)


def _text_stage_columns(columns: Sequence[str]) -> str:
    return ", ".join(f"{_quote_identifier(column)} TEXT" for column in columns)


def _physical_order_by(
    integer_table: IntegerKeyedTableDefinition, order_by: str
) -> str:
    clauses: list[str] = []
    for raw_clause in order_by.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        parts = clause.split()
        column = parts[0]
        dimension = integer_table.dimensions.get(column)
        physical_column = dimension.physical_column if dimension is not None else column
        suffix = " ".join(parts[1:])
        quoted_column = _quote_identifier(physical_column)
        clauses.append(f"{quoted_column} {suffix}" if suffix else quoted_column)
    return ", ".join(clauses)


def _field_name_for_column(model_type: type[BaseModel], column: str) -> str:
    for field_name, field_info in model_type.model_fields.items():
        if _field_column_name(field_name, field_info) == column:
            return field_name
    return column


def _duckdb_type_for_field(annotation: Any, column: str) -> str:
    if _is_json_column(column):
        return "JSON"
    annotation = _strip_optional(annotation)
    origin = get_origin(annotation)
    if origin is Literal:
        return "TEXT"
    if origin in {dict, list}:
        return "JSON"
    if origin in {UnionType, Union}:
        return "TEXT"
    if annotation is str:
        return "TEXT"
    if annotation is int:
        return "BIGINT"
    if annotation is float:
        return "DOUBLE"
    if annotation is bool:
        return "BOOLEAN"
    if annotation in {date, datetime}:
        return "TIMESTAMP"
    return "TEXT"


def _strip_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin not in {UnionType, Union}:
        return annotation
    args = tuple(arg for arg in get_args(annotation) if arg is not type(None))
    return args[0] if len(args) == 1 else annotation


def _field_value(record: Any, column: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(column)
    if isinstance(record, BaseModel):
        extra = record.model_extra or {}
        if column in extra:
            return extra[column]
        field_name = _field_name_for_column(type(record), column)
        if field_name in type(record).model_fields:
            return getattr(record, field_name)
        if field_name in extra:
            return extra[field_name]
        return None
    field_name = _field_name_for_column(type(record), column)
    return getattr(record, field_name)


def _to_db_value(value: Any) -> Any:
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _from_db_value(column: str, value: Any) -> Any:
    if isinstance(value, str) and value and value[0] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _is_json_column(column: str) -> bool:
    return column.endswith("_json") or column in {
        "value_json",
        "info_json",
        "format_json",
        "annotation_json",
        "metadata_json",
        "schema_json",
    }
