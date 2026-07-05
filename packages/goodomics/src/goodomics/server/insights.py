"""Execute saved Goodomics insights and reports.

This module is the server-side bridge between declarative insight/report
configuration and rendered dashboard/report payloads. It normalizes saved JSON
configs, compiles safe SQL against either the SQL catalog or DuckDB analytics
store, caches computed results, and translates rows into chart/table/metric
payloads.

The public functions are used by API routes. Private helpers keep the query
grammar small and Goodomics-specific instead of exposing raw chart-library or
database details as the primary user interface.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal, TypeGuard, cast
from uuid import uuid4

from sqlalchemy import or_, text
from sqlalchemy.sql import func
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.projects import DEFAULT_PROJECT_ID
from goodomics.server.db.catalog import CATALOG_MODELS
from goodomics.server.db.models import (
    InsightRecord,
    InsightResultCacheRecord,
    ReportRecord,
    ReportResultCacheRecord,
)
from goodomics.server.insight_catalog import (
    ALL_ROWS_INLINE_THRESHOLD,
    EXPORT_FULL_DATA_LIMIT,
    LINKERS,
    MORE_ROWS_MAX_LIMIT,
    PREVIEW_DEFAULT_LIMIT,
    chart_rule,
    explain_insight_config,
    normalize_linker,
    normalize_result_policy,
    validate_config_shape,
)
from goodomics.storage.duckdb import (
    INTEGER_KEYED_TABLES,
    SERIALIZERS_BY_TABLE,
    DuckDBAnalyticsStore,
)
from goodomics.storage.sqlalchemy import (
    DataProfileFieldRecord,
    DataProfileRecord,
    ProjectRecord,
    RunSampleRecord,
    SampleRecord,
    SampleSetMemberRecord,
    SampleSetRecord,
)

JsonObject = dict[str, Any]
StoreName = Literal["catalog", "analytics"]

# Builder queries intentionally support a tiny aggregation/operator vocabulary.
# Advanced SQL exists as an escape hatch, but the default UI/API path stays
# constrained and easy to validate.
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
CHART_COLORS = [
    "#38BDF8",
    "#636EFA",
    "#EF553B",
    "#00CC96",
    "#AB63FA",
    "#FFA15A",
    "#19D3F3",
    "#FF6692",
    "#B6E880",
    "#FF97FF",
    "#FECB52",
    "#2E91E5",
    "#E15F99",
    "#1CA71C",
    "#FB0D0D",
    "#DA16FF",
    "#222A2A",
    "#B68100",
    "#750D86",
    "#EB663B",
    "#511CFB",
    "#00A08B",
    "#FB00D1",
    "#FC0080",
    "#B2828D",
    "#6C7C32",
    "#778AAE",
    "#862A16",
    "#A777F1",
    "#AF0038",
]


def canonical_hash(value: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 hash for JSON-like config/cache inputs."""

    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def normalize_insight_config(config: Mapping[str, Any]) -> JsonObject:
    """Fill in default keys expected by insight execution."""

    normalized = dict(config)
    normalized.setdefault("version", 1)
    normalized.setdefault("context", {"kind": "cohort"})
    normalized.setdefault("mode", _default_mode(normalized))
    normalized.setdefault("visualization", "table")
    normalized.setdefault("query", {})
    normalized.setdefault("series", [])
    normalized["linker"] = normalize_linker(normalized.get("linker"))
    normalized.setdefault("filters", [])
    display = normalized.get("display")
    display_policy = (
        display.get("result_policy") if isinstance(display, Mapping) else None
    )
    normalized["result_policy"] = normalize_result_policy(
        normalized.get("result_policy") or display_policy
    )
    normalized.setdefault("display", {})
    return normalized


def validate_and_explain_config(config: Mapping[str, Any]) -> JsonObject:
    """Return shared validation/explanation payload for UI and AI callers."""

    normalized = normalize_insight_config(config)
    messages = validate_config_shape(normalized)
    return {
        "valid": not any(message.get("level") == "error" for message in messages),
        "messages": messages,
        "normalized_config": normalized,
        "explanation": explain_insight_config(normalized),
        "catalog_version": 1,
    }


def normalize_report_config(config: Mapping[str, Any]) -> JsonObject:
    """Fill in default keys expected by report execution."""

    normalized = dict(config)
    normalized.setdefault("version", 1)
    normalized.setdefault("items", [])
    normalized.setdefault("layout", {"columns": 12})
    normalized.setdefault("filters", [])
    normalized.setdefault("refresh_policy", {"mode": "manual"})
    return normalized


def _default_mode(config: Mapping[str, Any]) -> str:
    visualization = str(config.get("visualization") or "")
    query = config.get("query")
    if isinstance(query, Mapping) and query.get("sql"):
        return "variant_table"
    if visualization == "table":
        return "variant_table"
    if visualization == "scatter":
        return "comparison"
    return "profile_metrics"


