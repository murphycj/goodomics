from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

JsonObject = dict[str, Any]
JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class GoodomicsModel(BaseModel):
    """Immutable base for canonical Goodomics schema records."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class MutableGoodomicsModel(BaseModel):
    """Mutable base for request and aggregate models assembled during workflows."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Project(GoodomicsModel):
    """Workspace boundary that owns runs, samples, files, and analytics."""

    project_id: str
    slug: str | None = None
    name: str
    description: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Subject(GoodomicsModel):
    """Optional patient, donor, organism, cell line, or individual."""

    subject_id: str
    project_id: str
    metadata_json: JsonObject = Field(default_factory=dict)


class Sample(GoodomicsModel):
    """Stable biological, material, or analytical input across runs."""

    sample_id: str
    project_id: str | None = None
    subject_id: str | None = None
    sample_name: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)

    @property
    def metadata(self) -> JsonObject:
        return self.metadata_json


class Run(MutableGoodomicsModel):
    """Computational, import, benchmark, or analysis event."""

    run_id: str
    project_id: str | None = None
    data_import_id: str | None = None
    project: str | None = None
    name: str | None = None
    run_kind: str = "pipeline_run"
    assay: str | None = None
    pipeline_name: str | None = None
    pipeline_version: str | None = None
    parameters_json: JsonObject = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: str = "unknown"
    metadata_json: JsonObject = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    samples: list[Sample] = Field(default_factory=list)

    @field_validator("project_id", mode="before")
    @classmethod
    def _blank_project_id_to_none(cls, value: object) -> object:
        return None if value == "" else value


class RunSample(GoodomicsModel):
    """A sample within a run, used as the processed-sample comparison grain."""

    run_sample_id: str
    project_id: str | None = None
    run_id: str
    sample_id: str | None = None
    assay: str | None = None
    role: str | None = None
    status: str = "unknown"
    metadata_json: JsonObject = Field(default_factory=dict)


class DataProfile(GoodomicsModel):
    """Describes a stable semantic analytical data layer."""

    data_profile_id: str
    project_id: str | None = None
    name: str
    data_type: str
    assay: str | None = None
    producer_tool: str | None = None
    producer_tool_version: str | None = None
    producer_pipeline: str | None = None
    genome_build: str | None = None
    feature_type: str | None = None
    value_type: str | None = None
    unit: str | None = None
    query_modes_json: JsonObject = Field(default_factory=dict)
    mcp_description: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class DataImport(GoodomicsModel):
    """Audit record for data entering Goodomics from an external source."""

    data_import_id: str
    project_id: str | None = None
    source_type: str
    source_uri: str | None = None
    source_path: str | None = None
    importer_name: str
    importer_version: str | None = None
    status: str = "complete"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    parameters_json: JsonObject = Field(default_factory=dict)
    summary_json: JsonObject = Field(default_factory=dict)
    metadata_json: JsonObject = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FileAsset(GoodomicsModel):
    """File-level asset tracked by Goodomics control storage."""

    file_id: str
    project_id: str | None = None
    path: str | None = None
    uri: str | None = None
    file_role: str
    format: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata_json: JsonObject = Field(default_factory=dict)


class FileLink(GoodomicsModel):
    """Associates a file with imports, runs, samples, or data profiles."""

    file_id: str
    project_id: str | None = None
    data_import_id: str | None = None
    run_id: str | None = None
    run_sample_id: str | None = None
    sample_id: str | None = None
    data_profile_id: str | None = None
    link_role: str


class SampleSet(GoodomicsModel):
    """Saved group of processed samples, such as a cohort or reference set."""

    sample_set_id: str
    project_id: str | None = None
    name: str
    kind: str = "cohort"
    description: str | None = None
    definition_json: JsonObject = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata_json: JsonObject = Field(default_factory=dict)


class SampleSetMember(GoodomicsModel):
    """Membership row linking a sample set to a processed sample."""

    sample_set_id: str
    run_sample_id: str


class QCDecision(GoodomicsModel):
    """Quality-control decision with provenance for policy/report versions."""

    status: Literal["pass", "warn", "fail", "unknown"]
    reasons: list[str] = Field(default_factory=list)
    cohort: str | None = None
    report_version: str | None = None
    policy_version: str | None = None


class AnalyticalRecord(GoodomicsModel):
    """Base for DuckDB analytical-store records."""

    pass


