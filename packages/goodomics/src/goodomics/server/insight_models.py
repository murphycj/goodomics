"""Models for saved insights and reports.

The public configuration grammar deliberately contains no physical database
names or SQL escape hatch.  Values identify either a semantic data-contract
field or one field from the small set of server-owned metadata fields.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from goodomics.schemas.field_references import (
    ParsedFieldReference,
    parse_field_reference,
)

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
Grain = Literal["sample", "subject", "run", "feature", "variant", "file"]
Aggregation = Literal["raw", "count", "count_distinct", "sum", "avg", "min", "max"]
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESULT_LIMIT_DEFAULT = 1000
RESULT_LIMIT_MAX = 10000

GRAIN_IDENTITIES: dict[str, tuple[str, ...]] = {
    "sample": ("sample_id",),
    "subject": ("subject_id",),
    "run": ("run_id",),
    "feature": ("feature_id",),
    "variant": ("variant_id",),
    "file": ("file_id",),
}


class StrictModel(BaseModel):
    """Base class that rejects undeclared public configuration keys."""

    model_config = ConfigDict(extra="forbid")


class InsightFilter(StrictModel):
    """A typed predicate applied before aggregation and value joining."""

    field: str
    operator: Literal[
        "eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains"
    ] = "eq"
    value: JsonValue


class ResultScope(StrictModel):
    """Occurrence-selection constraints for one contract-backed value."""

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


class AnalysisValue(StrictModel):
    """One selected field addressed through the shared catalog grammar."""

    field: str
    alias: str | None = Field(default=None, alias="as")
    label: str | None = None
    aggregation: Aggregation = "raw"
    filters: list[InsightFilter] = Field(default_factory=list)
    scope: ResultScope | None = None

    @model_validator(mode="after")
    def validate_source(self) -> AnalysisValue:
        """Validate the reference and restrict occurrence scope to analytical data."""

        reference = self.parsed_field
        if reference.kind == "metadata" and self.scope is not None:
            raise ValueError("Metadata values cannot define scope.")
        if self.alias is not None and not SAFE_IDENTIFIER.fullmatch(self.alias):
            raise ValueError(f"Value alias is not a safe identifier: {self.alias!r}.")
        return self

    @property
    def reference(self) -> str:
        """Return the public name used by views, results, and diagnostics."""

        return self.alias or self.field

    @property
    def parsed_field(self) -> ParsedFieldReference:
        """Return the source components encoded by the canonical field reference."""

        return parse_field_reference(self.field)


class AnalysisConfig(StrictModel):
    """Grain, selected values, filters, and cross-value matching behavior."""

    grain: Grain = "sample"
    values: list[AnalysisValue] = Field(min_length=1)
    filters: list[InsightFilter] = Field(default_factory=list)
    match_by: (
        Literal["sample", "subject", "run", "feature", "variant", "file"] | None
    ) = None
    join: Literal["outer", "inner"] | None = None
    limit: int = Field(default=RESULT_LIMIT_DEFAULT, ge=1, le=RESULT_LIMIT_MAX)
    random: bool = False

    @model_validator(mode="after")
    def validate_value_references(self) -> AnalysisConfig:
        """Require unique effective references outside reserved grain identities."""

        value_references = [value.reference for value in self.values]
        duplicates = sorted(
            {
                reference
                for reference in value_references
                if value_references.count(reference) > 1
            }
        )
        if duplicates:
            raise ValueError(
                "Value references must be unique; add 'as' to repeated fields: "
                f"{', '.join(duplicates)}."
            )
        reserved = set(GRAIN_IDENTITIES[self.grain])
        collisions = sorted(reserved.intersection(value_references))
        if collisions:
            raise ValueError(
                "Value aliases cannot collide with grain identities: "
                f"{', '.join(collisions)}."
            )
        return self


class NumberFormat(StrictModel):
    """Portable numeric formatting owned by a view binding."""

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


class SortConfig(StrictModel):
    """A table sort binding to an identity or value alias."""

    by: str
    direction: Literal["asc", "desc"] = "asc"


class Threshold(StrictModel):
    """A metric display threshold with a stable severity label."""

    value: float
    label: str | None = None
    color: str | None = None


class ViewConfig(StrictModel):
    """Formatting shared by views without changing the ordered analysis."""

    hidden_values: list[str] = Field(default_factory=list)


class TableView(ViewConfig):
    """Table formatting over grain identities and ordered analysis values."""

    kind: Literal["table"] = "table"
    sorting: list[SortConfig] = Field(default_factory=list)
    null_format: str = "—"
    numeric_format: dict[str, NumberFormat] = Field(default_factory=dict)


class ScatterView(ViewConfig):
    """Two numeric value bindings rendered as a scatter plot."""

    kind: Literal["scatter"]
    x: str
    y: str
    x_axis: AxisConfig | None = None
    y_axis: AxisConfig | None = None
    colors: dict[str, str] = Field(default_factory=dict)
    tooltips: list[str] = Field(default_factory=list)


class MetricView(ViewConfig):
    """One value rendered as a headline metric."""

    kind: Literal["metric"]
    value: str
    number_format: NumberFormat | None = None
    thresholds: list[Threshold] = Field(default_factory=list)


class HistogramView(ViewConfig):
    """One or more independently binned numeric distributions."""

    kind: Literal["histogram"]
    bins: int = Field(default=20, ge=1, le=500)
    x_axis: AxisConfig | None = None
    y_axis: AxisConfig | None = None
    colors: dict[str, str] = Field(default_factory=dict)


class CategoryChartView(ViewConfig):
    """Category/value bindings shared by bar, line, area, pie, and donut views."""

    kind: Literal["bar", "stacked_bar", "line", "area", "pie", "donut"]
    category: str | None = None
    x_axis: AxisConfig | None = None
    y_axis: AxisConfig | None = None
    colors: dict[str, str] = Field(default_factory=dict)
    tooltips: list[str] = Field(default_factory=list)


class BoxplotView(ViewConfig):
    """Numeric value bindings grouped by an optional category."""

    kind: Literal["boxplot"]
    category: str | None = None
    x_axis: AxisConfig | None = None
    y_axis: AxisConfig | None = None
    colors: dict[str, str] = Field(default_factory=dict)


class HeatmapView(ViewConfig):
    """Three bindings describing heatmap x, y, and cell values."""

    kind: Literal["heatmap"]
    x: str
    y: str
    value: str
    colors: list[str] = Field(default_factory=list)
    tooltips: list[str] = Field(default_factory=list)


InsightView = Annotated[
    TableView
    | ScatterView
    | MetricView
    | HistogramView
    | CategoryChartView
    | BoxplotView
    | HeatmapView,
    Field(discriminator="kind"),
]


class InsightDefinition(StrictModel):
    """Complete portable version 1 insight definition."""

    version: Literal[1]
    insight_id: str | None = None
    name: str | None = None
    description: str | None = None
    analysis: AnalysisConfig
    view: InsightView

    @model_validator(mode="after")
    def validate_bindings(self) -> InsightDefinition:
        """Validate view references and expand join defaults."""

        for value in self.analysis.values:
            if value.parsed_field.kind == "contract" and value.scope is None:
                value.scope = ResultScope(
                    selection=(
                        "all_eligible"
                        if self.analysis.grain == "run"
                        else "latest_successful_per_sample"
                    )
                )

        value_references = {value.reference for value in self.analysis.values}
        identities = set(GRAIN_IDENTITIES[self.analysis.grain])
        allowed = value_references | identities
        references = _view_references(self.view)
        missing = sorted(set(references) - allowed)

        if missing:
            raise ValueError(f"View references unknown values: {', '.join(missing)}.")

        hidden = self.view.hidden_values
        duplicates = sorted({item for item in hidden if hidden.count(item) > 1})

        if duplicates:
            raise ValueError(
                f"Hidden value references must be unique: {', '.join(duplicates)}."
            )
        invalid_hidden = sorted(set(hidden) - value_references)

        if invalid_hidden:
            raise ValueError(
                f"Only analysis values can be hidden: {', '.join(invalid_hidden)}."
            )

        required = _required_view_bindings(self.view)
        hidden_required = sorted(set(hidden).intersection(required))

        if hidden_required:
            raise ValueError(
                "Required view bindings cannot be hidden: "
                f"{', '.join(hidden_required)}."
            )

        visible_series = _visible_series_ids(self)

        if (
            isinstance(self.view, (HistogramView, CategoryChartView, BoxplotView))
            and not visible_series
        ):
            raise ValueError(
                f"{self.view.kind} views require at least one visible value."
            )
        if self.view.kind in {"pie", "donut"} and len(visible_series) != 1:
            raise ValueError("Pie and donut views require exactly one visible value.")
        if self.view.kind == "stacked_bar" and len(visible_series) < 2:
            raise ValueError("Stacked bar views require at least two visible values.")
        if self.analysis.match_by is None and self.view.kind != "histogram":
            self.analysis.match_by = self.analysis.grain
        if self.analysis.join is None:
            self.analysis.join = "outer" if self.view.kind == "table" else "inner"
        return self

    def executable_config(self) -> dict[str, Any]:
        """Return only fields persisted in an insight record's JSON definition."""

        return self.model_dump(
            exclude={"insight_id", "name", "description"},
            exclude_none=True,
            mode="json",
            by_alias=True,
        )

    def compact_config(self) -> dict[str, Any]:
        """Serialize a valid definition without deterministic default noise."""

        data = self.executable_config()
        analysis = data["analysis"]

        if not analysis.get("filters"):
            analysis.pop("filters", None)

        if analysis.get("match_by") == analysis["grain"]:
            analysis.pop("match_by", None)

        default_join = "outer" if self.view.kind == "table" else "inner"

        if analysis.get("join") == default_join:
            analysis.pop("join", None)

        if analysis.get("limit") == RESULT_LIMIT_DEFAULT:
            analysis.pop("limit", None)

        if analysis.get("random") is False:
            analysis.pop("random", None)

        default_scope = (
            "all_eligible"
            if analysis["grain"] == "run"
            else "latest_successful_per_sample"
        )

        for value in analysis["values"]:
            if value.get("aggregation") == "raw":
                value.pop("aggregation", None)
            if not value.get("filters"):
                value.pop("filters", None)
            scope = value.get("scope")
            if (
                isinstance(scope, dict)
                and scope.get("selection") == default_scope
                and not any(scope.get(key) for key in scope if key != "selection")
            ):
                value.pop("scope", None)

        view = data["view"]

        for key, default in {
            "sorting": [],
            "null_format": "—",
            "numeric_format": {},
            "colors": {},
            "tooltips": [],
            "bins": 20,
            "thresholds": [],
            "hidden_values": [],
        }.items():
            if view.get(key) == default:
                view.pop(key, None)

        return data