async def execute_insight(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    insight: InsightRecord | None = None,
    config: Mapping[str, Any] | None = None,
    refresh: bool = False,
) -> JsonObject:
    """Execute an insight config or saved insight record.

    The result is a JSON-ready payload for the dashboard/report renderer. Cached
    results are reused unless ``refresh`` is true.
    """

    if insight is None and config is None:
        raise ValueError("An insight record or config is required.")
    source_config = (
        config if config is not None else (insight.config if insight else {})
    )
    insight_config = normalize_insight_config(source_config)
    validation = validate_and_explain_config(insight_config)
    if not validation["valid"]:
        first_error = next(
            message for message in validation["messages"] if message["level"] == "error"
        )
        raise ValueError(str(first_error["message"]))
    source = _query_source(insight_config)
    # Cache identity is split into the normalized spec and a source fingerprint
    # so a config can be reused until either the config or the underlying data
    # changes.
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
    policy_rows, policy_summary = _apply_result_policy(
        config=insight_config,
        columns=columns,
        rows=rows,
        analytics_store=analytics_store,
    )
    result = compile_insight_result(
        config=insight_config,
        columns=columns,
        rows=policy_rows,
        insight_id=insight_id,
        computed_at=datetime.now(UTC),
        cached=False,
        result_policy_summary=policy_summary,
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
    """Execute a saved report by executing its referenced insights."""

    report_config = normalize_report_config(report.config)
    report_id = report.report_id
    report_name = report.name
    report_description = report.description
    effective_insight_configs = [
        _inherit_report_context(insight.config, report_config) for insight in insights
    ]
    spec_hash = canonical_hash(
        {
            "report": report_config,
            "insights": effective_insight_configs,
            "project_id": project_id,
        }
    )
    source_fingerprint = canonical_hash(
        {
            # A report depends on all referenced insight sources. Hashing the
            # per-insight fingerprints keeps report cache invalidation aligned
            # with insight cache invalidation.
            "insights": [
                await fingerprint_source(
                    session=session,
                    analytics_store=analytics_store,
                    project_id=project_id,
                    source=_query_source(normalize_insight_config(config)),
                )
                for config in effective_insight_configs
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
            config=config,
            refresh=refresh,
        )
        for insight, config in zip(insights, effective_insight_configs, strict=True)
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


def _inherit_report_context(
    insight_config: Mapping[str, Any], report_config: Mapping[str, Any]
) -> JsonObject:
    inherited = dict(insight_config)
    for key in ("context", "linker", "result_policy"):
        if key not in inherited and key in report_config:
            inherited[key] = report_config[key]
    report_filters = report_config.get("filters")
    if isinstance(report_filters, Sequence) and not isinstance(report_filters, str):
        insight_filters = inherited.get("filters")
        inherited["filters"] = [
            *list(report_filters),
            *(
                list(insight_filters)
                if isinstance(insight_filters, Sequence)
                and not isinstance(insight_filters, str)
                else []
            ),
        ]
    return inherited


async def execute_data_query(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    config: Mapping[str, Any],
) -> tuple[list[str], list[JsonObject]]:
    """Run the data query described by an insight config.

    Profile-first queries are preferred because they use Goodomics semantic data
    profiles. Generic table queries and read-only SQL are supported as escape
    hatches.
    """

    query_config = _query_config(config)
    series_query = await _execute_profile_series_query(
        session=session,
        analytics_store=analytics_store,
        project_id=project_id,
        config=config,
    )
    if series_query is not None:
        return series_query
    profile_query = await _compile_profile_query(
        session=session,
        project_id=project_id,
        query_config=query_config,
        config=config,
    )
    if profile_query is not None:
        sql, parameters, columns = profile_query
        return analytics_store.query_rows(
            sql, parameters=parameters, limit=_query_limit(query_config, config)
        )
    store, table = _parse_source(query_config.get("source"))
    if query_config.get("sql") is not None:
        # Advanced SQL is still wrapped and limited by the storage adapters, but
        # it must pass a simple read-only validation gate first.
        sql = _validate_read_only_sql(str(query_config["sql"]))
        limit = _query_limit(query_config, config)
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
    limit = _query_limit(query_config, config)
    if store == "analytics":
        return analytics_store.query_rows(sql, parameters=parameters, limit=limit)
    return await _execute_catalog_sql(session, sql, parameters=parameters, limit=limit)


async def _execute_profile_series_query(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    config: Mapping[str, Any],
) -> tuple[list[str], list[JsonObject]] | None:
    # New mode-first configs put profile identity on each series so different
    # profiles can be aligned by sample/run_sample/feature without exposing a
    # raw SQL join to the dashboard or future AI tooling.
    series_items = _profile_series_items(config)
    if not series_items:
        return None
    visualization = str(config.get("visualization") or "table")
    if visualization in {"pie", "donut"} and len(series_items) == 1:
        return await _execute_single_series_count_query(
            session=session,
            analytics_store=analytics_store,
            project_id=project_id,
            config=config,
            series_item=series_items[0],
        )
    aliases = _series_aliases(series_items)
    limit = _query_limit(_query_config(config), config)
    if visualization == "histogram":
        return await _execute_histogram_series_query(
            session=session,
            analytics_store=analytics_store,
            project_id=project_id,
            config=config,
            series_items=series_items,
            aliases=aliases,
            limit=limit,
        )
    linker = await _resolve_profile_series_linker(
        session=session,
        project_id=project_id,
        config=config,
        series_items=series_items,
    )
    series_rows: list[list[JsonObject]] = []
    for series_item, alias in zip(series_items, aliases, strict=True):
        sql, parameters = await _profile_series_sql(
            session=session,
            project_id=project_id,
            config=config,
            series_item=series_item,
            alias=alias,
            linker_column=linker.get("column"),
        )
        _, rows = analytics_store.query_rows(sql, parameters=parameters, limit=limit)
        series_rows.append(rows)
    columns, rows, diagnostics = _align_series_rows(
        aliases=aliases,
        linker_column=cast(str | None, linker.get("column")),
        linker_kind=str(linker["kind"]),
        series_rows=series_rows,
    )
    _set_runtime_metadata(
        config,
        {
            "linker": linker,
            "linker_diagnostics": diagnostics,
            "series_aliases": aliases,
        },
    )
    return columns, rows


async def _execute_histogram_series_query(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    config: Mapping[str, Any],
    series_items: Sequence[Mapping[str, Any]],
    aliases: Sequence[str],
    limit: int,
) -> tuple[list[str], list[JsonObject]]:
    series_rows: list[list[JsonObject]] = []
    for series_item, alias in zip(series_items, aliases, strict=True):
        sql, parameters = await _profile_series_sql(
            session=session,
            project_id=project_id,
            config=config,
            series_item=series_item,
            alias=alias,
            linker_column=None,
        )
        _, rows = analytics_store.query_rows(sql, parameters=parameters, limit=limit)
        series_rows.append(rows)
    max_rows = max((len(rows) for rows in series_rows), default=0)
    rows: list[JsonObject] = []
    for row_index in range(max_rows):
        row: JsonObject = {}
        for alias, source_rows in zip(aliases, series_rows, strict=True):
            if row_index < len(source_rows):
                row[alias] = source_rows[row_index].get(alias)
        rows.append(row)
    diagnostics = {
        "linker": None,
        "matched_count": max_rows,
        "unmatched_count": 0,
        "duplicate_conflict_count": 0,
        "rows_excluded": 0,
        "message": "Histogram series are overlaid by value distribution.",
    }
    _set_runtime_metadata(
        config,
        {
            "linker": {"kind": "none", "column": None, "candidates": []},
            "linker_diagnostics": diagnostics,
            "series_aliases": list(aliases),
        },
    )
    return list(aliases), rows


async def _execute_single_series_count_query(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    config: Mapping[str, Any],
    series_item: Mapping[str, Any],
) -> tuple[list[str], list[JsonObject]]:
    alias = "count"
    profile = await _series_profile(session, project_id, series_item)
    table = _profile_table(profile)
    field_id = _series_field_id(series_item)
    field = await _series_field_record(
        session=session,
        profile=profile,
        table=table,
        field_id=field_id,
    )
    value_column = await _series_value_column(
        session=session,
        profile=profile,
        table=table,
        field_id=field_id,
    )
    source = _series_source_sql(table)
    columns = _columns_for_source("analytics", table)
    parameters: list[Any] = [_record_pk(profile)]
    where_parts = ["data_profile_id = ?"]
    if field is not None:
        where_parts.append(_field_id_match_sql(parameters, field))
    context_where = await _context_where_sql(
        session=session,
        project_id=project_id,
        config=config,
        columns=columns,
        parameters=parameters,
    )
    where_parts.extend(context_where)
    where_parts.extend(
        _series_filters_sql(
            table=table,
            profile_pk=_record_pk(profile),
            columns=columns,
            filters=_combined_filters(config, series_item),
            parameters=parameters,
        )
    )
    category = _quote_identifier(value_column)
    sql = (
        f"SELECT {category} AS category, COUNT(*) AS {alias} "
        f"FROM {source} WHERE {' AND '.join(where_parts)} "
        f"GROUP BY {category} ORDER BY {alias} DESC"
    )
    limit = _query_limit(_query_config(config), config)
    _, rows = analytics_store.query_rows(sql, parameters=parameters, limit=limit)
    _set_runtime_metadata(
        config,
        {
            "linker": {"kind": "none", "column": None, "candidates": []},
            "linker_diagnostics": {
                "linker": None,
                "matched_count": len(rows),
                "unmatched_count": 0,
                "duplicate_conflict_count": 0,
                "rows_excluded": 0,
            },
            "series_aliases": [alias],
        },
    )
    return ["category", alias], rows


async def _profile_series_sql(
    *,
    session: AsyncSession,
    project_id: str | None,
    config: Mapping[str, Any],
    series_item: Mapping[str, Any],
    alias: str,
    linker_column: str | None,
) -> tuple[str, list[Any]]:
    profile = await _series_profile(session, project_id, series_item)
    table = _profile_table(profile)
    field_id = _series_field_id(series_item)
    field = await _series_field_record(
        session=session,
        profile=profile,
        table=table,
        field_id=field_id,
    )
    value_column = await _series_value_column(
        session=session,
        profile=profile,
        table=table,
        field_id=field_id,
    )
    source = _series_source_sql(table)
    columns = _columns_for_source("analytics", table)
    select_parts = []
    if linker_column is not None:
        _require_column(columns, linker_column)
        select_parts.append(f"{_quote_identifier(linker_column)} AS __linker")
    select_parts.append(
        f"{_quote_identifier(value_column)} AS {_quote_identifier(alias)}"
    )
    parameters: list[Any] = [_record_pk(profile)]
    where_parts = ["data_profile_id = ?"]
    if field is not None:
        where_parts.append(_field_id_match_sql(parameters, field))
    context_where = await _context_where_sql(
        session=session,
        project_id=project_id,
        config=config,
        columns=columns,
        parameters=parameters,
    )
    where_parts.extend(context_where)
    where_parts.extend(
        _series_filters_sql(
            table=table,
            profile_pk=_record_pk(profile),
            columns=columns,
            filters=_combined_filters(config, series_item),
            parameters=parameters,
        )
    )
    order = "__linker" if linker_column is not None else _quote_identifier(value_column)
    sql = (
        f"SELECT {', '.join(select_parts)} FROM {source} "
        f"WHERE {' AND '.join(where_parts)} ORDER BY {order}"
    )
    return sql, parameters


async def _series_profile(
    session: AsyncSession,
    project_id: str | None,
    series_item: Mapping[str, Any],
) -> DataProfileRecord:
    profile_id = _series_profile_id(series_item)
    if not profile_id:
        raise ValueError("Profile series require a data_profile_id.")
    profile = await _get_profile_record(session, project_id, profile_id)
    if profile is None:
        raise ValueError(f"Unknown data profile: {profile_id}")
    return profile


def _profile_table(profile: DataProfileRecord) -> str:
    table = profile.primary_table
    if table not in {
        "sample_metrics",
        "entity_attributes",
        "feature_value_numeric",
        "feature_call",
        "copy_number_segments",
        "sample_variant_calls",
        "sample_structural_variant_calls",
        "profile_payloads",
        "gene_alteration_state",
    }:
        raise ValueError(
            f"Profile series are not available for table: {table or 'unknown'}"
        )
    return table


async def _series_value_column(
    *,
    session: AsyncSession,
    profile: DataProfileRecord,
    table: str,
    field_id: str,
) -> str:
    synthetic = _synthetic_profile_fields(table).get(table, {})
    if field_id in synthetic:
        return synthetic[field_id]
    if table == "feature_value_numeric":
        return "value"
    if table in {"sample_metrics", "entity_attributes"}:
        if not field_id:
            raise ValueError("Metric and attribute profile series require a field_id.")
        rows = await _get_profile_field_records(
            session, profile_id=_record_pk(profile), field_ids=[field_id]
        )
        if field_id not in rows:
            raise ValueError(f"Unknown profile field: {field_id}")
        return _profile_value_column(rows[field_id])
    fallback = {
        "feature_call": "call_rank",
        "copy_number_segments": "segment_mean",
        "sample_variant_calls": "allele_fraction",
        "sample_structural_variant_calls": "split_read_count",
        "profile_payloads": "payload_name",
        "gene_alteration_state": "value_numeric",
    }.get(table)
    if fallback is None:
        raise ValueError(f"No default value column for profile table: {table}")
    return fallback


async def _series_field_record(
    *,
    session: AsyncSession,
    profile: DataProfileRecord,
    table: str,
    field_id: str,
) -> DataProfileFieldRecord | None:
    if table not in {"sample_metrics", "entity_attributes"}:
        return None
    if not field_id:
        raise ValueError("Metric and attribute profile series require a field_id.")
    rows = await _get_profile_field_records(
        session, profile_id=_record_pk(profile), field_ids=[field_id]
    )
    field = rows.get(field_id)
    if field is None:
        raise ValueError(f"Unknown profile field: {field_id}")
    return field


async def _resolve_profile_series_linker(
    *,
    session: AsyncSession,
    project_id: str | None,
    config: Mapping[str, Any],
    series_items: Sequence[Mapping[str, Any]],
) -> JsonObject:
    column_sets = []
    for series_item in series_items:
        profile = await _series_profile(session, project_id, series_item)
        table = _profile_table(profile)
        column_sets.append(set(_columns_for_source("analytics", table)))
    valid = [
        linker_id
        for linker_id in ("sample", "run_sample", "feature", "run", "entity")
        if all(LINKERS[linker_id]["column"] in columns for columns in column_sets)
    ]
    requested = normalize_linker(config.get("linker"))
    chart = str(config.get("visualization") or "table")
    required = _chart_requires_linker(chart, config, series_items)
    if requested["kind"] != "auto":
        column = LINKERS[requested["kind"]]["column"]
        if requested["kind"] not in valid or not isinstance(column, str):
            raise ValueError(f"Matched by {requested['kind']} is not valid here.")
        return {
            "kind": requested["kind"],
            "column": column,
            "candidates": valid,
            "required": required,
            "auto_selected": False,
        }
    if len(valid) == 1:
        selected = valid[0]
        return {
            "kind": selected,
            "column": LINKERS[selected]["column"],
            "candidates": valid,
            "required": required,
            "auto_selected": True,
        }
    if required and len(valid) > 1:
        raise ValueError(
            "This plot has multiple valid linkers. Choose Matched by explicitly."
        )
    if required:
        raise ValueError("This plot requires a visible Matched by linker.")
    selected = valid[0] if valid else "auto"
    return {
        "kind": selected,
        "column": LINKERS.get(selected, LINKERS["auto"])["column"],
        "candidates": valid,
        "required": required,
        "auto_selected": bool(valid),
    }


def _chart_requires_linker(
    chart: str,
    config: Mapping[str, Any],
    series_items: Sequence[Mapping[str, Any]],
) -> bool:
    rule = chart_rule(chart)
    requirement = rule.get("requires_linker")
    if requirement is True:
        return True
    if requirement == "multi_series":
        return len(series_items) > 1
    if requirement == "multi_numeric":
        return len(series_items) > 1
    if requirement == "comparison":
        return str(config.get("mode") or "") == "comparison"
    return False


async def _context_where_sql(
    *,
    session: AsyncSession,
    project_id: str | None,
    config: Mapping[str, Any],
    columns: Sequence[str],
    parameters: list[Any],
) -> list[str]:
    context = config.get("context")
    if not isinstance(context, Mapping):
        return []
    kind = str(context.get("kind") or "cohort")
    where_parts: list[str] = []
    if kind == "sample":
        sample_id = context.get("sample_id")
        if isinstance(sample_id, str) and sample_id and "sample_id" in columns:
            sample_pk = await _sample_pk(session, project_id, sample_id)
            parameters.append(sample_pk)
            where_parts.append("sample_id = ?")
        run_sample_id = context.get("run_sample_id")
        if (
            isinstance(run_sample_id, str)
            and run_sample_id
            and "run_sample_id" in columns
        ):
            run_sample_pk = await _run_sample_pk(session, project_id, run_sample_id)
            parameters.append(run_sample_pk)
            where_parts.append("run_sample_id = ?")
    elif kind == "cohort":
        sample_set_id = context.get("sample_set_id")
        if (
            isinstance(sample_set_id, str)
            and sample_set_id
            and "run_sample_id" in columns
        ):
            run_sample_ids = await _sample_set_run_sample_pks(
                session, project_id, sample_set_id
            )
            if not run_sample_ids:
                where_parts.append("1 = 0")
            else:
                parameters.extend(run_sample_ids)
                where_parts.append(
                    f"run_sample_id IN ({', '.join('?' for _ in run_sample_ids)})"
                )
    return where_parts


def _series_filters_sql(
    *,
    table: str,
    profile_pk: int,
    columns: Sequence[str],
    filters: Sequence[Any],
    parameters: list[Any],
) -> list[str]:
    where_parts: list[str] = []
    for filter_config in filters:
        normalized = _normalize_series_filter(filter_config)
        if normalized is None:
            continue
        if table == "sample_variant_calls" and normalized["field"] == "feature_id":
            where_parts.append(
                _variant_feature_filter_sql(normalized, profile_pk, parameters)
            )
            continue
        where_parts.append(_filter_sql(columns, normalized, parameters))
    return where_parts


def _variant_feature_filter_sql(
    filter_config: Mapping[str, Any], profile_pk: int, parameters: list[Any]
) -> str:
    value = filter_config.get("value")
    operator = str(filter_config.get("operator") or filter_config.get("op") or "eq")
    annotation_source = _readable_source_sql("variant_annotations")
    if operator == "in":
        values = list(
            value
            if isinstance(value, Sequence) and not isinstance(value, str)
            else [value]
        )
        if not values:
            return "1 = 0"
        parameters.extend([profile_pk, *values])
        return (
            "variant_id IN ("
            f"SELECT variant_id FROM {annotation_source} "
            "WHERE data_profile_id = ? "
            f"AND feature_id IN ({', '.join('?' for _ in values)})"
            ")"
        )
    parameters.extend([profile_pk, value])
    return (
        "variant_id IN ("
        f"SELECT variant_id FROM {annotation_source} "
        "WHERE data_profile_id = ? AND feature_id = ?"
        ")"
    )


def _normalize_series_filter(filter_config: Any) -> JsonObject | None:
    if not isinstance(filter_config, Mapping):
        raise ValueError("Filters must be objects.")
    field = str(filter_config.get("field") or "")
    field = {
        "feature": "feature_id",
        "feature_label": "feature_id",
        "gene": "feature_id",
        "gene_symbol": "feature_id",
        "field": "field_id",
        "field_label": "field_id",
        "metric": "field_id",
        "sample": "sample_id",
        "processed_sample": "run_sample_id",
    }.get(field, field)
    if not field:
        return None
    return dict(filter_config) | {"field": field}


def _combined_filters(
    config: Mapping[str, Any], series_item: Mapping[str, Any]
) -> list[Any]:
    query = _query_config(config)
    filters: list[Any] = []
    for value in (
        config.get("filters"),
        query.get("filters"),
        series_item.get("filters"),
    ):
        if isinstance(value, Sequence) and not isinstance(value, str):
            filters.extend(value)
    return filters


def _align_series_rows(
    *,
    aliases: Sequence[str],
    linker_column: str | None,
    linker_kind: str,
    series_rows: Sequence[Sequence[Mapping[str, Any]]],
) -> tuple[list[str], list[JsonObject], JsonObject]:
    if linker_column is None:
        columns = list(aliases)
        rows = [dict(row) for row in series_rows[0]] if series_rows else []
        return (
            columns,
            rows,
            _linker_diagnostics(
                linker_kind=linker_kind,
                matched=len(rows),
                unmatched=0,
                duplicate_conflicts=0,
                rows_excluded=0,
            ),
        )
    maps: list[dict[Any, Any]] = []
    conflict_keys: set[Any] = set()
    total_source_rows = 0
    for alias, rows in zip(aliases, series_rows, strict=True):
        values: dict[Any, Any] = {}
        seen: dict[Any, Any] = {}
        for row in rows:
            total_source_rows += 1
            key = row.get("__linker")
            value = row.get(alias)
            if key is None:
                continue
            if key in seen and seen[key] != value:
                conflict_keys.add(key)
                continue
            seen[key] = value
            values[key] = value
        maps.append(values)
    if not maps:
        return (
            [linker_column, *aliases],
            [],
            _linker_diagnostics(
                linker_kind=linker_kind,
                matched=0,
                unmatched=0,
                duplicate_conflicts=0,
                rows_excluded=0,
            ),
        )
    key_sets = [set(values) - conflict_keys for values in maps]
    matched_keys = set.intersection(*key_sets) if key_sets else set()
    union_keys = set.union(*key_sets) if key_sets else set()
    rows = [
        {linker_column: key}
        | {alias: values.get(key) for alias, values in zip(aliases, maps, strict=True)}
        for key in sorted(matched_keys, key=lambda value: str(value))
    ]
    used_values = len(rows) * len(aliases)
    diagnostics = _linker_diagnostics(
        linker_kind=linker_kind,
        matched=len(rows),
        unmatched=len(union_keys - matched_keys),
        duplicate_conflicts=len(conflict_keys),
        rows_excluded=max(total_source_rows - used_values, 0),
    )
    return [linker_column, *aliases], rows, diagnostics


def _linker_diagnostics(
    *,
    linker_kind: str,
    matched: int,
    unmatched: int,
    duplicate_conflicts: int,
    rows_excluded: int,
) -> JsonObject:
    return {
        "linker": linker_kind,
        "matched_count": matched,
        "unmatched_count": unmatched,
        "duplicate_conflict_count": duplicate_conflicts,
        "rows_excluded": rows_excluded,
    }


def _profile_series_items(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = config.get("series")
    if isinstance(raw, Mapping):
        raw_items = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, str):
        raw_items = [item for item in raw if isinstance(item, Mapping)]
    else:
        raw_items = []
    items = [
        item
        for item in raw_items
        if _series_profile_id(item) and _series_field_id(item)
    ]
    return items


def _series_profile_id(series_item: Mapping[str, Any]) -> str:
    source = series_item.get("source")
    if isinstance(source, Mapping):
        value = source.get("data_profile_id") or source.get("id")
        if isinstance(value, str):
            return value
    value = (
        series_item.get("profile_id")
        or series_item.get("data_profile_id")
        or series_item.get("profileId")
    )
    return str(value) if isinstance(value, str) else ""


def _series_field_id(series_item: Mapping[str, Any]) -> str:
    value = (
        series_item.get("field_id")
        or series_item.get("field")
        or series_item.get("fieldId")
        or series_item.get("value")
    )
    return str(value) if isinstance(value, str) else ""


def _series_aliases(series_items: Sequence[Mapping[str, Any]]) -> list[str]:
    aliases: list[str] = []
    used: set[str] = set()
    for index, series_item in enumerate(series_items):
        label = str(
            series_item.get("name")
            or series_item.get("label")
            or _series_field_id(series_item)
            or f"series_{index + 1}"
        )
        alias = _safe_alias(label, fallback=f"series_{index + 1}")
        if alias in used:
            alias = f"{alias}_{index + 1}"
        used.add(alias)
        aliases.append(alias)
    return aliases


def _readable_source_sql(table: str) -> str:
    integer_table = INTEGER_KEYED_TABLES.get(table)
    if integer_table is None:
        return _quote_identifier(table)
    return f"({integer_table.readable_select_sql()})"


def _series_source_sql(table: str) -> str:
    if table in {"sample_metrics", "entity_attributes"}:
        return _quote_identifier(table)
    return _readable_source_sql(table)


def _set_runtime_metadata(
    config: Mapping[str, Any], metadata: Mapping[str, Any]
) -> None:
    if isinstance(config, dict):
        runtime = config.setdefault("_runtime", {})
        if isinstance(runtime, dict):
            runtime.update(metadata)


def _runtime_metadata(config: Mapping[str, Any]) -> Mapping[str, Any]:
    runtime = config.get("_runtime")
    return runtime if isinstance(runtime, Mapping) else {}


async def _sample_pk(
    session: AsyncSession, project_id: str | None, sample_id: str
) -> int | None:
    statement = select(SampleRecord).where(SampleRecord.sample_id == sample_id)
    if project_id is not None:
        statement = statement.where(
            SampleRecord.project_id == await _project_pk(session, project_id)
        )
    row = (await session.exec(statement)).first()
    return row.id if row is not None else None


async def _run_sample_pk(
    session: AsyncSession, project_id: str | None, run_sample_id: str
) -> int | None:
    statement = select(RunSampleRecord).where(
        RunSampleRecord.run_sample_id == run_sample_id
    )
    if project_id is not None:
        statement = statement.where(
            RunSampleRecord.project_id == await _project_pk(session, project_id)
        )
    row = (await session.exec(statement)).first()
    return row.id if row is not None else None


async def _sample_set_run_sample_pks(
    session: AsyncSession, project_id: str | None, sample_set_id: str
) -> list[int]:
    statement = select(SampleSetRecord).where(
        SampleSetRecord.sample_set_id == sample_set_id
    )
    if project_id is not None:
        statement = statement.where(
            SampleSetRecord.project_id == await _project_pk(session, project_id)
        )
    sample_set = (await session.exec(statement)).first()
    if sample_set is None or sample_set.id is None:
        return []
    rows = (
        await session.exec(
            select(SampleSetMemberRecord.run_sample_id).where(
                SampleSetMemberRecord.sample_set_id == sample_set.id
            )
        )
    ).all()
    return [int(row) for row in rows]


async def _compile_profile_query(
    *,
    session: AsyncSession,
    project_id: str | None,
    query_config: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[str, list[Any], list[str]] | None:
    # Profile queries start from a stable semantic data_profile_id rather than a
    # physical table name. That keeps insight configs portable across projects
    # and lets the profile decide which analytical table is authoritative.

    source = query_config.get("source")
    if not isinstance(source, Mapping) or source.get("kind") != "data_profile":
        return None

    profile_public_id = str(
        source.get("data_profile_id")
        or source.get("id")
        or query_config.get("data_profile_id")
        or ""
    )

    if not profile_public_id:
        raise ValueError("Profile queries require source.data_profile_id.")

    profile = await _get_profile_record(session, project_id, profile_public_id)

    if profile is None:
        raise ValueError(f"Unknown data profile: {profile_public_id}")

    table = profile.primary_table

    if table not in {
        "sample_metrics",
        "entity_attributes",
        "feature_value_numeric",
        "feature_call",
        "copy_number_segments",
        "sample_variant_calls",
        "sample_structural_variant_calls",
        "profile_payloads",
    }:
        raise ValueError(
            f"Profile-first queries are not available for table: {table or 'unknown'}"
        )

    requested_fields = _profile_requested_fields(query_config, config)
    synthetic_fields = _synthetic_profile_fields(table)

    # Some analytical tables expose meaningful columns directly instead of
    # catalog-backed data_profile_fields rows. Treat those as synthetic fields so
    # users can still query them through the same profile-first grammar.
    if table in {"feature_value_numeric", *synthetic_fields} and not requested_fields:
        requested_fields = [next(iter(synthetic_fields.get(table, {"value": "value"})))]

    if not requested_fields:
        raise ValueError("Profile queries require at least one field or measure.")

    if table == "feature_value_numeric":
        # Feature matrices store the measured value in a single canonical value
        # column; the feature dimension carries the biological identity.
        field = None
        field_id = "value"
        value_column = "value"
    elif table in synthetic_fields:
        requested_fields = _normalize_synthetic_requested_fields(
            requested_fields,
            synthetic_fields[table],
        )
        field = None
        field_id = requested_fields[0]
        value_column = synthetic_fields[table][field_id]
    else:
        field_rows = await _get_profile_field_records(
            session,
            profile_id=_record_pk(profile),
            field_ids=requested_fields,
        )
        if any(field_id not in field_rows for field_id in requested_fields):
            # The dashboard often sends safe aliases for fields with punctuation.
            # If direct lookup misses, load all fields and map aliases back to
            # canonical field IDs.
            field_rows = await _get_all_profile_field_records(
                session,
                profile_id=_record_pk(profile),
            )
        field_aliases = {
            _safe_alias(row.field_id, fallback="value"): field_id
            for field_id, row in field_rows.items()
        }
        requested_fields = list(
            dict.fromkeys(
                field_aliases.get(field_id, field_id) for field_id in requested_fields
            )
        )
        missing = [field for field in requested_fields if field not in field_rows]
        if missing:
            raise ValueError(f"Unknown profile field(s): {', '.join(missing)}")
        field = field_rows[requested_fields[0]]
        field_id = field.field_id
        value_column = _profile_value_column(field)

    field_alias = _safe_alias(field_id, fallback="value")
    dimensions = _string_list(
        query_config.get("dimensions") or query_config.get("group_by")
    )
    if not dimensions and isinstance(query_config.get("entity"), str):
        # Entity grain provides sensible default dimensions. A run_sample insight
        # should naturally group by processed sample unless the config says
        # otherwise.
        entity = str(query_config["entity"])
        if entity in {"run_sample", "sample"} and table == "sample_metrics":
            dimensions = ["run_sample_id" if entity == "run_sample" else "sample_id"]
        elif table == "entity_attributes":
            dimensions = ["entity_id"]
        elif table != "profile_payloads":
            dimensions = ["run_sample_id" if entity == "run_sample" else "sample_id"]

    columns = _columns_for_source("analytics", table)
    measures = _measures(query_config, config)
    if (
        table in {"sample_metrics", "entity_attributes"}
        and len(requested_fields) > 1
        and not measures
    ):
        # Multi-field metric/attribute requests should return one row per entity
        # with a column per field. This is the shape most chart/table previews
        # expect for MultiQC-like "several metrics per sample" payloads.
        entity = str(query_config.get("entity") or "")
        dimension = (
            "run_sample_id"
            if table == "sample_metrics" and entity != "sample"
            else "sample_id"
            if table == "sample_metrics"
            else "entity_id"
        )
        parameters: list[Any] = []
        select_parts = [
            f"{_quote_identifier(dimension)} AS {_quote_identifier(dimension)}"
        ]
        for requested_field in requested_fields:
            row = field_rows[requested_field]
            value_column = _profile_value_column(row)
            alias = _safe_alias(row.field_id, fallback="value")
            # Each field is stored as its own row in sample_metrics. CASE/MAX
            # pivots those sparse rows into a compact entity-wide row.
            select_parts.append(
                "MAX(CASE WHEN "
                f"{_field_id_match_sql(parameters, row)} "
                f"THEN {_quote_identifier(value_column)} END) "
                f"AS {_quote_identifier(alias)}"
            )
        parameters.append(_record_pk(profile))
        field_predicates = [
            _field_id_match_sql(parameters, field_rows[field_id])
            for field_id in requested_fields
        ]
        sql = (
            f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(table)} "
            f"WHERE data_profile_id = ? AND ({' OR '.join(field_predicates)}) "
            f"GROUP BY {_quote_identifier(dimension)}"
        )
        output_columns = [
            dimension,
            *[
                _safe_alias(field_rows[field_id].field_id, fallback="value")
                for field_id in requested_fields
            ],
        ]
        return sql, parameters, output_columns

    select_parts: list[str] = []
    group_parts: list[str] = []
    exposed_columns = set(columns) | {field_id, "value", field_alias}
    for dimension in dimensions:
        if dimension in {field_id, field_alias, "value"}:
            # Allow the selected value field itself to be used as a grouping
            # dimension, for example counting categorical values in a profile.
            expression = _quote_identifier(value_column)
            alias = field_alias
        else:
            _require_column(columns, dimension)
            expression = _quote_identifier(dimension)
            alias = dimension
        select_parts.append(f"{expression} AS {_quote_identifier(alias)}")
        group_parts.append(expression)
        exposed_columns.add(alias)

    for measure in measures:
        aggregation = measure["aggregation"]
        if aggregation not in AGGREGATIONS:
            raise ValueError(f"Unsupported aggregation: {aggregation}")
        measure_field = measure["field"]
        if measure_field in {field_id, field_alias, "value"}:
            expression = _quote_identifier(value_column)
        elif measure_field == "*":
            expression = "*"
        else:
            _require_column(columns, measure_field)
            expression = _quote_identifier(measure_field)
        alias = measure["alias"]
        select_parts.append(
            f"{aggregation.upper()}({expression}) AS {_quote_identifier(alias)}"
        )
        exposed_columns.add(alias)

    if not select_parts:
        # Without explicit dimensions or measures, return raw values with the
        # profile's natural entity dimensions.
        default_dimensions = _default_profile_dimensions(table)
        for column in default_dimensions:
            if column in columns:
                select_parts.append(
                    f"{_quote_identifier(column)} AS {_quote_identifier(column)}"
                )
        select_parts.append(
            f"{_quote_identifier(value_column)} AS {_quote_identifier(field_alias)}"
        )
        exposed_columns.add(field_alias)

    parameters: list[Any] = [_record_pk(profile)]
    where_parts = ["data_profile_id = ?"]
    if field is not None:
        where_parts.append(_field_id_match_sql(parameters, field))
    for filter_config in [
        *cast(Sequence[Any], query_config.get("filters") or []),
        *cast(Sequence[Any], config.get("filters") or []),
    ]:
        # Filters can live either inside query or at top-level config. Supporting
        # both keeps saved JSON compatible with dashboard and template shapes.
        where_parts.append(
            _profile_filter_sql(
                columns=columns,
                value_column=value_column,
                field_aliases={field_id, field_alias, "value"},
                filter_config=filter_config,
                parameters=parameters,
            )
        )

    sql = f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(table)}"
    sql += " WHERE " + " AND ".join(where_parts)
    if group_parts:
        sql += " GROUP BY " + ", ".join(group_parts)
    order_sql = _order_sql(
        columns=exposed_columns,
        value=query_config.get("order_by"),
    )
    if order_sql:
        sql += f" ORDER BY {order_sql}"
    output_columns = [part.split(" AS ")[-1].strip('"') for part in select_parts]
    return sql, parameters, output_columns


def compile_insight_result(
    *,
    config: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    insight_id: str | None,
    computed_at: datetime,
    cached: bool,
    result_policy_summary: Mapping[str, Any] | None = None,
) -> JsonObject:
    """Compile query rows into a dashboard/report insight payload."""

    visualization = str(config.get("visualization") or "table")
    row_dicts = [dict(row) for row in rows]
    plot_table = {
        "columns": list(columns),
        "rows": row_dicts,
        "row_count": len(row_dicts),
    }
    runtime = _runtime_metadata(config)
    result_policy = (
        dict(result_policy_summary)
        if result_policy_summary is not None
        else _inline_result_policy_summary(config, len(row_dicts))
    )
    result: JsonObject = {
        "kind": "insight_result",
        "insight_id": insight_id,
        "title": config.get("title") or config.get("name") or "Untitled insight",
        "description": config.get("description"),
        "context": (
            config.get("context") if isinstance(config.get("context"), dict) else {}
        ),
        "mode": config.get("mode") or _default_mode(config),
        "linker": runtime.get("linker") or normalize_linker(config.get("linker")),
        "filters": (
            config.get("filters") if isinstance(config.get("filters"), list) else []
        ),
        "result_policy": result_policy,
        "linker_diagnostics": runtime.get("linker_diagnostics")
        or _linker_diagnostics(
            linker_kind=str(normalize_linker(config.get("linker"))["kind"]),
            matched=len(row_dicts),
            unmatched=0,
            duplicate_conflicts=0,
            rows_excluded=0,
        ),
        "visualization": visualization,
        "display": (
            config.get("display") if isinstance(config.get("display"), dict) else {}
        ),
        "columns": list(columns),
        "rows": row_dicts,
        "plot_table": plot_table,
        "computed_at": computed_at.isoformat(),
        "cached": cached,
    }
    if visualization == "table":
        return result
    if visualization in {"metric", "stat", "number"}:
        # Metric cards are a special compact payload. Other non-table
        # visualizations are expressed as ECharts options.
        result["metric"] = _metric_payload(row_dicts, columns)
        return result
    _validate_plot_result(config, list(columns), row_dicts)
    result["echarts_options"] = _echarts_options(config, list(columns), row_dicts)
    return result


def _apply_result_policy(
    *,
    config: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    analytics_store: DuckDBAnalyticsStore,
) -> tuple[list[JsonObject], JsonObject]:
    policy = normalize_result_policy(config.get("result_policy"))
    mode = str(policy["mode"])
    limit = int(policy["limit"])
    row_dicts = [dict(row) for row in rows]
    if mode == "all_rows" and len(row_dicts) > ALL_ROWS_INLINE_THRESHOLD:
        raise ValueError(
            "All rows can only be embedded below the configured response threshold. "
            "Use Export full data for larger results."
        )
    if mode == "random_sample" and len(row_dicts) > limit:
        seed = str(policy.get("seed") or "goodomics")
        randomizer = random.Random(seed)
        sampled_indices = sorted(randomizer.sample(range(len(row_dicts)), limit))
        sampled = [row_dicts[index] for index in sampled_indices]
        return sampled, {
            **policy,
            "embedded_row_count": len(sampled),
            "source_row_count": len(row_dicts),
            "sampled": True,
        }
    if mode == "export_full_data":
        artifact = _write_plot_artifact(
            analytics_store=analytics_store,
            columns=columns,
            rows=row_dicts,
        )
        embedded = row_dicts[:PREVIEW_DEFAULT_LIMIT]
        return embedded, {
            **policy,
            "embedded_row_count": len(embedded),
            "source_row_count": len(row_dicts),
            "artifact": artifact,
            "exported": True,
        }
    embedded = row_dicts[:limit]
    return embedded, {
        **policy,
        "embedded_row_count": len(embedded),
        "source_row_count": len(row_dicts),
    }


def _write_plot_artifact(
    *,
    analytics_store: DuckDBAnalyticsStore,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> JsonObject:
    artifact_dir = analytics_store.path.parent / "insight_artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_id = f"plot_table_{uuid4().hex}.json"
    path = artifact_dir / artifact_id
    payload = {"columns": list(columns), "rows": [dict(row) for row in rows]}
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    return {
        "artifact_id": artifact_id,
        "path": str(path),
        "format": "json",
        "row_count": len(rows),
    }


def _inline_result_policy_summary(
    config: Mapping[str, Any], row_count: int
) -> JsonObject:
    policy = normalize_result_policy(config.get("result_policy"))
    return {
        **policy,
        "embedded_row_count": row_count,
        "source_row_count": row_count,
    }


def _validate_plot_result(
    config: Mapping[str, Any], columns: list[str], rows: list[JsonObject]
) -> None:
    visualization = str(config.get("visualization") or "table")
    if visualization in {"table", "metric", "stat", "number"}:
        return
    query = _query_config(config)
    x_field = str(query.get("x") or _default_x_field(config, columns))
    y_field = str(
        query.get("y") or _first_numeric_column(columns, rows, exclude={x_field}) or ""
    )
    series_fields = _plot_series_fields(config, columns, rows, x_field, y_field)
    numeric_fields = [
        field for field in series_fields if _column_is_numeric(rows, field)
    ]
    if visualization == "scatter":
        linker = _runtime_metadata(config).get("linker") or normalize_linker(
            config.get("linker")
        )
        if len(series_fields) != 2 or len(numeric_fields) != 2:
            raise ValueError("Scatter plots require exactly two numeric measures.")
        if not isinstance(linker, Mapping) or linker.get("kind") in {None, "auto"}:
            raise ValueError("Scatter plots require a visible Matched by linker.")
    if visualization in {"line", "area", "histogram", "boxplot"}:
        non_numeric = [field for field in series_fields if field not in numeric_fields]
        if non_numeric:
            raise ValueError(
                f"{visualization} charts require numeric fields: "
                f"{', '.join(non_numeric)}"
            )
    if visualization == "stacked_bar":
        if len(series_fields) < 2:
            raise ValueError("Stacked bars require at least two numeric series.")
        non_numeric = [field for field in series_fields if field not in numeric_fields]
        if non_numeric:
            raise ValueError(
                "Stacked bars require numeric fields: " + ", ".join(non_numeric)
            )
    if visualization in {"pie", "donut"} and len(series_fields) != 1:
        raise ValueError("Pie and donut charts require exactly one series.")


def _plot_series_fields(
    config: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    x_field: str,
    y_field: str,
) -> list[str]:
    runtime = _runtime_metadata(config)
    runtime_aliases = runtime.get("series_aliases")
    if isinstance(runtime_aliases, Sequence) and not isinstance(runtime_aliases, str):
        return [str(field) for field in runtime_aliases if str(field) in columns]
    query = _query_config(config)
    if str(config.get("visualization") or "") == "scatter":
        x_value = query.get("x")
        y_value = query.get("y")
        if isinstance(x_value, str) and isinstance(y_value, str):
            return [field for field in (x_value, y_value) if field in columns]
    if str(config.get("visualization") or "") == "histogram":
        return _histogram_value_fields(query, columns, y_field)
    if query.get("y") is not None and y_field in columns:
        return [y_field]
    first_row = rows[0] if rows else {}
    return [
        column
        for column in columns
        if column != x_field and column in first_row and column != "__linker"
    ]


def _default_x_field(config: Mapping[str, Any], columns: Sequence[str]) -> str:
    query = _query_config(config)
    dimensions = _string_list(query.get("dimensions") or query.get("group_by"))
    if query.get("x") is not None:
        return str(query["x"])
    if dimensions:
        return dimensions[0]
    return columns[0] if columns else ""


def _column_is_numeric(rows: Sequence[Mapping[str, Any]], field: str) -> bool:
    values = [row.get(field) for row in rows if row.get(field) is not None]
    return bool(values) and all(_is_numeric_value(value) for value in values)


async def fingerprint_source(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    source: Mapping[str, Any],
) -> str:
    """Return a cache fingerprint for an insight/report data source."""

    if source.get("kind") == "data_profile":
        profile_id = str(source.get("data_profile_id") or "")
        profile = await _get_profile_record(session, project_id, profile_id)
        field_count = 0
        if profile is not None:
            # Profile summaries/fingerprints capture data updates, while field
            # count captures schema changes that affect available measures.
            field_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(DataProfileFieldRecord)
                        .where(DataProfileFieldRecord.data_profile_id == profile.id)
                    )
                ).one()
            )
        return canonical_hash(
            {
                "kind": "data_profile",
                "data_profile_id": profile_id,
                "source_fingerprint": (
                    profile.source_fingerprint if profile is not None else None
                ),
                "last_profiled_at": (
                    profile.last_profiled_at.isoformat()
                    if profile is not None and profile.last_profiled_at is not None
                    else None
                ),
                "fields": field_count,
            }
        )
    if source.get("kind") == "profile_series":
        profile_ids = [
            str(value)
            for value in source.get("data_profile_ids", [])
            if isinstance(value, str)
        ]
        return canonical_hash(
            {
                "kind": "profile_series",
                "profiles": [
                    await fingerprint_source(
                        session=session,
                        analytics_store=analytics_store,
                        project_id=project_id,
                        source={"kind": "data_profile", "data_profile_id": profile_id},
                    )
                    for profile_id in profile_ids
                ],
            }
        )
    store = source.get("store")
    table = source.get("table")
    if store == "analytics":
        # For raw analytics table sources, row counts and file size are a cheap
        # invalidation signal. They are not a cryptographic data snapshot, but
        # they are enough for dashboard cache freshness in local workflows.
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
            # Catalog project columns are mixed: most core tables use integer
            # project foreign keys, while server tables store public project IDs.
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
    # Generic builder queries target a physical catalog/analytics table. They
    # are less semantic than profile-first queries but useful for database
    # previews and advanced dashboard workflows.
    columns = _columns_for_source(store, table)
    dimensions = _string_list(
        query_config.get("dimensions") or query_config.get("group_by")
    )
    if not dimensions and isinstance(query_config.get("x"), str):
        # Chart configs commonly use x/y language. Treat x as the grouping
        # dimension when dimensions/group_by are omitted.
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
        # No dimensions/measures means "show rows". Limit to the first handful
        # of columns unless the config requested specific columns.
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
    # Project scoping only applies to tables that expose a project_id column.
    # Analytics tables already store public project labels when they have one.
    if project_id is None or "project_id" not in columns:
        return None
    if store == "catalog":
        model = CATALOG_MODELS.get(table)
        if model is not None and _project_field_is_integer(model):
            # Core catalog tables use integer project FKs, so resolve the public
            # project_id to its SQL primary key before filtering.
            parameters.append(await _project_pk(session, project_id))
        else:
            parameters.append(project_id)
    else:
        parameters.append(project_id)
    return f"{_quote_identifier('project_id')} = ?"


