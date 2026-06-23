from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import duckdb
from goodomics.projects import DEFAULT_PROJECT_ID, analytics_path_for_project

DEFAULT_DB_PATH = analytics_path_for_project(Path(".goodomics"), DEFAULT_PROJECT_ID)
WARMUP_RUNS = 1
MEASURED_RUNS = 5


@dataclass(frozen=True)
class QueryCase:
    name: str
    sql: str | tuple[str, ...]


TARGET_RUN_CTE = """
WITH target_run AS (
    SELECT min(run_id) AS run_id
    FROM profile_observation_sets
),
target_run_samples AS (
    SELECT DISTINCT run_sample_key
    FROM profile_observation_sets
    WHERE run_id = (SELECT run_id FROM target_run)
)
"""

RUN_WIDE_QUERIES: tuple[str, ...] = (
    """
    SELECT *
    FROM profile_observation_sets
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    """
    SELECT *
    FROM sample_metric_numeric
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    """
    SELECT *
    FROM sample_metric_string
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    """
    SELECT *
    FROM sample_metric_json
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    """
    SELECT *
    FROM feature_value_numeric
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    """
    SELECT *
    FROM feature_call
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    """
    SELECT *
    FROM sample_interval_values
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT gi.*
    FROM genomic_intervals gi
    WHERE gi.interval_key IN (
        SELECT DISTINCT interval_key
        FROM sample_interval_values
        WHERE run_id = (SELECT run_id FROM target_run)
    )
    """,
    """
    SELECT *
    FROM copy_number_segments
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    """
    SELECT *
    FROM sample_variant_calls
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT v.*
    FROM variants v
    WHERE v.variant_key IN (
        SELECT DISTINCT variant_key
        FROM sample_variant_calls
        WHERE run_id = (SELECT run_id FROM target_run)
    )
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT va.*
    FROM variant_annotations va
    WHERE va.variant_key IN (
        SELECT DISTINCT variant_key
        FROM sample_variant_calls
        WHERE run_id = (SELECT run_id FROM target_run)
    )
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT vta.*
    FROM variant_transcript_annotations vta
    WHERE vta.variant_key IN (
        SELECT DISTINCT variant_key
        FROM sample_variant_calls
        WHERE run_id = (SELECT run_id FROM target_run)
    )
    """,
    """
    SELECT *
    FROM sample_structural_variant_calls
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT sve.*
    FROM structural_variant_events sve
    WHERE sve.structural_variant_key IN (
        SELECT DISTINCT structural_variant_key
        FROM sample_structural_variant_calls
        WHERE run_id = (SELECT run_id FROM target_run)
    )
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT te.*
    FROM timeline_events te
    JOIN target_run_samples trs USING (run_sample_key)
    """,
    """
    SELECT *
    FROM profile_payloads
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT gas.*
    FROM gene_alteration_state gas
    JOIN target_run_samples trs USING (run_sample_key)
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT spc.*
    FROM sample_profile_cache spc
    JOIN target_run_samples trs USING (run_sample_key)
    """,
    """
    SELECT *
    FROM tool_versions
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    """
    SELECT *
    FROM data_sources
    WHERE run_id = (SELECT min(run_id) FROM profile_observation_sets)
    """,
    f"""
    {TARGET_RUN_CTE}
    SELECT DISTINCT f.*
    FROM features f
    WHERE f.feature_key IN (
        SELECT feature_key
        FROM feature_value_numeric
        WHERE run_id = (SELECT run_id FROM target_run)
        UNION
        SELECT feature_key
        FROM feature_call
        WHERE run_id = (SELECT run_id FROM target_run)
        UNION
        SELECT va.feature_key
        FROM variant_annotations va
        JOIN sample_variant_calls svc USING (variant_key)
        WHERE svc.run_id = (SELECT run_id FROM target_run)
        UNION
        SELECT sve.site1_feature_key
        FROM structural_variant_events sve
        JOIN sample_structural_variant_calls ssvc USING (structural_variant_key)
        WHERE ssvc.run_id = (SELECT run_id FROM target_run)
        UNION
        SELECT sve.site2_feature_key
        FROM structural_variant_events sve
        JOIN sample_structural_variant_calls ssvc USING (structural_variant_key)
        WHERE ssvc.run_id = (SELECT run_id FROM target_run)
    )
    """,
)


