"""Server-owned insight/report builder capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from goodomics.schemas.field_references import metadata_field_reference
from goodomics.schemas.insights import (
    VIEWS_BY_QUERY_KIND,
    AlterationMatrixQuery,
    AssociationQuery,
    DistributionQuery,
    GenomeProfileQuery,
    InsightSpec,
    MatrixQuery,
    RelationshipQuery,
    RowsQuery,
    SeriesQuery,
    SummaryQuery,
    SurvivalQuery,
    TimelineQuery,
    VariantPositionQuery,
)

JsonObject = dict[str, Any]

PREVIEW_DEFAULT_LIMIT = 1000
MORE_ROWS_MAX_LIMIT = 10000
ALL_ROWS_INLINE_THRESHOLD = 10000
EXPORT_FULL_DATA_LIMIT = 100000

AGGREGATIONS_BY_TYPE: dict[str, list[str]] = {
    "string": ["raw", "count", "count_distinct"],
    "categorical": ["raw", "count", "count_distinct"],
    "boolean": ["raw", "count", "count_distinct"],
    "numeric": [
        "raw",
        "count",
        "count_distinct",
        "sum",
        "avg",
        "min",
        "max",
    ],
    "date": ["raw", "min", "max"],
    "datetime": ["raw", "min", "max"],
}

METADATA_FIELDS: tuple[JsonObject, ...] = (
    {
        "entity": "subject",
        "field": "subject_id",
        "label": "Subject ID",
        "value_type": "string",
        "allowed_grains": ["subject"],
    },
    {
        "entity": "sample",
        "field": "sample_id",
        "label": "Sample ID",
        "value_type": "string",
        "allowed_grains": ["sample"],
    },
    {
        "entity": "sample",
        "field": "sample_name",
        "label": "Sample name",
        "value_type": "string",
        "allowed_grains": ["sample"],
    },
    {
        "entity": "sample",
        "field": "subject_id",
        "label": "Subject ID",
        "value_type": "string",
        "allowed_grains": ["sample"],
    },
    *(
        {
            "entity": "run",
            "field": field,
            "label": label,
            "value_type": value_type,
            "allowed_grains": ["run"],
        }
        for field, label, value_type in (
            ("run_id", "Run ID", "string"),
            ("name", "Run name", "string"),
            ("run_kind", "Run kind", "string"),
            ("analysis_type_id", "Analysis type", "string"),
            ("method_id", "Method", "string"),
            ("method_version", "Method version", "string"),
            ("status", "Status", "string"),
            ("started_at", "Started at", "date"),
            ("ended_at", "Ended at", "date"),
            ("created_at", "Created at", "date"),
        )
    ),
    *(
        {
            "entity": "file",
            "field": field,
            "label": label,
            "value_type": value_type,
            "allowed_grains": ["file"],
        }
        for field, label, value_type in (
            ("file_id", "File ID", "string"),
            ("file_role", "File role", "string"),
            ("format", "Format", "string"),
            ("size_bytes", "Size (bytes)", "numeric"),
            ("storage_location", "Storage location", "string"),
            ("created_at", "Created at", "date"),
        )
    ),
)

ANALYSIS_GRAINS: dict[str, JsonObject] = {
    grain: {
        "id": grain,
        "label": label,
        "singular_label": singular,
        "identity_columns": [identity],
        "default_match_by": grain,
    }
    for grain, label, singular, identity in (
        ("sample", "Samples", "Sample", "sample_id"),
        ("subject", "Subjects", "Subject", "subject_id"),
        ("run", "Runs", "Run", "run_id"),
        ("feature", "Features", "Feature", "feature_id"),
        ("variant", "Variants", "Variant", "variant_id"),
        ("file", "Files", "File", "file_id"),
        ("row", "Rows", "Row", "row_id"),
    )
}

CHARTS: dict[str, JsonObject] = {
    "table": {
        "id": "table",
        "label": "Table",
        "visible_values": {"min": 1, "max": None, "numeric": False},
        "default_join": "outer",
    },
    "metric": {
        "id": "metric",
        "label": "Metric",
        "visible_values": {"min": 1, "max": 1, "numeric": "value"},
        "default_join": "inner",
    },
    "scatter": {
        "id": "scatter",
        "label": "Scatter plot",
        "visible_values": {"min": 2, "max": 2, "numeric": True},
        "default_join": "inner",
    },
    "histogram": {
        "id": "histogram",
        "label": "Histogram",
        "visible_values": {"min": 1, "max": None, "numeric": True},
        "default_join": None,
    },
    **{
        chart: {
            "id": chart,
            "label": label,
            "visible_values": {
                "min": minimum,
                "max": maximum,
                "numeric": numeric,
            },
            "default_join": "inner",
        }
        for chart, label, minimum, maximum, numeric in (
            ("bar", "Bar chart", 1, None, "mixed"),
            ("stacked_bar", "Stacked bar", 2, None, True),
            ("line", "Line chart", 1, None, True),
            ("area", "Area chart", 1, None, True),
            ("boxplot", "Box plot", 1, None, True),
            ("pie", "Pie chart", 1, 1, "value"),
            ("donut", "Donut chart", 1, 1, "value"),
            ("heatmap", "Heatmap", 3, 3, "value"),
        )
    },
}

OUTPUT_MODES: dict[str, JsonObject] = {
    "preview": {"id": "preview", "default_limit": 1000, "max_limit": 1000},
    "more_rows": {"id": "more_rows", "default_limit": 5000, "max_limit": 10000},
    "random_sample": {
        "id": "random_sample",
        "default_limit": 1000,
        "max_limit": 10000,
    },
    "all_rows": {"id": "all_rows", "default_limit": 10000, "max_limit": 10000},
    "export_full_data": {
        "id": "export_full_data",
        "default_limit": 100000,
        "max_limit": 100000,
    },
}

# These mappings remain private execution helpers behind typed query runners.
LINKERS: dict[str, JsonObject] = {
    "sample": {"id": "sample", "column": "sample_id"},
    "subject": {"id": "subject", "column": "entity_id"},
    "run": {"id": "run", "column": "run_id"},
    "feature": {"id": "feature", "column": "feature_id"},
    "variant": {"id": "variant", "column": "variant_id"},
    "file": {"id": "file", "column": "source_file_id"},
    "row": {"id": "row", "column": "row_id"},
    "auto": {"id": "auto", "column": None},
    "none": {"id": "none", "column": None},
}
TEMPLATES: dict[str, JsonObject] = {
    "build_table": {
        "id": "build_table",
        "label": "Build a table",
        "definition": {
            "version": 2,
            "name": "Untitled table",
            "query": {"kind": "rows", "grain": "sample", "columns": []},
            "view": {"kind": "table"},
        },
    },
    "compare_two_fields": {
        "id": "compare_two_fields",
        "label": "Compare two fields",
        "definition": {
            "version": 2,
            "name": "Untitled relationship",
            "query": {
                "kind": "relationship",
                "match_by": "sample",
            },
            "view": {"kind": "scatter"},
        },
    },
}


def metadata_fields() -> list[JsonObject]:
    """Return metadata field definitions enriched with type-specific behavior."""

    return [
        _enriched_metadata_field(entry, canonical_reference=True)
        for entry in METADATA_FIELDS
    ]


def metadata_field(entity: str, field: str) -> JsonObject | None:
    """Return one metadata field definition by its stable public source pair."""

    entry = next(
        (
            entry
            for entry in METADATA_FIELDS
            if entry["entity"] == entity and entry["field"] == field
        ),
        None,
    )
    return _enriched_metadata_field(entry) if entry is not None else None


def _enriched_metadata_field(
    entry: JsonObject, *, canonical_reference: bool = False
) -> JsonObject:
    field = str(entry["field"])
    return {
        **entry,
        "field": (
            metadata_field_reference(str(entry["entity"]), field)
            if canonical_reference
            else field
        ),
        "allowed_aggregations": AGGREGATIONS_BY_TYPE[str(entry["value_type"])],
        "filterable": True,
        "groupable": True,
    }


def insight_capabilities() -> JsonObject:
    """Return family-specific version 2 builder capabilities."""

    return {
        "version": 2,
        "analysis_grains": list(ANALYSIS_GRAINS.values()),
        "templates": list(TEMPLATES.values()),
        "charts": list(CHARTS.values()),
        "query_families": [
            {
                "kind": kind,
                "views": sorted(views),
                "provider_required": kind == "survival",
            }
            for kind, views in VIEWS_BY_QUERY_KIND.items()
        ],
        "metadata_fields": metadata_fields(),
        "aggregations_by_type": AGGREGATIONS_BY_TYPE,
        "result_rows": {
            "default_limit": PREVIEW_DEFAULT_LIMIT,
            "max_limit": MORE_ROWS_MAX_LIMIT,
            "random_supported": True,
        },
    }


def normalize_linker(value: Any) -> JsonObject:
    """Normalize an internal match-by value for the reused resolver."""

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or value.get("id") or "auto")
    else:
        kind = str(value or "auto")
    return {"kind": kind if kind in LINKERS else "auto"}


def normalize_result_policy(value: Any) -> JsonObject:
    """Normalize an internal output mapping with deterministic bounds."""

    if isinstance(value, Mapping):
        mode = str(value.get("mode") or "preview")
        raw_limit = value.get("limit")
        seed = value.get("seed")
    else:
        mode = str(value or "preview")
        raw_limit = None
        seed = None
    if mode not in OUTPUT_MODES:
        mode = "preview"
    definition = OUTPUT_MODES[mode]
    try:
        limit = int(raw_limit if raw_limit is not None else definition["default_limit"])
    except (TypeError, ValueError):
        limit = int(definition["default_limit"])
    normalized: JsonObject = {
        "mode": mode,
        "limit": min(max(limit, 1), int(definition["max_limit"])),
    }
    if mode == "random_sample":
        normalized["seed"] = str(seed or "goodomics")
    return normalized


def chart_rule(chart_id: str) -> JsonObject:
    """Return the server-owned rule for one chart kind."""

    return CHARTS.get(chart_id, CHARTS["table"])


def explain_insight_config(config: Mapping[str, Any]) -> str:
    """Explain a normalized version 2 definition in deterministic plain language."""

    definition = InsightSpec.model_validate(config)
    return explain_query(definition.query)


def explain_query(query: Any, labels: Mapping[str, str] | None = None) -> str:
    """Explain every typed query family using resolved labels when available."""

    labels = labels or {}

    def label(selection: Any) -> str:
        """Resolve a field selection to a display label or canonical reference."""

        field = str(selection.field)
        return labels.get(field) or selection.label or field

    if isinstance(query, RowsQuery):
        columns = ", ".join(label(item) for item in query.columns)
        text = f"Show one row per {query.grain} with {columns}."
    elif isinstance(query, SummaryQuery):
        groups = ", ".join(label(item) for item in query.group_by) or "the full cohort"
        operations = ", ".join(
            f"{item.aggregation.replace('_', ' ')} of {label(item)} as {item.reference}"
            for item in query.aggregations
        )
        text = f"Group {query.grain}s by {groups} and calculate {operations}."
        if query.calculations:
            calculations = ", ".join(
                f"{item.calculation.replace('_', ' ')} of {item.input} as {item.alias}"
                for item in query.calculations
            )
            text = f"{text[:-1]} and {calculations}."
    elif isinstance(query, RelationshipQuery):
        text = (
            f"Compare {label(query.x)} with {label(query.y)}, matching "
            f"observations by {query.match_by}."
        )
    elif isinstance(query, DistributionQuery):
        split = (
            f" split by {', '.join(label(item) for item in query.split_by)}"
            if query.split_by
            else ""
        )
        text = f"Show the distribution of {label(query.value)}{split}."
    elif isinstance(query, SeriesQuery):
        series = ", ".join(label(item) for item in query.series_by)
        text = (
            f"Order {', '.join(label(item) for item in query.measurements)} by "
            f"{label(query.position)}"
            + (f" with separate series for {series}" if query.series_by else "")
            + "."
        )
    elif isinstance(query, MatrixQuery):
        text = (
            f"Build a raw-value matrix with {label(query.rows)} as rows, "
            f"{label(query.columns)} as columns, and {label(query.value)} as cells."
        )
    elif isinstance(query, AlterationMatrixQuery):
        alterations = ", ".join(label(item) for item in query.alterations)
        text = (
            f"Build a coverage-aware alteration matrix for {len(query.features)} "
            f"features using {alterations}."
        )
    elif isinstance(query, VariantPositionQuery):
        text = (
            f"Group variants at {label(query.position)} and size recurrent "
            f"positions by {label(query.frequency)}."
        )
    elif isinstance(query, GenomeProfileQuery):
        text = (
            f"Lay out {label(query.value)} over {label(query.coordinate)} "
            "genomic coordinates."
        )
    elif isinstance(query, SurvivalQuery):
        text = (
            f"Analyze time to event using {label(query.duration)} and "
            f"{label(query.event)}; "
            f"execution requires an analysis provider for {query.provider.method}."
        )
    elif isinstance(query, TimelineQuery):
        text = (
            f"Arrange events for {label(query.subject)} by {label(query.start)} "
            "on a subject timeline."
        )
    elif isinstance(query, AssociationQuery):
        text = (
            "Calculate descriptive eligible and co-occurrence counts for "
            f"{len(query.features)} features without significance testing."
        )
    else:
        raise TypeError(f"Unsupported query type: {type(query).__name__}")
    filters = getattr(query, "filters", [])
    if filters:
        suffix = "s" if len(filters) != 1 else ""
        text = f"{text[:-1]} after applying {len(filters)} filter{suffix}."
    return text


def validate_config_shape(config: Mapping[str, Any]) -> list[JsonObject]:
    """Return deterministic structural validation diagnostics for a v2 envelope."""

    try:
        InsightSpec.model_validate(config)
    except ValueError as error:
        return [{"level": "error", "code": "invalid_definition", "message": str(error)}]
    return []