def _filter_sql(
    columns: Sequence[str], filter_config: Any, parameters: list[Any]
) -> str:
    # Convert a small JSON filter grammar into parameterized SQL. Column and
    # operator validation happen before any SQL fragment is returned.
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
    # ORDER BY accepts either "column" or {"field": "column", "direction":
    # "desc"}. The chosen column must already be exposed by the query.
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
    # SQLAlchemy text queries use named parameters, while the shared query
    # compiler emits positional question marks for both stores. Rewrite them
    # just before execution.
    bounded_sql, named_parameters = _named_sql_parameters(sql, parameters)
    result = await cast(Any, session).exec(
        text(
            f"SELECT * FROM ({bounded_sql}) AS goodomics_query LIMIT :goodomics_limit"
        ),
        params=named_parameters
        | {"goodomics_limit": min(max(limit, 1), EXPORT_FULL_DATA_LIMIT)},
    )
    rows = [dict(row) for row in result.mappings().all()]
    columns = list(rows[0]) if rows else []
    return columns, rows


def _named_sql_parameters(
    sql: str, parameters: Sequence[Any]
) -> tuple[str, dict[str, Any]]:
    # Replace ? placeholders with SQLAlchemy named parameters. This keeps the
    # compiler simple while still using safe bound values for catalog SQL.
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
    # Cache rows are append-only. Pick the newest matching row so a refresh can
    # write a new result without mutating older history.
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
    # Report cache lookup mirrors insight cache lookup but keys by report_id.
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
    # Missing or malformed query blocks are treated as empty query config so
    # callers get a clear "source required" error downstream.
    query = config.get("query")
    return query if isinstance(query, Mapping) else {}


