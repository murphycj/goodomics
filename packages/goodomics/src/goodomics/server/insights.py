from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal, TypeGuard, cast
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.sql import func
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.server.db.models import (
    InsightRecord,
    InsightResultCacheRecord,
    ReportRecord,
    ReportResultCacheRecord,
)
from goodomics.storage.duckdb import SERIALIZERS_BY_TABLE, DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataImportRecord,
    DataProfileRecord,
    FileLinkRecord,
    FileRecord,
    ProjectRecord,
    QCDecisionRecord,
    RunRecord,
    RunSampleRecord,
    SampleRecord,
    SampleSetMemberRecord,
    SampleSetRecord,
    SubjectRecord,
)

JsonObject = dict[str, Any]
StoreName = Literal["catalog", "analytics"]

CATALOG_MODELS: dict[str, type[SQLModel]] = {
    "projects": ProjectRecord,
    "subjects": SubjectRecord,
    "samples": SampleRecord,
    "runs": RunRecord,
    "run_samples": RunSampleRecord,
    "data_imports": DataImportRecord,
    "data_profiles": DataProfileRecord,
    "files": FileRecord,
    "file_links": FileLinkRecord,
    "sample_sets": SampleSetRecord,
    "sample_set_members": SampleSetMemberRecord,
    "qc_decisions": QCDecisionRecord,
    "insights": InsightRecord,
    "reports": ReportRecord,
}

AGGREGATIONS = {"count", "sum", "avg", "min", "max"}
OPERATORS = {
    "eq": "=",
    "=": "=",
    "ne": "!=",
    "!=": "!=",
    "gt": ">",
    ">": ">",
    "gte": ">=",
    ">=": ">=",
    "lt": "<",
    "<": "<",
    "lte": "<=",
    "<=": "<=",
}
READ_ONLY_SQL = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
BLOCKED_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|pragma|set|vacuum)\b",
    re.IGNORECASE,
)