QUERIES: tuple[QueryCase, ...] = (
    # QueryCase(
    #     "Top expressed genes",
    #     """
    #     SELECT
    #         feature_key,
    #         avg(value) AS mean_tpm,
    #         quantile_cont(value, 0.95) AS p95_tpm,
    #         count(*) AS observations
    #     FROM feature_value_numeric_by_sample
    #     WHERE data_profile_key = 'rna_expression'
    #     GROUP BY feature_key
    #     ORDER BY mean_tpm DESC
    #     LIMIT 25
    #     """,
    # ),
    QueryCase(
        "Two-sample expression distance",
        """
        WITH selected_samples AS (
            SELECT DISTINCT run_sample_key
            FROM feature_value_numeric
            ORDER BY run_sample_key
            LIMIT 2
        ),
        expression AS (
            SELECT
                fvn.run_sample_key,
                fvn.feature_key,
                fvn.value
            FROM feature_value_numeric fvn
            JOIN selected_samples ss USING (run_sample_key)
        )
        SELECT
            a.run_sample_key AS sample_a,
            b.run_sample_key AS sample_b,
            sqrt(sum(power(a.value - b.value, 2))) AS euclidean_distance,
            corr(a.value, b.value) AS pearson_correlation
        FROM expression a
        JOIN expression b USING (feature_key)
        WHERE a.run_sample_key < b.run_sample_key
        GROUP BY sample_a, sample_b
        """,
    ),
    QueryCase(
        "QC metric distribution",
        """
        SELECT
            metric_key,
            count(*) AS n,
            avg(value) AS mean_value,
            stddev(value) AS stddev_value,
            quantile_cont(value, 0.05) AS q05,
            quantile_cont(value, 0.50) AS median,
            quantile_cont(value, 0.95) AS q95
        FROM sample_metric_numeric_by_metric
        GROUP BY metric_key
        ORDER BY metric_key
        """,
    ),
    QueryCase(
        "QC failure context",
        """
        SELECT
            sms.value AS qc_status,
            eas.value AS cancer_type,
            count(*) AS samples,
            avg(smn.value) FILTER (WHERE smn.metric_key = 'qc.metric.01') AS mean_metric_01,
            avg(smn.value) FILTER (WHERE smn.metric_key = 'qc.metric.04') AS mean_metric_04
        FROM sample_metric_string sms
        JOIN entity_attribute_string eas
            ON eas.entity_key = sms.run_sample_key
            AND eas.attribute_key = 'attr:cancer_type'
        JOIN sample_metric_numeric smn
            ON smn.run_sample_key = sms.run_sample_key
        WHERE sms.metric_key = 'qc.status'
        GROUP BY qc_status, cancer_type
        ORDER BY qc_status, cancer_type
        """,
    ),
    QueryCase(
        "Variant burden by sample",
        """
        SELECT
            run_sample_key,
            count(*) FILTER (WHERE filter = 'PASS') AS pass_variants,
            avg(allele_fraction) AS mean_allele_fraction,
            max(depth) AS max_depth
        FROM sample_variant_calls_by_variant
        GROUP BY run_sample_key
        ORDER BY pass_variants DESC, run_sample_key
        LIMIT 50
        """,
    ),
    QueryCase(
        "Actionable variant genes",
        """
        SELECT
            f.symbol,
            va.consequence,
            va.impact,
            count(*) AS calls,
            avg(svc.allele_fraction) AS mean_allele_fraction
        FROM sample_variant_calls svc
        JOIN variant_annotations va USING (variant_key)
        JOIN features f ON f.feature_key = va.feature_key
        WHERE
            svc.filter = 'PASS'
            AND va.impact IN ('HIGH', 'MODERATE')
        GROUP BY f.symbol, va.consequence, va.impact
        ORDER BY calls DESC
        LIMIT 50
        """,
    ),
    QueryCase(
        "Structural variant recurrence",
        """
        SELECT
            sve.event_class,
            coalesce(f1.symbol, 'unknown') AS site1_gene,
            coalesce(f2.symbol, 'unknown') AS site2_gene,
            count(*) AS calls,
            avg(ssvc.tumor_read_count) AS mean_tumor_reads
        FROM sample_structural_variant_calls ssvc
        JOIN structural_variant_events sve USING (structural_variant_key)
        LEFT JOIN features f1 ON f1.feature_key = sve.site1_feature_key
        LEFT JOIN features f2 ON f2.feature_key = sve.site2_feature_key
        WHERE ssvc.call_status = 'called'
        GROUP BY sve.event_class, site1_gene, site2_gene
        ORDER BY calls DESC
        LIMIT 50
        """,
    ),
    QueryCase(
        "Copy number chromosome scan",
        """
        SELECT
            contig,
            call_label,
            count(*) AS segments,
            avg(segment_mean) AS mean_segment_mean,
            quantile_cont(total_copy_number, 0.95) AS p95_copy_number
        FROM copy_number_segments_by_region
        WHERE contig IN ('1', '7', '8', '17')
        GROUP BY contig, call_label
        ORDER BY contig, call_label
        """,
    ),
    QueryCase(
        "Gene alteration recurrence",
        """
        SELECT
            f.symbol,
            gas.alteration_type,
            gas.alteration_subtype,
            count(DISTINCT gas.run_sample_key) AS altered_samples,
            avg(gas.value_numeric) AS mean_value
        FROM gene_alteration_state_by_sample gas
        JOIN features f USING (feature_key)
        GROUP BY f.symbol, gas.alteration_type, gas.alteration_subtype
        ORDER BY altered_samples DESC
        LIMIT 50
        """,
    ),
    QueryCase(
        "Profile completeness and payloads",
        """
        SELECT
            pos.data_profile_key,
            pos.availability_status,
            count(DISTINCT pos.run_sample_key) AS samples,
            count(DISTINCT pp.payload_id) AS payloads,
            sum(coalesce(pp.row_count, 0)) AS declared_payload_rows
        FROM profile_observation_sets pos
        LEFT JOIN profile_payloads pp
            ON pp.run_sample_key = pos.run_sample_key
            AND pp.data_profile_key = pos.data_profile_key
        GROUP BY pos.data_profile_key, pos.availability_status
        ORDER BY pos.data_profile_key, pos.availability_status
        """,
    ),
    QueryCase("All data for one run", RUN_WIDE_QUERIES),
)