def _query_source(config: Mapping[str, Any]) -> JsonObject:
    # Extract only the source identity used for fingerprinting. Query shape,
    # filters, and visualization are already part of the config hash.
    profile_series = _profile_series_items(config)
    if profile_series:
        return {
            "kind": "profile_series",
            "data_profile_ids": sorted(
                {_series_profile_id(series_item) for series_item in profile_series}
            ),
        }
    query = _query_config(config)
    source = query.get("source")
    if isinstance(source, Mapping) and source.get("kind") == "data_profile":
        return {
            "kind": "data_profile",
            "data_profile_id": source.get("data_profile_id") or source.get("id"),
        }
    store, table = _parse_source(query.get("source"))
    return {"store": store, "table": table}


def _parse_source(value: Any) -> tuple[StoreName, str | None]:
    # Sources can be explicit objects, "store.table" strings, or bare analytics
    # table names. Normalize all variants into (store, table).
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


async def _get_profile_record(
    session: AsyncSession,
    project_id: str | None,
    data_profile_id: str,
) -> DataProfileRecord | None:
    statement = select(DataProfileRecord).where(
        DataProfileRecord.data_profile_id == data_profile_id
    )
    if project_id is not None:
        project_pk = await _project_pk(session, project_id)
        if project_pk is None:
            return None
        if project_id == DEFAULT_PROJECT_ID:
            profile_project_id = cast(Any, DataProfileRecord.project_id)
            statement = statement.where(
                or_(
                    profile_project_id == project_pk,
                    profile_project_id.is_(None),
                )
            )
        else:
            statement = statement.where(DataProfileRecord.project_id == project_pk)
    rows = list((await session.exec(statement)).all())
    if project_id == DEFAULT_PROJECT_ID:
        for row in rows:
            if row.project_id == project_pk:
                return row
    return rows[0] if rows else None


