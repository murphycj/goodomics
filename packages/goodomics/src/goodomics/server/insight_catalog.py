"""Insight/report builder catalog and validation helpers.

The catalog is the Goodomics-owned contract for chart intent. Dashboard controls,
API validation, report execution, and future AI insight drafting should use this
module rather than reaching directly for ECharts-specific behavior.
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
    "run_sample": {
        "id": "run_sample",
        "label": "Run sample",
        "column": "run_sample_id",
        "description": "Align values by sample/run link.",
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

MODES: dict[str, JsonObject] = {
    "contract_metrics": {
        "id": "contract_metrics",
        "label": "Cohort analysis",
        "icon": "BarChart3",
        "description": "Cohort-level metric panels from one or more contract fields.",
        "default_visualization": "bar",
        "supports_add_all_numeric": True,
    },
    "comparison": {
        "id": "comparison",
        "label": "Comparison",
        "icon": "ScatterChart",
        "description": "Align two or more values across a shared linker.",
        "default_visualization": "scatter",
        "supports_add_all_numeric": False,
    },
    "sample_detail": {
        "id": "sample_detail",
        "label": "Sample detail",
        "icon": "FileSearch",
        "description": "Inspect a single sample or run/sample link.",
        "default_visualization": "table",
        "supports_add_all_numeric": False,
    },
    "variant_table": {
        "id": "variant_table",
        "label": "Table",
        "icon": "Table2",
        "description": "Variant, feature-call, and generic table outputs.",
        "default_visualization": "table",
        "supports_add_all_numeric": False,
    },
    "advanced_sql": {
        "id": "advanced_sql",
        "label": "Advanced SQL",
        "icon": "Code2",
        "description": (
            "Read-only SQL escape hatch with the same result policy guardrails."
        ),
        "default_visualization": "table",
        "supports_add_all_numeric": False,
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
        "rule": "Numeric values grouped by sample set, sample, run, or category.",
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


def insight_catalog() -> JsonObject:
    """Return the server-owned catalog used by builders and validators."""

    return {
        "version": 1,
        "modes": list(MODES.values()),
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
    catalog_policy = RESULT_POLICIES[mode]
    default_limit = int(catalog_policy["default_limit"])
    max_limit = int(catalog_policy["max_limit"])
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

    mode = str(config.get("mode") or "contract_metrics")
    chart = str(config.get("visualization") or "table")
    raw_context = config.get("context")
    context: Mapping[str, Any] = raw_context if isinstance(raw_context, Mapping) else {}
    linker = normalize_linker(config.get("linker"))
    policy = normalize_result_policy(config.get("result_policy"))
    series_labels = [
        str(item.get("name") or item.get("label") or item.get("field_id") or "series")
        for item in _series_items(config)
    ]
    context_label = str(context.get("kind") or "cohort")
    if context.get("sample_set_id"):
        context_label += f" {context['sample_set_id']}"
    if context.get("sample_id"):
        context_label += f" {context['sample_id']}"
    return (
        f"{MODES.get(mode, MODES['contract_metrics'])['label']} insight using "
        f"{CHARTS.get(chart, CHARTS['table'])['label']} over {context_label}; "
        f"series: {', '.join(series_labels) or 'table rows'}; "
        f"matched by {linker['kind']}; data size policy {policy['mode']}."
    )


def validate_config_shape(config: Mapping[str, Any]) -> list[JsonObject]:
    """Validate catalog-level config shape before data-specific checks."""

    messages: list[JsonObject] = []
    chart = str(config.get("visualization") or "table")
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