class GridLayout(StrictModel):
    """Report-wide grid geometry."""

    columns: int = Field(default=12, ge=1, le=48)
    row_height: int = Field(default=64, ge=1, le=1000)


class ReportInsightLayout(StrictModel):
    """Placement of one report insight in grid coordinates."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ReportInsight(StrictModel):
    """A uniquely placed saved-insight reference."""

    id: str = Field(min_length=1)
    layout: ReportInsightLayout


class RefreshPolicy(StrictModel):
    """Saved report refresh behavior."""

    mode: Literal["manual"] = "manual"


class ReportDefinition(StrictModel):
    """Executable version 1 saved-report configuration."""

    version: Literal[1]
    filters: list[InsightFilter] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=RESULT_LIMIT_MAX)
    random: bool | None = None
    layout: GridLayout = Field(default_factory=GridLayout)
    insights: list[ReportInsight] = Field(min_length=1)
    refresh_policy: RefreshPolicy = Field(default_factory=RefreshPolicy)

    @model_validator(mode="after")
    def validate_insights(self) -> ReportDefinition:
        """Require unique insight identities and placements within grid bounds."""

        insight_ids = [insight.id for insight in self.insights]
        duplicates = sorted(
            {
                insight_id
                for insight_id in insight_ids
                if insight_ids.count(insight_id) > 1
            }
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
        """Return only fields persisted in a report record's JSON definition."""

        return self.model_dump(
            exclude_none=True,
            mode="json",
        )

    def compact_config(self) -> dict[str, Any]:
        """Serialize a valid report while omitting optional default blocks."""

        data = self.executable_config()
        if not data.get("filters"):
            data.pop("filters", None)
        if data.get("refresh_policy") == {"mode": "manual"}:
            data.pop("refresh_policy", None)
        return data


