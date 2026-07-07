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
    """Simple linker indicating that a run includes a sample."""

    run_sample_id: str
    run_id: str
    sample_id: str
    role: str | None = None


class RunRelationship(GoodomicsModel):
    """Directed provenance relationship between two runs."""

    source_run_id: str
    target_run_id: str
    relationship_type: str
    metadata_json: JsonObject = Field(default_factory=dict)


class DataContract(GoodomicsModel):
    """Describes a stable semantic analytical data layer."""

    data_contract_id: str
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
    entity_grain: str | None = None
    value_semantics: str | None = None
    primary_table: str | None = None
    physical_tables_json: JsonObject = Field(default_factory=dict)
    summary_json: JsonObject = Field(default_factory=dict)
    last_profiled_at: datetime | None = None
    source_fingerprint: str | None = None
    query_modes_json: JsonObject = Field(default_factory=dict)
    mcp_description: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class DataContractField(GoodomicsModel):
    """Queryable field exposed by a semantic data contract."""

    data_contract_id: str
    field_id: str
    field_role: str = "metric"
    entity_scope: str | None = None
    display_name: str
    value_type: Literal["numeric", "string", "boolean", "date", "json"] = "numeric"
    unit: str | None = None
    direction: str | None = None
    description: str | None = None
    priority: str | None = None
    query_ref_json: JsonObject = Field(default_factory=dict)
    summary_json: JsonObject = Field(default_factory=dict)
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
    """Associates a file with imports, runs, samples, or data contracts."""

    file_id: str
    project_id: str | None = None
    data_import_id: str | None = None
    run_id: str | None = None
    run_sample_id: str | None = None
    sample_id: str | None = None
    data_contract_id: str | None = None
    link_role: str


class SampleSet(GoodomicsModel):
    """Saved group of sample/run links, such as a cohort or reference set."""

    sample_set_id: str
    project_id: str | None = None
    name: str
    kind: str = "cohort"
    description: str | None = None
    definition_json: JsonObject = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata_json: JsonObject = Field(default_factory=dict)


class SampleSetMember(GoodomicsModel):
    """Membership row linking a sample set to a run/sample link."""

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