class DuckDBMetadata(AnalyticalRecord):
    """Project-level metadata stored in the analytical database."""

    project_id: str | None = None
    project_name: str | None = None
    schema_version: str = "analytics-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata_json: JsonObject = Field(default_factory=dict)


class MetricDefinition(AnalyticalRecord):
    """Catalog entry describing metric identity, display, and value semantics."""

    metric_key: str | None = None
    metric_id: str
    namespace: str | None = None
    metric_name: str
    display_name: str
    value_type: Literal["numeric", "string", "json"] = "numeric"
    unit: str | None = None
    direction: str | None = None
    description: str | None = None
    producer_tool: str | None = None
    producer_module: str | None = None
    schema_version: str | None = None


class AttributeDefinition(AnalyticalRecord):
    """Catalog entry describing flexible attributes on analytical entities."""

    attribute_key: int | None = None
    attribute_id: str
    entity_scope: str
    display_name: str
    value_type: Literal["numeric", "string", "boolean", "date", "json"]
    unit: str | None = None
    description: str | None = None
    priority: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class EntityAttributeBase(AnalyticalRecord):
    """Shared keys for typed entity-attribute value records."""

    entity_scope: str
    entity_key: str
    attribute_key: str
    data_profile_key: str | None = None
    source_file_id: str | None = None


class EntityAttributeNumeric(EntityAttributeBase):
    """Numeric attribute value for a project, subject, sample, or run entity."""

    value: float


class EntityAttributeString(EntityAttributeBase):
    """String attribute value for a project, subject, sample, or run entity."""

    value: str


class EntityAttributeBoolean(EntityAttributeBase):
    """Boolean attribute value for a project, subject, sample, or run entity."""

    value: bool


class EntityAttributeDate(EntityAttributeBase):
    """Datetime attribute value for a project, subject, sample, or run entity."""

    value: datetime


class EntityAttributeJson(EntityAttributeBase):
    """JSON attribute value for a project, subject, sample, or run entity."""

    value_json: JsonValue


class SampleMetricBase(AnalyticalRecord):
    """Shared keys for typed metrics measured at sample or run-sample grain."""

    data_profile_key: str
    run_id: str
    run_sample_key: str | None = None
    sample_key: str | None = None
    metric_key: str
    source_file_id: str | None = None


class SampleMetricNumeric(SampleMetricBase):
    """Numeric metric value measured for a sample or processed sample."""

    value: float


class SampleMetricString(SampleMetricBase):
    """String metric value measured for a sample or processed sample."""

    value: str


class SampleMetricJson(SampleMetricBase):
    """JSON metric value measured for a sample or processed sample."""

    value_json: JsonValue


class Feature(AnalyticalRecord):
    """Biological or analytical feature such as a gene, transcript, or region."""

    feature_key: str
    feature_id: str
    feature_type: str
    symbol: str
    stable_id: str | None = None
    namespace: str | None = None
    genome_build: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class FeatureAlias(AnalyticalRecord):
    """Alternative identifier or symbol for a feature."""

    feature_key: str
    alias: str
    namespace: str | None = None


class FeatureSet(AnalyticalRecord):
    """Named collection of features used for grouping or interpretation."""

    feature_set_key: str
    feature_set_id: str
    feature_set_type: str
    name: str
    description: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class FeatureSetMember(AnalyticalRecord):
    """Membership row linking a feature set to a feature."""

    feature_set_key: str
    feature_key: str
    member_role: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class FeatureValueNumeric(AnalyticalRecord):
    """Numeric value for a feature in a processed sample and data profile."""

    data_profile_key: str
    run_id: str
    run_sample_key: str
    sample_key: str | None = None
    feature_key: str
    value: float
    value_semantics: str
    source_file_id: str | None = None


class FeatureCall(AnalyticalRecord):
    """Categorical feature-level call for a processed sample."""

    data_profile_key: str
    run_id: str
    run_sample_key: str
    sample_key: str | None = None
    feature_key: str
    call_code: str
    call_label: str | None = None
    call_rank: int | None = None
    score: float | None = None
    confidence: float | None = None
    source_event_id: str | None = None
    source_file_id: str | None = None


class GenomicInterval(AnalyticalRecord):
    """Genomic coordinate interval, optionally linked to a feature."""

    interval_key: str
    genome_build: str
    contig: str
    start_pos: int
    end_pos: int
    strand: str | None = None
    feature_key: str | None = None
    interval_type: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class SampleIntervalValue(AnalyticalRecord):
    """Numeric value assigned to a genomic interval for a processed sample."""

    data_profile_key: str
    run_id: str
    run_sample_key: str
    sample_key: str | None = None
    interval_key: str
    value: float
    value_semantics: str
    source_file_id: str | None = None