async def _get_profile_field_records(
    session: AsyncSession,
    *,
    profile_id: int,
    field_ids: Sequence[str],
) -> dict[str, DataProfileFieldRecord]:
    rows = (
        await session.exec(
            select(DataProfileFieldRecord)
            .where(DataProfileFieldRecord.data_profile_id == profile_id)
            .where(cast(Any, DataProfileFieldRecord.field_id).in_(list(field_ids)))
        )
    ).all()
    return {row.field_id: row for row in rows}


async def _get_all_profile_field_records(
    session: AsyncSession,
    *,
    profile_id: int,
) -> dict[str, DataProfileFieldRecord]:
    rows = (
        await session.exec(
            select(DataProfileFieldRecord).where(
                DataProfileFieldRecord.data_profile_id == profile_id
            )
        )
    ).all()
    return {row.field_id: row for row in rows}


def _profile_requested_fields(
    query_config: Mapping[str, Any], config: Mapping[str, Any]
) -> list[str]:
    # Fields can be declared explicitly, implied by measures, or used as
    # dimensions. Collect all field-like references before validating them.
    fields = _string_list(query_config.get("fields"))
    for measure in _measures(query_config, config):
        field = measure["field"]
        if field not in {"*", "value"}:
            fields.append(field)
    for value in _string_list(
        query_config.get("dimensions") or query_config.get("group_by")
    ):
        if value not in {"run_id", "run_sample_id", "sample_id", "entity_id"}:
            fields.append(value)
    return list(dict.fromkeys(fields))