class UnresolvedAnalyticalRecord(BaseModel):
    """Parser-emitted analytical row before DuckDB dimension IDs are resolved."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    @property
    def sample_id(self) -> str | None:
        explicit = self.model_extra.get("sample_id") if self.model_extra else None
        if isinstance(explicit, str):
            return explicit
        metadata = self.model_extra.get("metadata_json") if self.model_extra else None
        if not isinstance(metadata, dict):
            return None
        metadata_sample_id = metadata.get("sample_id")
        return metadata_sample_id if isinstance(metadata_sample_id, str) else None

    @property
    def columns(self) -> list[str]:
        metadata = self.model_extra.get("metadata_json") if self.model_extra else None
        columns = metadata.get("columns") if isinstance(metadata, dict) else None
        return [str(column) for column in columns] if isinstance(columns, list) else []

    @property
    def rows(self) -> list[dict[str, Any]]:
        metadata = self.model_extra.get("metadata_json") if self.model_extra else None
        rows = metadata.get("rows") if isinstance(metadata, dict) else None
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]


class EntityAttribute(AnalyticalRecord):
    """Unified typed attribute value for a project, subject, sample, or run entity."""

    entity_scope: str
    entity_id: str
    field_id: int
    data_contract_id: int | None = None
    source_file_id: int | None = None
    value_type: Literal["numeric", "string", "boolean", "date", "json"]
    value_numeric: float | None = None
    value_string: str | None = None
    value_boolean: bool | None = None
    value_datetime: datetime | None = None
    value_json: JsonValue = None


class SampleMetric(AnalyticalRecord):
    """Unified metric value measured for a sample/run link."""

    data_contract_id: int
    run_id: int
    run_sample_id: int | None = None
    sample_id: int | None = None
    field_id: int
    source_file_id: int | None = None
    source_observation_id: str | None = None
    source_observation_label: str | None = None
    source_observation_metadata_json: JsonObject = Field(default_factory=dict)
    value_type: Literal["numeric", "string", "json"]
    value_numeric: float | None = None
    value_string: str | None = None
    value_json: JsonValue = None


class Feature(AnalyticalRecord):
    """Biological or analytical feature such as a gene, transcript, or region."""

    feature_id: str
    source_feature_id: str
    feature_type: str
    symbol: str
    stable_id: str | None = None
    namespace: str | None = None
    genome_build: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class FeatureAlias(AnalyticalRecord):
    """Alternative identifier or symbol for a feature."""

    feature_id: str
    alias: str
    namespace: str | None = None


class FeatureSet(AnalyticalRecord):
    """Named collection of features used for grouping or interpretation."""

    feature_set_id: str
    feature_set_type: str
    name: str
    description: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class FeatureSetMember(AnalyticalRecord):
    """Membership row linking a feature set to a feature."""

    feature_set_id: str
    feature_id: str
    member_role: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class FeatureValueNumeric(AnalyticalRecord):
    """Numeric value for a feature in a sample/run link and data contract."""

    data_contract_id: int
    run_id: int
    run_sample_id: int
    sample_id: int | None = None
    feature_id: int
    value: float
    source_file_id: int | None = None


class FeatureCall(AnalyticalRecord):
    """Categorical feature-level call for a sample/run link."""

    data_contract_id: int
    run_id: int
    run_sample_id: int
    sample_id: int | None = None
    feature_id: int
    call_code: str
    call_label: str | None = None
    call_rank: int | None = None
    score: float | None = None
    confidence: float | None = None
    source_event_id: str | None = None
    source_file_id: int | None = None


class GenomicInterval(AnalyticalRecord):
    """Genomic coordinate interval, optionally linked to a feature."""

    interval_id: str
    genome_build: str
    contig: str
    start_pos: int
    end_pos: int
    strand: str | None = None
    feature_id: str | None = None
    interval_type: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class SampleIntervalValue(AnalyticalRecord):
    """Numeric value assigned to a genomic interval for a sample/run link."""

    data_contract_id: int
    run_id: int
    run_sample_id: int
    sample_id: int | None = None
    interval_id: int
    value: float
    source_file_id: int | None = None


class CopyNumberSegment(AnalyticalRecord):
    """Copy-number segment call for a sample/run link."""

    data_contract_id: int
    run_id: int
    run_sample_id: int
    sample_id: int | None = None
    genome_build: str
    contig: str
    start_pos: int
    end_pos: int
    num_probes: int | None = None
    segment_mean: float
    total_copy_number: float | None = None
    minor_copy_number: float | None = None
    call_label: str | None = None
    source_file_id: int | None = None


class Variant(AnalyticalRecord):
    """Normalized genomic variant identity."""

    variant_id: str
    source_variant_id: str | None = None
    genome_build: str
    contig: str
    pos: int
    end_pos: int | None = None
    ref: str | None = None
    alt: str | None = None
    variant_type: str | None = None
    normalized_id: str


class VariantAnnotation(AnalyticalRecord):
    """Contract-level annotation describing a variant and optional feature."""

    data_contract_id: int | None = None
    variant_id: int
    feature_id: int | None = None
    consequence: str | None = None
    impact: str | None = None
    clinvar_significance: str | None = None
    gnomad_af: float | None = None
    info_json: JsonObject = Field(default_factory=dict)


class VariantTranscriptAnnotation(AnalyticalRecord):
    """Transcript-specific annotation for a variant."""

    data_contract_id: int | None = None
    variant_id: int
    transcript_feature_id: int
    gene_feature_id: int | None = None
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

    data_contract_id: int
    run_id: int
    run_sample_id: int
    sample_id: int | None = None
    variant_id: int
    genotype: str | None = None
    depth: int | None = None
    genotype_quality: float | None = None
    allele_depth_ref: int | None = None
    allele_depth_alt: int | None = None
    allele_fraction: float | None = None
    filter: str | None = None
    format_json: JsonObject = Field(default_factory=dict)
    source_file_id: int | None = None


class StructuralVariantEvent(AnalyticalRecord):
    """Structural variant event identity and annotation."""

    structural_variant_id: int
    event_id: str
    event_class: str
    genome_build: str | None = None
    site1_feature_id: int | None = None
    site2_feature_id: int | None = None
    site1_contig: str | None = None
    site1_pos: int | None = None
    site2_contig: str | None = None
    site2_pos: int | None = None
    frame_status: str | None = None
    event_info: str | None = None
    annotation_json: JsonObject = Field(default_factory=dict)


class SampleStructuralVariantCall(AnalyticalRecord):
    """Per-sample call and evidence for a structural variant event."""

    data_contract_id: int
    run_id: int
    run_sample_id: int
    sample_id: int | None = None
    structural_variant_id: int
    call_status: str = "called"
    dna_support: str | None = None
    rna_support: str | None = None
    tumor_read_count: int | None = None
    normal_read_count: int | None = None
    split_read_count: int | None = None
    paired_end_read_count: int | None = None
    format_json: JsonObject = Field(default_factory=dict)
    source_file_id: int | None = None


class TimelineEvent(AnalyticalRecord):
    """Subject or sample timeline event for longitudinal context."""

    event_id: int
    subject_id: int
    sample_id: int | None = None
    run_sample_id: int | None = None
    event_type: str
    start_time: datetime | float | int | None = None
    end_time: datetime | float | int | None = None
    time_unit: str | None = None
    event_status: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)


class ResultPayload(AnalyticalRecord):
    """Logical non-scalar result data attached to a data contract."""

    payload_id: int
    data_contract_id: int
    run_id: int
    run_sample_id: int | None = None
    sample_id: int | None = None
    field_id: int
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
    source_file_id: int | None = None
    source_observation_id: str | None = None
    source_observation_label: str | None = None
    source_observation_metadata_json: JsonObject = Field(default_factory=dict)
    data_json: JsonValue = Field(default_factory=list)
    metadata_json: JsonObject = Field(default_factory=dict)

    @field_validator("payload_schema_json", mode="before")
    @classmethod
    def _blank_schema_to_empty_dict(cls, value: object) -> object:
        return {} if value is None else value

    @field_validator("source_observation_metadata_json", mode="before")
    @classmethod
    def _blank_source_observation_metadata_to_empty_dict(
        cls, value: object
    ) -> object:
        return {} if value is None else value

    @field_validator("data_json", mode="before")
    @classmethod
    def _blank_data_to_empty_list(cls, value: object) -> object:
        return [] if value is None else value

    @property
    def columns(self) -> list[str]:
        columns = self.payload_schema_json.get("columns")
        if not isinstance(columns, list) and isinstance(self.data_json, list):
            first_row = next(
                (row for row in self.data_json if isinstance(row, dict)),
                None,
            )
            columns = list(first_row) if first_row is not None else []
        return [str(column) for column in columns] if isinstance(columns, list) else []

    @property
    def rows(self) -> list[dict[str, Any]]:
        rows = self.data_json
        if not isinstance(rows, list):
            return []
        if self.payload_schema_json.get("shape") == "xy_pairs":
            columns = self.columns
            if len(columns) >= 2:
                x_column, y_column = columns[:2]
                return [
                    {x_column: row[0], y_column: row[1]}
                    for row in rows
                    if isinstance(row, list | tuple) and len(row) >= 2
                ]
        return [row for row in rows if isinstance(row, dict)]

    @property
    def source_hash(self) -> str | None:
        source_hash = self.metadata_json.get("source_hash")
        return source_hash if isinstance(source_hash, str) else None

    @property
    def source_file(self) -> int | None:
        return self.source_file_id


class GeneAlterationState(AnalyticalRecord):
    """Unified alteration state for a gene-like feature in a sample/run link."""

    run_sample_id: int
    sample_id: int | None = None
    subject_id: int | None = None
    feature_id: int
    data_contract_id: int
    alteration_type: str
    alteration_subtype: str | None = None
    is_altered: bool
    value_numeric: float | None = None
    value_string: str | None = None
    driver_status: str | None = None
    source_table: str
    source_event_id: str | None = None


class CohortSummary(AnalyticalRecord):
    """Precomputed summary statistics for a sample set and contract feature."""

    sample_set_id: int
    data_contract_id: int
    field_id: int | None = None
    feature_id: int | None = None
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

    run_id: int
    tool: str
    version: str
    source_file_id: int | None = None


class DataSource(AnalyticalRecord):
    """Source path provenance for imported analytical data."""

    run_id: int
    run_sample_id: int | None = None
    sample_id: int | None = None
    tool: str | None = None
    module: str | None = None
    source_path: str


class AnalyticsIngestBatch(MutableGoodomicsModel):
    """Container for analytical records staged for DuckDB ingestion."""

    entity_attributes: list[Any] = Field(default_factory=list)
    sample_metrics: list[Any] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    feature_aliases: list[FeatureAlias] = Field(default_factory=list)
    feature_sets: list[FeatureSet] = Field(default_factory=list)
    feature_set_members: list[FeatureSetMember] = Field(default_factory=list)
    feature_value_numeric: list[Any] = Field(default_factory=list)
    feature_call: list[Any] = Field(default_factory=list)
    genomic_intervals: list[GenomicInterval] = Field(default_factory=list)
    sample_interval_values: list[Any] = Field(default_factory=list)
    copy_number_segments: list[Any] = Field(default_factory=list)
    variants: list[Variant] = Field(default_factory=list)
    variant_annotations: list[Any] = Field(default_factory=list)
    variant_transcript_annotations: list[Any] = Field(default_factory=list)
    sample_variant_calls: list[Any] = Field(default_factory=list)
    structural_variant_events: list[Any] = Field(default_factory=list)
    sample_structural_variant_calls: list[Any] = Field(default_factory=list)
    timeline_events: list[Any] = Field(default_factory=list)
    result_payloads: list[Any] = Field(default_factory=list)
    gene_alteration_state: list[Any] = Field(default_factory=list)
    cohort_summaries: list[Any] = Field(default_factory=list)
    tool_versions: list[Any] = Field(default_factory=list)
    data_sources: list[Any] = Field(default_factory=list)
