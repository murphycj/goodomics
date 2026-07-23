"""Execute saved Goodomics insights and reports.

This module is the server-side bridge between declarative insight/report
configuration and rendered dashboard/report payloads. It normalizes saved JSON
configs, compiles safe SQL against either the SQL metadata store or DuckDB
analytics store, caches computed results, and translates rows into
chart/table/metric payloads.

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
from goodomics.server.db.metadata import METADATA_MODELS
from goodomics.server.db.models import (
    InsightRecord,
    InsightResultCacheRecord,
    ReportRecord,
    ReportResultCacheRecord,
)
from goodomics.server.insight_capabilities import (
    ALL_ROWS_INLINE_THRESHOLD,
    ANALYSIS_GRAINS,
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
from goodomics.server.result_resolution import SampleSelection, resolve_contract_results
from goodomics.storage.duckdb import (
    INTEGER_KEYED_TABLES,
    SERIALIZERS_BY_TABLE,
    DuckDBAnalyticsStore,
)
from goodomics.storage.sqlalchemy import (
    DataContractFieldRecord,
    DataContractRecord,
    ProjectRecord,
    RunContractRecord,
    RunContractSampleRecord,
    RunRecord,
    RunSampleRecord,
    SampleGroupMemberRecord,
    SampleGroupRecord,
    SampleRecord,
)

JsonObject = dict[str, Any]
StoreName = Literal["metadata", "analytics"]

# Builder queries intentionally support a tiny aggregation/operator vocabulary.
# Advanced SQL exists as an escape hatch, but the default UI/API path stays
# constrained and easy to validate.
AGGREGATIONS = {"count", "count_distinct", "sum", "avg", "min", "max"}
RESULT_FORMAT_VERSION = 6
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
    normalized.pop("name", None)
    normalized.pop("description", None)
    normalized.pop("context", None)
    normalized.setdefault("version", 1)
    normalized["analysis_grain"] = _normalize_analysis_grain(
        normalized.get("analysis_grain")
    )
    normalized.pop("mode", None)
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
        "capabilities_version": 1,
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


def _normalize_analysis_grain(value: Any) -> str:
    """Return a supported public analysis grain, defaulting to sample."""
    grain = str(value or "sample")
    return grain if grain in ANALYSIS_GRAINS else "sample"


async def execute_insight(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    insight: InsightRecord | None = None,
    config: Mapping[str, Any] | None = None,
    name: str | None = None,
    description: str | None = None,
    refresh: bool = False,
    persist_results: bool = True,
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
    result_name = name or (insight.name if insight is not None else "Untitled insight")
    result_description = description
    if result_description is None and insight is not None:
        result_description = insight.description
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
        {
            "config": insight_config,
            "name": result_name,
            "description": result_description,
            "project_id": project_id,
            "result_format_version": RESULT_FORMAT_VERSION,
            "source": source,
        }
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
    rows = await _decorate_identity_values(
        session=session,
        columns=columns,
        rows=rows,
    )
    policy_rows, policy_summary = _apply_result_policy(
        config=insight_config,
        columns=columns,
        rows=rows,
        analytics_store=analytics_store,
    )
    result = compile_insight_result(
        config=insight_config,
        name=result_name,
        description=result_description,
        columns=columns,
        rows=policy_rows,
        insight_id=insight_id,
        computed_at=datetime.now(UTC),
        cached=False,
        result_policy_summary=policy_summary,
    )
    cache_id = f"insight_cache_{uuid4().hex}"
    if persist_results:
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
    persist_results: bool = True,
) -> JsonObject:
    """Execute a saved report by executing its referenced insights."""

    report_config = normalize_report_config(report.config)
    report_id = report.report_id
    report_name = report.name
    report_description = report.description
    effective_insight_configs = [
        _inherit_report_config(insight.config, report_config) for insight in insights
    ]
    spec_hash = canonical_hash(
        {
            "report": report_config,
            "insights": effective_insight_configs,
            "project_id": project_id,
            "result_format_version": RESULT_FORMAT_VERSION,
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
            persist_results=persist_results,
        )
        for insight, config in zip(insights, effective_insight_configs, strict=True)
    ]
    result = {
        **report_config,
        "kind": "report_result",
        "report_id": report_id,
        "name": report_name,
        "description": report_description,
        "insights": insight_results,
        "computed_at": datetime.now(UTC).isoformat(),
        "cached": False,
    }
    cache_id = f"report_cache_{uuid4().hex}"
    if persist_results:
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


def _inherit_report_config(
    insight_config: Mapping[str, Any], report_config: Mapping[str, Any]
) -> JsonObject:
    """Apply report-level filters, linkers, and policies to an insight."""
    inherited = dict(insight_config)
    for key in ("linker", "result_policy"):
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

    Contract-first queries are preferred because they use Goodomics semantic data
    contracts. Generic table queries and read-only SQL are supported as escape
    hatches.
    """

    query_config = _query_config(config)
    if not _is_table_preview_config(config):
        series_query = await _execute_contract_series_query(
            session=session,
            analytics_store=analytics_store,
            project_id=project_id,
            config=config,
        )
        if series_query is not None:
            return series_query
    contract_query = await _compile_contract_query(
        session=session,
        project_id=project_id,
        query_config=query_config,
        config=config,
    )
    if contract_query is not None:
        sql, parameters, columns = contract_query
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
        return await _execute_metadata_sql(session, sql, limit=limit)
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
    return await _execute_metadata_sql(session, sql, parameters=parameters, limit=limit)


