"""Version 2 semantic insight, query, result, and report contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from pydantic import (
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from goodomics.schemas.base import BaseModel
from goodomics.schemas.field_references import (
    ParsedFieldReference,
    parse_field_reference,
)

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
JsonObject = dict[str, Any]
Grain = Literal["sample", "subject", "run", "feature", "variant", "file", "row"]
Aggregation = Literal["count", "count_distinct", "sum", "avg", "min", "max"]
NonBlankName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESULT_LIMIT_DEFAULT = 1000
RESULT_LIMIT_MAX = 10000
MATRIX_CELL_LIMIT_DEFAULT = 250_000
MATRIX_CELL_LIMIT_MAX = 1_000_000

GRAIN_IDENTITIES: dict[str, tuple[str, ...]] = {
    "sample": ("sample_id",),
    "subject": ("subject_id",),
    "run": ("run_id",),
    "feature": ("feature_id",),
    "variant": ("variant_id",),
    "file": ("file_id",),
    "row": ("row_id",),
}


class StrictModel(BaseModel):
    """Base class for closed public v2 configuration objects."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class InsightFilter(StrictModel):
    """Typed predicate applied before query-family reshaping."""

    field: str
    operator: Literal[
        "eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains"
    ] = "eq"
    value: JsonValue

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        """Require a canonical source-bearing field reference."""

        parse_field_reference(value)
        return value


class ResultScope(StrictModel):
    """Occurrence-selection constraints for contract-backed fields."""

    selection: Literal[
        "latest_successful_per_sample",
        "all_eligible",
        "specific_methods",
        "specific_versions",
        "specific_runs",
        "pinned_results",
    ] = "latest_successful_per_sample"
    analysis_type_ids: list[str] = Field(default_factory=list)
    method_ids: list[str] = Field(default_factory=list)
    method_versions: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    started_after: datetime | None = None
    ended_before: datetime | None = None
    run_contract_ids: list[str] = Field(default_factory=list)


class FieldSelection(StrictModel):
    """Canonical field reference with a stable result alias and occurrence scope."""

    field: str
    alias: str | None = Field(default=None, alias="as")
    label: str | None = None
    scope: ResultScope | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> FieldSelection:
        """Validate canonical syntax, scope ownership, and safe aliases."""

        reference = self.parsed_field
        if reference.kind == "metadata" and self.scope is not None:
            raise ValueError("Metadata fields cannot define occurrence selection.")
        if self.alias is not None and not SAFE_IDENTIFIER.fullmatch(self.alias):
            raise ValueError(f"Field alias is not a safe identifier: {self.alias!r}.")
        return self

    @property
    def reference(self) -> str:
        """Return the stable name emitted in a typed result."""

        return self.alias or self.field

    @property
    def parsed_field(self) -> ParsedFieldReference:
        """Return the trusted typed form of the canonical public reference."""

        return parse_field_reference(self.field)


class QueryOrder(StrictModel):
    """Deterministic ordering by a query output alias or grain identity."""

    by: str
    direction: Literal["asc", "desc"] = "asc"


class DeterministicSampling(StrictModel):
    """Explicit deterministic sampling applied after query completion."""

    size: int = Field(ge=1, le=RESULT_LIMIT_MAX)
    seed: str = "goodomics"


class QueryBase(StrictModel):
    """Selection and size controls shared by every query family."""

    filters: list[InsightFilter] = Field(default_factory=list)
    order_by: list[QueryOrder] = Field(default_factory=list)
    limit: int = Field(default=RESULT_LIMIT_DEFAULT, ge=1, le=RESULT_LIMIT_MAX)
    sampling: DeterministicSampling | None = None


class RowsQuery(QueryBase):
    """Identity-preserving retrieval of selected columns."""

    kind: Literal["rows"] = "rows"
    grain: Grain
    columns: list[FieldSelection] = Field(min_length=1)


class GroupField(FieldSelection):
    """Field used to define groups in a summary query."""


class AggregationSpec(FieldSelection):
    """Descriptive aggregation over one canonical field."""

    aggregation: Aggregation