def _view_references(view: InsightView) -> list[str]:
    """Return all identity/value aliases referenced by a strict view model."""

    if isinstance(view, TableView):
        references = list(view.hidden_values)
        references.extend(sort.by for sort in view.sorting)
        references.extend(view.numeric_format)
        return references

    if isinstance(view, ScatterView):
        return [
            view.x,
            view.y,
            *view.hidden_values,
            *view.tooltips,
            *view.colors,
        ]

    if isinstance(view, MetricView):
        return [view.value, *view.hidden_values]

    if isinstance(view, HistogramView):
        return [*view.hidden_values, *view.colors]

    if isinstance(view, CategoryChartView):
        return [
            *([] if view.category is None else [view.category]),
            *view.hidden_values,
            *view.tooltips,
            *view.colors,
        ]

    if isinstance(view, BoxplotView):
        return [
            *([] if view.category is None else [view.category]),
            *view.hidden_values,
            *view.colors,
        ]

    return [
        view.x,
        view.y,
        view.value,
        *view.hidden_values,
        *view.tooltips,
    ]


def _required_view_bindings(view: InsightView) -> set[str]:
    """Return bindings that define a view and therefore cannot be hidden."""

    if isinstance(view, ScatterView):
        return {view.x, view.y}
    if isinstance(view, MetricView):
        return {view.value}
    if isinstance(view, HeatmapView):
        return {view.x, view.y, view.value}
    if isinstance(view, (CategoryChartView, BoxplotView)) and view.category:
        return {view.category}
    return set()


def _visible_series_ids(definition: InsightDefinition) -> list[str]:
    """Derive rendered series from canonical value order and view visibility."""

    hidden = set(definition.view.hidden_values)
    category = (
        definition.view.category
        if isinstance(definition.view, (CategoryChartView, BoxplotView))
        else None
    )
    return [
        value.reference
        for value in definition.analysis.values
        if value.reference not in hidden and value.reference != category
    ]


def normalize_insight_definition(value: dict[str, Any]) -> InsightDefinition:
    """Parse a complete definition and expand deterministic version 1 defaults."""

    return InsightDefinition.model_validate(value)


def normalize_report_definition(value: dict[str, Any]) -> ReportDefinition:
    """Parse a complete report definition with optional result-row overrides."""

    return ReportDefinition.model_validate(value)