def _profile_value_column(field: DataProfileFieldRecord) -> str:
    # Field definitions can override the physical value column. Otherwise choose
    # the column from the declared value_type.
    query_ref = field.query_ref_json if isinstance(field.query_ref_json, dict) else {}
    value_column = query_ref.get("value_column")
    if isinstance(value_column, str) and value_column in {
        "value_numeric",
        "value_string",
        "value_boolean",
        "value_datetime",
        "value_json",
    }:
        return value_column
    return {
        "numeric": "value_numeric",
        "string": "value_string",
        "boolean": "value_boolean",
        "date": "value_datetime",
        "json": "value_json",
    }.get(field.value_type, "value_string")


def _field_id_match_sql(parameters: list[Any], field: DataProfileFieldRecord) -> str:
    # DuckDB may store field_id as the SQL integer ID, while readable views can
    # expose field labels through dim_fields. Match both forms.
    parameters.extend([_record_pk(field), field.field_id])
    return (
        "(field_id = ? OR field_id IN ("
        "SELECT field_id FROM dim_fields WHERE field_label = ?"
        "))"
    )


def _synthetic_profile_fields(table: str | None) -> dict[str, dict[str, str]]:
    # Tables without data_profile_fields rows still expose important queryable
    # columns. These synthetic fields let the profile grammar address them by
    # stable names.
    fields = {
        "feature_call": {
            "call_code": "call_code",
            "call_rank": "call_rank",
        },
        "copy_number_segments": {
            "segment_mean": "segment_mean",
            "num_probes": "num_probes",
        },
        "sample_variant_calls": {
            "allele_fraction": "allele_fraction",
            "genotype": "genotype",
            "filter": "filter",
        },
        "sample_structural_variant_calls": {
            "call_status": "call_status",
            "split_read_count": "split_read_count",
            "paired_end_read_count": "paired_end_read_count",
        },
        "profile_payloads": {
            "payload_kind": "payload_kind",
            "payload_name": "payload_name",
        },
    }
    if table == "feature_value_numeric":
        return {"feature_value_numeric": {"value": "value"}}
    return fields