class CalculationSpec(StrictModel):
    """Deterministic calculation over summary outputs."""

    calculation: Literal["percent_of_total", "percent_of_eligible"]
    input: str
    alias: str = Field(alias="as")
    denominator: str | None = None

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, value: str) -> str:
        """Require a portable result identifier."""

        if not SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError(f"Calculation alias is not a safe identifier: {value!r}.")
        return value


class SummaryQuery(QueryBase):
    """Grouped descriptive aggregation with explicit calculations."""

    kind: Literal["summary"] = "summary"
    grain: Grain
    group_by: list[GroupField] = Field(default_factory=list)
    aggregations: list[AggregationSpec] = Field(min_length=1)
    calculations: list[CalculationSpec] = Field(default_factory=list)


class RelationshipQuery(QueryBase):
    """Matched two-measure relationship without inferential modeling."""

    kind: Literal["relationship"] = "relationship"
    x: FieldSelection
    y: FieldSelection
    match_by: Grain


class DistributionQuery(QueryBase):
    """Raw numeric or categorical distribution with optional splitting."""

    kind: Literal["distribution"] = "distribution"
    value: FieldSelection
    split_by: list[FieldSelection] = Field(default_factory=list)
    bins: int | None = Field(default=None, ge=1, le=500)
    summaries: list[Literal["count", "min", "max", "avg"]] = Field(default_factory=list)


class SeriesQuery(QueryBase):
    """Ordered measurements over a semantic position domain."""

    kind: Literal["series"] = "series"
    position: FieldSelection
    series_by: list[FieldSelection] = Field(default_factory=list)
    measurements: list[FieldSelection] = Field(min_length=1)


class MatrixQuery(QueryBase):
    """Bounded raw-value pivot across row and column identities."""

    kind: Literal["matrix"] = "matrix"
    rows: FieldSelection
    columns: FieldSelection
    value: FieldSelection
    cell_limit: int = Field(
        default=MATRIX_CELL_LIMIT_DEFAULT, ge=1, le=MATRIX_CELL_LIMIT_MAX
    )


class AlterationMatrixQuery(QueryBase):
    """Feature-by-entity alteration states with coverage-aware eligibility."""

    kind: Literal["alteration_matrix"] = "alteration_matrix"
    features: list[str] = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)
    alterations: list[FieldSelection] = Field(min_length=1)
    feature_set_ids: list[str] = Field(default_factory=list)
    cell_limit: int = Field(
        default=MATRIX_CELL_LIMIT_DEFAULT, ge=1, le=MATRIX_CELL_LIMIT_MAX
    )


class VariantPositionQuery(QueryBase):
    """Variant recurrence over transcript or protein position."""

    kind: Literal["variant_position"] = "variant_position"
    position: FieldSelection
    frequency: FieldSelection
    color_by: FieldSelection | None = None
    annotation_contract_ids: list[str] = Field(default_factory=list)


class GenomeProfileQuery(QueryBase):
    """Values laid out over a genomic coordinate domain."""

    kind: Literal["genome_profile"] = "genome_profile"
    coordinate: FieldSelection
    value: FieldSelection
    group_by: list[FieldSelection] = Field(default_factory=list)


class ProviderSettings(StrictModel):
    """Explicit external analysis-provider selection and parameters."""

    provider_id: str | None = None
    method: str
    parameters: JsonObject = Field(default_factory=dict)


class SurvivalQuery(QueryBase):
    """Representable time-to-event input requiring a compatible provider."""

    kind: Literal["survival"] = "survival"
    duration: FieldSelection
    event: FieldSelection
    group_by: list[FieldSelection] = Field(default_factory=list)
    provider: ProviderSettings


class TimelineQuery(QueryBase):
    """Subject events laid out over absolute or relative time."""

    kind: Literal["timeline"] = "timeline"
    subject: FieldSelection
    start: FieldSelection
    end: FieldSelection | None = None
    track: FieldSelection | None = None
    label: FieldSelection | None = None


class AssociationQuery(QueryBase):
    """Coverage-aware descriptive co-occurrence counts and percentages."""

    kind: Literal["association"] = "association"
    features: list[str] = Field(min_length=2)
    state: list[FieldSelection] = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)
    feature_set_ids: list[str] = Field(default_factory=list)


