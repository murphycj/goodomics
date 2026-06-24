from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar

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
    table_name: str
    batch_field: str
    model_type: type[BaseModel]
    columns: tuple[str, ...]
    column_sql: tuple[str, ...]
    order_by: str
    run_column: str | None = None
    unique_columns: tuple[str, ...] = ()

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
        raw_records = getattr(batch, self.batch_field)
        return [self.model_type.model_validate(record) for record in raw_records]


SERIALIZERS: tuple[AnalyticalTableSerializer, ...] = (
    AnalyticalTableSerializer(
        "duckdb_metadata",
        "duckdb_metadata",
        DuckDBMetadata,
        (
            "project_id",
            "project_name",
            "schema_version",
            "created_at",
            "updated_at",
            "metadata_json",
        ),
        (
            "project_id TEXT",
            "project_name TEXT",
            "schema_version TEXT",
            "created_at TIMESTAMP",
            "updated_at TIMESTAMP",
            "metadata_json JSON",
        ),
        "project_id",
        unique_columns=("project_id",),
    ),
    AnalyticalTableSerializer(
        "metric_definitions",
        "metric_definitions",
        MetricDefinition,
        (
            "metric_key",
            "metric_id",
            "namespace",
            "metric_name",
            "display_name",
            "value_type",
            "unit",
            "direction",
            "description",
            "producer_tool",
            "producer_module",
            "schema_version",
        ),
        (
            "metric_key TEXT",
            "metric_id TEXT",
            "namespace TEXT",
            "metric_name TEXT",
            "display_name TEXT",
            "value_type TEXT",
            "unit TEXT",
            "direction TEXT",
            "description TEXT",
            "producer_tool TEXT",
            "producer_module TEXT",
            "schema_version TEXT",
        ),
        "metric_key, metric_id",
        unique_columns=("metric_key", "metric_id"),
    ),
    AnalyticalTableSerializer(
        "attribute_definitions",
        "attribute_definitions",
        AttributeDefinition,
        (
            "attribute_key",
            "attribute_id",
            "entity_scope",
            "display_name",
            "value_type",
            "unit",
            "description",
            "priority",
            "metadata_json",
        ),
        (
            "attribute_key TEXT",
            "attribute_id TEXT",
            "entity_scope TEXT",
            "display_name TEXT",
            "value_type TEXT",
            "unit TEXT",
            "description TEXT",
            "priority TEXT",
            "metadata_json JSON",
        ),
        "entity_scope, attribute_key",
        unique_columns=("entity_scope", "attribute_key", "attribute_id"),
    ),
    AnalyticalTableSerializer(
        "entity_attribute_numeric",
        "entity_attribute_numeric",
        EntityAttributeNumeric,
        (
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
            "source_file_id",
            "value",
        ),
        (
            "entity_scope TEXT",
            "entity_key TEXT",
            "attribute_key TEXT",
            "data_profile_key TEXT",
            "source_file_id TEXT",
            "value DOUBLE",
        ),
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
        "entity_attribute_string",
        EntityAttributeString,
        (
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
            "source_file_id",
            "value",
        ),
        (
            "entity_scope TEXT",
            "entity_key TEXT",
            "attribute_key TEXT",
            "data_profile_key TEXT",
            "source_file_id TEXT",
            "value TEXT",
        ),
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
        "entity_attribute_boolean",
        EntityAttributeBoolean,
        (
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
            "source_file_id",
            "value",
        ),
        (
            "entity_scope TEXT",
            "entity_key TEXT",
            "attribute_key TEXT",
            "data_profile_key TEXT",
            "source_file_id TEXT",
            "value BOOLEAN",
        ),
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
        "entity_attribute_date",
        EntityAttributeDate,
        (
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
            "source_file_id",
            "value",
        ),
        (
            "entity_scope TEXT",
            "entity_key TEXT",
            "attribute_key TEXT",
            "data_profile_key TEXT",
            "source_file_id TEXT",
            "value TIMESTAMP",
        ),
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
        "entity_attribute_json",
        EntityAttributeJson,
        (
            "entity_scope",
            "entity_key",
            "attribute_key",
            "data_profile_key",
            "source_file_id",
            "value_json",
        ),
        (
            "entity_scope TEXT",
            "entity_key TEXT",
            "attribute_key TEXT",
            "data_profile_key TEXT",
            "source_file_id TEXT",
            "value_json JSON",
        ),
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
        "sample_metric_numeric",
        SampleMetricNumeric,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "metric_key",
            "source_file_id",
            "value",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "metric_key TEXT",
            "source_file_id TEXT",
            "value DOUBLE",
        ),
        "data_profile_key, run_id, run_sample_key, metric_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "sample_metric_string",
        "sample_metric_string",
        SampleMetricString,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "metric_key",
            "source_file_id",
            "value",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "metric_key TEXT",
            "source_file_id TEXT",
            "value TEXT",
        ),
        "data_profile_key, run_id, run_sample_key, metric_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "sample_metric_json",
        "sample_metric_json",
        SampleMetricJson,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "metric_key",
            "source_file_id",
            "value_json",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "metric_key TEXT",
            "source_file_id TEXT",
            "value_json JSON",
        ),
        "data_profile_key, run_id, run_sample_key, metric_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "features",
        "features",
        Feature,
        (
            "feature_key",
            "feature_id",
            "feature_type",
            "symbol",
            "stable_id",
            "namespace",
            "genome_build",
            "metadata_json",
        ),
        (
            "feature_key TEXT",
            "feature_id TEXT",
            "feature_type TEXT",
            "symbol TEXT",
            "stable_id TEXT",
            "namespace TEXT",
            "genome_build TEXT",
            "metadata_json JSON",
        ),
        "feature_type, feature_key",
        unique_columns=("feature_key",),
    ),
    AnalyticalTableSerializer(
        "feature_aliases",
        "feature_aliases",
        FeatureAlias,
        ("feature_key", "alias", "namespace"),
        ("feature_key TEXT", "alias TEXT", "namespace TEXT"),
        "feature_key, alias",
        unique_columns=("feature_key", "alias", "namespace"),
    ),
    AnalyticalTableSerializer(
        "feature_sets",
        "feature_sets",
        FeatureSet,
        (
            "feature_set_key",
            "feature_set_id",
            "feature_set_type",
            "name",
            "description",
            "metadata_json",
        ),
        (
            "feature_set_key TEXT",
            "feature_set_id TEXT",
            "feature_set_type TEXT",
            "name TEXT",
            "description TEXT",
            "metadata_json JSON",
        ),
        "feature_set_type, feature_set_key",
        unique_columns=("feature_set_key",),
    ),
    AnalyticalTableSerializer(
        "feature_set_members",
        "feature_set_members",
        FeatureSetMember,
        ("feature_set_key", "feature_key", "member_role", "metadata_json"),
        (
            "feature_set_key TEXT",
            "feature_key TEXT",
            "member_role TEXT",
            "metadata_json JSON",
        ),
        "feature_set_key, feature_key",
        unique_columns=("feature_set_key", "feature_key"),
    ),
    AnalyticalTableSerializer(
        "profile_observation_sets",
        "profile_observation_sets",
        ProfileObservationSet,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "subject_key",
            "availability_status",
            "feature_set_key",
            "source_file_id",
            "missing_reason",
            "metadata_json",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "subject_key TEXT",
            "availability_status TEXT",
            "feature_set_key TEXT",
            "source_file_id TEXT",
            "missing_reason TEXT",
            "metadata_json JSON",
        ),
        "run_sample_key, data_profile_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "feature_value_numeric",
        "feature_value_numeric",
        FeatureValueNumeric,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "feature_key",
            "value",
            "value_semantics",
            "source_file_id",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "feature_key TEXT",
            "value DOUBLE",
            "value_semantics TEXT",
            "source_file_id TEXT",
        ),
        "data_profile_key, feature_key, run_sample_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "feature_call",
        "feature_call",
        FeatureCall,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "feature_key",
            "call_code",
            "call_label",
            "call_rank",
            "score",
            "confidence",
            "source_event_id",
            "source_file_id",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "feature_key TEXT",
            "call_code TEXT",
            "call_label TEXT",
            "call_rank INTEGER",
            "score DOUBLE",
            "confidence DOUBLE",
            "source_event_id TEXT",
            "source_file_id TEXT",
        ),
        "data_profile_key, feature_key, call_code, run_sample_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "genomic_intervals",
        "genomic_intervals",
        GenomicInterval,
        (
            "interval_key",
            "genome_build",
            "contig",
            "start_pos",
            "end_pos",
            "strand",
            "feature_key",
            "interval_type",
            "metadata_json",
        ),
        (
            "interval_key TEXT",
            "genome_build TEXT",
            "contig TEXT",
            "start_pos BIGINT",
            "end_pos BIGINT",
            "strand TEXT",
            "feature_key TEXT",
            "interval_type TEXT",
            "metadata_json JSON",
        ),
        "genome_build, contig, start_pos, end_pos",
        unique_columns=("interval_key",),
    ),
    AnalyticalTableSerializer(
        "sample_interval_values",
        "sample_interval_values",
        SampleIntervalValue,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "interval_key",
            "value",
            "value_semantics",
            "source_file_id",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "interval_key TEXT",
            "value DOUBLE",
            "value_semantics TEXT",
            "source_file_id TEXT",
        ),
        "data_profile_key, run_sample_key, interval_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "copy_number_segments",
        "copy_number_segments",
        CopyNumberSegment,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "genome_build",
            "contig",
            "start_pos",
            "end_pos",
            "num_probes",
            "segment_mean",
            "total_copy_number",
            "minor_copy_number",
            "call_label",
            "source_file_id",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "genome_build TEXT",
            "contig TEXT",
            "start_pos BIGINT",
            "end_pos BIGINT",
            "num_probes BIGINT",
            "segment_mean DOUBLE",
            "total_copy_number DOUBLE",
            "minor_copy_number DOUBLE",
            "call_label TEXT",
            "source_file_id TEXT",
        ),
        "data_profile_key, run_sample_key, contig, start_pos",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "variants",
        "variants",
        Variant,
        (
            "variant_key",
            "variant_id",
            "genome_build",
            "contig",
            "pos",
            "end_pos",
            "ref",
            "alt",
            "variant_type",
            "normalized_key",
        ),
        (
            "variant_key TEXT",
            "variant_id TEXT",
            "genome_build TEXT",
            "contig TEXT",
            "pos BIGINT",
            "end_pos BIGINT",
            "ref TEXT",
            "alt TEXT",
            "variant_type TEXT",
            "normalized_key TEXT",
        ),
        "genome_build, contig, pos, end_pos, variant_key",
        unique_columns=("variant_key",),
    ),
    AnalyticalTableSerializer(
        "variant_annotations",
        "variant_annotations",
        VariantAnnotation,
        (
            "data_profile_key",
            "variant_key",
            "feature_key",
            "consequence",
            "impact",
            "clinvar_significance",
            "gnomad_af",
            "info_json",
        ),
        (
            "data_profile_key TEXT",
            "variant_key TEXT",
            "feature_key TEXT",
            "consequence TEXT",
            "impact TEXT",
            "clinvar_significance TEXT",
            "gnomad_af DOUBLE",
            "info_json JSON",
        ),
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
        "variant_transcript_annotations",
        VariantTranscriptAnnotation,
        (
            "data_profile_key",
            "variant_key",
            "transcript_feature_key",
            "gene_feature_key",
            "consequence",
            "impact",
            "protein_change",
            "cdna_change",
            "protein_pos_start",
            "protein_pos_end",
            "canonical",
            "annotation_json",
        ),
        (
            "data_profile_key TEXT",
            "variant_key TEXT",
            "transcript_feature_key TEXT",
            "gene_feature_key TEXT",
            "consequence TEXT",
            "impact TEXT",
            "protein_change TEXT",
            "cdna_change TEXT",
            "protein_pos_start BIGINT",
            "protein_pos_end BIGINT",
            "canonical BOOLEAN",
            "annotation_json JSON",
        ),
        "variant_key, transcript_feature_key",
        unique_columns=("data_profile_key", "variant_key", "transcript_feature_key"),
    ),
    AnalyticalTableSerializer(
        "sample_variant_calls",
        "sample_variant_calls",
        SampleVariantCall,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "variant_key",
            "genotype",
            "depth",
            "genotype_quality",
            "allele_depth_ref",
            "allele_depth_alt",
            "allele_fraction",
            "filter",
            "format_json",
            "source_file_id",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "variant_key TEXT",
            "genotype TEXT",
            "depth BIGINT",
            "genotype_quality DOUBLE",
            "allele_depth_ref BIGINT",
            "allele_depth_alt BIGINT",
            "allele_fraction DOUBLE",
            "filter TEXT",
            "format_json JSON",
            "source_file_id TEXT",
        ),
        "data_profile_key, run_sample_key, variant_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "structural_variant_events",
        "structural_variant_events",
        StructuralVariantEvent,
        (
            "structural_variant_key",
            "event_id",
            "event_class",
            "genome_build",
            "site1_feature_key",
            "site2_feature_key",
            "site1_contig",
            "site1_pos",
            "site2_contig",
            "site2_pos",
            "frame_status",
            "event_info",
            "annotation_json",
        ),
        (
            "structural_variant_key TEXT",
            "event_id TEXT",
            "event_class TEXT",
            "genome_build TEXT",
            "site1_feature_key TEXT",
            "site2_feature_key TEXT",
            "site1_contig TEXT",
            "site1_pos BIGINT",
            "site2_contig TEXT",
            "site2_pos BIGINT",
            "frame_status TEXT",
            "event_info TEXT",
            "annotation_json JSON",
        ),
        "structural_variant_key",
        unique_columns=("structural_variant_key",),
    ),
    AnalyticalTableSerializer(
        "sample_structural_variant_calls",
        "sample_structural_variant_calls",
        SampleStructuralVariantCall,
        (
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "sample_key",
            "structural_variant_key",
            "call_status",
            "dna_support",
            "rna_support",
            "tumor_read_count",
            "normal_read_count",
            "split_read_count",
            "paired_end_read_count",
            "format_json",
            "source_file_id",
        ),
        (
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "structural_variant_key TEXT",
            "call_status TEXT",
            "dna_support TEXT",
            "rna_support TEXT",
            "tumor_read_count BIGINT",
            "normal_read_count BIGINT",
            "split_read_count BIGINT",
            "paired_end_read_count BIGINT",
            "format_json JSON",
            "source_file_id TEXT",
        ),
        "data_profile_key, run_sample_key, structural_variant_key",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "timeline_events",
        "timeline_events",
        TimelineEvent,
        (
            "event_key",
            "subject_key",
            "sample_key",
            "run_sample_key",
            "event_type",
            "start_time",
            "end_time",
            "time_unit",
            "event_status",
            "metadata_json",
        ),
        (
            "event_key TEXT",
            "subject_key TEXT",
            "sample_key TEXT",
            "run_sample_key TEXT",
            "event_type TEXT",
            "start_time TEXT",
            "end_time TEXT",
            "time_unit TEXT",
            "event_status TEXT",
            "metadata_json JSON",
        ),
        "subject_key, event_type, start_time",
        unique_columns=("event_key",),
    ),
    AnalyticalTableSerializer(
        "profile_payloads",
        "profile_payloads",
        ProfilePayload,
        (
            "payload_id",
            "data_profile_key",
            "run_id",
            "run_sample_key",
            "payload_name",
            "payload_kind",
            "storage_format",
            "path",
            "uri",
            "schema_json",
            "row_count",
            "source_file_id",
            "metadata_json",
        ),
        (
            "payload_id TEXT",
            "data_profile_key TEXT",
            "run_id TEXT",
            "run_sample_key TEXT",
            "payload_name TEXT",
            "payload_kind TEXT",
            "storage_format TEXT",
            "path TEXT",
            "uri TEXT",
            "schema_json JSON",
            "row_count BIGINT",
            "source_file_id TEXT",
            "metadata_json JSON",
        ),
        "data_profile_key, run_id, run_sample_key, payload_name",
        run_column="run_id",
        unique_columns=("payload_id",),
    ),
    AnalyticalTableSerializer(
        "gene_alteration_state",
        "gene_alteration_state",
        GeneAlterationState,
        (
            "run_sample_key",
            "sample_key",
            "subject_key",
            "feature_key",
            "data_profile_key",
            "alteration_type",
            "alteration_subtype",
            "is_altered",
            "value_numeric",
            "value_string",
            "driver_status",
            "source_table",
            "source_event_id",
        ),
        (
            "run_sample_key TEXT",
            "sample_key TEXT",
            "subject_key TEXT",
            "feature_key TEXT",
            "data_profile_key TEXT",
            "alteration_type TEXT",
            "alteration_subtype TEXT",
            "is_altered BOOLEAN",
            "value_numeric DOUBLE",
            "value_string TEXT",
            "driver_status TEXT",
            "source_table TEXT",
            "source_event_id TEXT",
        ),
        "feature_key, alteration_type, data_profile_key, run_sample_key",
    ),
    AnalyticalTableSerializer(
        "sample_profile_cache",
        "sample_profile_cache",
        SampleProfileCache,
        ("run_sample_key", "profile_summary_json", "updated_at"),
        ("run_sample_key TEXT", "profile_summary_json JSON", "updated_at TIMESTAMP"),
        "run_sample_key",
        unique_columns=("run_sample_key",),
    ),
    AnalyticalTableSerializer(
        "cohort_summaries",
        "cohort_summaries",
        CohortSummary,
        (
            "sample_set_id",
            "data_profile_key",
            "metric_key",
            "feature_key",
            "n",
            "mean",
            "median",
            "stddev",
            "min",
            "max",
            "q05",
            "q25",
            "q75",
            "q95",
        ),
        (
            "sample_set_id TEXT",
            "data_profile_key TEXT",
            "metric_key TEXT",
            "feature_key TEXT",
            "n BIGINT",
            "mean DOUBLE",
            "median DOUBLE",
            "stddev DOUBLE",
            "min DOUBLE",
            "max DOUBLE",
            "q05 DOUBLE",
            "q25 DOUBLE",
            "q75 DOUBLE",
            "q95 DOUBLE",
        ),
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
        "tool_versions",
        ToolVersion,
        ("run_id", "tool", "version", "source_file_id"),
        ("run_id TEXT", "tool TEXT", "version TEXT", "source_file_id TEXT"),
        "run_id, tool",
        run_column="run_id",
    ),
    AnalyticalTableSerializer(
        "data_sources",
        "data_sources",
        DataSource,
        ("run_id", "run_sample_key", "sample_key", "tool", "module", "source_path"),
        (
            "run_id TEXT",
            "run_sample_key TEXT",
            "sample_key TEXT",
            "tool TEXT",
            "module TEXT",
            "source_path TEXT",
        ),
        "run_id, sample_key, tool, module",
        run_column="run_id",
    ),
)