def _normalize_synthetic_requested_fields(
    requested_fields: Sequence[str],
    field_map: Mapping[str, str],
) -> list[str]:
    # Accept both canonical synthetic names and their safe aliases.
    aliases = {
        _safe_alias(field_id, fallback="value"): field_id for field_id in field_map
    }
    normalized = [
        aliases.get(field_id, field_id)
        for field_id in requested_fields
        if field_id in field_map or field_id in aliases
    ]
    if not normalized:
        unknown = ", ".join(requested_fields)
        raise ValueError(f"Unknown profile field(s): {unknown}")
    return list(dict.fromkeys(normalized))


def _default_profile_dimensions(table: str | None) -> list[str]:
    # Raw profile previews should include the natural entity columns users need
    # to understand what each value belongs to.
    if table in {"sample_metrics", "feature_value_numeric", "feature_call"}:
        return ["run_sample_id", "sample_id"]
    if table == "entity_attributes":
        return ["entity_id"]
    if table in {
        "copy_number_segments",
        "sample_variant_calls",
        "sample_structural_variant_calls",
    }:
        return ["run_sample_id", "sample_id"]
    if table == "profile_payloads":
        return ["run_id", "payload_name"]
    return []


def _profile_filter_sql(
    *,
    columns: Sequence[str],
    value_column: str,
    field_aliases: set[str],
    filter_config: Any,
    parameters: list[Any],
) -> str:
    # Filters may use the profile field alias ("value", field_id, safe alias) or
    # a physical table column. Rewrite field-value filters to the value column.
    if not isinstance(filter_config, Mapping):
        raise ValueError("Filters must be objects.")
    field = str(filter_config.get("field") or "")
    if field in field_aliases:
        rewritten = dict(filter_config)
        rewritten["field"] = value_column
        return _filter_sql(columns, rewritten, parameters)
    return _filter_sql(columns, filter_config, parameters)


def _record_pk(row: Any) -> int:
    # Query compilation depends on catalog primary keys; fail loudly if a caller
    # passes an unflushed SQLModel row.
    row_id = getattr(row, "id", None)
    if row_id is None:
        raise ValueError("Catalog record has not been flushed.")
    return int(row_id)


def _columns_for_source(store: StoreName, table: str) -> list[str]:
    # Column validation is based on registered serializers/models rather than
    # trusting table names from client-provided config.
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
    # Measures can come from query.measures or top-level series. Normalize both
    # shapes into field/aggregation/alias records used by query compilers.
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


def _query_limit(
    query_config: Mapping[str, Any], config: Mapping[str, Any] | None = None
) -> int:
    # Bound every query according to the visible result-size policy. The final
    # response may be smaller, sampled, or file-backed after rows are returned.
    policy = normalize_result_policy(
        config.get("result_policy") if isinstance(config, Mapping) else None
    )
    mode = str(policy["mode"])
    if mode == "preview":
        return PREVIEW_DEFAULT_LIMIT
    if mode == "more_rows":
        return min(int(policy["limit"]), MORE_ROWS_MAX_LIMIT)
    if mode == "random_sample":
        return min(
            max(int(policy["limit"]) * 5, PREVIEW_DEFAULT_LIMIT),
            MORE_ROWS_MAX_LIMIT,
        )
    if mode == "all_rows":
        return ALL_ROWS_INLINE_THRESHOLD + 1
    if mode == "export_full_data":
        return EXPORT_FULL_DATA_LIMIT
    value = query_config.get("limit", PREVIEW_DEFAULT_LIMIT)
    try:
        return min(max(int(value), 1), MORE_ROWS_MAX_LIMIT)
    except (TypeError, ValueError):
        return PREVIEW_DEFAULT_LIMIT