QueryNode = Annotated[
    RowsQuery
    | SummaryQuery
    | RelationshipQuery
    | DistributionQuery
    | SeriesQuery
    | MatrixQuery
    | AlterationMatrixQuery
    | VariantPositionQuery
    | GenomeProfileQuery
    | SurvivalQuery
    | TimelineQuery
    | AssociationQuery,
    Field(discriminator="kind"),
]


class NumberFormat(StrictModel):
    """Portable numeric formatting owned by a view."""

    style: Literal["number", "percent", "scientific", "compact"] = "number"
    decimals: int | None = Field(default=None, ge=0, le=12)
    prefix: str | None = None
    suffix: str | None = None


class AxisConfig(StrictModel):
    """Portable chart-axis presentation settings."""

    label: str | None = None
    scale: Literal["linear", "log", "category", "time"] | None = None
    minimum: float | None = None
    maximum: float | None = None


class SortConfig(QueryOrder):
    """Table sort binding retained as view formatting."""


class Threshold(StrictModel):
    """Metric threshold with a stable label and optional color."""

    value: float
    label: str | None = None
    color: str | None = None


class ViewConfig(StrictModel):
    """Formatting shared by compatible typed-result views."""

    hidden_values: list[str] = Field(default_factory=list)


class TableView(ViewConfig):
    """Tabular rendering for row-like typed results."""

    kind: Literal["table"] = "table"
    sorting: list[SortConfig] = Field(default_factory=list)
    null_format: str = "—"
    numeric_format: dict[str, NumberFormat] = Field(default_factory=dict)


class ScatterView(ViewConfig):
    """Scatter rendering for relationship results."""

    kind: Literal["scatter"] = "scatter"
    x: str | None = None
    y: str | None = None
    x_axis: AxisConfig | None = None
    y_axis: AxisConfig | None = None
    colors: dict[str, str] = Field(default_factory=dict)
    tooltips: list[str] = Field(default_factory=list)


class MetricView(ViewConfig):
    """Single descriptive value rendering."""

    kind: Literal["metric"] = "metric"
    value: str | None = None
    number_format: NumberFormat | None = None
    thresholds: list[Threshold] = Field(default_factory=list)


class HistogramView(ViewConfig):
    """Histogram rendering for distribution results."""

    kind: Literal["histogram"] = "histogram"
    bins: int = Field(default=20, ge=1, le=500)
    x_axis: AxisConfig | None = None
    y_axis: AxisConfig | None = None
    colors: dict[str, str] = Field(default_factory=dict)


class CategoryChartView(ViewConfig):
    """Bar, line, area, pie, or donut rendering over compatible results."""

    kind: Literal["bar", "stacked_bar", "line", "area", "pie", "donut"]
    category: str | None = None
    x_axis: AxisConfig | None = None
    y_axis: AxisConfig | None = None
    colors: dict[str, str] = Field(default_factory=dict)
    tooltips: list[str] = Field(default_factory=list)


class BoxplotView(ViewConfig):
    """Box or violin rendering for distribution results."""

    kind: Literal["boxplot", "violin"]
    category: str | None = None
    x_axis: AxisConfig | None = None
    y_axis: AxisConfig | None = None
    colors: dict[str, str] = Field(default_factory=dict)


class HeatmapView(ViewConfig):
    """Heatmap rendering for matrix-compatible results."""

    kind: Literal["heatmap"] = "heatmap"
    x: str | None = None
    y: str | None = None
    value: str | None = None
    colors: list[str] = Field(default_factory=list)
    tooltips: list[str] = Field(default_factory=list)


class SpecializedView(ViewConfig):
    """Domain-aware rendering with bindings supplied by its typed query."""

    kind: Literal[
        "oncoprint",
        "lollipop",
        "genome_profile",
        "survival",
        "timeline",
        "association_matrix",
    ]
    options: JsonObject = Field(default_factory=dict)


InsightView = Annotated[
    TableView
    | ScatterView
    | MetricView
    | HistogramView
    | CategoryChartView
    | BoxplotView
    | HeatmapView
    | SpecializedView,
    Field(discriminator="kind"),
]


