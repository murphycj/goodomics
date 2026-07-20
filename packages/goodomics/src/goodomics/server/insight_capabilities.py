"""Insight/report builder capabilities and validation helpers.

These capabilities are the Goodomics-owned contract for chart intent. Dashboard
controls, API validation, report execution, and future AI insight drafting should
use this module rather than reaching directly for ECharts-specific behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

JsonObject = dict[str, Any]

PREVIEW_DEFAULT_LIMIT = 1000
MORE_ROWS_MAX_LIMIT = 10000
ALL_ROWS_INLINE_THRESHOLD = 10000
EXPORT_FULL_DATA_LIMIT = 100000

LINKERS: dict[str, JsonObject] = {
    "auto": {
        "id": "auto",
        "label": "Auto",
        "column": None,
        "description": "Let Goodomics select the only valid linker.",
    },
    "sample": {
        "id": "sample",
        "label": "Sample",
        "column": "sample_id",
        "description": "Align values by biological sample.",
    },
    "run": {
        "id": "run",
        "label": "Run",
        "column": "run_id",
        "description": "Align values by run.",
    },
    "feature": {
        "id": "feature",
        "label": "Feature",
        "column": "feature_id",
        "description": "Align values by measured feature, gene, variant, or metric.",
    },
    "entity": {
        "id": "entity",
        "label": "Entity",
        "column": "entity_id",
        "description": "Align generic entity-attribute values.",
    },
    "time": {
        "id": "time",
        "label": "Time",
        "column": "time",
        "description": "Align values by a selected time/date field.",
    },
}

ANALYSIS_GRAINS: dict[str, JsonObject] = {
    "sample": {
        "id": "sample",
        "label": "Samples",
        "singular_label": "Sample",
        "description": "Analyze biological samples across one or more runs.",
        "default_visualization": "table",
        "default_linker": "sample",
        "identity_columns": ["sample_id"],
        "valid_linkers": ["sample"],
    },
    "subject": {
        "id": "subject",
        "label": "Subjects",
        "singular_label": "Subject",
        "description": "Analyze subject-level attributes and rollups.",
        "default_visualization": "table",
        "default_linker": "entity",
        "identity_columns": ["entity_id", "sample_id"],
        "valid_linkers": ["entity", "sample"],
    },
    "run": {
        "id": "run",
        "label": "Runs",
        "singular_label": "Run",
        "description": "Analyze pipeline runs and run-level files or metrics.",
        "default_visualization": "table",
        "default_linker": "run",
        "identity_columns": ["run_id"],
        "valid_linkers": ["run"],
    },
    "feature": {
        "id": "feature",
        "label": "Features",
        "singular_label": "Feature",
        "description": "Analyze genes, regions, features, or measured entities.",
        "default_visualization": "histogram",
        "default_linker": "feature",
        "identity_columns": ["feature_id", "sample_id"],
        "valid_linkers": ["feature", "sample"],
    },
    "variant": {
        "id": "variant",
        "label": "Variants",
        "singular_label": "Variant",
        "description": "Analyze variant and feature-call rows.",
        "default_visualization": "table",
        "default_linker": "feature",
        "identity_columns": ["variant_id", "feature_id", "sample_id"],
        "valid_linkers": ["feature", "sample"],
    },
    "file": {
        "id": "file",
        "label": "Files",
        "singular_label": "File",
        "description": "Analyze stored files and payload artifacts.",
        "default_visualization": "table",
        "default_linker": "run",
        "identity_columns": ["source_file_id", "run_id", "sample_id"],
        "valid_linkers": ["run", "sample"],
    },
}

TEMPLATES: dict[str, JsonObject] = {
    "qc_metrics_samples": {
        "id": "qc_metrics_samples",
        "label": "QC metrics across samples",
        "description": "Start a sample table from QC contract fields.",
        "analysis_grain": "sample",
        "visualization": "table",
        "linker": {"kind": "sample"},
        "result_policy": {"mode": "preview"},
    },
    "build_table": {
        "id": "build_table",
        "label": "Build a table",
        "description": "Choose identity and contract columns at the selected grain.",
        "analysis_grain": "sample",
        "visualization": "table",
        "linker": {"kind": "sample"},
        "result_policy": {"mode": "preview"},
    },
    "compare_two_fields": {
        "id": "compare_two_fields",
        "label": "Compare two fields",
        "description": "Create a two-value scatter matched by sample.",
        "analysis_grain": "sample",
        "visualization": "scatter",
        "linker": {"kind": "sample"},
        "result_policy": {"mode": "preview"},
    },
    "inspect_one_sample": {
        "id": "inspect_one_sample",
        "label": "Inspect one sample",
        "description": "Start a sample-filtered detail table.",
        "analysis_grain": "sample",
        "visualization": "table",
        "linker": {"kind": "sample"},
        "context": {"kind": "sample"},
        "result_policy": {"mode": "preview"},
    },
    "explore_feature": {
        "id": "explore_feature",
        "label": "Explore a gene/feature",
        "description": "Start a feature-grain numeric distribution.",
        "analysis_grain": "feature",
        "visualization": "histogram",
        "linker": {"kind": "feature"},
        "result_policy": {"mode": "preview"},
    },
    "variant_call_table": {
        "id": "variant_call_table",
        "label": "Variant/call table",
        "description": "Start a table for variants, calls, or feature states.",
        "analysis_grain": "variant",
        "visualization": "table",
        "linker": {"kind": "feature"},
        "result_policy": {"mode": "preview"},
    },
}

CHARTS: dict[str, JsonObject] = {
    "bar": {
        "id": "bar",
        "label": "Bar chart",
        "icon": "BarChart3",
        "series": {"min": 1, "max": None, "numeric": "mixed"},
        "requires_linker": "multi_numeric",
        "rule": (
            "One numeric series plots values by entity/linker; categorical "
            "series count categories; multiple numeric series align by linker."
        ),
    },
    "stacked_bar": {
        "id": "stacked_bar",
        "label": "Stacked bar",
        "icon": "BarChart2",
        "series": {"min": 2, "max": None, "numeric": True},
        "requires_linker": True,
        "rule": (
            "Two or more numeric series with a shared linker; duplicate fields "
            "remain separate colored stacked series."
        ),
    },
    "line": {
        "id": "line",
        "label": "Line chart",
        "icon": "LineChart",
        "series": {"min": 1, "max": None, "numeric": True},
        "requires_linker": "multi_series",
        "rule": "Numeric series aligned by entity, feature, time, or selected linker.",
    },
    "area": {
        "id": "area",
        "label": "Area chart",
        "icon": "AreaChart",
        "series": {"min": 1, "max": None, "numeric": True},
        "requires_linker": "multi_series",
        "rule": "Numeric series aligned by entity, feature, time, or selected linker.",
    },
    "scatter": {
        "id": "scatter",
        "label": "Scatter plot",
        "icon": "ScatterChart",
        "series": {"min": 2, "max": 2, "numeric": True},
        "requires_linker": True,
        "rule": "Exactly two numeric measures with a visible linker.",
    },
    "histogram": {
        "id": "histogram",
        "label": "Histogram",
        "icon": "BarChart2",
        "series": {"min": 1, "max": None, "numeric": True},
        "requires_linker": False,
        "rule": "One or more numeric series rendered as overlaid bins.",
    },
    "boxplot": {
        "id": "boxplot",
        "label": "Box plot",
        "icon": "Box",
        "series": {"min": 1, "max": None, "numeric": True},
        "requires_linker": "comparison",
        "rule": "Numeric values grouped by sample group, sample, run, or category.",
    },
    "pie": {
        "id": "pie",
        "label": "Pie chart",
        "icon": "PieChart",
        "series": {"min": 1, "max": 1, "numeric": "value"},
        "requires_linker": False,
        "rule": "Exactly one series.",
    },
    "donut": {
        "id": "donut",
        "label": "Donut chart",
        "icon": "PieChart",
        "series": {"min": 1, "max": 1, "numeric": "value"},
        "requires_linker": False,
        "rule": "Exactly one series.",
    },
    "table": {
        "id": "table",
        "label": "Table",
        "icon": "Table2",
        "series": {"min": 0, "max": None, "numeric": False},
        "requires_linker": False,
        "rule": "Any supported fields.",
    },
    "metric": {
        "id": "metric",
        "label": "Metric",
        "icon": "Hash",
        "series": {"min": 1, "max": 1, "numeric": "value"},
        "requires_linker": False,
        "rule": "One headline value.",
    },
}

RESULT_POLICIES: dict[str, JsonObject] = {
    "preview": {
        "id": "preview",
        "label": "Preview default",
        "default_limit": PREVIEW_DEFAULT_LIMIT,
        "max_limit": PREVIEW_DEFAULT_LIMIT,
        "description": "Embed up to 1,000 rows.",
    },
    "more_rows": {
        "id": "more_rows",
        "label": "More rows",
        "default_limit": 5000,
        "max_limit": MORE_ROWS_MAX_LIMIT,
        "description": "Embed a bounded user-selected number of rows.",
    },
    "random_sample": {
        "id": "random_sample",
        "label": "Random sample",
        "default_limit": PREVIEW_DEFAULT_LIMIT,
        "max_limit": MORE_ROWS_MAX_LIMIT,
        "description": "Embed a deterministic sampled subset.",
    },
    "all_rows": {
        "id": "all_rows",
        "label": "All rows",
        "default_limit": ALL_ROWS_INLINE_THRESHOLD,
        "max_limit": ALL_ROWS_INLINE_THRESHOLD,
        "description": "Embed all rows only below the configured threshold.",
    },
    "export_full_data": {
        "id": "export_full_data",
        "label": "Export full data",
        "default_limit": EXPORT_FULL_DATA_LIMIT,
        "max_limit": EXPORT_FULL_DATA_LIMIT,
        "description": "Write complete plot/table data to a file-backed artifact.",
    },
}


def insight_capabilities() -> JsonObject:
    """Return the server-owned capabilities used by builders and validators."""

    return {
        "version": 1,
        "analysis_grains": list(ANALYSIS_GRAINS.values()),
        "templates": list(TEMPLATES.values()),
        "charts": list(CHARTS.values()),
        "linkers": list(LINKERS.values()),
        "result_policies": list(RESULT_POLICIES.values()),
        "validation_messages": {
            "scatter_two_numeric": (
                "Scatter plots require exactly two numeric measures."
            ),
            "linker_choice": (
                "This chart has multiple valid linkers; choose Matched by explicitly."
            ),
            "numeric_only": "This chart only supports numeric series.",
            "single_series": "Pie and donut charts require exactly one series.",
            "all_rows_threshold": (
                "All rows can only be embedded below the configured response threshold."
            ),
            "invalid_analysis_grain": "Choose a supported Analyze by grain.",
        },
    }


def normalize_linker(value: Any) -> JsonObject:
    """Normalize string/object linker config to ``{"kind": ...}``."""

    if isinstance(value, str):
        kind = value
    elif isinstance(value, Mapping):
        kind = str(value.get("kind") or value.get("id") or "auto")
    else:
        kind = "auto"
    if kind not in LINKERS:
        kind = "auto"
    normalized = {"kind": kind}
    if isinstance(value, Mapping):
        for key in ("field", "label"):
            if isinstance(value.get(key), str):
                normalized[key] = value[key]
    return normalized


def normalize_result_policy(value: Any) -> JsonObject:
    """Normalize result-size policy config with bounded limits."""

    if isinstance(value, str):
        mode = value
        raw_limit = None
        raw_seed = None
    elif isinstance(value, Mapping):
        mode = str(value.get("mode") or value.get("kind") or "preview")
        raw_limit = value.get("limit") or value.get("sample_size")
        raw_seed = value.get("seed")
    else:
        mode = "preview"
        raw_limit = None
        raw_seed = None
    if mode not in RESULT_POLICIES:
        mode = "preview"
    policy_definition = RESULT_POLICIES[mode]
    default_limit = int(policy_definition["default_limit"])
    max_limit = int(policy_definition["max_limit"])
    try:
        limit = int(raw_limit if raw_limit is not None else default_limit)
    except (TypeError, ValueError):
        limit = default_limit
    normalized: JsonObject = {
        "mode": mode,
        "limit": min(max(limit, 1), max_limit),
    }
    if mode == "random_sample":
        normalized["seed"] = str(raw_seed if raw_seed is not None else "goodomics")
    return normalized


def chart_rule(chart_id: str) -> JsonObject:
    """Return a chart rule, defaulting unknown charts to table."""

    return CHARTS.get(chart_id, CHARTS["table"])


def explain_insight_config(config: Mapping[str, Any]) -> str:
    """Build a compact explanation of a normalized insight config."""

    analysis_grain = str(config.get("analysis_grain") or "sample")
    grain = ANALYSIS_GRAINS.get(analysis_grain, ANALYSIS_GRAINS["sample"])
    chart = str(config.get("visualization") or "table")
    raw_context = config.get("context")
    context: Mapping[str, Any] = raw_context if isinstance(raw_context, Mapping) else {}
    linker = normalize_linker(config.get("linker"))
    policy = normalize_result_policy(config.get("result_policy"))
    value_labels = [
        str(item.get("name") or item.get("label") or item.get("field_id") or "series")
        for item in _series_items(config)
    ]
    table_labels = [
        str(item.get("label") or item.get("field_id") or item.get("column") or "column")
        for item in _table_column_items(config)
    ]
    context_label = str(context.get("kind") or "sample_group")
    if context.get("sample_group_id"):
        context_label += f" {context['sample_group_id']}"
    if context.get("sample_id"):
        context_label += f" {context['sample_id']}"
    return (
        f"{grain['label']} insight using "
        f"{CHARTS.get(chart, CHARTS['table'])['label']} over {context_label}; "
        f"values: {', '.join(value_labels) or 'none'}; "
        f"columns: {', '.join(table_labels) or 'default identity'}; "
        f"matched by {linker['kind']}; data size policy {policy['mode']}."
    )


def validate_config_shape(config: Mapping[str, Any]) -> list[JsonObject]:
    """Validate the config shape before data-specific checks."""

    messages: list[JsonObject] = []
    chart = str(config.get("visualization") or "table")
    grain = str(config.get("analysis_grain") or "sample")
    if grain not in ANALYSIS_GRAINS:
        messages.append(
            {
                "level": "error",
                "code": "invalid_analysis_grain",
                "message": f"Unsupported analysis grain: {grain}.",
            }
        )
    rule = chart_rule(chart)
    series_count = len(_series_items(config))
    series_rule = rule["series"]
    minimum = int(series_rule["min"])
    maximum = series_rule["max"]
    if series_count < minimum:
        messages.append(
            {
                "level": "error",
                "code": "too_few_series",
                "message": (
                    f"{rule['label']} requires at least {minimum} "
                    f"{'series' if minimum != 1 else 'series'}."
                ),
            }
        )
    if maximum is not None and series_count > int(maximum):
        messages.append(
            {
                "level": "error",
                "code": "too_many_series",
                "message": f"{rule['label']} allows at most {maximum} series.",
            }
        )
    if chart in {"pie", "donut"} and series_count != 1:
        messages.append(
            {
                "level": "error",
                "code": "single_series",
                "message": "Pie and donut charts require exactly one series.",
            }
        )
    return messages


def _series_items(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = config.get("series")
    query = config.get("query") if isinstance(config.get("query"), Mapping) else {}
    if not raw and isinstance(query, Mapping):
        raw = query.get("measures")
    if not raw and isinstance(query, Mapping):
        x_value = query.get("x")
        y_value = query.get("y")
        if isinstance(x_value, str) and isinstance(y_value, str):
            raw = [{"field": x_value}, {"field": y_value}]
    if isinstance(raw, Mapping):
        return [raw]
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        return [item for item in raw if isinstance(item, Mapping)]
    return []


def _table_column_items(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = config.get("table_columns")
    if isinstance(raw, Mapping):
        return [raw]
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        return [item for item in raw if isinstance(item, Mapping)]
    return []