def main() -> None:
    if not DEFAULT_DB_PATH.exists():
        raise SystemExit(
            f"{DEFAULT_DB_PATH} does not exist. Run create_simulated_data.py first."
        )

    with duckdb.connect(str(DEFAULT_DB_PATH), read_only=True) as connection:
        connection.execute("PRAGMA threads = 8")
        print(
            f"Testing {len(QUERIES)} queries against {DEFAULT_DB_PATH} "
            f"({MEASURED_RUNS} measured runs, {WARMUP_RUNS} warmup run)."
        )
        results: list[tuple[QueryCase, QueryResult]] = []
        for query in QUERIES:
            result = _benchmark_query(connection, query)
            results.append((query, result))
        _print_results_table(results)


@dataclass(frozen=True)
class QueryResult:
    rows_returned: int
    average_ms: float
    min_ms: float
    max_ms: float


def _benchmark_query(
    connection: duckdb.DuckDBPyConnection,
    query: QueryCase,
) -> QueryResult:
    rows_returned = 0
    for _ in range(WARMUP_RUNS):
        rows_returned = _execute_case(connection, query)

    timings_ms: list[float] = []
    for _ in range(MEASURED_RUNS):
        started_at = perf_counter()
        rows_returned = _execute_case(connection, query)
        timings_ms.append((perf_counter() - started_at) * 1000)

    return QueryResult(
        rows_returned=rows_returned,
        average_ms=sum(timings_ms) / len(timings_ms),
        min_ms=min(timings_ms),
        max_ms=max(timings_ms),
    )


def _execute_case(connection: duckdb.DuckDBPyConnection, query: QueryCase) -> int:
    if isinstance(query.sql, str):
        return len(connection.execute(query.sql).fetchall())
    return sum(len(connection.execute(sql).fetchall()) for sql in query.sql)


def _print_results_table(results: list[tuple[QueryCase, QueryResult]]) -> None:
    headers = ("Query", "Rows returned", "Average ms", "Min ms", "Max ms")
    rows = [
        (
            query.name,
            f"{result.rows_returned:,}",
            f"{result.average_ms:,.2f}",
            f"{result.min_ms:,.2f}",
            f"{result.max_ms:,.2f}",
        )
        for query, result in results
    ]
    widths = [
        max(len(headers[column]), *(len(row[column]) for row in rows))
        for column in range(len(headers))
    ]

    print()
    print(_format_table_row(headers, widths))
    print(_format_separator(widths))
    for row in rows:
        print(_format_table_row(row, widths))


def _format_table_row(row: tuple[str, ...], widths: list[int]) -> str:
    cells = [
        row[0].ljust(widths[0]),
        *(row[column].rjust(widths[column]) for column in range(1, len(row))),
    ]
    return "  ".join(cells)


def _format_separator(widths: list[int]) -> str:
    return "  ".join("-" * width for width in widths)


if __name__ == "__main__":
    main()