VIEWS_BY_QUERY_KIND: dict[str, frozenset[str]] = {
    "rows": frozenset({"table", "bar", "stacked_bar", "line", "area", "metric"}),
    "summary": frozenset({"table", "bar", "line", "area", "pie", "donut", "metric"}),
    "relationship": frozenset({"table", "scatter"}),
    "distribution": frozenset({"table", "histogram", "boxplot", "violin", "bar"}),
    "series": frozenset({"table", "line", "area"}),
    "matrix": frozenset({"table", "heatmap"}),
    "alteration_matrix": frozenset({"table", "oncoprint", "heatmap"}),
    "variant_position": frozenset({"table", "lollipop"}),
    "genome_profile": frozenset({"table", "genome_profile"}),
    "survival": frozenset({"table", "survival"}),
    "timeline": frozenset({"table", "timeline"}),
    "association": frozenset({"table", "association_matrix", "heatmap"}),
}


class AnalysisValue(StrictModel):
    """Internal projection consumed by the proven descriptive row executor."""

    field: str
    alias: str | None = Field(default=None, alias="as")
    label: str | None = None
    aggregation: Literal[
        "raw", "count", "count_distinct", "sum", "avg", "min", "max"
    ] = "raw"
    filters: list[InsightFilter] = Field(default_factory=list)
    scope: ResultScope | None = None

    @property
    def reference(self) -> str:
        """Return the effective result reference."""

        return self.alias or self.field

    @property
    def parsed_field(self) -> ParsedFieldReference:
        """Parse the canonical field reference."""

        return parse_field_reference(self.field)


class AnalysisConfig(StrictModel):
    """Internal normalized projection for existing safe SQL compilation."""

    grain: Grain = "sample"
    values: list[AnalysisValue] = Field(min_length=1)
    filters: list[InsightFilter] = Field(default_factory=list)
    match_by: Grain | None = None
    join: Literal["outer", "inner"] = "outer"
    limit: int = Field(default=RESULT_LIMIT_DEFAULT, ge=1, le=RESULT_LIMIT_MAX)
    random: bool = False


class InsightSpec(StrictModel):
    """Complete normalized semantic insight definition shared by every surface."""

    version: Literal[2]
    name: NonBlankName
    query: QueryNode
    view: InsightView

    @model_validator(mode="after")
    def validate_view_compatibility(self) -> InsightSpec:
        """Require a view compatible with the query family's typed result."""

        allowed = VIEWS_BY_QUERY_KIND[self.query.kind]
        if self.view.kind not in allowed:
            raise ValueError(
                f"View {self.view.kind!r} is not compatible with query family "
                f"{self.query.kind!r}; expected one of {', '.join(sorted(allowed))}."
            )
        references = query_output_references(self.query)
        duplicates = sorted(
            {value for value in references if references.count(value) > 1}
        )
        if duplicates:
            raise ValueError(
                "Query output aliases must be unique; add 'as' to repeated fields: "
                f"{', '.join(duplicates)}."
            )
        return self

    @property
    def analysis(self) -> AnalysisConfig:
        """Return a private execution projection without serializing v1 grammar."""

        return _analysis_projection(self.query, self.view.kind)

    def executable_config(self) -> dict[str, Any]:
        """Return the complete persisted v2 envelope in deterministic key order."""

        return self.model_dump(
            include={"version", "name", "query", "view"},
            exclude_none=True,
            mode="json",
            by_alias=True,
        )

    def compact_config(self) -> dict[str, Any]:
        """Return normalized v2 JSON while omitting empty and no-op properties."""

        return _drop_empty(self.executable_config())


