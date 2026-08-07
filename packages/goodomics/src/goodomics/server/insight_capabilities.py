"""Server-owned insight/report builder capabilities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from goodomics.schemas.field_references import metadata_field_reference

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

# These mappings remain private execution helpers while the old resolver is
# incrementally reused under the version 1 value planner.
LINKERS: dict[str, JsonObject] = {
    "sample": {"id": "sample", "column": "sample_id"},
    "subject": {"id": "subject", "column": "entity_id"},
    "run": {"id": "run", "column": "run_id"},
    "feature": {"id": "feature", "column": "feature_id"},
    "variant": {"id": "variant", "column": "variant_id"},
    "file": {"id": "file", "column": "source_file_id"},
    "auto": {"id": "auto", "column": None},
    "none": {"id": "none", "column": None},
}
TEMPLATES: dict[str, JsonObject] = {
    "build_table": {
        "id": "build_table",
        "label": "Build a table",
        "definition": {
            "version": 1,
            "analysis": {"grain": "sample", "values": []},
            "view": {"kind": "table"},
        },
    },
    "compare_two_fields": {
        "id": "compare_two_fields",
        "label": "Compare two fields",
        "definition": {
            "version": 1,
            "analysis": {
                "grain": "sample",
                "values": [],
                "match_by": "sample",
                "join": "inner",
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
    """Return strict version 1 builder capabilities."""

    return {
        "version": 1,
        "analysis_grains": list(ANALYSIS_GRAINS.values()),
        "templates": list(TEMPLATES.values()),
        "charts": list(CHARTS.values()),
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
    """Explain a normalized version 1 definition in public terminology."""

    raw_analysis = config.get("analysis")
    analysis: Mapping[str, Any] = (
        raw_analysis if isinstance(raw_analysis, Mapping) else {}
    )
    raw_values = analysis.get("values")
    values = raw_values if isinstance(raw_values, Sequence) else []
    value_labels = [
        str(value.get("label") or value.get("as") or value.get("field"))
        for value in values
        if isinstance(value, Mapping)
    ]
    raw_view = config.get("view")
    view: Mapping[str, Any] = raw_view if isinstance(raw_view, Mapping) else {}
    return (
        f"{analysis.get('grain', 'sample')} insight with {view.get('kind', 'table')} "
        f"view; values: {', '.join(value_labels) or 'none'}; matched by "
        f"{analysis.get('match_by') or 'none'} using "
        f"{analysis.get('join') or 'view default'} join; returning up to "
        f"{analysis.get('limit', PREVIEW_DEFAULT_LIMIT)} final rows"
        f"{' selected randomly' if analysis.get('random') else ''}."
    )


def validate_config_shape(config: Mapping[str, Any]) -> list[JsonObject]:
    """Retain the old helper name for callers; Pydantic owns shape validation."""

    del config
    return []