class CopyNumberSegment(AnalyticalRecord):
    """Copy-number segment call for a processed sample."""

    data_profile_key: str
    run_id: str
    run_sample_key: str
    sample_key: str | None = None
    genome_build: str
    contig: str
    start_pos: int
    end_pos: int
    num_probes: int | None = None
    segment_mean: float
    total_copy_number: float | None = None
    minor_copy_number: float | None = None
    call_label: str | None = None
    source_file_id: str | None = None


class Variant(AnalyticalRecord):
    """Normalized genomic variant identity."""

    variant_key: str
    variant_id: str
    genome_build: str
    contig: str
    pos: int
    end_pos: int | None = None
    ref: str | None = None
    alt: str | None = None
    variant_type: str | None = None
    normalized_key: str


class VariantAnnotation(AnalyticalRecord):
    """Profile-level annotation describing a variant and optional feature."""

    data_profile_key: str | None = None
    variant_key: str
    feature_key: str | None = None
    consequence: str | None = None
    impact: str | None = None
    clinvar_significance: str | None = None
    gnomad_af: float | None = None
    info_json: JsonObject = Field(default_factory=dict)


class VariantTranscriptAnnotation(AnalyticalRecord):
    """Transcript-specific annotation for a variant."""

    data_profile_key: str | None = None
    variant_key: str
    transcript_feature_key: str
    gene_feature_key: str | None = None
    consequence: str
    impact: str | None = None
    protein_change: str | None = None
    cdna_change: str | None = None
    protein_pos_start: int | None = None
    protein_pos_end: int | None = None
    canonical: bool | None = None
    annotation_json: JsonObject = Field(default_factory=dict)


class SampleVariantCall(AnalyticalRecord):
    """Per-sample call and sequencing evidence for a variant."""

    data_profile_key: str
    run_id: str
    run_sample_key: str
    sample_key: str | None = None
    variant_key: str
    genotype: str | None = None
    depth: int | None = None
    genotype_quality: float | None = None
    allele_depth_ref: int | None = None
    allele_depth_alt: int | None = None
    allele_fraction: float | None = None
    filter: str | None = None
    format_json: JsonObject = Field(default_factory=dict)
    source_file_id: str | None = None


class StructuralVariantEvent(AnalyticalRecord):
    """Structural variant event identity and annotation."""

    structural_variant_key: str
    event_id: str
    event_class: str
    genome_build: str | None = None
    site1_feature_key: str | None = None
    site2_feature_key: str | None = None
    site1_contig: str | None = None
    site1_pos: int | None = None
    site2_contig: str | None = None
    site2_pos: int | None = None
    frame_status: str | None = None
    event_info: str | None = None
    annotation_json: JsonObject = Field(default_factory=dict)


class SampleStructuralVariantCall(AnalyticalRecord):
    """Per-sample call and evidence for a structural variant event."""

    data_profile_key: str
    run_id: str
    run_sample_key: str
    sample_key: str | None = None
    structural_variant_key: str
    call_status: str = "called"
    dna_support: str | None = None
    rna_support: str | None = None
    tumor_read_count: int | None = None
    normal_read_count: int | None = None
    split_read_count: int | None = None
    paired_end_read_count: int | None = None
    format_json: JsonObject = Field(default_factory=dict)
    source_file_id: str | None = None


class TimelineEvent(AnalyticalRecord):
    """Subject or sample timeline event for longitudinal context."""

    event_key: str
    subject_key: str
    sample_key: str | None = None
    run_sample_key: str | None = None
    event_type: str
    start_time: datetime | float | int | None = None
    end_time: datetime | float | int | None = None
    time_unit: str | None = None
    event_status: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class ProfilePayload(AnalyticalRecord):
    """Stored payload attached to a data profile, such as a table or blob."""

    payload_id: str
    data_profile_key: str
    run_id: str
    run_sample_key: str | None = None
    payload_name: str
    payload_kind: str
    storage_format: str
    path: str | None = None
    uri: str | None = None
    payload_schema_json: JsonObject = Field(
        default_factory=dict,
        alias="schema_json",
    )
    row_count: int | None = None
    source_file_id: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)

    @property
    def sample_id(self) -> str | None:
        sample_key = self.metadata_json.get("sample_key")
        return sample_key if isinstance(sample_key, str) else None

    @property
    def columns(self) -> list[str]:
        columns = self.metadata_json.get("columns")
        return [str(column) for column in columns] if isinstance(columns, list) else []

    @property
    def rows(self) -> list[dict[str, Any]]:
        rows = self.metadata_json.get("rows")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    @property
    def source_hash(self) -> str | None:
        source_hash = self.metadata_json.get("source_hash")
        return source_hash if isinstance(source_hash, str) else None

    @property
    def source_file(self) -> str | None:
        return self.source_file_id