def referenced_fields(query: QueryNode) -> tuple[str, ...]:
    """Return canonical fields referenced by any typed query in stable order."""

    values: list[str] = []

    def add(selection: FieldSelection | None) -> None:
        """Append one optional selection exactly once."""

        if selection is not None and selection.field not in values:
            values.append(selection.field)

    if isinstance(query, RowsQuery):
        for item in query.columns:
            add(item)
    elif isinstance(query, SummaryQuery):
        for item in [*query.group_by, *query.aggregations]:
            add(item)
    elif isinstance(query, RelationshipQuery):
        add(query.x)
        add(query.y)
    elif isinstance(query, DistributionQuery):
        add(query.value)
        for item in query.split_by:
            add(item)
    elif isinstance(query, SeriesQuery):
        add(query.position)
        for item in [*query.series_by, *query.measurements]:
            add(item)
    elif isinstance(query, MatrixQuery):
        add(query.rows)
        add(query.columns)
        add(query.value)
    elif isinstance(query, AlterationMatrixQuery):
        for item in query.alterations:
            add(item)
    elif isinstance(query, VariantPositionQuery):
        add(query.position)
        add(query.frequency)
        add(query.color_by)
    elif isinstance(query, GenomeProfileQuery):
        add(query.coordinate)
        add(query.value)
        for item in query.group_by:
            add(item)
    elif isinstance(query, SurvivalQuery):
        add(query.duration)
        add(query.event)
        for item in query.group_by:
            add(item)
    elif isinstance(query, TimelineQuery):
        add(query.subject)
        add(query.start)
        add(query.end)
        add(query.track)
        add(query.label)
    else:
        for item in query.state:
            add(item)
    for query_filter in query.filters:
        if query_filter.field not in values:
            values.append(query_filter.field)
    return tuple(values)


def query_output_references(query: QueryNode) -> list[str]:
    """Return stable aliases emitted by a query family."""

    projection = _analysis_projection(query, "table")
    references = [value.reference for value in projection.values]
    if isinstance(query, SummaryQuery):
        references.extend(calculation.alias for calculation in query.calculations)
    return references


def _analysis_projection(query: QueryNode, view_kind: str) -> AnalysisConfig:
    """Project a typed query onto the private descriptive SQL primitives."""

    values: list[AnalysisValue] = []

    def append(selection: FieldSelection, aggregation: str = "raw") -> None:
        """Append one field selection to the private projection."""

        values.append(
            AnalysisValue.model_validate(
                {
                    "field": selection.field,
                    "as": selection.alias,
                    "label": selection.label,
                    "aggregation": aggregation,
                    "scope": selection.scope,
                }
            )
        )

    grain: Grain = "sample"
    match_by: Grain | None = None
    if isinstance(query, RowsQuery):
        grain = query.grain
        for item in query.columns:
            append(item)
    elif isinstance(query, SummaryQuery):
        grain = query.grain
        for item in query.group_by:
            append(item)
        for item in query.aggregations:
            append(item, item.aggregation)
    elif isinstance(query, RelationshipQuery):
        grain = query.match_by
        match_by = query.match_by
        append(query.x)
        append(query.y)
    elif isinstance(query, DistributionQuery):
        append(query.value)
        for item in query.split_by:
            append(item)
    elif isinstance(query, SeriesQuery):
        append(query.position)
        for item in [*query.series_by, *query.measurements]:
            append(item)
    elif isinstance(query, MatrixQuery):
        append(query.rows)
        append(query.columns)
        append(query.value)
    elif isinstance(query, AlterationMatrixQuery):
        for item in query.alterations:
            append(item)
    elif isinstance(query, VariantPositionQuery):
        append(query.position)
        append(query.frequency)
        if query.color_by is not None:
            append(query.color_by)
    elif isinstance(query, GenomeProfileQuery):
        append(query.coordinate)
        append(query.value)
        for item in query.group_by:
            append(item)
    elif isinstance(query, SurvivalQuery):
        append(query.duration)
        append(query.event)
        for item in query.group_by:
            append(item)
    elif isinstance(query, TimelineQuery):
        grain = "subject"
        for item in (query.subject, query.start, query.end, query.track, query.label):
            if item is not None:
                append(item)
    else:
        for item in query.state:
            append(item)
    return AnalysisConfig(
        grain=grain,
        values=values,
        filters=list(query.filters),
        match_by=match_by or grain,
        join="outer" if view_kind == "table" else "inner",
        limit=min(query.limit, query.sampling.size) if query.sampling else query.limit,
        random=query.sampling is not None,
    )


def _drop_empty(value: Any) -> Any:
    """Recursively omit empty containers while retaining explicit false and zero."""

    if isinstance(value, dict):
        return {
            key: _drop_empty(item)
            for key, item in value.items()
            if item is not None and item != [] and item != {}
        }
    if isinstance(value, list):
        return [_drop_empty(item) for item in value]
    return value


