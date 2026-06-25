from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import UnionType
from typing import Any, Literal, TypeVar, Union, get_args, get_origin

import duckdb
from pydantic import BaseModel

from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    AttributeDefinition,
    CohortSummary,
    CopyNumberSegment,
    DataSource,
    DuckDBMetadata,
    EntityAttributeBoolean,
    EntityAttributeDate,
    EntityAttributeJson,
    EntityAttributeNumeric,
    EntityAttributeString,
    Feature,
    FeatureAlias,
    FeatureCall,
    FeatureSet,
    FeatureSetMember,
    FeatureValueNumeric,
    GeneAlterationState,
    GenomicInterval,
    MetricDefinition,
    ProfileObservationSet,
    ProfilePayload,
    SampleIntervalValue,
    SampleMetricJson,
    SampleMetricNumeric,
    SampleMetricString,
    SampleProfileCache,
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
    # One serializer is the complete adapter between an AnalyticsIngestBatch
    # field, a Pydantic record model, and a physical DuckDB table.
    table_name: str
    model_type: type[BaseModel]
    order_by: str
    # Defaults to the table name because AnalyticsIngestBatch uses matching
    # field names for almost every analytical table.
    batch_field: str | None = None
    # Tables with a run column can be replaced one run at a time during ingest.
    run_column: str | None = None
    # Dimension/reference tables use natural keys so repeated imports update by
    # deleting matching rows before inserting the latest records.
    unique_columns: tuple[str, ...] = ()
    # Escape hatch for physical storage choices that Pydantic annotations do not
    # fully express, such as keeping call_rank as INTEGER instead of BIGINT.
    column_types: dict[str, str] = field(default_factory=dict)

    @property
    def resolved_batch_field(self) -> str:
        return self.batch_field or self.table_name

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(
            _field_column_name(field_name, field_info)
            for field_name, field_info in self.model_type.model_fields.items()
        )

    @property
    def column_sql(self) -> tuple[str, ...]:
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
        columns = ",\n                    ".join(self.column_sql)
        return f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    {columns}
                )
                """

    def create_table(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(self.create_sql)

    def create_sorted_view(self, connection: duckdb.DuckDBPyConnection) -> None:
        # Sorted views give API/query callers deterministic row order without
        # requiring every query to remember the table-specific ORDER BY clause.
        view_name = f"{self.table_name}_sorted"
        connection.execute(f"DROP VIEW IF EXISTS {view_name}")
        connection.execute(
            f"CREATE VIEW {view_name} AS SELECT * FROM {self.table_name} "
            f"ORDER BY {self.order_by}"
        )

    def delete_run(
        self, connection: duckdb.DuckDBPyConnection, run_id: str | None
    ) -> None:
        if run_id is None or self.run_column is None:
            return
        connection.execute(
            f"DELETE FROM {self.table_name} WHERE {self.run_column} = ?", [run_id]
        )

    def delete_unique_values(
        self,
        connection: duckdb.DuckDBPyConnection,
        records: Sequence[BaseModel],
    ) -> None:
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
        connection.executemany(
            f"DELETE FROM {self.table_name} WHERE {where}",
            [tuple(value) for value in values],
        )

    def insert_records(
        self,
        connection: duckdb.DuckDBPyConnection,
        records: Sequence[BaseModel],
    ) -> None:
        if not records:
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

    def records_from_batch(self, batch: AnalyticsIngestBatch) -> list[BaseModel]:
        # The batch field name and model type are paired here, which lets the
        # write loop handle every analytical table with the same code path.
        raw_records = getattr(batch, self.resolved_batch_field)
        return [self.model_type.model_validate(record) for record in raw_records]


# SERIALIZERS is the DuckDB analytical schema registry. Adding a new analytical
# table generally means adding a Pydantic model/list field to AnalyticsIngestBatch
# and then adding one serializer entry here for table-specific behavior.
SERIALIZERS: tuple[AnalyticalTableSerializer, ...] = (
    AnalyticalTableSerializer(
        "duckdb_metadata",
        DuckDBMetadata,
        "project_id",
        unique_columns=("project_id",),
    ),
    AnalyticalTableSerializer(
        "metric_definitions",
        MetricDefinition,
        "metric_key, metric_id",
        unique_columns=("metric_key", "metric_id"),
    ),
    AnalyticalTableSerializer(
        "attribute_definitions",
        AttributeDefinition,
        "entity_scope, attribute_key",
        unique_columns=("entity_scope", "attribute_key", "attribute_id"),
        column_types={
            "attribute_key": "TEXT",
        },
    ),
    AnalyticalTableSerializer(
        "entity_attribute_numeric",
        EntityAttributeNumeric,
        "entity_scope, entity_key, attribute_key",
        unique_columns=(
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
        ),
    ),
    AnalyticalTableSerializer(
        "entity_attribute_string",
        EntityAttributeString,
        "entity_scope, entity_key, attribute_key",
        unique_columns=(
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
        ),
    ),
    AnalyticalTableSerializer(
        "entity_attribute_boolean",
        EntityAttributeBoolean,
        "entity_scope, entity_key, attribute_key",
        unique_columns=(
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
        ),
    ),
    AnalyticalTableSerializer(
        "entity_attribute_date",
        EntityAttributeDate,
        "entity_scope, entity_key, attribute_key",
        unique_columns=(
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
        ),
    ),
    AnalyticalTableSerializer(
        "entity_attribute_json",
        EntityAttributeJson,
        "entity_scope, entity_key, attribute_key",
        unique_columns=(
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
        ),
    ),
    AnalyticalTableSerializer(
        "sample_metric_numeric",
        SampleMetricNumeric,
        "data_profile_key, run_id, run_sample_key, metric_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "sample_metric_string",
        SampleMetricString,
        "data_profile_key, run_id, run_sample_key, metric_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "sample_metric_json",
        SampleMetricJson,
        "data_profile_key, run_id, run_sample_key, metric_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "features",
        Feature,
        "feature_type, feature_key",
        unique_columns=("feature_key",),
    ),
    AnalyticalTableSerializer(
        "feature_aliases",
        FeatureAlias,
        "feature_key, alias",
        unique_columns=("feature_key", "alias", "namespace"),
    ),
    AnalyticalTableSerializer(
        "feature_sets",
        FeatureSet,
        "feature_set_type, feature_set_key",
        unique_columns=("feature_set_key",),
    ),
    AnalyticalTableSerializer(
        "feature_set_members",
        FeatureSetMember,
        "feature_set_key, feature_key",
        unique_columns=("feature_set_key", "feature_key"),
    ),
    AnalyticalTableSerializer(
        "profile_observation_sets",
        ProfileObservationSet,
        "run_sample_key, data_profile_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "feature_value_numeric",
        FeatureValueNumeric,
        "data_profile_key, feature_key, run_sample_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "feature_call",
        FeatureCall,
        "data_profile_key, feature_key, call_code, run_sample_key",
        run_column="run_id",
        column_types={
            "call_rank": "INTEGER",
        },
    ),
    AnalyticalTableSerializer(
        "genomic_intervals",
        GenomicInterval,
        "genome_build, contig, start_pos, end_pos",
        unique_columns=("interval_key",),
    ),
    AnalyticalTableSerializer(
        "sample_interval_values",
        SampleIntervalValue,
        "data_profile_key, run_sample_key, interval_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "copy_number_segments",
        CopyNumberSegment,
        "data_profile_key, run_sample_key, contig, start_pos",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "variants",
        Variant,
        "genome_build, contig, pos, end_pos, variant_key",
        unique_columns=("variant_key",),
    ),
    AnalyticalTableSerializer(
        "variant_annotations",
        VariantAnnotation,
        "variant_key, data_profile_key, feature_key",
        unique_columns=(
            "data_profile_key",
            "variant_key",
            "feature_key",
            "consequence",
        ),
    ),
    AnalyticalTableSerializer(
        "variant_transcript_annotations",
        VariantTranscriptAnnotation,
        "variant_key, transcript_feature_key",
        unique_columns=("data_profile_key", "variant_key", "transcript_feature_key"),
    ),
    AnalyticalTableSerializer(
        "sample_variant_calls",
        SampleVariantCall,
        "data_profile_key, run_sample_key, variant_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "structural_variant_events",
        StructuralVariantEvent,
        "structural_variant_key",
        unique_columns=("structural_variant_key",),
    ),
    AnalyticalTableSerializer(
        "sample_structural_variant_calls",
        SampleStructuralVariantCall,
        "data_profile_key, run_sample_key, structural_variant_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "timeline_events",
        TimelineEvent,
        "subject_key, event_type, start_time",
        unique_columns=("event_key",),
    ),
    AnalyticalTableSerializer(
        "profile_payloads",
        ProfilePayload,
        "data_profile_key, run_id, run_sample_key, payload_name",
        run_column="run_id",
        unique_columns=("payload_id",),
    ),
    AnalyticalTableSerializer(
        "gene_alteration_state",
        GeneAlterationState,
        "feature_key, alteration_type, data_profile_key, run_sample_key",
    ),
    AnalyticalTableSerializer(
        "sample_profile_cache",
        SampleProfileCache,
        "run_sample_key",
        unique_columns=("run_sample_key",),
    ),
    AnalyticalTableSerializer(
        "cohort_summaries",
        CohortSummary,
        "sample_set_id, data_profile_key, metric_key, feature_key",
        unique_columns=(
            "sample_set_id",
            "data_profile_key",
            "metric_key",
            "feature_key",
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
        "run_id, sample_key, tool, module",
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


class DuckDBAnalyticsStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.path))

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            # The registry is the source of truth for physical DuckDB tables.
            for serializer in SERIALIZERS:
                serializer.create_table(connection)
                serializer.create_sorted_view(connection)
            self._create_derived_views(connection)

    def write_batch(
        self,
        batch: AnalyticsIngestBatch,
        *,
        replace_run_id: str | None = None,
        replace_run_ids: Sequence[str] | None = None,
        refresh_derived: bool = True,
    ) -> None:
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
                    connection.execute(
                        """
                        DELETE FROM gene_alteration_state
                        WHERE run_sample_key IN (
                            SELECT DISTINCT run_sample_key
                            FROM profile_observation_sets
                            WHERE run_id = ?
                        )
                        """,
                        [run_id],
                    )

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
                    self._refresh_sample_profile_cache(
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
        replace_run_id: str | None = None,
        replace_run_ids: Sequence[str] | None = None,
        bulk_load_progress: Callable[[Any, int, int], None] | None = None,
    ) -> None:
        self.write_batch(
            batch,
            replace_run_id=replace_run_id,
            replace_run_ids=replace_run_ids,
            refresh_derived=False,
        )
        if not bulk_loads:
            with self._connect() as connection:
                refresh_run_id = (
                    replace_run_id
                    if replace_run_id is not None and not replace_run_ids
                    else None
                )
                self._refresh_gene_alteration_state(connection, run_id=refresh_run_id)
                self._refresh_sample_profile_cache(connection, run_id=refresh_run_id)
            return

        self.ensure_schema()
        with self._connect() as connection:
            connection.begin()
            try:
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
                self._refresh_sample_profile_cache(connection, run_id=refresh_run_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def replace_run_data(
        self,
        run_id: str,
        batch: AnalyticsIngestBatch | None = None,
        *,
        metrics: Sequence[SampleMetricNumeric | SampleMetricString] | None = None,
        definitions: Sequence[MetricDefinition] | None = None,
        payloads: Sequence[ProfilePayload] | None = None,
        tool_versions: Sequence[ToolVersion] | None = None,
        data_sources: Sequence[DataSource] | None = None,
    ) -> None:
        if batch is None:
            metric_records = list(metrics or [])
            batch = AnalyticsIngestBatch(
                metric_definitions=list(definitions or []),
                sample_metric_numeric=[
                    metric
                    for metric in metric_records
                    if isinstance(metric, SampleMetricNumeric)
                ],
                sample_metric_string=[
                    metric
                    for metric in metric_records
                    if isinstance(metric, SampleMetricString)
                ],
                profile_payloads=list(payloads or []),
                tool_versions=list(tool_versions or []),
                data_sources=list(data_sources or []),
            )
        self.write_batch(batch, replace_run_id=run_id, refresh_derived=True)

    def fetch_records(
        self, table_name: str, model_type: type[RecordT], *, run_id: str | None = None
    ) -> list[RecordT]:
        serializer = SERIALIZERS_BY_TABLE[table_name]
        if not self.path.exists():
            return []
        self.ensure_schema()
        query = f"SELECT {', '.join(serializer.columns)} FROM {table_name}"
        parameters: list[str] = []
        if run_id is not None and serializer.run_column is not None:
            query += f" WHERE {serializer.run_column} = ?"
            parameters.append(run_id)
        query += f" ORDER BY {serializer.order_by}"
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
        run_id: str,
        *,
        sample_key: str | None = None,
        run_sample_key: str | None = None,
    ) -> list[SampleMetricNumeric | SampleMetricString]:
        numeric = self.fetch_records(
            "sample_metric_numeric", SampleMetricNumeric, run_id=run_id
        )
        string = self.fetch_records(
            "sample_metric_string", SampleMetricString, run_id=run_id
        )
        values = [*numeric, *string]
        if sample_key is None and run_sample_key is None:
            return values
        return [
            value
            for value in values
            if (sample_key is not None and value.sample_key == sample_key)
            or (run_sample_key is not None and value.run_sample_key == run_sample_key)
        ]

    def list_profile_payloads(self, run_id: str) -> list[ProfilePayload]:
        return self.fetch_records("profile_payloads", ProfilePayload, run_id=run_id)

    def list_table_payloads(self, run_id: str) -> list[ProfilePayload]:
        return self.list_profile_payloads(run_id)

    def row_counts(self) -> dict[str, int]:
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
        serializer = SERIALIZERS_BY_TABLE[table_name]
        columns = list(serializer.columns)
        if not self.path.exists():
            return columns, [], 0
        self.ensure_schema()
        order_by = serializer.order_by
        if sort_by is not None:
            if sort_by not in serializer.columns:
                raise ValueError(f"Unknown analytical table column: {sort_by}")
            direction = "DESC" if sort_direction == "desc" else "ASC"
            order_by = f"{sort_by} {direction}"
        query = (
            f"SELECT {', '.join(serializer.columns)} FROM {table_name} "
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

    def database_size_bytes(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    def _create_derived_views(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE VIEW sample_metric_numeric_by_metric AS
            SELECT *
            FROM sample_metric_numeric
            ORDER BY data_profile_key, metric_key, value, run_sample_key
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW feature_value_numeric_by_sample AS
            SELECT *
            FROM feature_value_numeric
            ORDER BY data_profile_key, run_sample_key, feature_key
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW feature_call_by_sample AS
            SELECT *
            FROM feature_call
            ORDER BY data_profile_key, run_sample_key, feature_key
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW sample_variant_calls_by_variant AS
            SELECT *
            FROM sample_variant_calls
            ORDER BY data_profile_key, variant_key, run_sample_key
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW copy_number_segments_by_region AS
            SELECT *
            FROM copy_number_segments
            ORDER BY genome_build, contig, start_pos, end_pos,
                data_profile_key, run_sample_key
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW gene_alteration_state_by_sample AS
            SELECT *
            FROM gene_alteration_state
            ORDER BY run_sample_key, feature_key, alteration_type
            """
        )

    def _refresh_gene_alteration_state(
        self, connection: duckdb.DuckDBPyConnection, *, run_id: str | None
    ) -> None:
        if run_id is None:
            connection.execute("DELETE FROM gene_alteration_state")
            svc_run_filter = "WHERE TRUE"
            feature_call_run_filter = "WHERE TRUE"
            sv_run_filter = "WHERE TRUE"
            parameters: list[str] = []
        else:
            connection.execute(
                """
                DELETE FROM gene_alteration_state
                WHERE run_sample_key IN (
                    SELECT DISTINCT run_sample_key
                    FROM sample_variant_calls
                    WHERE run_id = ?
                    UNION
                    SELECT DISTINCT run_sample_key
                    FROM feature_call
                    WHERE run_id = ?
                    UNION
                    SELECT DISTINCT run_sample_key
                    FROM sample_structural_variant_calls
                    WHERE run_id = ?
                )
                """,
                [run_id, run_id, run_id],
            )
            svc_run_filter = "WHERE svc.run_id = ?"
            feature_call_run_filter = "WHERE run_id = ?"
            sv_run_filter = "WHERE ssvc.run_id = ?"
            parameters = [run_id]

        connection.execute(
            f"""
            INSERT INTO gene_alteration_state
            SELECT
                svc.run_sample_key,
                svc.sample_key,
                NULL AS subject_key,
                va.feature_key,
                svc.data_profile_key,
                'mutation' AS alteration_type,
                va.consequence AS alteration_subtype,
                TRUE AS is_altered,
                svc.allele_fraction AS value_numeric,
                svc.genotype AS value_string,
                NULL AS driver_status,
                'sample_variant_calls' AS source_table,
                svc.variant_key AS source_event_id
            FROM sample_variant_calls svc
            LEFT JOIN variant_annotations va ON svc.variant_key = va.variant_key
            {svc_run_filter}
            AND va.feature_key IS NOT NULL
            """,
            parameters,
        )
        connection.execute(
            f"""
            INSERT INTO gene_alteration_state
            SELECT
                run_sample_key,
                sample_key,
                NULL AS subject_key,
                feature_key,
                data_profile_key,
                'feature_call' AS alteration_type,
                call_code AS alteration_subtype,
                TRUE AS is_altered,
                score AS value_numeric,
                call_code AS value_string,
                NULL AS driver_status,
                'feature_call' AS source_table,
                source_event_id
            FROM feature_call
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
        connection.execute(
            f"""
            INSERT INTO gene_alteration_state
            SELECT
                ssvc.run_sample_key,
                ssvc.sample_key,
                NULL AS subject_key,
                sve.site1_feature_key AS feature_key,
                ssvc.data_profile_key,
                'sv' AS alteration_type,
                sve.event_class AS alteration_subtype,
                TRUE AS is_altered,
                NULL AS value_numeric,
                ssvc.call_status AS value_string,
                NULL AS driver_status,
                'sample_structural_variant_calls' AS source_table,
                ssvc.structural_variant_key AS source_event_id
            FROM sample_structural_variant_calls ssvc
            JOIN structural_variant_events sve
                ON ssvc.structural_variant_key = sve.structural_variant_key
            {sv_run_filter}
            AND sve.site1_feature_key IS NOT NULL
            """,
            parameters,
        )
        connection.execute(
            f"""
            INSERT INTO gene_alteration_state
            SELECT
                ssvc.run_sample_key,
                ssvc.sample_key,
                NULL AS subject_key,
                sve.site2_feature_key AS feature_key,
                ssvc.data_profile_key,
                'sv' AS alteration_type,
                sve.event_class AS alteration_subtype,
                TRUE AS is_altered,
                NULL AS value_numeric,
                ssvc.call_status AS value_string,
                NULL AS driver_status,
                'sample_structural_variant_calls' AS source_table,
                ssvc.structural_variant_key AS source_event_id
            FROM sample_structural_variant_calls ssvc
            JOIN structural_variant_events sve
                ON ssvc.structural_variant_key = sve.structural_variant_key
            {sv_run_filter}
            AND sve.site2_feature_key IS NOT NULL
            AND (
                sve.site1_feature_key IS NULL
                OR sve.site2_feature_key != sve.site1_feature_key
            )
            """,
            parameters,
        )

    def _refresh_sample_profile_cache(
        self, connection: duckdb.DuckDBPyConnection, *, run_id: str | None
    ) -> None:
        if run_id is None:
            connection.execute("DELETE FROM sample_profile_cache")
            run_filter = "WHERE TRUE"
            parameters: list[str] = []
        else:
            connection.execute(
                """
                DELETE FROM sample_profile_cache
                WHERE run_sample_key IN (
                    SELECT DISTINCT run_sample_key
                    FROM profile_observation_sets
                    WHERE run_id = ?
                )
                """,
                [run_id],
            )
            run_filter = "WHERE run_id = ?"
            parameters = [run_id]

        connection.execute(
            f"""
            INSERT INTO sample_profile_cache
            SELECT
                run_sample_key,
                json_object(
                    'profiles', list(data_profile_key),
                    'availability', list(availability_status)
                ) AS profile_summary_json,
                current_timestamp AS updated_at
            FROM profile_observation_sets
            {run_filter}
            GROUP BY run_sample_key
            """,
            parameters,
        )


def validate_records(
    table_name: str,
    records: Iterable[dict[str, Any] | BaseModel],
) -> list[BaseModel]:
    serializer = SERIALIZERS_BY_TABLE[table_name]
    return [serializer.model_type.model_validate(record) for record in records]


def _field_column_name(field_name: str, field_info: Any) -> str:
    return str(field_info.alias or field_name)


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


def _field_value(record: BaseModel, column: str) -> Any:
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
    if (
        _is_json_column(column)
        and isinstance(value, str)
        and value
        and value[0] in "[{"
    ):
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
        "profile_summary_json",
    }