def canonical_hash(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def normalize_insight_config(config: Mapping[str, Any]) -> JsonObject:
    normalized = dict(config)
    normalized.setdefault("version", 1)
    normalized.setdefault("visualization", "table")
    normalized.setdefault("query", {})
    normalized.setdefault("series", [])
    normalized.setdefault("filters", [])
    normalized.setdefault("display", {})
    return normalized


def normalize_report_config(config: Mapping[str, Any]) -> JsonObject:
    normalized = dict(config)
    normalized.setdefault("version", 1)
    normalized.setdefault("items", [])
    normalized.setdefault("layout", {"columns": 12})
    normalized.setdefault("filters", [])
    normalized.setdefault("refresh_policy", {"mode": "manual"})
    return normalized


async def execute_insight(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    insight: InsightRecord | None = None,
    config: Mapping[str, Any] | None = None,
    refresh: bool = False,
) -> JsonObject:
    if insight is None and config is None:
        raise ValueError("An insight record or config is required.")
    source_config = (
        config if config is not None else (insight.config if insight else {})
    )
    insight_config = normalize_insight_config(source_config)
    source = _query_source(insight_config)
    source_fingerprint = await fingerprint_source(
        session=session,
        analytics_store=analytics_store,
        project_id=project_id,
        source=source,
    )
    spec_hash = canonical_hash(
        {"config": insight_config, "project_id": project_id, "source": source}
    )
    insight_id = insight.insight_id if insight is not None else None
    if not refresh:
        cached = await _get_cached_insight(
            session,
            project_id=project_id,
            insight_id=insight_id,
            spec_hash=spec_hash,
            source_fingerprint=source_fingerprint,
        )
        if cached is not None:
            return cached

    columns, rows = await execute_data_query(
        session=session,
        analytics_store=analytics_store,
        project_id=project_id,
        config=insight_config,
    )
    result = compile_insight_result(
        config=insight_config,
        columns=columns,
        rows=rows,
        insight_id=insight_id,
        computed_at=datetime.now(UTC),
        cached=False,
    )
    cache_id = f"insight_cache_{uuid4().hex}"
    session.add(
        InsightResultCacheRecord(
            cache_id=cache_id,
            project_id=project_id,
            insight_id=insight_id,
            spec_hash=spec_hash,
            source_fingerprint=source_fingerprint,
            result=result,
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return result


async def execute_report(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    report: ReportRecord,
    insights: Sequence[InsightRecord],
    refresh: bool = False,
) -> JsonObject:
    report_config = normalize_report_config(report.config)
    report_id = report.report_id
    report_name = report.name
    report_description = report.description
    spec_hash = canonical_hash(
        {
            "report": report_config,
            "insights": [insight.config for insight in insights],
            "project_id": project_id,
        }
    )
    source_fingerprint = canonical_hash(
        {
            "insights": [
                await fingerprint_source(
                    session=session,
                    analytics_store=analytics_store,
                    project_id=project_id,
                    source=_query_source(normalize_insight_config(insight.config)),
                )
                for insight in insights
            ]
        }
    )
    if not refresh:
        cached = await _get_cached_report(
            session,
            project_id=project_id,
            report_id=report_id,
            spec_hash=spec_hash,
            source_fingerprint=source_fingerprint,
        )
        if cached is not None:
            return cached

    insight_results = [
        await execute_insight(
            session=session,
            analytics_store=analytics_store,
            project_id=project_id,
            insight=insight,
            refresh=refresh,
        )
        for insight in insights
    ]
    result = {
        "kind": "report_result",
        "report_id": report_id,
        "title": report_name,
        "description": report_description,
        "config": report_config,
        "insights": insight_results,
        "computed_at": datetime.now(UTC).isoformat(),
        "cached": False,
    }
    cache_id = f"report_cache_{uuid4().hex}"
    session.add(
        ReportResultCacheRecord(
            cache_id=cache_id,
            project_id=project_id,
            report_id=report_id,
            spec_hash=spec_hash,
            source_fingerprint=source_fingerprint,
            result=result,
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return result


async def execute_data_query(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    config: Mapping[str, Any],
) -> tuple[list[str], list[JsonObject]]:
    query_config = _query_config(config)
    store, table = _parse_source(query_config.get("source"))
    if query_config.get("sql") is not None:
        sql = _validate_read_only_sql(str(query_config["sql"]))
        limit = _query_limit(query_config)
        if store == "analytics":
            return analytics_store.query_rows(sql, limit=limit)
        return await _execute_catalog_sql(session, sql, limit=limit)
    if table is None:
        raise ValueError("Query source must include a table.")
    sql, parameters, columns = await _compile_builder_query(
        session=session,
        project_id=project_id,
        store=store,
        table=table,
        query_config=query_config,
        config=config,
    )
    limit = _query_limit(query_config)
    if store == "analytics":
        return analytics_store.query_rows(sql, parameters=parameters, limit=limit)
    return await _execute_catalog_sql(session, sql, parameters=parameters, limit=limit)


def compile_insight_result(
    *,
    config: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    insight_id: str | None,
    computed_at: datetime,
    cached: bool,
) -> JsonObject:
    visualization = str(config.get("visualization") or "table")
    row_dicts = [dict(row) for row in rows]
    result: JsonObject = {
        "kind": "insight_result",
        "insight_id": insight_id,
        "title": config.get("title") or config.get("name") or "Untitled insight",
        "description": config.get("description"),
        "visualization": visualization,
        "columns": list(columns),
        "rows": row_dicts,
        "computed_at": computed_at.isoformat(),
        "cached": cached,
    }
    if visualization == "table":
        return result
    if visualization in {"metric", "stat", "number"}:
        result["metric"] = _metric_payload(row_dicts, columns)
        return result
    result["echarts_options"] = _echarts_options(config, list(columns), row_dicts)
    return result


async def fingerprint_source(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    source: Mapping[str, Any],
) -> str:
    store = source.get("store")
    table = source.get("table")
    if store == "analytics":
        counts = analytics_store.row_counts()
        return canonical_hash(
            {
                "store": "analytics",
                "table": table,
                "rows": counts.get(str(table), 0) if table else counts,
                "size": analytics_store.database_size_bytes(),
            }
        )
    if table and table in CATALOG_MODELS:
        model = CATALOG_MODELS[str(table)]
        statement = select(func.count()).select_from(model)
        if project_id is not None and "project_id" in model.model_fields:
            project_pk = await _project_pk(session, project_id)
            model_any = cast(Any, model)
            statement = statement.where(
                model_any.project_id == project_pk
                if _project_field_is_integer(model)
                else model_any.project_id == project_id
            )
        count = int((await session.exec(statement)).one())
        return canonical_hash({"store": "catalog", "table": table, "rows": count})
    return canonical_hash({"store": store, "table": table, "project_id": project_id})


async def _compile_builder_query(
    *,
    session: AsyncSession,
    project_id: str | None,
    store: StoreName,
    table: str,
    query_config: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[str, list[Any], list[str]]:
    columns = _columns_for_source(store, table)
    dimensions = _string_list(
        query_config.get("dimensions") or query_config.get("group_by")
    )
    if not dimensions and isinstance(query_config.get("x"), str):
        dimensions = [str(query_config["x"])]
    measures = _measures(query_config, config)
    requested_columns = _string_list(query_config.get("columns"))
    parameters: list[Any] = []
    select_parts: list[str] = []
    group_parts: list[str] = []

    for dimension in dimensions:
        _require_column(columns, dimension)
        select_parts.append(
            f"{_quote_identifier(dimension)} AS {_quote_identifier(dimension)}"
        )
        group_parts.append(_quote_identifier(dimension))

    for measure in measures:
        field = measure["field"]
        aggregation = measure["aggregation"]
        alias = measure["alias"]
        if field != "*" or aggregation != "count":
            _require_column(columns, field)
        if aggregation not in AGGREGATIONS:
            raise ValueError(f"Unsupported aggregation: {aggregation}")
        expression = "*" if field == "*" else _quote_identifier(field)
        select_parts.append(
            f"{aggregation.upper()}({expression}) AS {_quote_identifier(alias)}"
        )

    if not select_parts:
        selected = requested_columns or columns[: min(len(columns), 12)]
        for column in selected:
            _require_column(columns, column)
        select_parts = [_quote_identifier(column) for column in selected]

    where_parts = []
    project_where = await _project_scope_where(
        session=session,
        store=store,
        table=table,
        project_id=project_id,
        columns=columns,
        parameters=parameters,
    )
    if project_where:
        where_parts.append(project_where)
    for filter_config in [
        *cast(Sequence[Any], query_config.get("filters") or []),
        *cast(Sequence[Any], config.get("filters") or []),
    ]:
        where_parts.append(_filter_sql(columns, filter_config, parameters))

    sql = f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(table)}"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    if group_parts:
        sql += " GROUP BY " + ", ".join(group_parts)
    order_sql = _order_sql(
        columns=set(columns) | {measure["alias"] for measure in measures},
        value=query_config.get("order_by"),
    )
    if order_sql:
        sql += f" ORDER BY {order_sql}"
    return sql, parameters, [part.split(" AS ")[-1].strip('"') for part in select_parts]


async def _project_scope_where(
    *,
    session: AsyncSession,
    store: StoreName,
    table: str,
    project_id: str | None,
    columns: Sequence[str],
    parameters: list[Any],
) -> str | None:
    if project_id is None or "project_id" not in columns:
        return None
    if store == "catalog":
        model = CATALOG_MODELS.get(table)
        if model is not None and _project_field_is_integer(model):
            parameters.append(await _project_pk(session, project_id))
        else:
            parameters.append(project_id)
    else:
        parameters.append(project_id)
    return f"{_quote_identifier('project_id')} = ?"


def _filter_sql(
    columns: Sequence[str], filter_config: Any, parameters: list[Any]
) -> str:
    if not isinstance(filter_config, Mapping):
        raise ValueError("Filters must be objects.")
    field = str(filter_config.get("field") or "")
    _require_column(columns, field)
    operator = str(filter_config.get("operator") or filter_config.get("op") or "eq")
    value = filter_config.get("value")
    quoted = _quote_identifier(field)
    if operator in OPERATORS:
        parameters.append(value)
        return f"{quoted} {OPERATORS[operator]} ?"
    if operator == "in":
        values = list(
            value
            if isinstance(value, Sequence) and not isinstance(value, str)
            else [value]
        )
        if not values:
            return "1 = 0"
        parameters.extend(values)
        return f"{quoted} IN ({', '.join('?' for _ in values)})"
    if operator == "contains":
        parameters.append(f"%{value}%")
        return f"CAST({quoted} AS TEXT) LIKE ?"
    raise ValueError(f"Unsupported filter operator: {operator}")


def _order_sql(columns: set[str], value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        column = value
        direction = "ASC"
    elif isinstance(value, Mapping):
        column = str(value.get("field") or value.get("column") or "")
        direction = "DESC" if str(value.get("direction")).lower() == "desc" else "ASC"
    else:
        return None
    _require_column(columns, column)
    return f"{_quote_identifier(column)} {direction}"


async def _execute_catalog_sql(
    session: AsyncSession,
    sql: str,
    *,
    parameters: Sequence[Any] = (),
    limit: int,
) -> tuple[list[str], list[JsonObject]]:
    bounded_sql, named_parameters = _named_sql_parameters(sql, parameters)
    result = await cast(Any, session).exec(
        text(
            f"SELECT * FROM ({bounded_sql}) AS goodomics_query LIMIT :goodomics_limit"
        ),
        params=named_parameters | {"goodomics_limit": min(max(limit, 1), 5000)},
    )
    rows = [dict(row) for row in result.mappings().all()]
    columns = list(rows[0]) if rows else []
    return columns, rows


def _named_sql_parameters(
    sql: str, parameters: Sequence[Any]
) -> tuple[str, dict[str, Any]]:
    named: dict[str, Any] = {}
    parts = sql.split("?")
    if len(parts) == 1:
        return sql, named
    if len(parts) - 1 != len(parameters):
        raise ValueError("SQL parameter count does not match query.")
    rebuilt = [parts[0]]
    for index, value in enumerate(parameters):
        name = f"p{index}"
        named[name] = value
        rebuilt.append(f":{name}")
        rebuilt.append(parts[index + 1])
    return "".join(rebuilt), named


async def _get_cached_insight(
    session: AsyncSession,
    *,
    project_id: str | None,
    insight_id: str | None,
    spec_hash: str,
    source_fingerprint: str,
) -> JsonObject | None:
    statement = (
        select(InsightResultCacheRecord)
        .where(InsightResultCacheRecord.project_id == project_id)
        .where(InsightResultCacheRecord.insight_id == insight_id)
        .where(InsightResultCacheRecord.spec_hash == spec_hash)
        .where(InsightResultCacheRecord.source_fingerprint == source_fingerprint)
        .order_by(cast(Any, InsightResultCacheRecord.created_at).desc())
    )
    row = (await session.exec(statement)).first()
    if row is None:
        return None
    result = dict(row.result)
    result["cached"] = True
    return result


async def _get_cached_report(
    session: AsyncSession,
    *,
    project_id: str | None,
    report_id: str | None,
    spec_hash: str,
    source_fingerprint: str,
) -> JsonObject | None:
    statement = (
        select(ReportResultCacheRecord)
        .where(ReportResultCacheRecord.project_id == project_id)
        .where(ReportResultCacheRecord.report_id == report_id)
        .where(ReportResultCacheRecord.spec_hash == spec_hash)
        .where(ReportResultCacheRecord.source_fingerprint == source_fingerprint)
        .order_by(cast(Any, ReportResultCacheRecord.created_at).desc())
    )
    row = (await session.exec(statement)).first()
    if row is None:
        return None
    result = dict(row.result)
    result["cached"] = True
    return result


def _query_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    query = config.get("query")
    return query if isinstance(query, Mapping) else {}


def _query_source(config: Mapping[str, Any]) -> JsonObject:
    query = _query_config(config)
    store, table = _parse_source(query.get("source"))
    return {"store": store, "table": table}


def _parse_source(value: Any) -> tuple[StoreName, str | None]:
    if isinstance(value, Mapping):
        store = str(value.get("store") or "analytics")
        table = value.get("table")
        if "sql" in value and table is None:
            table = value.get("name")
    elif isinstance(value, str):
        if "." in value:
            store, table = value.split(".", 1)
        else:
            store, table = "analytics", value
    else:
        store, table = "analytics", None
    if store not in {"catalog", "analytics"}:
        raise ValueError(f"Unsupported query store: {store}")
    return cast(StoreName, store), str(table) if table else None


def _columns_for_source(store: StoreName, table: str) -> list[str]:
    if store == "analytics":
        serializer = SERIALIZERS_BY_TABLE.get(table)
        if serializer is None:
            raise ValueError(f"Unknown analytical table: {table}")
        return list(serializer.columns)
    model = CATALOG_MODELS.get(table)
    if model is None:
        raise ValueError(f"Unknown catalog table: {table}")
    return list(model.model_fields)


def _measures(
    query_config: Mapping[str, Any], config: Mapping[str, Any]
) -> list[JsonObject]:
    raw = query_config.get("measures") or config.get("series") or []
    if isinstance(raw, Mapping):
        raw = [raw]
    measures = []
    for index, value in enumerate(cast(Sequence[Any], raw)):
        if not isinstance(value, Mapping):
            continue
        aggregation = str(value.get("aggregation") or value.get("aggregate") or "count")
        field = str(value.get("field") or ("*" if aggregation == "count" else "value"))
        label = str(
            value.get("label") or value.get("alias") or f"{aggregation}_{field}"
        )
        alias = _safe_alias(label, fallback=f"series_{index + 1}")
        measures.append({"field": field, "aggregation": aggregation, "alias": alias})
    return measures


def _query_limit(query_config: Mapping[str, Any]) -> int:
    value = query_config.get("limit", 1000)
    try:
        return min(max(int(value), 1), 5000)
    except (TypeError, ValueError):
        return 1000


def _validate_read_only_sql(sql: str) -> str:
    stripped = sql.strip().rstrip(";")
    if (
        ";" in stripped
        or not READ_ONLY_SQL.search(stripped)
        or BLOCKED_SQL.search(stripped)
    ):
        raise ValueError("Advanced SQL must be a single read-only SELECT query.")
    return stripped


def _echarts_options(
    config: Mapping[str, Any], columns: list[str], rows: list[JsonObject]
) -> JsonObject:
    visualization = str(config.get("visualization") or "bar")
    query = _query_config(config)
    dimensions = _string_list(query.get("dimensions") or query.get("group_by"))
    x_field = str(query.get("x") or (dimensions[0] if dimensions else columns[0]))
    y_field = str(
        query.get("y") or _first_numeric_column(columns, rows, exclude={x_field})
    )
    title = str(config.get("title") or config.get("name") or "Insight")
    if visualization in {"pie", "donut"}:
        return {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "item"},
            "series": [
                {
                    "type": "pie",
                    "radius": ["42%", "70%"] if visualization == "donut" else "65%",
                    "data": [
                        {"name": str(row.get(x_field)), "value": row.get(y_field)}
                        for row in rows
                    ],
                }
            ],
        }
    if visualization == "scatter":
        return {
            "tooltip": {"trigger": "item"},
            "xAxis": {"type": "value", "name": x_field},
            "yAxis": {"type": "value", "name": y_field},
            "series": [
                {
                    "type": "scatter",
                    "data": [[row.get(x_field), row.get(y_field)] for row in rows],
                }
            ],
        }
    if visualization == "heatmap":
        y_dimension = str(
            query.get("y_dimension")
            or (dimensions[1] if len(dimensions) > 1 else y_field)
        )
        values: list[int | float] = []
        for row in rows:
            value = row.get(y_field)
            if isinstance(value, int | float):
                values.append(value)
        return {
            "tooltip": {"position": "top"},
            "xAxis": {
                "type": "category",
                "data": sorted(str(row.get(x_field)) for row in rows),
            },
            "yAxis": {
                "type": "category",
                "data": sorted(str(row.get(y_dimension)) for row in rows),
            },
            "visualMap": {
                "min": min(values) if values else 0,
                "max": max(values) if values else 1,
                "calculable": True,
                "orient": "horizontal",
                "left": "center",
                "bottom": 0,
            },
            "series": [
                {
                    "type": "heatmap",
                    "data": [
                        [
                            str(row.get(x_field)),
                            str(row.get(y_dimension)),
                            row.get(y_field),
                        ]
                        for row in rows
                    ],
                }
            ],
        }
    if visualization == "histogram":
        value_field = str(query.get("value") or query.get("y") or y_field)
        bins = _histogram_bins(
            rows,
            value_field=value_field,
            bin_count=_histogram_bin_count(config),
        )
        return {
            "tooltip": {"trigger": "axis"},
            "grid": {"left": 48, "right": 24, "top": 32, "bottom": 56},
            "xAxis": {
                "type": "category",
                "name": value_field,
                "data": [bin_["label"] for bin_ in bins],
                "axisLabel": {"rotate": 30},
            },
            "yAxis": {"type": "value", "name": "Count"},
            "series": [
                {
                    "name": "Count",
                    "type": "bar",
                    "barGap": "0%",
                    "data": [bin_["count"] for bin_ in bins],
                    "itemStyle": {"color": "#16784a"},
                }
            ],
        }
    chart_type = {
        "line": "line",
        "area": "line",
        "bar": "bar",
        "stacked_bar": "bar",
        "boxplot": "boxplot",
        "box_plot": "boxplot",
    }.get(visualization, "bar")
    first_row = rows[0] if rows else {}
    series_fields = [
        column for column in columns if column != x_field and column in first_row
    ] or ([y_field] if y_field else [])
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"type": "scroll"},
        "grid": {"left": 48, "right": 24, "top": 40, "bottom": 42},
        "xAxis": {"type": "category", "data": [row.get(x_field) for row in rows]},
        "yAxis": {"type": "value"},
        "series": [
            {
                "name": field,
                "type": chart_type,
                "stack": "total" if visualization == "stacked_bar" else None,
                "areaStyle": {} if visualization == "area" else None,
                "data": [row.get(field) for row in rows],
            }
            for field in series_fields
        ],
    }


def _metric_payload(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[str]
) -> JsonObject:
    if not rows or not columns:
        return {"value": None, "label": "No data"}
    row = rows[0]
    value_column = _first_numeric_column(list(columns), [dict(row)]) or columns[-1]
    return {"value": row.get(value_column), "label": value_column}


def _first_numeric_column(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    *,
    exclude: set[str] | None = None,
) -> str | None:
    excluded = exclude or set()
    for column in columns:
        if column in excluded:
            continue
        if any(isinstance(row.get(column), int | float) for row in rows):
            return column
    return None


def _histogram_bin_count(config: Mapping[str, Any]) -> int:
    query = _query_config(config)
    display = config.get("display")
    raw = query.get("bins")
    if raw is None and isinstance(display, Mapping):
        raw = display.get("bins")
    if raw is None:
        return 20
    try:
        return min(max(int(raw), 1), 100)
    except (TypeError, ValueError):
        return 20


def _histogram_bins(
    rows: Sequence[Mapping[str, Any]], *, value_field: str, bin_count: int
) -> list[JsonObject]:
    values: list[float] = []
    for row in rows:
        value = row.get(value_field)
        if _is_numeric_value(value):
            values.append(float(value))
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return [{"label": _format_bin_edge(minimum), "count": len(values)}]
    width = (maximum - minimum) / bin_count
    counts = [0] * bin_count
    for value in values:
        index = min(int((value - minimum) / width), bin_count - 1)
        counts[index] += 1
    return [
        {
            "label": (
                f"{_format_bin_edge(minimum + index * width)}-"
                f"{_format_bin_edge(minimum + (index + 1) * width)}"
            ),
            "count": count,
        }
        for index, count in enumerate(counts)
    ]


def _is_numeric_value(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _format_bin_edge(value: float) -> str:
    return f"{value:.4g}"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if isinstance(item, str)]
    return []


def _safe_alias(value: str, *, fallback: str) -> str:
    alias = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()
    return alias or fallback


def _quote_identifier(value: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        raise ValueError(f"Invalid identifier: {value}")
    return f'"{value}"'


def _require_column(columns: Sequence[str] | set[str], column: str) -> None:
    if column not in columns:
        raise ValueError(f"Unknown column: {column}")


async def _project_pk(session: AsyncSession, project_id: str) -> int | None:
    row = (
        await session.exec(
            select(ProjectRecord).where(ProjectRecord.project_id == project_id)
        )
    ).first()
    return row.id if row is not None else None


def _project_field_is_integer(model: type[SQLModel]) -> bool:
    field = model.model_fields.get("project_id")
    return field is not None and "int" in str(field.annotation)