class ResultProvenance(StrictModel):
    """Resolved source occurrences and stable execution fingerprint."""

    query_fingerprint: str
    run_contract_ids: list[str] = Field(default_factory=list)
    source_fingerprints: list[str] = Field(default_factory=list)
    executed_at: datetime


class ProviderRequirement(StrictModel):
    """Unavailable or selected external scientific analysis capability."""

    required: bool
    method: str
    provider_id: str | None = None
    available: bool = False
    message: str | None = None


class TypedResultBase(StrictModel):
    """Coverage, warnings, and provenance common to every typed result."""

    provenance: ResultProvenance
    coverage: JsonObject = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    provider_requirement: ProviderRequirement | None = None


class RowsResult(TypedResultBase):
    """Identity-preserving row result."""

    kind: Literal["rows"] = "rows"
    columns: list[str]
    rows: list[JsonObject]


class SummaryResult(TypedResultBase):
    """Grouped descriptive summary result."""

    kind: Literal["summary"] = "summary"
    columns: list[str]
    rows: list[JsonObject]


class RelationshipResult(TypedResultBase):
    """Matched relationship points."""

    kind: Literal["relationship"] = "relationship"
    points: list[JsonObject]


class DistributionResult(TypedResultBase):
    """Raw values, bounded bins, and descriptive summaries."""

    kind: Literal["distribution"] = "distribution"
    values: list[JsonObject]
    bins: list[JsonObject] = Field(default_factory=list)
    summaries: list[JsonObject] = Field(default_factory=list)


class SeriesResult(TypedResultBase):
    """Ordered series points."""

    kind: Literal["series"] = "series"
    series: list[JsonObject]


class MatrixResult(TypedResultBase):
    """Bounded row-column matrix."""

    kind: Literal["matrix"] = "matrix"
    row_ids: list[str]
    column_ids: list[str]
    cells: list[JsonObject]


class DomainResult(TypedResultBase):
    """Typed domain records for specialized descriptive query families."""

    kind: Literal[
        "alteration_matrix",
        "variant_position",
        "genome_profile",
        "survival",
        "timeline",
        "association",
    ]
    records: list[JsonObject]


TypedInsightResult = Annotated[
    RowsResult
    | SummaryResult
    | RelationshipResult
    | DistributionResult
    | SeriesResult
    | MatrixResult
    | DomainResult,
    Field(discriminator="kind"),
]


class GridLayout(StrictModel):
    """Report-wide grid geometry."""

    columns: int = Field(default=12, ge=1, le=48)
    row_height: int = Field(default=64, ge=1, le=1000)