class GeneAlterationState(AnalyticalRecord):
    """Unified alteration state for a gene-like feature in a processed sample."""

    run_sample_key: str
    sample_key: str | None = None
    subject_key: str | None = None
    feature_key: str
    data_profile_key: str
    alteration_type: str
    alteration_subtype: str | None = None
    is_altered: bool
    value_numeric: float | None = None
    value_string: str | None = None
    driver_status: str | None = None
    source_table: str
    source_event_id: str | None = None


class CohortSummary(AnalyticalRecord):
    """Precomputed summary statistics for a sample set and profile feature."""

    sample_set_id: str
    data_profile_key: str
    metric_key: str | None = None
    feature_key: str | None = None
    n: int
    mean: float | None = None
    median: float | None = None
    stddev: float | None = None
    min: float | None = None
    max: float | None = None
    q05: float | None = None
    q25: float | None = None
    q75: float | None = None
    q95: float | None = None


class ToolVersion(AnalyticalRecord):
    """Tool version observed while producing or importing a run."""

    run_id: str
    tool: str
    version: str
    source_file_id: str | None = None


class DataSource(AnalyticalRecord):
    """Source path provenance for imported analytical data."""

    run_id: str
    run_sample_key: str | None = None
    sample_key: str | None = None
    tool: str | None = None
    module: str | None = None
    source_path: str


class AnalyticsIngestBatch(MutableGoodomicsModel):
    """Container for analytical records staged for DuckDB ingestion."""

    duckdb_metadata: list[DuckDBMetadata] = Field(default_factory=list)
    metric_definitions: list[MetricDefinition] = Field(default_factory=list)
    attribute_definitions: list[AttributeDefinition] = Field(default_factory=list)
    entity_attribute_numeric: list[EntityAttributeNumeric] = Field(default_factory=list)
    entity_attribute_string: list[EntityAttributeString] = Field(default_factory=list)
    entity_attribute_boolean: list[EntityAttributeBoolean] = Field(default_factory=list)
    entity_attribute_date: list[EntityAttributeDate] = Field(default_factory=list)
    entity_attribute_json: list[EntityAttributeJson] = Field(default_factory=list)
    sample_metric_numeric: list[SampleMetricNumeric] = Field(default_factory=list)
    sample_metric_string: list[SampleMetricString] = Field(default_factory=list)
    sample_metric_json: list[SampleMetricJson] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    feature_aliases: list[FeatureAlias] = Field(default_factory=list)
    feature_sets: list[FeatureSet] = Field(default_factory=list)
    feature_set_members: list[FeatureSetMember] = Field(default_factory=list)
    feature_value_numeric: list[FeatureValueNumeric] = Field(default_factory=list)
    feature_call: list[FeatureCall] = Field(default_factory=list)
    genomic_intervals: list[GenomicInterval] = Field(default_factory=list)
    sample_interval_values: list[SampleIntervalValue] = Field(default_factory=list)
    copy_number_segments: list[CopyNumberSegment] = Field(default_factory=list)
    variants: list[Variant] = Field(default_factory=list)
    variant_annotations: list[VariantAnnotation] = Field(default_factory=list)
    variant_transcript_annotations: list[VariantTranscriptAnnotation] = Field(
        default_factory=list
    )
    sample_variant_calls: list[SampleVariantCall] = Field(default_factory=list)
    structural_variant_events: list[StructuralVariantEvent] = Field(
        default_factory=list
    )
    sample_structural_variant_calls: list[SampleStructuralVariantCall] = Field(
        default_factory=list
    )
    timeline_events: list[TimelineEvent] = Field(default_factory=list)
    profile_payloads: list[ProfilePayload] = Field(default_factory=list)
    gene_alteration_state: list[GeneAlterationState] = Field(default_factory=list)
    cohort_summaries: list[CohortSummary] = Field(default_factory=list)
    tool_versions: list[ToolVersion] = Field(default_factory=list)
    data_sources: list[DataSource] = Field(default_factory=list)