SERIALIZERS_BY_FIELD = {
    serializer.batch_field: serializer for serializer in SERIALIZERS
}
SERIALIZERS_BY_TABLE = {serializer.table_name: serializer for serializer in SERIALIZERS}
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
            for serializer in SERIALIZERS:
                serializer.create_table(connection)
                serializer.create_sorted_view(connection)
            self._create_derived_views(connection)

    def write_batch(
        self,
        batch: AnalyticsIngestBatch,
        *,
        replace_run_id: str | None = None,
        refresh_derived: bool = True,
    ) -> None:
        validated = AnalyticsIngestBatch.model_validate(batch)
        self.ensure_schema()
        with self._connect() as connection:
            connection.begin()
            try:
                if replace_run_id is not None:
                    for serializer in RUN_SCOPED_TABLES:
                        serializer.delete_run(connection, replace_run_id)
                    connection.execute(
                        """
                        DELETE FROM gene_alteration_state
                        WHERE run_sample_key IN (
                            SELECT DISTINCT run_sample_key
                            FROM profile_observation_sets
                            WHERE run_id = ?
                        )
                        """,
                        [replace_run_id],
                    )

                for serializer in SERIALIZERS:
                    records = serializer.records_from_batch(validated)
                    if serializer.run_column is None:
                        serializer.delete_unique_values(connection, records)
                    serializer.insert_records(connection, records)

                if refresh_derived:
                    self._refresh_gene_alteration_state(
                        connection, run_id=replace_run_id
                    )
                    self._refresh_sample_profile_cache(
                        connection, run_id=replace_run_id
                    )
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
        self, run_id: str
    ) -> list[SampleMetricNumeric | SampleMetricString]:
        numeric = self.fetch_records(
            "sample_metric_numeric", SampleMetricNumeric, run_id=run_id
        )
        string = self.fetch_records(
            "sample_metric_string", SampleMetricString, run_id=run_id
        )
        return [*numeric, *string]

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


def _field_value(record: BaseModel, column: str) -> Any:
    if column == "schema_json" and isinstance(record, ProfilePayload):
        return record.payload_schema_json
    return getattr(record, column)


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