class ReportInsightLayout(StrictModel):
    """Placement of one saved insight in report grid coordinates."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ReportInsight(StrictModel):
    """Uniquely placed saved-insight reference."""

    id: str = Field(min_length=1)
    layout: ReportInsightLayout


class RefreshPolicy(StrictModel):
    """Saved report refresh behavior."""

    mode: Literal["manual"] = "manual"


class ReportSpec(StrictModel):
    """Version 2 report configuration referencing saved semantic insights."""

    version: Literal[2]
    filters: list[InsightFilter] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=RESULT_LIMIT_MAX)
    random: bool | None = None
    layout: GridLayout = Field(default_factory=GridLayout)
    insights: list[ReportInsight] = Field(min_length=1)
    refresh_policy: RefreshPolicy = Field(default_factory=RefreshPolicy)

    @model_validator(mode="after")
    def validate_insights(self) -> ReportSpec:
        """Require unique insight IDs and placements within grid bounds."""

        insight_ids = [insight.id for insight in self.insights]
        duplicates = sorted(
            {item for item in insight_ids if insight_ids.count(item) > 1}
        )
        if duplicates:
            raise ValueError(
                f"Report insight ids must be unique: {', '.join(duplicates)}."
            )
        for insight in self.insights:
            if insight.layout.x + insight.layout.width > self.layout.columns:
                raise ValueError(
                    f"Report insight {insight.id!r} extends beyond the grid columns."
                )
        return self

    def executable_config(self) -> dict[str, Any]:
        """Return persisted report fields in deterministic order."""

        return self.model_dump(
            include={
                "version",
                "filters",
                "limit",
                "random",
                "layout",
                "insights",
                "refresh_policy",
            },
            exclude_none=True,
            mode="json",
        )

    def compact_config(self) -> dict[str, Any]:
        """Omit empty optional report blocks."""

        return _drop_empty(self.executable_config())


class InsightDocument(InsightSpec):
    """Portable insight document with optional stable identity and description."""

    insight_id: str | None = None
    description: str | None = None


class ReportDocument(ReportSpec):
    """Portable named report document."""

    report_id: str | None = None
    name: NonBlankName
    description: str | None = None


class SavedInsightCreate(InsightDocument):
    """Request contract for creating a saved v2 insight."""

    project_id: str | None = None
    preview_fingerprint: str = Field(min_length=64, max_length=64)

    def executable_fields(self) -> dict[str, JsonValue]:
        """Return the complete v2 envelope persisted with the insight."""

        return cast(dict[str, JsonValue], self.executable_config())


class SavedInsightPatch(StrictModel):
    """Request contract for patching a saved v2 insight."""

    name: NonBlankName | None = None
    description: str | None = None
    version: Literal[2] | None = None
    query: QueryNode | None = None
    view: InsightView | None = None
    preview_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)

    def executable_fields(self) -> dict[str, JsonValue]:
        """Return executable fields explicitly present in the patch."""

        return cast(
            dict[str, JsonValue],
            self.model_dump(
                include={"version", "name", "query", "view"},
                exclude_unset=True,
                mode="json",
                by_alias=True,
            ),
        )

    @field_validator("name")
    @classmethod
    def reject_empty_name(cls, value: str | None) -> str | None:
        """Reject attempts to clear an existing insight name."""

        if value is None:
            raise ValueError("Insight name cannot be cleared.")
        return value


class SavedInsightMetadata(StrictModel):
    """Shared persisted insight metadata."""

    insight_id: str
    url_slug: str
    project_id: str | None = None
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class SavedInsightSummary(SavedInsightMetadata):
    """Compact insight list response."""

    view_kind: str
    sources: list[str]


class SavedInsightRead(SavedInsightMetadata, InsightSpec):
    """Saved insight metadata with its complete v2 envelope."""


class SavedReportCreate(ReportSpec):
    """Request contract for creating a saved report."""

    project_id: str | None = None
    name: NonBlankName
    description: str | None = None

    def executable_fields(self) -> dict[str, JsonValue]:
        """Return the complete report configuration."""

        return cast(dict[str, JsonValue], self.executable_config())


class SavedReportPatch(StrictModel):
    """Request contract for patching a saved report."""

    name: NonBlankName | None = None
    description: str | None = None
    version: Literal[2] | None = None
    filters: list[InsightFilter] | None = None
    limit: int | None = Field(default=None, ge=1, le=RESULT_LIMIT_MAX)
    random: bool | None = None
    layout: GridLayout | None = None
    insights: list[ReportInsight] | None = Field(default=None, min_length=1)
    refresh_policy: RefreshPolicy | None = None

    def executable_fields(self) -> dict[str, JsonValue]:
        """Return executable report fields explicitly present in the patch."""

        return cast(
            dict[str, JsonValue],
            self.model_dump(
                exclude_unset=True,
                exclude={"name", "description"},
                mode="json",
            ),
        )

    @field_validator("name")
    @classmethod
    def reject_empty_name(cls, value: str | None) -> str | None:
        """Reject attempts to clear an existing report name."""

        if value is None:
            raise ValueError("Report name cannot be cleared.")
        return value


class SavedReportMetadata(StrictModel):
    """Shared persisted report resource metadata."""

    report_id: str
    url_slug: str
    project_id: str | None = None
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class SavedReportSummary(SavedReportMetadata):
    """Compact report list response."""

    insight_count: int
    insight_ids: list[str]


class SavedReportRead(SavedReportMetadata, ReportSpec):
    """Saved report metadata with its complete definition."""


def normalize_insight_definition(value: dict[str, Any]) -> InsightSpec:
    """Parse a complete strict v2 definition."""

    return InsightSpec.model_validate(value)


def normalize_report_definition(value: dict[str, Any]) -> ReportSpec:
    """Parse a complete strict v2 report definition."""

    return ReportSpec.model_validate(value)