async def _decorate_identity_values(
    *,
    session: AsyncSession,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> list[JsonObject]:
    """Replace internal identity primary keys with display labels in result rows."""
    if not rows:
        return [dict(row) for row in rows]
    decorated = [dict(row) for row in rows]
    if "sample_id" in columns:
        sample_labels = await _sample_display_labels(
            session, _integer_values(decorated, "sample_id")
        )
        _replace_column_values(decorated, "sample_id", sample_labels)
    if "run_id" in columns:
        run_labels = await _run_display_labels(
            session, _integer_values(decorated, "run_id")
        )
        _replace_column_values(decorated, "run_id", run_labels)
    if "run_sample_id" in columns:
        run_sample_labels = await _run_sample_display_labels(
            session, _integer_values(decorated, "run_sample_id")
        )
        _replace_column_values(decorated, "run_sample_id", run_sample_labels)
    return decorated


def _integer_values(rows: Sequence[Mapping[str, Any]], column: str) -> list[int]:
    """Collect unique integer values from a result column."""
    values: list[int] = []
    for row in rows:
        value = row.get(column)
        if isinstance(value, int) and not isinstance(value, bool):
            values.append(value)
    return list(dict.fromkeys(values))


def _replace_column_values(
    rows: list[JsonObject], column: str, labels: Mapping[int, str]
) -> None:
    """Replace integer result values with readable labels when available."""
    if not labels:
        return
    for row in rows:
        value = row.get(column)
        if isinstance(value, int) and value in labels:
            row[column] = labels[value]


async def _sample_display_labels(
    session: AsyncSession, sample_pks: Sequence[int]
) -> dict[int, str]:
    """Fetch readable labels for sample primary keys."""
    if not sample_pks:
        return {}
    rows = (
        await session.exec(
            select(SampleRecord).where(cast(Any, SampleRecord.id).in_(sample_pks))
        )
    ).all()
    return {
        int(row.id): row.sample_name or row.sample_id
        for row in rows
        if row.id is not None
    }


async def _run_display_labels(
    session: AsyncSession, run_pks: Sequence[int]
) -> dict[int, str]:
    """Fetch readable labels for run primary keys."""
    if not run_pks:
        return {}
    rows = (
        await session.exec(
            select(RunRecord).where(cast(Any, RunRecord.id).in_(run_pks))
        )
    ).all()
    return {int(row.id): row.name or row.run_id for row in rows if row.id is not None}


async def _run_sample_display_labels(
    session: AsyncSession, run_sample_pks: Sequence[int]
) -> dict[int, str]:
    """Build readable labels for run/sample linker primary keys."""
    if not run_sample_pks:
        return {}
    links = (
        await session.exec(
            select(RunSampleRecord).where(
                cast(Any, RunSampleRecord.id).in_(run_sample_pks)
            )
        )
    ).all()
    sample_labels = await _sample_display_labels(
        session,
        [int(link.sample_id) for link in links if link.sample_id is not None],
    )
    run_labels = await _run_display_labels(
        session,
        [int(link.run_id) for link in links if link.run_id is not None],
    )
    labels: dict[int, str] = {}
    for link in links:
        if link.id is None:
            continue
        sample_label = sample_labels.get(int(link.sample_id or 0))
        run_label = run_labels.get(int(link.run_id or 0))
        if sample_label and run_label:
            labels[int(link.id)] = f"{sample_label} · {run_label}"
        else:
            labels[int(link.id)] = link.run_sample_id
    return labels


async def _execute_contract_series_query(
    *,
    session: AsyncSession,
    analytics_store: DuckDBAnalyticsStore,
    project_id: str | None,
    config: Mapping[str, Any],
) -> tuple[list[str], list[JsonObject]] | None:
    """Run configured contract series and align them for chart output.

    Grain-first configs put contract identity on each value so different
    contracts can be aligned by sample/run_sample/feature without exposing a
    raw SQL join to the dashboard or future AI tooling.
    """
    series_items = _contract_series_items(config)
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
    linker = await _resolve_contract_series_linker(
        session=session,
        project_id=project_id,
        config=config,
        series_items=series_items,
    )
    series_rows: list[list[JsonObject]] = []
    selection_diagnostics: list[JsonObject] = []
    for series_item, alias in zip(series_items, aliases, strict=True):
        sql, parameters = await _contract_series_sql(
            session=session,
            project_id=project_id,
            config=config,
            series_item=series_item,
            alias=alias,
            linker_column=linker.get("column"),
        )
        _, rows = analytics_store.query_rows(sql, parameters=parameters, limit=limit)
        series_rows.append(rows)
        runtime_diagnostics = _runtime_metadata(config).get(
            "result_selection_diagnostics"
        )
        if isinstance(runtime_diagnostics, list) and runtime_diagnostics:
            selection_diagnostics = runtime_diagnostics
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
            "result_selection_diagnostics": selection_diagnostics,
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
    """Run raw numeric series queries and bin them into histogram rows."""
    series_rows: list[list[JsonObject]] = []
    for series_item, alias in zip(series_items, aliases, strict=True):
        sql, parameters = await _contract_series_sql(
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
    """Count rows for a single categorical series without linker alignment."""
    alias = "count"
    contract = await _series_contract(session, project_id, series_item)
    field_id = _series_field_id(series_item)
    field = await _series_field_record(
        session=session,
        contract=contract,
        field_id=field_id,
    )
    table = _series_table(contract, field, field_id)
    value_column = await _series_value_column(
        session=session,
        contract=contract,
        table=table,
        field_id=field_id,
        field=field,
    )
    source = _series_source_sql(table)
    columns = _columns_for_source("analytics", table)
    parameters: list[Any] = [_record_pk(contract)]
    where_parts = ["data_contract_id = ?"]
    where_parts.extend(
        await _resolved_result_where_sql(
            session=session,
            project_id=project_id,
            config=config,
            series_item=series_item,
            contract=contract,
            columns=columns,
            parameters=parameters,
        )
    )
    if field is not None and "field_id" in columns:
        where_parts.append(_field_id_match_sql(parameters, field))
    where_parts.extend(
        _series_filters_sql(
            table=table,
            contract_pk=_record_pk(contract),
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


async def _contract_series_sql(
    *,
    session: AsyncSession,
    project_id: str | None,
    config: Mapping[str, Any],
    series_item: Mapping[str, Any],
    alias: str,
    linker_column: str | None,
) -> tuple[str, list[Any]]:
    """Compile one chart series into SQL and bound parameters."""
    contract = await _series_contract(session, project_id, series_item)
    field_id = _series_field_id(series_item)
    field = await _series_field_record(
        session=session,
        contract=contract,
        field_id=field_id,
    )
    table = _series_table(contract, field, field_id)
    value_column = await _series_value_column(
        session=session,
        contract=contract,
        table=table,
        field_id=field_id,
        field=field,
    )
    source = _series_source_sql(table)
    columns = _columns_for_source("analytics", table)
    select_parts = []
    if linker_column is not None:
        _require_column(columns, linker_column)
        select_parts.append(f"{_quote_identifier(linker_column)} AS __linker")
    aggregation = _series_aggregation(series_item)
    value_expression = _quote_identifier(value_column)
    if aggregation is None:
        select_parts.append(f"{value_expression} AS {_quote_identifier(alias)}")
    else:
        select_parts.append(
            f"{_aggregation_sql(aggregation, value_expression)} "
            f"AS {_quote_identifier(alias)}"
        )
    parameters: list[Any] = [_record_pk(contract)]
    where_parts = ["data_contract_id = ?"]
    where_parts.extend(
        await _resolved_result_where_sql(
            session=session,
            project_id=project_id,
            config=config,
            series_item=series_item,
            contract=contract,
            columns=columns,
            parameters=parameters,
        )
    )
    if field is not None and "field_id" in columns:
        where_parts.append(_field_id_match_sql(parameters, field))
    where_parts.extend(
        _series_filters_sql(
            table=table,
            contract_pk=_record_pk(contract),
            columns=columns,
            filters=_combined_filters(config, series_item),
            parameters=parameters,
        )
    )
    group_by = " GROUP BY __linker" if linker_column is not None and aggregation else ""
    order = "__linker" if linker_column is not None else _quote_identifier(alias)
    sql = (
        f"SELECT {', '.join(select_parts)} FROM {source} "
        f"WHERE {' AND '.join(where_parts)}{group_by} ORDER BY {order}"
    )
    return sql, parameters


async def _resolved_result_where_sql(
    *,
    session: AsyncSession,
    project_id: str | None,
    config: Mapping[str, Any],
    series_item: Mapping[str, Any],
    contract: DataContractRecord,
    columns: Sequence[str],
    parameters: list[Any],
) -> list[str]:
    """Resolve and constrain one series to exact produced-result occurrences."""

    sample_selections = await _resolve_sample_selections(
        session=session, project_id=project_id, config=config
    )
    if "run_contract_id" not in columns:
        return _sample_selection_where_sql(
            selections=sample_selections,
            columns=columns,
            parameters=parameters,
        )
    raw_scope = series_item.get("result_scope")
    result_scope = raw_scope if isinstance(raw_scope, Mapping) else {}
    resolution = await resolve_contract_results(
        session=session,
        project_id=project_id,
        contract=contract,
        analysis_grain=_normalize_analysis_grain(config.get("analysis_grain")),
        result_scope=result_scope,
        sample_selections=sample_selections,
    )
    diagnostics = _runtime_metadata(config).get("result_selection_diagnostics")
    collected = list(diagnostics) if isinstance(diagnostics, list) else []
    collected.append(
        {
            "series_id": series_item.get("id") or series_item.get("label"),
            **resolution.diagnostics,
        }
    )
    _set_runtime_metadata(config, {"result_selection_diagnostics": collected})
    if not resolution.run_contract_pks:
        return ["1 = 0"]
    parameters.extend(resolution.run_contract_pks)
    clauses = [
        f"run_contract_id IN ({', '.join('?' for _ in resolution.run_contract_pks)})"
    ]
    if (
        _normalize_analysis_grain(config.get("analysis_grain")) != "run"
        and "run_sample_id" in columns
    ):
        if not resolution.run_sample_pks:
            return ["1 = 0"]
        parameters.extend(resolution.run_sample_pks)
        clauses.append(
            f"run_sample_id IN ({', '.join('?' for _ in resolution.run_sample_pks)})"
        )
    return clauses


async def _series_contract(
    session: AsyncSession,
    project_id: str | None,
    series_item: Mapping[str, Any],
) -> DataContractRecord:
    """Resolve the data contract record referenced by a series config."""
    contract_id = _series_contract_id(series_item)
    if not contract_id:
        raise ValueError("Contract series require a data_contract_id.")
    contract = await _get_contract_record(session, project_id, contract_id)
    if contract is None:
        raise ValueError(f"Unknown data contract: {contract_id}")
    return contract


def _series_table(
    contract: DataContractRecord,
    field: DataContractFieldRecord | None,
    field_id: str,
) -> str:
    """Choose the physical analytics table for a series."""
    if field is not None:
        table = _field_primary_table(field)
    else:
        table = _default_contract_table(contract)
        if field_id and field_id not in _synthetic_contract_fields(table).get(
            table or "", {}
        ):
            raise ValueError(f"Unknown contract field: {field_id}")
    if table not in {
        "sample_metrics",
        "entity_attributes",
        "feature_value_numeric",
        "feature_call",
        "copy_number_segments",
        "sample_variant_calls",
        "sample_structural_variant_calls",
        "result_payloads",
        "gene_alteration_state",
    }:
        raise ValueError(
            f"Contract series are not available for table: {table or 'unknown'}"
        )
    return table


def _field_primary_table(field: DataContractFieldRecord) -> str | None:
    """Read the primary analytics table declared for a contract field."""
    query_table = field.query_ref_json.get("table")
    if isinstance(query_table, str) and query_table:
        return query_table
    return field.primary_table


def _default_contract_table(contract: DataContractRecord) -> str | None:
    """Read the default analytics table declared by a data contract."""
    return {
        "entity_attributes": "entity_attributes",
        "feature_matrix": "feature_value_numeric",
        "feature_calls": "feature_call",
        "copy_number_segments": "copy_number_segments",
        "small_variants": "sample_variant_calls",
        "structural_variants": "sample_structural_variant_calls",
        "result_payload": "result_payloads",
    }.get(contract.data_type)


async def _series_value_column(
    *,
    session: AsyncSession,
    contract: DataContractRecord,
    table: str,
    field_id: str,
    field: DataContractFieldRecord | None,
) -> str:
    """Resolve the value column a series should read from."""
    synthetic = _synthetic_contract_fields(table).get(table, {})
    if field_id in synthetic:
        return synthetic[field_id]
    if table == "feature_value_numeric":
        return "value"
    if table in {"sample_metrics", "entity_attributes", "result_payloads"}:
        if not field_id:
            raise ValueError(
                "Metric, attribute, and result payload contract series require "
                "a field_id."
            )
        if field is None:
            raise ValueError(f"Unknown contract field: {field_id}")
        return _contract_value_column(field)
    fallback = {
        "feature_call": "call_rank",
        "copy_number_segments": "segment_mean",
        "sample_variant_calls": "allele_fraction",
        "sample_structural_variant_calls": "split_read_count",
        "result_payloads": "data_json",
        "gene_alteration_state": "value_numeric",
    }.get(table)
    if fallback is None:
        raise ValueError(f"No default value column for contract table: {table}")
    return fallback


async def _series_field_record(
    *,
    session: AsyncSession,
    contract: DataContractRecord,
    field_id: str,
) -> DataContractFieldRecord | None:
    """Resolve the optional contract field record for a series."""
    if not field_id:
        return None
    rows = await _get_contract_field_records(
        session, contract_id=_record_pk(contract), field_ids=[field_id]
    )
    field = rows.get(field_id)
    return field


async def _resolve_contract_series_linker(
    *,
    session: AsyncSession,
    project_id: str | None,
    config: Mapping[str, Any],
    series_items: Sequence[Mapping[str, Any]],
) -> JsonObject:
    """Choose the linker column used to align multiple contract series."""
    column_sets = []
    for series_item in series_items:
        contract = await _series_contract(session, project_id, series_item)
        field_id = _series_field_id(series_item)
        field = await _series_field_record(
            session=session,
            contract=contract,
            field_id=field_id,
        )
        table = _series_table(contract, field, field_id)
        column_sets.append(set(_columns_for_source("analytics", table)))
    valid = [
        linker_id
        for linker_id in ("sample", "feature", "run", "entity")
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
    """Return whether a visualization requires aligned series rows."""
    rule = chart_rule(chart)
    requirement = rule.get("requires_linker")
    if requirement is True:
        return True
    if requirement == "multi_series":
        return len(series_items) > 1
    if requirement == "multi_numeric":
        return len(series_items) > 1
    if requirement == "comparison":
        return len(series_items) > 1
    return False


async def _resolve_sample_selections(
    *,
    session: AsyncSession,
    project_id: str | None,
    config: Mapping[str, Any],
) -> list[SampleSelection]:
    """Resolve each top-level semantic sample filter to internal identities."""

    filters = config.get("filters")
    if not isinstance(filters, Sequence) or isinstance(filters, str):
        return []
    selections: list[SampleSelection] = []
    for filter_config in filters:
        if not _is_semantic_sample_filter(filter_config):
            continue
        operator = str(filter_config.get("operator") or filter_config.get("op") or "")
        if operator != "in":
            raise ValueError("The sample filter requires operator: in.")
        raw_values = filter_config.get("value")
        if not isinstance(raw_values, Sequence) or isinstance(raw_values, str):
            raise ValueError(
                "The sample filter value must be a list of sample references."
            )
        sample_pks: set[int] = set()
        run_sample_pks: set[int] = set()
        for raw_value in raw_values:
            if not isinstance(raw_value, Mapping):
                raise ValueError("Each sample filter value must be an object.")
            kind = str(raw_value.get("kind") or "")
            public_id = str(raw_value.get("id") or "").strip()
            if not public_id:
                raise ValueError("Each sample filter value requires an id.")
            if kind == "sample":
                sample_pk = await _sample_pk(session, project_id, public_id)
                if sample_pk is not None:
                    sample_pks.add(int(sample_pk))
            elif kind == "sample_group":
                run_sample_pks.update(
                    await _sample_group_run_sample_pks(session, project_id, public_id)
                )
            else:
                raise ValueError(
                    "Sample filter kinds must be sample or sample_group."
                )
        selections.append(
            SampleSelection(
                sample_pks=frozenset(sample_pks),
                run_sample_pks=frozenset(run_sample_pks),
            )
        )
    return selections


def _sample_selection_where_sql(
    *,
    selections: Sequence[SampleSelection],
    columns: Sequence[str],
    parameters: list[Any],
) -> list[str]:
    """Compile resolved semantic sample clauses for an integer-keyed source."""

    clauses: list[str] = []
    for selection in selections:
        alternatives: list[str] = []
        if selection.sample_pks and "sample_id" in columns:
            values = sorted(selection.sample_pks)
            parameters.extend(values)
            alternatives.append(
                f"sample_id IN ({', '.join('?' for _ in values)})"
            )
        if selection.run_sample_pks and "run_sample_id" in columns:
            values = sorted(selection.run_sample_pks)
            parameters.extend(values)
            alternatives.append(
                f"run_sample_id IN ({', '.join('?' for _ in values)})"
            )
        clauses.append(f"({' OR '.join(alternatives)})" if alternatives else "1 = 0")
    return clauses


def _is_semantic_sample_filter(filter_config: Any) -> TypeGuard[Mapping[str, Any]]:
    """Return whether a top-level filter is the semantic sample selector."""

    return isinstance(filter_config, Mapping) and filter_config.get("field") == "sample"


def _series_filters_sql(
    *,
    table: str,
    contract_pk: int,
    columns: Sequence[str],
    filters: Sequence[Any],
    parameters: list[Any],
) -> list[str]:
    """Compile filters attached to an individual series."""
    where_parts: list[str] = []
    for filter_config in filters:
        normalized = _normalize_series_filter(filter_config)
        if normalized is None:
            continue
        if table == "sample_variant_calls" and normalized["field"] == "feature_id":
            where_parts.append(
                _variant_feature_filter_sql(normalized, contract_pk, parameters)
            )
            continue
        where_parts.append(_filter_sql(columns, normalized, parameters))
    return where_parts


def _variant_feature_filter_sql(
    filter_config: Mapping[str, Any], contract_pk: int, parameters: list[Any]
) -> str:
    """Compile feature filters against variant-oriented analytical tables."""
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
        parameters.extend([contract_pk, *values])
        return (
            "variant_id IN ("
            f"SELECT variant_id FROM {annotation_source} "
            "WHERE data_contract_id = ? "
            f"AND feature_id IN ({', '.join('?' for _ in values)})"
            ")"
        )
    parameters.extend([contract_pk, value])
    return (
        "variant_id IN ("
        f"SELECT variant_id FROM {annotation_source} "
        "WHERE data_contract_id = ? AND feature_id = ?"
        ")"
    )


def _normalize_series_filter(filter_config: Any) -> JsonObject | None:
    """Normalize a raw filter config into a validated filter shape."""
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
    """Merge global insight filters with per-series filters."""
    filters: list[Any] = []
    for value in (
        _physical_global_filters(config),
        series_item.get("filters"),
    ):
        if isinstance(value, Sequence) and not isinstance(value, str):
            filters.extend(value)
    return filters


def _physical_global_filters(config: Mapping[str, Any]) -> list[Any]:
    """Return global filters that map directly to source-table fields."""

    filters = config.get("filters")
    if not isinstance(filters, Sequence) or isinstance(filters, str):
        return []
    return [item for item in filters if not _is_semantic_sample_filter(item)]


def _align_series_rows(
    *,
    aliases: Sequence[str],
    linker_column: str | None,
    linker_kind: str,
    series_rows: Sequence[Sequence[Mapping[str, Any]]],
) -> tuple[list[str], list[JsonObject], JsonObject]:
    """Align multiple series result sets by linker and report diagnostics."""
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
    """Summarize matched, unmatched, and duplicate linker behavior."""
    return {
        "linker": linker_kind,
        "matched_count": matched,
        "unmatched_count": unmatched,
        "duplicate_conflict_count": duplicate_conflicts,
        "rows_excluded": rows_excluded,
    }


def _contract_series_items(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return contract-backed series configs from an insight config."""
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
        if _series_contract_id(item) and _series_field_id(item)
    ]
    return items


def _series_contract_id(series_item: Mapping[str, Any]) -> str:
    """Read the contract ID from a series config."""
    source = series_item.get("source")
    if isinstance(source, Mapping):
        value = source.get("data_contract_id") or source.get("id")
        if isinstance(value, str):
            return value
    value = (
        series_item.get("contract_id")
        or series_item.get("data_contract_id")
        or series_item.get("contractId")
    )
    return str(value) if isinstance(value, str) else ""


def _series_field_id(series_item: Mapping[str, Any]) -> str:
    """Read the field ID from a series config."""
    value = (
        series_item.get("field_id")
        or series_item.get("field")
        or series_item.get("fieldId")
        or series_item.get("value")
    )
    return str(value) if isinstance(value, str) else ""


def _series_aggregation(series_item: Mapping[str, Any]) -> str | None:
    """Normalize the aggregation requested by a series config."""
    value = str(
        series_item.get("aggregation")
        or series_item.get("aggregate")
        or series_item.get("show")
        or "raw"
    )
    if value in {"", "raw", "none", "value", "values"}:
        return None
    if value == "average":
        value = "avg"
    if value == "count_rows":
        value = "count"
    if value not in AGGREGATIONS:
        raise ValueError(f"Unsupported aggregation: {value}")
    return value


def _aggregation_sql(aggregation: str, expression: str) -> str:
    """Render an aggregation function for a SQL expression."""
    if aggregation == "count_distinct":
        return f"COUNT(DISTINCT {expression})"
    if aggregation == "count":
        return "COUNT(*)"
    return f"{aggregation.upper()}({expression})"


def _series_aliases(series_items: Sequence[Mapping[str, Any]]) -> list[str]:
    """Create stable, unique output aliases for series values."""
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
    """Render a table reference for readable source SQL."""
    integer_table = INTEGER_KEYED_TABLES.get(table)
    if integer_table is None:
        return _quote_identifier(table)
    return f"({integer_table.readable_select_sql()})"


def _series_source_sql(table: str) -> str:
    """Render a table reference for series SQL."""
    if table in {"sample_metrics", "entity_attributes"}:
        return _quote_identifier(table)
    return _readable_source_sql(table)


def _set_runtime_metadata(
    config: Mapping[str, Any], metadata: Mapping[str, Any]
) -> None:
    """Attach transient execution metadata to a normalized config copy."""
    if isinstance(config, dict):
        runtime = config.setdefault("_runtime", {})
        if isinstance(runtime, dict):
            runtime.update(metadata)


def _runtime_metadata(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return transient execution metadata from a config."""
    runtime = config.get("_runtime")
    return runtime if isinstance(runtime, Mapping) else {}


async def _sample_pk(
    session: AsyncSession, project_id: str | None, sample_id: str
) -> int | None:
    """Resolve a sample public ID to its internal primary key."""
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
    """Resolve a run/sample public ID to its internal primary key."""
    statement = select(RunSampleRecord).where(
        RunSampleRecord.run_sample_id == run_sample_id
    )
    if project_id is not None:
        statement = statement.join(
            RunRecord, cast(Any, RunRecord.id) == RunSampleRecord.run_id
        ).where(RunRecord.project_id == await _project_pk(session, project_id))
    row = (await session.exec(statement)).first()
    return row.id if row is not None else None


async def _sample_group_run_sample_pks(
    session: AsyncSession, project_id: str | None, sample_group_id: str
) -> list[int]:
    """Resolve a sample group to member run/sample primary keys."""
    statement = select(SampleGroupRecord).where(
        SampleGroupRecord.sample_group_id == sample_group_id
    )
    if project_id is not None:
        statement = statement.where(
            SampleGroupRecord.project_id == await _project_pk(session, project_id)
        )
    sample_group = (await session.exec(statement)).first()
    if sample_group is None or sample_group.id is None:
        return []
    rows = (
        await session.exec(
            select(SampleGroupMemberRecord.run_sample_id).where(
                SampleGroupMemberRecord.sample_group_id == sample_group.id
            )
        )
    ).all()
    return [int(row) for row in rows]


async def _compile_contract_query(
    *,
    session: AsyncSession,
    project_id: str | None,
    query_config: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[str, list[Any], list[str]] | None:
    """Compile a contract-backed table or metric query.

    Contract queries start from a stable semantic data_contract_id, then use
    the selected field to choose the physical analytical table.
    """
    source = query_config.get("source")
    if not isinstance(source, Mapping) or source.get("kind") != "data_contract":
        return None

    contract_public_id = str(
        source.get("data_contract_id")
        or source.get("id")
        or query_config.get("data_contract_id")
        or ""
    )

    if not contract_public_id:
        raise ValueError("Contract queries require source.data_contract_id.")

    contract = await _get_contract_record(session, project_id, contract_public_id)

    if contract is None:
        raise ValueError(f"Unknown data contract: {contract_public_id}")

    requested_fields = _contract_requested_fields(query_config, config)
    field_rows: dict[str, DataContractFieldRecord] = {}
    table: str | None = None

    if requested_fields:
        field_rows = await _get_contract_field_records(
            session,
            contract_id=_record_pk(contract),
            field_ids=requested_fields,
        )
        if any(field_id not in field_rows for field_id in requested_fields):
            # The dashboard often sends safe aliases for fields with punctuation.
            # If direct lookup misses, load all fields and map aliases back to
            # canonical field IDs.
            field_rows = await _get_all_contract_field_records(
                session,
                contract_id=_record_pk(contract),
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
            table = _default_contract_table(contract)
            synthetic_fields = _synthetic_contract_fields(table).get(table or "", {})
            if not all(field_id in synthetic_fields for field_id in requested_fields):
                raise ValueError(f"Unknown contract field(s): {', '.join(missing)}")
        else:
            field_tables = {
                _field_primary_table(field_rows[field_id])
                for field_id in requested_fields
            }
            if (
                _is_table_preview_config(config)
                and len(requested_fields) > 1
                and not _measures(query_config, config)
            ):
                return await _compile_mixed_contract_table_query(
                    session=session,
                    project_id=project_id,
                    contract=contract,
                    query_config=query_config,
                    config=config,
                    requested_fields=requested_fields,
                    field_rows=field_rows,
                )
            if len(field_tables) != 1:
                raise ValueError(
                    "Contract queries cannot mix fields from different analytical "
                    "tables in one series."
                )
            table = next(iter(field_tables))
    else:
        table = _default_contract_table(contract)

    if table not in {
        "sample_metrics",
        "entity_attributes",
        "feature_value_numeric",
        "feature_call",
        "copy_number_segments",
        "sample_variant_calls",
        "sample_structural_variant_calls",
        "result_payloads",
    }:
        raise ValueError(
            f"Contract-first queries are not available for table: {table or 'unknown'}"
        )

    synthetic_fields = _synthetic_contract_fields(table)

    # Some analytical tables expose meaningful columns directly instead of
    # metadata-backed data_contract_fields rows. Treat those as synthetic fields so
    # users can still query them through the same contract-first grammar.
    if table in {"feature_value_numeric", *synthetic_fields} and not requested_fields:
        requested_fields = [next(iter(synthetic_fields.get(table, {"value": "value"})))]

    if not requested_fields:
        raise ValueError("Contract queries require at least one field or measure.")

    if table == "feature_value_numeric":
        # Feature matrices store the measured value in a single canonical value
        # column; the contract field supplies its semantic public name while the
        # feature dimension carries the biological identity.
        field = None
        field_id = requested_fields[0]
        declared_field = field_rows.get(field_id)
        value_column = (
            _contract_value_column(declared_field)
            if declared_field is not None
            else "value"
        )
    elif table in synthetic_fields:
        requested_fields = _normalize_synthetic_requested_fields(
            requested_fields,
            synthetic_fields[table],
        )
        field = None
        field_id = requested_fields[0]
        value_column = synthetic_fields[table][field_id]
    else:
        field = field_rows[requested_fields[0]]
        field_id = field.field_id
        value_column = _contract_value_column(field)

    field_alias = _safe_alias(field_id, fallback="value")
    dimensions = _string_list(
        query_config.get("dimensions") or query_config.get("group_by")
    )
    entity_grain = str(
        query_config.get("entity") or config.get("analysis_grain") or "sample"
    )
    if not dimensions:
        # Entity grain provides sensible default dimensions. A run_sample insight
        # should naturally group by sample/run link unless the config says
        # otherwise.
        if entity_grain == "sample" and table == "sample_metrics":
            dimensions = ["sample_id"]
        elif table == "entity_attributes":
            dimensions = ["entity_id"]
        elif table != "result_payloads":
            dimensions = ["sample_id"]

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
        identity_dimensions = [
            dimension for dimension in dimensions if dimension in columns
        ]
        if not identity_dimensions:
            identity_dimensions = [
                ("sample_id" if table == "sample_metrics" else "entity_id")
            ]
        parameters: list[Any] = []
        select_parts = [
            f"{_quote_identifier(dimension)} AS {_quote_identifier(dimension)}"
            for dimension in identity_dimensions
        ]
        for requested_field in requested_fields:
            row = field_rows[requested_field]
            value_column = _contract_value_column(row)
            alias = _safe_alias(row.field_id, fallback="value")
            # Each field is stored as its own row in sample_metrics. CASE/MAX
            # pivots those sparse rows into a compact entity-wide row.
            select_parts.append(
                "MAX(CASE WHEN "
                f"{_field_id_match_sql(parameters, row)} "
                f"THEN {_quote_identifier(value_column)} END) "
                f"AS {_quote_identifier(alias)}"
            )
        parameters.append(_record_pk(contract))
        field_predicates = [
            _field_id_match_sql(parameters, field_rows[field_id])
            for field_id in requested_fields
        ]
        result_where = await _resolved_result_where_sql(
            session=session,
            project_id=project_id,
            config=config,
            series_item={
                "id": "table",
                "result_scope": _table_result_scope(config, query_config),
            },
            contract=contract,
            columns=columns,
            parameters=parameters,
        )
        group_columns = ", ".join(
            _quote_identifier(item) for item in identity_dimensions
        )
        sql = (
            f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(table)} "
            f"WHERE data_contract_id = ? AND ({' OR '.join(field_predicates)}) "
            f"{'AND ' + ' AND '.join(result_where) + ' ' if result_where else ''}"
            f"GROUP BY {group_columns}"
        )
        output_columns = [
            *identity_dimensions,
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
            # dimension, for example counting categorical values in a contract.
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
            f"{_aggregation_sql(aggregation, expression)} AS {_quote_identifier(alias)}"
        )
        exposed_columns.add(alias)

    if requested_fields and not measures and len(requested_fields) == 1:
        select_parts.append(
            f"{_quote_identifier(value_column)} AS {_quote_identifier(field_alias)}"
        )
        exposed_columns.add(field_alias)
        group_parts = []

    if not select_parts:
        # Without explicit dimensions or measures, return raw values with the
        # contract's natural entity dimensions.
        default_dimensions = _default_contract_dimensions(table)
        for column in default_dimensions:
            if column in columns:
                select_parts.append(
                    f"{_quote_identifier(column)} AS {_quote_identifier(column)}"
                )
        select_parts.append(
            f"{_quote_identifier(value_column)} AS {_quote_identifier(field_alias)}"
        )
        exposed_columns.add(field_alias)

    parameters: list[Any] = [_record_pk(contract)]
    where_parts = ["data_contract_id = ?"]
    where_parts.extend(
        await _resolved_result_where_sql(
            session=session,
            project_id=project_id,
            config=config,
            series_item={
                "id": "table",
                "result_scope": _table_result_scope(config, query_config),
            },
            contract=contract,
            columns=columns,
            parameters=parameters,
        )
    )
    if field is not None:
        where_parts.append(_field_id_match_sql(parameters, field))
    for filter_config in _physical_global_filters(config):
        where_parts.append(
            _contract_filter_sql(
                columns=columns,
                value_column=value_column,
                field_aliases={field_id, field_alias, "value"},
                filter_config=filter_config,
                parameters=parameters,
            )
        )

    sql = f"SELECT {', '.join(select_parts)} FROM {_series_source_sql(table)}"
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


def _table_result_scope(
    config: Mapping[str, Any], query_config: Mapping[str, Any]
) -> Mapping[str, Any]:
    direct = query_config.get("result_scope")
    if isinstance(direct, Mapping):
        return direct
    for item in _table_column_items(config):
        value = item.get("result_scope")
        if isinstance(value, Mapping):
            return value
    return {}


async def _compile_mixed_contract_table_query(
    *,
    session: AsyncSession,
    project_id: str | None,
    contract: DataContractRecord,
    query_config: Mapping[str, Any],
    config: Mapping[str, Any],
    requested_fields: Sequence[str],
    field_rows: Mapping[str, DataContractFieldRecord],
) -> tuple[str, list[Any], list[str]]:
    """Compile a wide table preview across compatible contract tables.

    Table previews are allowed to show several contract fields side by side,
    even when those fields are stored in different analytics tables. The rest
    of the contract query compiler usually assumes one source table; this
    helper takes the slower but more flexible path of normalizing each field
    into the same temporary shape and then pivoting that shape into columns.
    Longer-term, complex query planning may move toward materialized views or a
    Python planning layer.
    """
    dimensions = _string_list(
        query_config.get("dimensions") or query_config.get("group_by")
    )
    if not dimensions:
        # If the caller did not explicitly pick dimensions, choose the natural
        # identity columns for the requested analysis grain. These become the
        # row keys used to align fields from different tables.
        dimensions = identity_dimensions_for_contract_table(config)
    if not dimensions:
        # Keep a final defensive fallback so table previews still have stable
        # row keys if an older or malformed config reaches this path.
        dimensions = ["sample_id"]

    parameters: list[Any] = []
    # Each union part selects one requested field from its physical source table.
    # All parts must expose the exact same columns so DuckDB can UNION them.
    union_parts: list[str] = []
    # aliases are the final user-visible value column names. value_columns keeps
    # the physical value column for each alias so the final pivot knows which
    # normalized value bucket to read from.
    aliases: list[str] = []
    value_columns: list[str] = []
    used_aliases: set[str] = set()
    # Preserve dimension order while removing duplicates. The order matters
    # because it controls both the SQL SELECT list and the returned column list.
    dimension_set = list(dict.fromkeys(dimensions))

    for field_id in requested_fields:
        field = field_rows[field_id]
        table = _field_primary_table(field)
        # Mixed previews are intentionally limited to contract tables with
        # compatible identity columns and simple scalar/payload values. Feature
        # and variant tables need additional domain keys, so combining them here
        # would produce misleading rows.
        if table not in {"sample_metrics", "entity_attributes", "result_payloads"}:
            raise ValueError(
                f"Table previews cannot combine fields from table: {table or 'unknown'}"
            )
        columns = _columns_for_source("analytics", table)
        # Field IDs can contain punctuation or collide after alias sanitization.
        # The final result needs safe, unique column names for dashboard tables
        # and chart configs, so reserve the alias as soon as it is created.
        alias = _unique_alias(
            _safe_alias(field.field_id, fallback="value"), used_aliases
        )
        aliases.append(alias)
        value_column = _contract_value_column(field)
        value_columns.append(value_column)
        # Normalize dimensions across heterogeneous tables. If a source table
        # does not have a requested identity column, emit NULL for that column so
        # every SELECT in the UNION has the same schema.
        select_parts = [
            (
                f"{_quote_identifier(dimension)} AS {_quote_identifier(dimension)}"
                if dimension in columns
                else f"NULL AS {_quote_identifier(dimension)}"
            )
            for dimension in dimension_set
        ]
        # Store the logical field alias in each normalized row. The outer query
        # uses this marker in CASE expressions to pivot rows back into columns.
        parameters.append(alias)
        select_parts.append("? AS __field_alias")
        # Values can be physically stored in numeric, string, or JSON columns.
        # A UNION requires consistent column types, so expose three internal
        # buckets and populate only the bucket that matches this field.
        select_parts.append(
            f"{_quote_identifier(value_column)} AS __value_numeric"
            if value_column == "value_numeric"
            else "NULL::DOUBLE AS __value_numeric"
        )
        select_parts.append(
            f"{_quote_identifier(value_column)} AS __value_string"
            if value_column == "value_string"
            else "NULL::VARCHAR AS __value_string"
        )
        select_parts.append(
            f"CAST({_quote_identifier(value_column)} AS VARCHAR) AS __value_json"
            if value_column in {"value_json", "data_json"}
            else "NULL::VARCHAR AS __value_json"
        )
        # Keep the per-field SELECT scoped to this contract and this field. The
        # _field_id_match_sql call can append more bound parameters, so it must
        # receive the same parameters list used to execute the final query.
        parameters.append(_record_pk(contract))
        where_parts = ["data_contract_id = ?", _field_id_match_sql(parameters, field)]
        # Mixed previews use raw integer-keyed tables, so semantic sample filters
        # can be compiled directly against their identity columns.
        where_parts.extend(
            _sample_selection_where_sql(
                selections=await _resolve_sample_selections(
                    session=session, project_id=project_id, config=config
                ),
                columns=columns,
                parameters=parameters,
            )
        )
        # Add one normalized SELECT for this field. The final CTE is a vertical
        # list of "dimension keys + field alias + one value bucket" rows.
        union_parts.append(
            f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(table)} "
            f"WHERE {' AND '.join(where_parts)}"
        )

    # The outer query starts with the identity columns; these are both returned
    # to the caller and used as the GROUP BY key for the pivot.
    select_parts = [
        f"{_quote_identifier(dimension)} AS {_quote_identifier(dimension)}"
        for dimension in dimension_set
    ]
    for alias, value_column in zip(aliases, value_columns, strict=True):
        # Add one output column per requested field. The CASE expression selects
        # only rows for that field alias, and MAX collapses the normalized rows
        # down to a single value per identity key. This assumes one value per
        # field/key pair; if duplicates exist, MAX gives a deterministic preview.
        parameters.append(alias)
        source_column = (
            "__value_numeric"
            if value_column == "value_numeric"
            else "__value_string"
            if value_column == "value_string"
            else "__value_json"
        )
        select_parts.append(
            f"MAX(CASE WHEN __field_alias = ? THEN {source_column} END) "
            f"AS {_quote_identifier(alias)}"
        )
    group_columns = ", ".join(_quote_identifier(column) for column in dimension_set)
    # normalized_fields is deliberately a CTE instead of nested subqueries so the
    # generated SQL reads in two phases: gather compatible rows, then pivot them.
    sql = (
        "WITH normalized_fields AS ("
        f"{' UNION ALL '.join(union_parts)}"
        f") SELECT {', '.join(select_parts)} FROM normalized_fields"
    )
    if group_columns:
        # Ordering by the same identity key makes preview rows stable between
        # executions, which is helpful for saved insight diffs and UI tests.
        sql += f" GROUP BY {group_columns} ORDER BY {group_columns}"
    return sql, parameters, [*dimension_set, *aliases]


def _is_table_preview_config(config: Mapping[str, Any]) -> bool:
    """Return whether a config should use table-preview semantics."""
    visualization = str(config.get("visualization") or "table")
    if visualization == "table":
        return True
    return bool(_table_column_items(config)) and not _contract_series_items(config)


def identity_dimensions_for_contract_table(config: Mapping[str, Any]) -> list[str]:
    """Choose default identity columns for a table preview grain."""
    grain = _normalize_analysis_grain(config.get("analysis_grain"))
    if grain == "sample":
        return ["sample_id"]
    if grain == "subject":
        return ["entity_id", "sample_id"]
    if grain == "run":
        return ["run_id"]
    return ["sample_id"]


def _unique_alias(alias: str, used_aliases: set[str]) -> str:
    """Return an unused alias by appending a numeric suffix when needed."""
    candidate = alias
    index = 2
    while candidate in used_aliases:
        candidate = f"{alias}_{index}"
        index += 1
    used_aliases.add(candidate)
    return candidate


def compile_insight_result(
    *,
    config: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    insight_id: str | None,
    computed_at: datetime,
    cached: bool,
    name: str = "Untitled insight",
    description: str | None = None,
    result_policy_summary: Mapping[str, Any] | None = None,
) -> JsonObject:
    """Compile query rows into a dashboard/report insight payload."""

    visualization = str(config.get("visualization") or "table")
    row_dicts = [dict(row) for row in rows]
    column_labels = _result_column_labels(config, columns)
    plot_table = {
        "columns": list(columns),
        "column_labels": column_labels,
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
        "name": name,
        "description": description,
        "analysis_grain": _normalize_analysis_grain(config.get("analysis_grain")),
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
        "result_selection_diagnostics": runtime.get("result_selection_diagnostics", []),
        "visualization": visualization,
        "display": (
            config.get("display") if isinstance(config.get("display"), dict) else {}
        ),
        "columns": list(columns),
        "column_labels": column_labels,
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


def _result_column_labels(
    config: Mapping[str, Any], columns: Sequence[str]
) -> dict[str, str]:
    """Build display labels for result columns."""
    labels: dict[str, str] = {column: column for column in columns}
    for item in _table_column_items(config):
        raw_label = item.get("label") or item.get("name")
        if not isinstance(raw_label, str) or not raw_label.strip():
            continue
        label = raw_label.strip()
        aliases: list[str] = []
        for key in ("column", "field_id", "field"):
            raw_value = item.get(key)
            if isinstance(raw_value, str) and raw_value:
                aliases.extend([raw_value, _safe_alias(raw_value, fallback=raw_value)])
        for alias in aliases:
            if alias in columns:
                labels[alias] = label
    for column in columns:
        if column in IDENTITY_COLUMN_LABELS:
            labels[column] = _identity_column_label(column)
    return {column: labels[column] for column in columns}


IDENTITY_COLUMN_LABELS = {
    "run_sample_id": "Run sample",
    "sample_id": "Sample",
    "run_id": "Run",
    "entity_id": "Subject",
    "feature_id": "Feature",
    "source_file_id": "Source file",
}


def _identity_column_label(column: str) -> str:
    """Return a readable label for an identity column name."""
    return IDENTITY_COLUMN_LABELS.get(column, column.replace("_", " ").title())


def _apply_result_policy(
    *,
    config: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    analytics_store: DuckDBAnalyticsStore,
) -> tuple[list[JsonObject], JsonObject]:
    """Apply inline, sampling, and export policies to result rows."""
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
    """Write a full result payload to a file-backed plot artifact."""
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
    """Describe the result policy used for inline payloads."""
    policy = normalize_result_policy(config.get("result_policy"))
    return {
        **policy,
        "embedded_row_count": row_count,
        "source_row_count": row_count,
    }


def _validate_plot_result(
    config: Mapping[str, Any], columns: list[str], rows: list[JsonObject]
) -> None:
    """Validate that a result can satisfy the requested visualization."""
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
    """Choose numeric result columns that should become chart series."""
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
    """Choose the default x-axis field for a result table."""
    query = _query_config(config)
    dimensions = _string_list(query.get("dimensions") or query.get("group_by"))
    if query.get("x") is not None:
        return str(query["x"])
    if dimensions:
        return dimensions[0]
    return columns[0] if columns else ""


def _column_is_numeric(rows: Sequence[Mapping[str, Any]], field: str) -> bool:
    """Return whether any value in a column is numeric."""
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

    if source.get("kind") == "data_contract":
        contract_id = str(source.get("data_contract_id") or "")
        contract = await _get_contract_record(session, project_id, contract_id)
        field_count = 0
        occurrence_count = 0
        availability_count = 0
        latest_occurrence = None
        if contract is not None:
            # Contract summaries/fingerprints capture data updates, while field
            # count captures schema changes that affect available measures.
            field_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(DataContractFieldRecord)
                        .where(DataContractFieldRecord.data_contract_id == contract.id)
                    )
                ).one()
            )
            occurrence_ids = select(RunContractRecord.id).where(
                RunContractRecord.data_contract_id == contract.id
            )
            occurrence_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(RunContractRecord)
                        .where(RunContractRecord.data_contract_id == contract.id)
                    )
                ).one()
            )
            latest_occurrence = (
                await session.exec(
                    select(func.max(RunContractRecord.created_at)).where(
                        RunContractRecord.data_contract_id == contract.id
                    )
                )
            ).one()
            availability_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(RunContractSampleRecord)
                        .where(
                            cast(Any, RunContractSampleRecord.run_contract_id).in_(
                                occurrence_ids
                            )
                        )
                    )
                ).one()
            )
        return canonical_hash(
            {
                "kind": "data_contract",
                "data_contract_id": contract_id,
                "source_fingerprint": (
                    contract.source_fingerprint if contract is not None else None
                ),
                "last_profiled_at": (
                    contract.last_profiled_at.isoformat()
                    if contract is not None and contract.last_profiled_at is not None
                    else None
                ),
                "fields": field_count,
                "run_contracts": occurrence_count,
                "run_contract_samples": availability_count,
                "latest_occurrence": (
                    latest_occurrence.isoformat()
                    if isinstance(latest_occurrence, datetime)
                    else None
                ),
            }
        )
    if source.get("kind") == "contract_series":
        contract_ids = [
            str(value)
            for value in source.get("data_contract_ids", [])
            if isinstance(value, str)
        ]
        return canonical_hash(
            {
                "kind": "contract_series",
                "contracts": [
                    await fingerprint_source(
                        session=session,
                        analytics_store=analytics_store,
                        project_id=project_id,
                        source={
                            "kind": "data_contract",
                            "data_contract_id": contract_id,
                        },
                    )
                    for contract_id in contract_ids
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
    if table and table in METADATA_MODELS:
        model = METADATA_MODELS[str(table)]
        statement = select(func.count()).select_from(model)
        if project_id is not None and "project_id" in model.model_fields:
            # Metadata project columns are mixed: most core tables use integer
            # project foreign keys, while server tables store public project IDs.
            project_pk = await _project_pk(session, project_id)
            model_any = cast(Any, model)
            statement = statement.where(
                model_any.project_id == project_pk
                if _project_field_is_integer(model)
                else model_any.project_id == project_id
            )
        count = int((await session.exec(statement)).one())
        return canonical_hash({"store": "metadata", "table": table, "rows": count})
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
    """Compile a metadata-backed builder query into SQL.

    Generic builder queries target a physical metadata/analytics table. They
    are less semantic than contract-first queries but useful for database
    previews and advanced dashboard workflows.
    """
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
            f"{_aggregation_sql(aggregation, expression)} AS {_quote_identifier(alias)}"
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
    if store == "analytics" and table in INTEGER_KEYED_TABLES:
        where_parts.extend(
            _sample_selection_where_sql(
                selections=await _resolve_sample_selections(
                    session=session, project_id=project_id, config=config
                ),
                columns=columns,
                parameters=parameters,
            )
        )
    for filter_config in _physical_global_filters(config):
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
    """Compile project scoping for metadata SQL tables.

    Project scoping only applies to tables that expose a project_id column.
    Analytics tables already store public project labels when they have one.
    """
    if project_id is None or "project_id" not in columns:
        return None
    if store == "metadata":
        model = METADATA_MODELS.get(table)
        if model is not None and _project_field_is_integer(model):
            # Core metadata tables use integer project FKs, so resolve the public
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
    """Compile a builder filter into SQL and bound parameters.

    Convert a small JSON filter grammar into parameterized SQL. Column and
    operator validation happen before any SQL fragment is returned.
    """
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
    """Compile an ORDER BY clause for exposed output columns.

    ORDER BY accepts either "column" or {"field": "column", "direction":
    "desc"}. The chosen column must already be exposed by the query.
    """
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


async def _execute_metadata_sql(
    session: AsyncSession,
    sql: str,
    *,
    parameters: Sequence[Any] = (),
    limit: int,
) -> tuple[list[str], list[JsonObject]]:
    """Execute metadata SQL and return JSON-compatible rows.

    SQLAlchemy text queries use named parameters, while the shared query
    compiler emits positional question marks for both stores. Rewrite them
    just before execution.
    """
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
    """Extract named parameters from a SQL string.

    Replace ? placeholders with SQLAlchemy named parameters. This keeps the
    compiler simple while still using safe bound values for metadata SQL.
    """
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
    """Fetch a cached insight result when its spec hash still matches.

    Cache rows are append-only. Pick the newest matching row so a refresh can
    write a new result without mutating older history.
    """
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
    """Fetch a cached report result when its spec hash still matches.

    Report cache lookup mirrors insight cache lookup but keys by report_id.
    """
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
    """Return the normalized query section from a config.

    Missing or malformed query blocks are treated as empty query config so
    callers get a clear "source required" error downstream.
    """
    query = config.get("query")
    return query if isinstance(query, Mapping) else {}


def _query_source(config: Mapping[str, Any]) -> JsonObject:
    """Return the normalized source section from a config.

    Extract only the source identity used for fingerprinting. Query shape,
    filters, and visualization are already part of the config hash.
    """
    contract_series = _contract_series_items(config)
    if contract_series:
        return {
            "kind": "contract_series",
            "data_contract_ids": sorted(
                {_series_contract_id(series_item) for series_item in contract_series}
            ),
        }
    query = _query_config(config)
    source = query.get("source")
    if isinstance(source, Mapping) and source.get("kind") == "data_contract":
        return {
            "kind": "data_contract",
            "data_contract_id": source.get("data_contract_id") or source.get("id"),
        }
    store, table = _parse_source(query.get("source"))
    return {"store": store, "table": table}


def _parse_source(value: Any) -> tuple[StoreName, str | None]:
    """Parse a source config into a store and optional table name.

    Sources can be explicit objects, "store.table" strings, or bare analytics
    table names. Normalize all variants into (store, table).
    """
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
    if store not in {"metadata", "analytics"}:
        raise ValueError(f"Unsupported query store: {store}")
    return cast(StoreName, store), str(table) if table else None


async def _get_contract_record(
    session: AsyncSession,
    project_id: str | None,
    data_contract_id: str,
) -> DataContractRecord | None:
    """Fetch a data contract by public ID within project scope."""
    statement = select(DataContractRecord).where(
        DataContractRecord.data_contract_id == data_contract_id
    )
    if project_id is not None:
        project_pk = await _project_pk(session, project_id)
        if project_pk is None:
            return None
        if project_id == DEFAULT_PROJECT_ID:
            contract_project_id = cast(Any, DataContractRecord.project_id)
            statement = statement.where(
                or_(
                    contract_project_id == project_pk,
                    contract_project_id.is_(None),
                )
            )
        else:
            statement = statement.where(DataContractRecord.project_id == project_pk)
    rows = list((await session.exec(statement)).all())
    if project_id == DEFAULT_PROJECT_ID:
        for row in rows:
            if row.project_id == project_pk:
                return row
    return rows[0] if rows else None


async def _get_contract_field_records(
    session: AsyncSession,
    *,
    contract_id: int,
    field_ids: Sequence[str],
) -> dict[str, DataContractFieldRecord]:
    """Fetch selected field records for a data contract."""
    rows = (
        await session.exec(
            select(DataContractFieldRecord)
            .where(DataContractFieldRecord.data_contract_id == contract_id)
            .where(cast(Any, DataContractFieldRecord.field_id).in_(list(field_ids)))
        )
    ).all()
    return {row.field_id: row for row in rows}


async def _get_all_contract_field_records(
    session: AsyncSession,
    *,
    contract_id: int,
) -> dict[str, DataContractFieldRecord]:
    """Fetch every field record for a data contract."""
    rows = (
        await session.exec(
            select(DataContractFieldRecord).where(
                DataContractFieldRecord.data_contract_id == contract_id
            )
        )
    ).all()
    return {row.field_id: row for row in rows}


def _contract_requested_fields(
    query_config: Mapping[str, Any], config: Mapping[str, Any]
) -> list[str]:
    """Collect field IDs referenced by query and table config.

    Fields can be declared explicitly, implied by measures, or used as
    dimensions. Collect all field-like references before validating them.
    """
    fields = _string_list(query_config.get("fields"))
    for column in _table_column_items(config):
        field_id = column.get("field_id") or column.get("field")
        if isinstance(field_id, str):
            fields.append(field_id)
    for measure in _measures(query_config, config):
        field = measure["field"]
        if field not in {"*", "value"}:
            fields.append(field)
    identity_columns = {
        str(column)
        for grain in ANALYSIS_GRAINS.values()
        for column in cast(Sequence[Any], grain.get("identity_columns") or [])
    }
    for value in _string_list(
        query_config.get("dimensions") or query_config.get("group_by")
    ):
        if value not in identity_columns:
            fields.append(value)
    return list(dict.fromkeys(fields))


def _table_column_items(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return normalized table column config items."""
    raw = config.get("table_columns")
    if isinstance(raw, Mapping):
        return [raw]
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        return [item for item in raw if isinstance(item, Mapping)]
    return []


def _contract_value_column(field: DataContractFieldRecord) -> str:
    """Choose the physical value column for a contract field.

    Field definitions can override the physical value column. Otherwise choose
    the column from the declared value_type.
    """
    query_ref = field.query_ref_json if isinstance(field.query_ref_json, dict) else {}
    value_column = query_ref.get("value_column")
    if isinstance(value_column, str) and value_column in {
        "value",
        "value_numeric",
        "value_string",
        "value_boolean",
        "value_datetime",
        "value_json",
        "data_json",
    }:
        return value_column
    return {
        "numeric": "value_numeric",
        "string": "value_string",
        "boolean": "value_boolean",
        "date": "value_datetime",
        "json": "value_json",
    }.get(field.value_type, "value_string")


def _field_id_match_sql(parameters: list[Any], field: DataContractFieldRecord) -> str:
    """Compile a field match predicate for canonical or legacy IDs.

    DuckDB may store field_id as the SQL integer ID, while readable views can
    expose field labels through dim_fields. Match both forms.
    """
    parameters.extend([_record_pk(field), field.field_id])
    return (
        "(field_id = ? OR field_id IN ("
        "SELECT field_id FROM dim_fields WHERE field_label = ?"
        "))"
    )


def _synthetic_contract_fields(table: str | None) -> dict[str, dict[str, str]]:
    """Return built-in field definitions for tables without field rows.

    Tables without data_contract_fields rows still expose important queryable
    columns. These synthetic fields let the contract grammar address them by
    stable names.
    """
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
        "result_payloads": {
            "payload_kind": "payload_kind",
            "payload_name": "payload_name",
            "schema_json": "schema_json",
            "source_observation_id": "source_observation_id",
            "source_observation_label": "source_observation_label",
        },
    }
    if table == "feature_value_numeric":
        return {"feature_value_numeric": {"value": "value"}}
    return fields


def _normalize_synthetic_requested_fields(
    requested_fields: Sequence[str],
    field_map: Mapping[str, str],
) -> list[str]:
    """Map synthetic field requests to valid table columns.

    Accept both canonical synthetic names and their safe aliases.
    """
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
        raise ValueError(f"Unknown contract field(s): {unknown}")
    return list(dict.fromkeys(normalized))


def _default_contract_dimensions(table: str | None) -> list[str]:
    """Choose natural dimensions for a contract source table.

    Raw contract previews should include the natural entity columns users need
    to understand what each value belongs to.
    """
    if table in {"sample_metrics", "feature_value_numeric", "feature_call"}:
        return ["sample_id"]
    if table == "entity_attributes":
        return ["entity_id"]
    if table in {
        "copy_number_segments",
        "sample_variant_calls",
        "sample_structural_variant_calls",
    }:
        return ["sample_id"]
    if table == "result_payloads":
        return [
            "run_id",
            "sample_id",
            "source_observation_label",
            "payload_name",
            "payload_kind",
        ]
    return []


def _contract_filter_sql(
    *,
    columns: Sequence[str],
    value_column: str,
    field_aliases: set[str],
    filter_config: Any,
    parameters: list[Any],
) -> str:
    """Compile a contract table filter into SQL and parameters.

    Filters may use the contract field alias ("value", field_id, safe alias) or
    a physical table column. Rewrite field-value filters to the value column.
    """
    if not isinstance(filter_config, Mapping):
        raise ValueError("Filters must be objects.")
    field = str(filter_config.get("field") or "")
    if field in field_aliases:
        rewritten = dict(filter_config)
        rewritten["field"] = value_column
        return _filter_sql(columns, rewritten, parameters)
    return _filter_sql(columns, filter_config, parameters)


def _record_pk(row: Any) -> int:
    """Return a model primary key or raise if it is not persisted.

    Query compilation depends on metadata primary keys; fail loudly if a caller
    passes an unflushed SQLModel row.
    """
    row_id = getattr(row, "id", None)
    if row_id is None:
        raise ValueError("Metadata record has not been flushed.")
    return int(row_id)


def _columns_for_source(store: StoreName, table: str) -> list[str]:
    """Return known readable columns for a source table.

    Column validation is based on registered serializers/models rather than
    trusting table names from client-provided config.
    """
    if store == "analytics":
        serializer = SERIALIZERS_BY_TABLE.get(table)
        if serializer is None:
            raise ValueError(f"Unknown analytical table: {table}")
        return list(serializer.columns)
    model = METADATA_MODELS.get(table)
    if model is None:
        raise ValueError(f"Unknown metadata table: {table}")
    return list(model.model_fields)


def _measures(
    query_config: Mapping[str, Any], config: Mapping[str, Any]
) -> list[JsonObject]:
    """Normalize metric/aggregation configs into measure specs.

    Measures can come from query.measures or top-level series. Normalize both
    shapes into field/aggregation/alias records used by query compilers.
    """
    raw = query_config.get("measures") or config.get("series") or []
    if isinstance(raw, Mapping):
        raw = [raw]
    measures = []
    for index, value in enumerate(cast(Sequence[Any], raw)):
        if not isinstance(value, Mapping):
            continue
        aggregation = str(value.get("aggregation") or value.get("aggregate") or "count")
        if aggregation in {"", "raw", "none", "value", "values"}:
            continue
        if aggregation == "average":
            aggregation = "avg"
        if aggregation == "count_rows":
            aggregation = "count"
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
    """Resolve the row limit for an insight query.

    Bound every query according to the visible result-size policy. The final
    response may be smaller, sampled, or file-backed after rows are returned.
    """
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
    """Reject SQL that is not a single read-only SELECT/WITH query.

    Advanced SQL is intentionally SELECT/WITH-only and single-statement. This
    avoids mutating local databases through dashboard-authored SQL.
    """
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
    """Build ECharts options from result rows and visualization config.

    ECharts is an implementation detail: configs describe chart intent, and
    this helper compiles rows into the option shape the dashboard can render.
    """
    visualization = str(config.get("visualization") or "bar")
    query = _query_config(config)
    colors = _display_colors(config)
    column_labels = _result_column_labels(config, columns)
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
    label_for = column_labels.get
    if visualization in {"pie", "donut"}:
        return {
            "color": CHART_COLORS,
            "tooltip": {"trigger": "item"},
            "series": [
                {
                    "name": label_for(x_field, x_field),
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
                "left": 52,
                "right": 18,
                "top": 28,
                "bottom": 56,
                "containLabel": True,
            },
            "xAxis": {
                "type": "value",
                "name": label_for(x_field, x_field),
                "nameLocation": "middle",
                "nameGap": 40,
            },
            "yAxis": {
                "type": "value",
                "name": label_for(y_field, y_field),
                "nameLocation": "middle",
                "nameGap": 36,
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
                "name": label_for(x_field, x_field),
                "data": sorted(str(row.get(x_field)) for row in rows),
            },
            "yAxis": {
                "type": "category",
                "name": label_for(y_dimension, y_dimension),
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
                "left": 52,
                "right": 18,
                "top": 28,
                "bottom": 56,
                "containLabel": True,
            },
            "xAxis": {
                "type": "value",
                "name": (
                    label_for(value_fields[0], value_fields[0])
                    if len(value_fields) == 1
                    else "Value"
                ),
                "nameLocation": "middle",
                "nameGap": 40,
                "scale": True,
                "axisLabel": {"formatter": "{value}"},
            },
            "yAxis": {
                "type": "value",
                "name": "Count",
                "nameLocation": "middle",
                "nameGap": 36,
            },
            "series": [
                {
                    "name": label_for(value_field, value_field),
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
            "left": 52,
            "right": 18,
            "top": 28,
            "bottom": 56,
            "containLabel": True,
        },
        "xAxis": {
            "type": "category",
            "name": label_for(x_field, x_field),
            "nameLocation": "middle",
            "nameGap": 40,
            "data": [row.get(x_field) for row in rows],
        },
        "yAxis": {
            "type": "value",
            "name": label_for(y_field, y_field),
            "nameLocation": "middle",
            "nameGap": 36,
        },
        "series": [
            {
                "name": label_for(field, field),
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
    """Return configured chart colors keyed by series or category."""
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
    """Build ECharts boxplot options from grouped numeric values."""
    colors = _display_colors(config)
    column_labels = _result_column_labels(config, columns)
    label_for = column_labels.get
    group_field = x_field if x_field in columns else columns[0] if columns else "group"
    groups = list(dict.fromkeys(str(row.get(group_field)) for row in rows))
    return {
        "tooltip": {"trigger": "item"},
        "legend": {"type": "scroll"},
        "grid": {
            "left": 52,
            "right": 18,
            "top": 28,
            "bottom": 56,
            "containLabel": True,
        },
        "xAxis": {
            "type": "category",
            "name": label_for(group_field, group_field),
            "data": groups,
            "nameLocation": "middle",
            "nameGap": 40,
        },
        "yAxis": {
            "type": "value",
            "name": ", ".join(label_for(field, field) for field in y_fields),
            "nameLocation": "middle",
            "nameGap": 36,
        },
        "series": [
            {
                "name": label_for(field, field),
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
    """Compute the min, quartiles, and max for a numeric sample."""
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
    """Compute a linear-interpolated quantile for sorted numeric values."""
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
    """Choose a color for a chart series."""
    configured = list(dict.fromkeys(colors.values()))
    return (
        colors.get(field)
        or colors.get(_safe_alias(field, fallback="series"))
        or (configured[index] if index < len(configured) else None)
        or fallback
        or CHART_COLORS[index % len(CHART_COLORS)]
    )


def _category_color(colors: Mapping[str, str], category: str, index: int) -> str:
    """Choose a color for a categorical chart slice or bar."""
    return (
        colors.get(category)
        or colors.get(_safe_alias(category, fallback="category"))
        or CHART_COLORS[index % len(CHART_COLORS)]
    )


def _metric_payload(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[str]
) -> JsonObject:
    """Build the compact payload for a single metric visualization."""
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
    """Find the first numeric result column not explicitly excluded."""
    excluded = exclude or set()
    for column in columns:
        if column in excluded:
            continue
        if any(isinstance(row.get(column), int | float) for row in rows):
            return column
    return None


def _histogram_bin_count(config: Mapping[str, Any]) -> int:
    """Resolve the number of histogram bins to render."""
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
    """Choose numeric fields that should be binned for histograms."""
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
    """Bin numeric fields into histogram rows for chart rendering."""
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
    """Return whether a value is numeric but not boolean."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _format_bin_edge(value: float) -> str:
    """Format a histogram bin edge for stable display."""
    return f"{value:.4g}"


def _string_list(value: Any) -> list[str]:
    """Normalize a scalar or sequence into a list of strings."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if isinstance(item, str)]
    return []


def _safe_alias(value: str, *, fallback: str) -> str:
    """Convert a user-facing identifier into a SQL-safe alias."""
    alias = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()
    return alias or fallback


def _quote_identifier(value: str) -> str:
    """Quote a SQL identifier for generated queries."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        raise ValueError(f"Invalid identifier: {value}")
    return f'"{value}"'


def _require_column(columns: Sequence[str] | set[str], column: str) -> None:
    """Raise when a requested column is unavailable."""
    if column not in columns:
        raise ValueError(f"Unknown column: {column}")


async def _project_pk(session: AsyncSession, project_id: str) -> int | None:
    """Resolve a project public ID to its internal primary key."""
    row = (
        await session.exec(
            select(ProjectRecord).where(ProjectRecord.project_id == project_id)
        )
    ).first()
    return row.id if row is not None else None


def _project_field_is_integer(model: type[SQLModel]) -> bool:
    """Return whether a SQLModel project_id field stores integers."""
    field = model.model_fields.get("project_id")
    return field is not None and "int" in str(field.annotation)