def _validate_read_only_sql(sql: str) -> str:
    # Advanced SQL is intentionally SELECT/WITH-only and single-statement. This
    # avoids mutating local databases through dashboard-authored SQL.
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
    # ECharts is an implementation detail: configs describe chart intent, and
    # this helper compiles rows into the option shape the dashboard can render.
    visualization = str(config.get("visualization") or "bar")
    query = _query_config(config)
    colors = _display_colors(config)
    runtime = _runtime_metadata(config)
    runtime_aliases = runtime.get("series_aliases")
    series_aliases = (
        [str(value) for value in runtime_aliases if str(value) in columns]
        if isinstance(runtime_aliases, Sequence)
        and not isinstance(runtime_aliases, str)
        else []
    )
    dimensions = _string_list(query.get("dimensions") or query.get("group_by"))
    x_field = str(query.get("x") or (dimensions[0] if dimensions else columns[0]))
    y_field = str(
        query.get("y") or _first_numeric_column(columns, rows, exclude={x_field})
    )
    title = str(config.get("title") or config.get("name") or "Insight")
    if visualization in {"pie", "donut"}:
        return {
            "title": {"text": title, "left": "center"},
            "color": CHART_COLORS,
            "tooltip": {"trigger": "item"},
            "series": [
                {
                    "name": x_field,
                    "type": "pie",
                    "radius": ["42%", "70%"] if visualization == "donut" else "65%",
                    "data": [
                        {
                            "name": str(row.get(x_field)),
                            "value": row.get(y_field),
                            "itemStyle": {
                                "color": _category_color(
                                    colors, str(row.get(x_field)), index
                                )
                            },
                        }
                        for index, row in enumerate(rows)
                    ],
                }
            ],
        }
    if visualization == "scatter":
        if len(series_aliases) >= 2:
            x_field = series_aliases[0]
            y_field = series_aliases[1]
        return {
            "tooltip": {"trigger": "item"},
            "grid": {
                "left": 64,
                "right": 32,
                "top": 40,
                "bottom": 72,
                "containLabel": True,
            },
            "xAxis": {
                "type": "value",
                "name": x_field,
                "nameLocation": "middle",
                "nameGap": 48,
            },
            "yAxis": {
                "type": "value",
                "name": y_field,
                "nameLocation": "middle",
                "nameGap": 44,
            },
            "series": [
                {
                    "type": "scatter",
                    "data": [
                        {
                            "value": [row.get(x_field), row.get(y_field)],
                            "name": str(row.get(columns[0])) if columns else "",
                        }
                        for row in rows
                    ],
                    "itemStyle": {"color": _series_color(colors, x_field, 0)},
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
        # Histograms are computed server-side from raw numeric values so the
        # dashboard receives a compact binned series.
        value_fields = (
            series_aliases
            or _histogram_value_fields(query, columns, y_field)
            or ([y_field] if y_field in columns else columns[:1])
        )
        bin_count = _histogram_bin_count(config)
        return {
            "tooltip": {"trigger": "axis"},
            "grid": {
                "left": 64,
                "right": 32,
                "top": 40,
                "bottom": 72,
                "containLabel": True,
            },
            "xAxis": {
                "type": "value",
                "name": value_fields[0] if len(value_fields) == 1 else "Value",
                "nameLocation": "middle",
                "nameGap": 48,
                "scale": True,
                "axisLabel": {"formatter": "{value}"},
            },
            "yAxis": {
                "type": "value",
                "name": "Count",
                "nameLocation": "middle",
                "nameGap": 44,
            },
            "series": [
                {
                    "name": value_field,
                    "type": "bar",
                    "barGap": "-100%" if len(value_fields) > 1 else "0%",
                    "data": [
                        {
                            "name": bin_["label"],
                            "value": [bin_["center"], bin_["count"]],
                        }
                        for bin_ in _histogram_bins(
                            rows,
                            value_field=value_field,
                            bin_count=bin_count,
                        )
                    ],
                    "itemStyle": {
                        "color": _series_color(colors, value_field, index),
                        "opacity": 0.48 if len(value_fields) > 1 else 0.82,
                    },
                }
                for index, value_field in enumerate(value_fields)
            ],
        }
    if visualization in {"boxplot", "box_plot"}:
        return _boxplot_options(
            config=config,
            columns=columns,
            rows=rows,
            x_field=x_field,
            y_fields=series_aliases or [y_field],
        )
    chart_type = {
        "line": "line",
        "area": "line",
        "bar": "bar",
        "stacked_bar": "bar",
        "boxplot": "boxplot",
        "box_plot": "boxplot",
    }.get(visualization, "bar")
    first_row = rows[0] if rows else {}
    series_fields = (
        series_aliases
        if series_aliases
        else (
            [y_field]
            if query.get("y") is not None and y_field and y_field in first_row
            else [
                column
                for column in columns
                if column != x_field and column in first_row
            ]
        )
    ) or ([y_field] if y_field else [])
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"type": "scroll"},
        "grid": {
            "left": 64,
            "right": 32,
            "top": 40,
            "bottom": 72,
            "containLabel": True,
        },
        "xAxis": {
            "type": "category",
            "name": x_field,
            "nameLocation": "middle",
            "nameGap": 48,
            "data": [row.get(x_field) for row in rows],
        },
        "yAxis": {
            "type": "value",
            "name": y_field,
            "nameLocation": "middle",
            "nameGap": 44,
        },
        "series": [
            {
                "name": field,
                "type": chart_type,
                "stack": "total" if visualization == "stacked_bar" else None,
                "areaStyle": {} if visualization == "area" else None,
                "data": [row.get(field) for row in rows],
                "itemStyle": {"color": _series_color(colors, field, index)},
                "lineStyle": {"color": _series_color(colors, field, index)},
            }
            for index, field in enumerate(series_fields)
        ],
    }


def _display_colors(config: Mapping[str, Any]) -> dict[str, str]:
    display = config.get("display")
    if not isinstance(display, Mapping):
        return {}
    colors = display.get("colors")
    if not isinstance(colors, Mapping):
        return {}
    return {
        str(key): str(value)
        for key, value in colors.items()
        if isinstance(value, str) and value.startswith("#")
    }


def _boxplot_options(
    *,
    config: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    x_field: str,
    y_fields: Sequence[str],
) -> JsonObject:
    colors = _display_colors(config)
    title = str(config.get("title") or config.get("name") or "Insight")
    group_field = x_field if x_field in columns else columns[0] if columns else "group"
    groups = list(dict.fromkeys(str(row.get(group_field)) for row in rows))
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item"},
        "legend": {"type": "scroll"},
        "grid": {
            "left": 64,
            "right": 32,
            "top": 40,
            "bottom": 72,
            "containLabel": True,
        },
        "xAxis": {
            "type": "category",
            "name": group_field,
            "data": groups,
            "nameLocation": "middle",
            "nameGap": 48,
        },
        "yAxis": {
            "type": "value",
            "name": ", ".join(y_fields),
            "nameLocation": "middle",
            "nameGap": 44,
        },
        "series": [
            {
                "name": field,
                "type": "boxplot",
                "data": [
                    _five_number_summary(
                        [
                            float(row[field])
                            for row in rows
                            if str(row.get(group_field)) == group
                            and _is_numeric_value(row.get(field))
                        ]
                    )
                    for group in groups
                ],
                "itemStyle": {"color": _series_color(colors, field, index)},
            }
            for index, field in enumerate(y_fields)
            if field in columns
        ],
    }


def _five_number_summary(values: Sequence[float]) -> list[float | None]:
    if not values:
        return [None, None, None, None, None]
    sorted_values = sorted(values)
    return [
        sorted_values[0],
        _quantile(sorted_values, 0.25),
        _quantile(sorted_values, 0.5),
        _quantile(sorted_values, 0.75),
        sorted_values[-1],
    ]


def _quantile(values: Sequence[float], q: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def _series_color(
    colors: Mapping[str, str],
    field: str,
    index: int,
    fallback: str | None = None,
) -> str:
    configured = list(dict.fromkeys(colors.values()))
    return (
        colors.get(field)
        or colors.get(_safe_alias(field, fallback="series"))
        or (configured[index] if index < len(configured) else None)
        or fallback
        or CHART_COLORS[index % len(CHART_COLORS)]
    )


def _category_color(colors: Mapping[str, str], category: str, index: int) -> str:
    return (
        colors.get(category)
        or colors.get(_safe_alias(category, fallback="category"))
        or CHART_COLORS[index % len(CHART_COLORS)]
    )


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


def _histogram_value_fields(
    query: Mapping[str, Any], columns: Sequence[str], fallback: str
) -> list[str]:
    fields: list[str] = []
    for field in _string_list(query.get("fields")):
        if field in columns:
            fields.append(field)
            continue
        alias = _safe_alias(field, fallback="value")
        if alias in columns:
            fields.append(alias)
    value = query.get("value") or query.get("y")
    if isinstance(value, str):
        fields.append(value)
    if fallback:
        fields.append(fallback)
    return list(dict.fromkeys(field for field in fields if field in columns))


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
        return [
            {
                "label": _format_bin_edge(minimum),
                "start": minimum,
                "end": maximum,
                "center": minimum,
                "count": len(values),
            }
        ]
    width = (maximum - minimum) / bin_count
    counts = [0] * bin_count
    for value in values:
        index = min(int((value - minimum) / width), bin_count - 1)
        counts[index] += 1
    return [
        {
            "start": minimum + index * width,
            "end": minimum + (index + 1) * width,
            "center": minimum + (index + 0.5) * width,
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
