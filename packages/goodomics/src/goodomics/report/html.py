from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import yaml


def load_report_template(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
    return value if isinstance(value, dict) else {}


def render_report(
    results: Path | str,
    *,
    name: str = "Goodomics Report",
    template: dict[str, Any] | None = None,
) -> str:
    template = template or {}
    config = template.get("config")
    if isinstance(config, dict) and isinstance(config.get("name"), str):
        name = config["name"]
    safe_results = escape(str(results))
    safe_name = escape(name)
    return (
        "<!doctype html>"
        f"<title>{safe_name}</title>"
        f"<h1>{safe_name}</h1>"
        f"<p>Scanned results: {safe_results}</p>"
    )


def render_report_result(result: dict[str, Any]) -> str:
    name = str(result.get("name") or "Goodomics Report")
    insights = result.get("insights")
    insight_items = insights if isinstance(insights, list) else []
    payload_json = json.dumps(result, default=str)
    return (
        "<!doctype html>"
        "<html><head>"
        '<meta charset="utf-8">'
        f"<title>{escape(name)}</title>"
        "<style>"
        "body{margin:0;font-family:Inter,system-ui,sans-serif;background:#f7f8fa;"
        "color:#1d2430;}"
        "main{padding:28px;}.report-grid{display:grid;"
        "grid-template-columns:repeat(12,1fr);gap:16px;}"
        ".insight{grid-column:span 6;min-height:260px;border:1px solid #dce3eb;"
        "background:white;border-radius:8px;padding:16px;}"
        ".insight-wide{grid-column:span 12;}h1{margin:0 0 8px;}"
        "h2{margin:0 0 8px;font-size:18px;}"
        "table{width:100%;border-collapse:collapse;font-size:13px;}"
        "th,td{border-bottom:1px solid #e4eaf1;padding:8px;text-align:left;}"
        ".metric-value{font-size:34px;font-weight:700;color:#16784a;}"
        ".chart-fallback{overflow:auto;max-height:360px;}"
        "</style>"
        "</head><body>"
        "<main>"
        f"<h1>{escape(name)}</h1>"
        f"<p>Computed {escape(str(result.get('computed_at') or ''))}</p>"
        '<div class="report-grid">'
        + "".join(_render_insight_block(item) for item in insight_items)
        + "</div>"
        "</main>"
        "<script>window.goodomicsReport="
        + payload_json.replace("</", "<\\/")
        + ";</script>"
        "<script>/* ECharts option payloads are embedded above. */</script>"
        "</body></html>"
    )


def _render_insight_block(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    name = escape(str(result.get("name") or "Untitled insight"))
    visualization = str(result.get("visualization") or "table")
    class_name = "insight insight-wide" if visualization == "table" else "insight"
    body = (
        _render_metric(result)
        if visualization in {"metric", "stat", "number"}
        else _render_rows_table(result)
    )
    return f'<section class="{class_name}"><h2>{name}</h2>{body}</section>'


def _render_metric(result: dict[str, Any]) -> str:
    metric = result.get("metric")
    metric_data = metric if isinstance(metric, dict) else {}
    value = escape(str(metric_data.get("value") or "NA"))
    label = escape(str(metric_data.get("label") or "Value"))
    return f'<div class="metric-value">{value}</div><p>{label}</p>'


def _render_rows_table(result: dict[str, Any]) -> str:
    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return "<p>No data.</p>"
    header = "".join(f"<th>{escape(str(column))}</th>" for column in columns)
    body = ""
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        body += (
            "<tr>"
            + "".join(
                f"<td>{escape(str(row.get(str(column), '')))}</td>"
                for column in columns
            )
            + "</tr>"
        )
    return (
        '<div class="chart-fallback">'
        f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"
        "</div>"
    )


def write_report(
    results: Path,
    out: Path,
    *,
    name: str = "Goodomics Report",
    template: dict[str, Any] | None = None,
) -> Path:
    out.write_text(
        render_report(results, name=name, template=template), encoding="utf-8"
    )
    return out
