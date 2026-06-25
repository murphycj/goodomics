from __future__ import annotations

# ruff: noqa: E501
import argparse
import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from goodomics.projects import (
    DEFAULT_PROJECT_ID,
    DEFAULT_PROJECT_NAME,
    analytics_path_for_project,
)
from goodomics.storage.database import DEFAULT_DATABASE_URL, sqlite_database_path
from goodomics.storage.duckdb import ANALYTICS_TABLES, DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    ProjectRecord,
    RunRecord,
    SQLModelGoodomicsStore,
)
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

DEFAULT_GOODOMICS_ROOT = Path(".goodomics")
DEFAULT_ANALYTICS_PATH = analytics_path_for_project(
    DEFAULT_GOODOMICS_ROOT,
    DEFAULT_PROJECT_ID,
)
GENE_COUNT = 20_000
VARIANT_COUNT = 1_000
STRUCTURAL_VARIANT_COUNT = 300
INTERVAL_COUNT = 4_000
COPY_NUMBER_SEGMENTS_PER_SAMPLE = 120
INTERVAL_VALUES_PER_SAMPLE = 300
FEATURE_CALLS_PER_SAMPLE = 80
QC_NUMERIC_METRIC_COUNT = 36


def main() -> None:
    args = _parse_args()
    analytics_path = DEFAULT_ANALYTICS_PATH
    _reset_database(analytics_path)
    database_path = sqlite_database_path(DEFAULT_DATABASE_URL)
    if database_path is not None:
        _reset_database(database_path)

    store = DuckDBAnalyticsStore(analytics_path)
    store.ensure_schema()

    with duckdb.connect(str(analytics_path)) as connection:
        connection.execute("PRAGMA threads = 8")
        _create_staging_tables(connection, args.runs, args.samples)
        _load_reference_tables(connection)
        _load_run_scoped_tables(connection)
        _refresh_derived_tables(store)

    asyncio.run(_write_control_database(args.runs, args.samples))
    _print_summary(store, analytics_path)
    print(f"control database: {DEFAULT_DATABASE_URL}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a synthetic cancer omics DuckDB analytics database for query "
            "pressure testing. The script writes the default paths used by "
            f"`goodomics serve`: {DEFAULT_ANALYTICS_PATH} and {DEFAULT_DATABASE_URL}. "
            "The only inputs are run and sample counts."
        )
    )
    parser.add_argument("runs", type=_positive_int, help="Number of simulated runs.")
    parser.add_argument(
        "samples", type=_positive_int, help="Number of samples per run."
    )
    return parser.parse_args()


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return value


def _reset_database(path: Path) -> None:
    for candidate in (path, path.with_suffix(path.suffix + ".wal")):
        if candidate.exists():
            candidate.unlink()


async def _write_control_database(runs: int, samples: int) -> None:
    print("writing minimal UI control database...")
    store = SQLModelGoodomicsStore(DEFAULT_DATABASE_URL)
    await store.ensure_schema()
    await store.ensure_default_project()
    now = datetime.now(UTC)
    async with AsyncSession(store._get_engine()) as session:
        await session.exec(delete(RunRecord))
        project = await session.get(ProjectRecord, DEFAULT_PROJECT_ID)
        if project is not None:
            project.description = (
                "Minimal control metadata for the DuckDB query pressure test."
            )
            project.metadata_json = {
                "purpose": "query_performance_pressure_test",
                "analytics_path": str(DEFAULT_ANALYTICS_PATH),
            }
        session.add_all(
            [
                RunRecord(
                    run_id=f"run_{run_index + 1:04d}",
                    project_id=DEFAULT_PROJECT_ID,
                    project=DEFAULT_PROJECT_NAME,
                    name=f"Synthetic cancer performance run {run_index + 1}",
                    run_kind="query_performance_fixture",
                    assay="synthetic_multiomic_cancer",
                    pipeline_name="goodomics-query-performance-sim",
                    pipeline_version="synthetic-v1",
                    parameters_json={
                        "samples_per_run": samples,
                        "gene_count": GENE_COUNT,
                        "variant_count": VARIANT_COUNT,
                        "structural_variant_count": STRUCTURAL_VARIANT_COUNT,
                    },
                    status="complete",
                    metadata_json={
                        "note": (
                            "Run rows are intentionally minimal; pressure-test data "
                            "lives in DuckDB analytics tables."
                        )
                    },
                    created_at=now,
                )
                for run_index in range(runs)
            ]
        )
        await session.commit()


def _create_staging_tables(
    connection: duckdb.DuckDBPyConnection, runs: int, samples: int
) -> None:
    connection.execute(
        """
        CREATE TEMP TABLE perf_runs AS
        SELECT
            run_index,
            printf('run_%04d', run_index + 1) AS run_id
        FROM range(?) AS run_range(run_index)
        """,
        [runs],
    )
    connection.execute(
        """
        CREATE TEMP TABLE perf_run_samples AS
        SELECT
            r.run_index,
            r.run_id,
            sample_index,
            printf('%s__S%05d', r.run_id, sample_index + 1) AS run_sample_key,
            printf('S%05d', sample_index + 1) AS sample_key,
            printf('SUBJ%05d', sample_index + 1) AS subject_key,
            CASE WHEN sample_index % 2 = 0 THEN 'tumor' ELSE 'normal' END AS sample_role
        FROM perf_runs r
        CROSS JOIN range(?) AS sample_range(sample_index)
        """,
        [samples],
    )
    connection.execute(
        """
        CREATE TEMP TABLE perf_genes AS
        SELECT
            feature_index,
            printf('gene:%05d', feature_index + 1) AS feature_key,
            printf('G%05d', feature_index + 1) AS feature_id,
            printf('GENE%05d', feature_index + 1) AS symbol,
            printf('ENSG%011d', feature_index + 1) AS stable_id
        FROM range(?) AS feature_range(feature_index)
        """,
        [GENE_COUNT],
    )
    connection.execute(
        """
        CREATE TEMP TABLE perf_transcripts AS
        SELECT
            feature_index,
            printf('transcript:%05d', feature_index + 1) AS feature_key,
            printf('T%05d', feature_index + 1) AS feature_id,
            printf('TX%05d', feature_index + 1) AS symbol,
            printf('ENST%011d', feature_index + 1) AS stable_id,
            printf('gene:%05d', feature_index + 1) AS gene_feature_key
        FROM range(?) AS feature_range(feature_index)
        """,
        [VARIANT_COUNT],
    )
    connection.execute(
        """
        CREATE TEMP TABLE perf_variants AS
        SELECT
            variant_index,
            printf('variant:%05d', variant_index + 1) AS variant_key,
            printf('VAR%05d', variant_index + 1) AS variant_id,
            printf('%d', variant_index % 22 + 1) AS contig,
            1000000 + variant_index * 113 AS pos,
            1000000 + variant_index * 113 AS end_pos,
            CASE variant_index % 4 WHEN 0 THEN 'A' WHEN 1 THEN 'C' WHEN 2 THEN 'G' ELSE 'T' END AS ref,
            CASE variant_index % 4 WHEN 0 THEN 'G' WHEN 1 THEN 'T' WHEN 2 THEN 'A' ELSE 'C' END AS alt,
            printf('gene:%05d', variant_index % ? + 1) AS feature_key,
            printf('transcript:%05d', variant_index + 1) AS transcript_feature_key
        FROM range(?) AS variant_range(variant_index)
        """,
        [GENE_COUNT, VARIANT_COUNT],
    )
    connection.execute(
        """
        CREATE TEMP TABLE perf_structural_variants AS
        SELECT
            sv_index,
            printf('sv:%05d', sv_index + 1) AS structural_variant_key,
            printf('SV%05d', sv_index + 1) AS event_id,
            CASE sv_index % 5
                WHEN 0 THEN 'fusion'
                WHEN 1 THEN 'deletion'
                WHEN 2 THEN 'duplication'
                WHEN 3 THEN 'inversion'
                ELSE 'translocation'
            END AS event_class,
            printf('gene:%05d', sv_index % ? + 1) AS site1_feature_key,
            printf('gene:%05d', (sv_index * 17) % ? + 1) AS site2_feature_key,
            printf('%d', sv_index % 22 + 1) AS site1_contig,
            2000000 + sv_index * 1009 AS site1_pos,
            printf('%d', (sv_index * 5) % 22 + 1) AS site2_contig,
            5000000 + sv_index * 1543 AS site2_pos
        FROM range(?) AS sv_range(sv_index)
        """,
        [GENE_COUNT, GENE_COUNT, STRUCTURAL_VARIANT_COUNT],
    )
    connection.execute(
        """
        CREATE TEMP TABLE perf_intervals AS
        SELECT
            interval_index,
            printf('interval:%05d', interval_index + 1) AS interval_key,
            printf('%d', interval_index % 22 + 1) AS contig,
            100000 + interval_index * 5000 AS start_pos,
            100000 + interval_index * 5000 + 999 AS end_pos,
            printf('gene:%05d', interval_index % ? + 1) AS feature_key
        FROM range(?) AS interval_range(interval_index)
        """,
        [GENE_COUNT, INTERVAL_COUNT],
    )
    connection.execute(
        """
        CREATE TEMP TABLE perf_qc_metrics AS
        SELECT
            metric_index,
            printf('qc.metric.%02d', metric_index + 1) AS metric_key,
            CASE metric_index % 6
                WHEN 0 THEN 'pct'
                WHEN 1 THEN 'reads'
                WHEN 2 THEN 'bp'
                WHEN 3 THEN 'score'
                WHEN 4 THEN 'x'
                ELSE NULL
            END AS unit
        FROM range(?) AS metric_range(metric_index)
        """,
        [QC_NUMERIC_METRIC_COUNT],
    )


def _load_reference_tables(connection: duckdb.DuckDBPyConnection) -> None:
    steps: tuple[tuple[str, Callable[[], None]], ...] = (
        ("duckdb_metadata", lambda: _insert_duckdb_metadata(connection)),
        ("metric_definitions", lambda: _insert_metric_definitions(connection)),
        ("attribute_definitions", lambda: _insert_attribute_definitions(connection)),
        ("features", lambda: _insert_features(connection)),
        ("feature_aliases", lambda: _insert_feature_aliases(connection)),
        ("feature_sets", lambda: _insert_feature_sets(connection)),
        ("feature_set_members", lambda: _insert_feature_set_members(connection)),
        ("genomic_intervals", lambda: _insert_genomic_intervals(connection)),
        ("variants", lambda: _insert_variants(connection)),
        ("variant_annotations", lambda: _insert_variant_annotations(connection)),
        (
            "variant_transcript_annotations",
            lambda: _insert_variant_transcript_annotations(connection),
        ),
        (
            "structural_variant_events",
            lambda: _insert_structural_variant_events(connection),
        ),
    )
    _run_steps(steps)


def _load_run_scoped_tables(connection: duckdb.DuckDBPyConnection) -> None:
    steps: tuple[tuple[str, Callable[[], None]], ...] = (
        (
            "entity_attribute_numeric",
            lambda: _insert_entity_attribute_numeric(connection),
        ),
        (
            "entity_attribute_string",
            lambda: _insert_entity_attribute_string(connection),
        ),
        (
            "entity_attribute_boolean",
            lambda: _insert_entity_attribute_boolean(connection),
        ),
        ("entity_attribute_date", lambda: _insert_entity_attribute_date(connection)),
        ("entity_attribute_json", lambda: _insert_entity_attribute_json(connection)),
        (
            "profile_observation_sets",
            lambda: _insert_profile_observation_sets(connection),
        ),
        ("sample_metric_numeric", lambda: _insert_sample_metric_numeric(connection)),
        ("sample_metric_string", lambda: _insert_sample_metric_string(connection)),
        ("sample_metric_json", lambda: _insert_sample_metric_json(connection)),
        ("feature_value_numeric", lambda: _insert_feature_value_numeric(connection)),
        ("feature_call", lambda: _insert_feature_call(connection)),
        ("sample_interval_values", lambda: _insert_sample_interval_values(connection)),
        ("copy_number_segments", lambda: _insert_copy_number_segments(connection)),
        ("sample_variant_calls", lambda: _insert_sample_variant_calls(connection)),
        (
            "sample_structural_variant_calls",
            lambda: _insert_sample_structural_variant_calls(connection),
        ),
        ("timeline_events", lambda: _insert_timeline_events(connection)),
        ("profile_payloads", lambda: _insert_profile_payloads(connection)),
        ("cohort_summaries", lambda: _insert_cohort_summaries(connection)),
        ("tool_versions", lambda: _insert_tool_versions(connection)),
        ("data_sources", lambda: _insert_data_sources(connection)),
    )
    _run_steps(steps)


def _run_steps(steps: tuple[tuple[str, Callable[[], None]], ...]) -> None:
    for label, step in steps:
        print(f"loading {label}...")
        step()


def _insert_duckdb_metadata(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO duckdb_metadata
        SELECT
            ?,
            'Default Project',
            'analytics-v1',
            current_timestamp,
            current_timestamp,
            json_object(
                'purpose', 'query_performance_pressure_test',
                'gene_count', ?,
                'variant_count', ?,
                'structural_variant_count', ?
            )
        """,
        [DEFAULT_PROJECT_ID, GENE_COUNT, VARIANT_COUNT, STRUCTURAL_VARIANT_COUNT],
    )


def _insert_metric_definitions(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO metric_definitions
        SELECT
            metric_key,
            metric_key,
            'multiqc',
            metric_key,
            replace(metric_key, '.', ' '),
            'numeric',
            unit,
            CASE metric_index % 3 WHEN 0 THEN 'higher_is_better' WHEN 1 THEN 'lower_is_better' ELSE NULL END,
            'Synthetic MultiQC-like metric for DuckDB query pressure testing.',
            CASE metric_index % 4
                WHEN 0 THEN 'fastqc'
                WHEN 1 THEN 'star'
                WHEN 2 THEN 'picard'
                ELSE 'samtools'
            END,
            'general_stats',
            'synthetic-v1'
        FROM perf_qc_metrics
        UNION ALL
        SELECT
            'qc.status',
            'qc.status',
            'multiqc',
            'qc.status',
            'QC status',
            'string',
            NULL,
            NULL,
            'Synthetic per-sample QC status.',
            'goodomics-sim',
            'qc',
            'synthetic-v1'
        UNION ALL
        SELECT
            'qc.flags',
            'qc.flags',
            'multiqc',
            'qc.flags',
            'QC flags',
            'json',
            NULL,
            NULL,
            'Synthetic per-sample QC flag payload.',
            'goodomics-sim',
            'qc',
            'synthetic-v1'
        """
    )


def _insert_attribute_definitions(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO attribute_definitions VALUES
            ('attr:tumor_purity', 'tumor_purity', 'run_sample', 'Tumor purity', 'numeric', NULL, NULL, 'high', '{}'),
            ('attr:cancer_type', 'cancer_type', 'run_sample', 'Cancer type', 'string', NULL, NULL, 'high', '{}'),
            ('attr:is_tumor', 'is_tumor', 'run_sample', 'Is tumor sample', 'boolean', NULL, NULL, 'high', '{}'),
            ('attr:collection_date', 'collection_date', 'run_sample', 'Collection date', 'date', NULL, NULL, 'medium', '{}'),
            ('attr:clinical_context', 'clinical_context', 'run_sample', 'Clinical context', 'json', NULL, NULL, 'medium', '{}')
        """
    )


def _insert_features(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO features
        SELECT
            feature_key,
            feature_id,
            'gene',
            symbol,
            stable_id,
            'ensembl',
            'GRCh38',
            json_object('biotype', 'protein_coding', 'synthetic_index', feature_index)
        FROM perf_genes
        UNION ALL
        SELECT
            feature_key,
            feature_id,
            'transcript',
            symbol,
            stable_id,
            'ensembl',
            'GRCh38',
            json_object('parent_gene_key', gene_feature_key, 'biotype', 'protein_coding')
        FROM perf_transcripts
        """
    )


def _insert_feature_aliases(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO feature_aliases
        SELECT feature_key, symbol || '_ALIAS', 'synthetic_symbol'
        FROM perf_genes
        WHERE feature_index < 5000
        """
    )


def _insert_feature_sets(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO feature_sets VALUES
            ('set:transcriptome', 'transcriptome', 'gene_panel', 'Synthetic transcriptome', 'All simulated expression genes.', '{}'),
            ('set:cancer_drivers', 'cancer_drivers', 'gene_panel', 'Synthetic cancer drivers', 'Synthetic driver-like subset.', '{}'),
            ('set:variant_annotation_genes', 'variant_annotation_genes', 'gene_panel', 'Variant annotation genes', 'Genes used by variant annotations.', '{}')
        """
    )


def _insert_feature_set_members(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO feature_set_members
        SELECT 'set:transcriptome', feature_key, 'member', json_object('rank', feature_index + 1)
        FROM perf_genes
        UNION ALL
        SELECT 'set:cancer_drivers', feature_key, 'driver', json_object('rank', feature_index + 1)
        FROM perf_genes
        WHERE feature_index < 512
        UNION ALL
        SELECT 'set:variant_annotation_genes', feature_key, 'variant_annotation_target', '{}'
        FROM perf_genes
        WHERE feature_index < ?
        """,
        [VARIANT_COUNT],
    )


def _insert_genomic_intervals(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO genomic_intervals
        SELECT
            interval_key,
            'GRCh38',
            contig,
            start_pos,
            end_pos,
            '+',
            feature_key,
            CASE interval_index % 3 WHEN 0 THEN 'exon' WHEN 1 THEN 'target_region' ELSE 'cnv_bin' END,
            json_object('synthetic_index', interval_index)
        FROM perf_intervals
        """
    )


def _insert_variants(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO variants
        SELECT
            variant_key,
            variant_id,
            'GRCh38',
            contig,
            pos,
            end_pos,
            ref,
            alt,
            CASE variant_index % 3 WHEN 0 THEN 'SNV' WHEN 1 THEN 'insertion' ELSE 'deletion' END,
            printf('GRCh38:%s:%d:%s:%s', contig, pos, ref, alt)
        FROM perf_variants
        """
    )


def _insert_variant_annotations(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO variant_annotations
        SELECT
            'somatic_variants',
            variant_key,
            feature_key,
            CASE variant_index % 6
                WHEN 0 THEN 'missense_variant'
                WHEN 1 THEN 'frameshift_variant'
                WHEN 2 THEN 'splice_region_variant'
                WHEN 3 THEN 'stop_gained'
                WHEN 4 THEN 'synonymous_variant'
                ELSE 'intron_variant'
            END,
            CASE variant_index % 4 WHEN 0 THEN 'HIGH' WHEN 1 THEN 'MODERATE' WHEN 2 THEN 'LOW' ELSE 'MODIFIER' END,
            CASE variant_index % 11 WHEN 0 THEN 'pathogenic' WHEN 1 THEN 'likely_pathogenic' ELSE NULL END,
            (variant_index % 1000)::DOUBLE / 100000.0,
            json_object('oncogenicity', CASE WHEN variant_index % 13 = 0 THEN 'oncogenic' ELSE 'unknown' END)
        FROM perf_variants
        """
    )


def _insert_variant_transcript_annotations(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    connection.execute(
        """
        INSERT INTO variant_transcript_annotations
        SELECT
            'somatic_variants',
            variant_key,
            transcript_feature_key,
            feature_key,
            CASE variant_index % 6
                WHEN 0 THEN 'missense_variant'
                WHEN 1 THEN 'frameshift_variant'
                WHEN 2 THEN 'splice_region_variant'
                WHEN 3 THEN 'stop_gained'
                WHEN 4 THEN 'synonymous_variant'
                ELSE 'intron_variant'
            END,
            CASE variant_index % 4 WHEN 0 THEN 'HIGH' WHEN 1 THEN 'MODERATE' WHEN 2 THEN 'LOW' ELSE 'MODIFIER' END,
            printf(
                'p.%s%d%s',
                chr((65 + variant_index % 20)::INTEGER),
                variant_index % 900 + 1,
                chr((65 + (variant_index + 7) % 20)::INTEGER)
            ),
            printf('c.%dA>G', variant_index % 3000 + 1),
            variant_index % 900 + 1,
            variant_index % 900 + 1,
            variant_index % 2 = 0,
            json_object('mane_select', variant_index % 5 = 0)
        FROM perf_variants
        """
    )


def _insert_structural_variant_events(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO structural_variant_events
        SELECT
            structural_variant_key,
            event_id,
            event_class,
            'GRCh38',
            site1_feature_key,
            site2_feature_key,
            site1_contig,
            site1_pos,
            site2_contig,
            site2_pos,
            CASE sv_index % 3 WHEN 0 THEN 'in_frame' WHEN 1 THEN 'out_of_frame' ELSE NULL END,
            printf('%s event between synthetic loci', event_class),
            json_object('confidence', CASE WHEN sv_index % 4 = 0 THEN 'high' ELSE 'medium' END)
        FROM perf_structural_variants
        """
    )


def _insert_entity_attribute_numeric(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO entity_attribute_numeric
        SELECT
            'run_sample',
            run_sample_key,
            'attr:tumor_purity',
            'sample_attributes',
            NULL,
            CASE WHEN sample_role = 'tumor' THEN 0.35 + (sample_index % 55) / 100.0 ELSE 0.0 END
        FROM perf_run_samples
        """
    )


def _insert_entity_attribute_string(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO entity_attribute_string
        SELECT
            'run_sample',
            run_sample_key,
            'attr:cancer_type',
            'sample_attributes',
            NULL,
            CASE sample_index % 5
                WHEN 0 THEN 'lung_adenocarcinoma'
                WHEN 1 THEN 'breast_carcinoma'
                WHEN 2 THEN 'melanoma'
                WHEN 3 THEN 'colorectal_carcinoma'
                ELSE 'glioblastoma'
            END
        FROM perf_run_samples
        """
    )


def _insert_entity_attribute_boolean(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO entity_attribute_boolean
        SELECT
            'run_sample',
            run_sample_key,
            'attr:is_tumor',
            'sample_attributes',
            NULL,
            sample_role = 'tumor'
        FROM perf_run_samples
        """
    )


def _insert_entity_attribute_date(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO entity_attribute_date
        SELECT
            'run_sample',
            run_sample_key,
            'attr:collection_date',
            'sample_attributes',
            NULL,
            TIMESTAMP '2024-01-01' + (sample_index % 365) * INTERVAL '1 day'
        FROM perf_run_samples
        """
    )


def _insert_entity_attribute_json(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO entity_attribute_json
        SELECT
            'run_sample',
            run_sample_key,
            'attr:clinical_context',
            'sample_attributes',
            NULL,
            json_object(
                'subject_key', subject_key,
                'sample_role', sample_role,
                'stage', CASE sample_index % 4 WHEN 0 THEN 'I' WHEN 1 THEN 'II' WHEN 2 THEN 'III' ELSE 'IV' END
            )
        FROM perf_run_samples
        """
    )


def _insert_profile_observation_sets(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO profile_observation_sets
        SELECT
            profile_key,
            run_id,
            run_sample_key,
            sample_key,
            subject_key,
            'profiled',
            feature_set_key,
            NULL,
            NULL,
            json_object('project_id', ?, 'sample_role', sample_role)
        FROM perf_run_samples
        CROSS JOIN (
            VALUES
                ('rna_expression', 'set:transcriptome'),
                ('somatic_variants', 'set:variant_annotation_genes'),
                ('structural_variants', 'set:cancer_drivers'),
                ('copy_number', 'set:cancer_drivers'),
                ('multiqc_qc_metrics', NULL)
        ) AS profiles(profile_key, feature_set_key)
        """,
        [DEFAULT_PROJECT_ID],
    )


def _insert_sample_metric_numeric(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO sample_metric_numeric
        SELECT
            'multiqc_qc_metrics',
            rs.run_id,
            rs.run_sample_key,
            rs.sample_key,
            qm.metric_key,
            NULL,
            CASE qm.metric_index % 6
                WHEN 0 THEN 80 + ((rs.sample_index + qm.metric_index + rs.run_index) % 2000) / 100.0
                WHEN 1 THEN 10000000 + ((rs.sample_index + 1) * (qm.metric_index + 11) * 1000)
                WHEN 2 THEN 500000 + ((rs.sample_index + qm.metric_index) % 1000) * 50
                WHEN 3 THEN 20 + ((rs.sample_index * 7 + qm.metric_index) % 400) / 10.0
                WHEN 4 THEN 15 + ((rs.sample_index + qm.metric_index) % 60) / 2.0
                ELSE ((rs.sample_index * 13 + qm.metric_index + rs.run_index) % 1000) / 10.0
            END
        FROM perf_run_samples rs
        CROSS JOIN perf_qc_metrics qm
        """
    )


def _insert_sample_metric_string(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO sample_metric_string
        SELECT
            'multiqc_qc_metrics',
            run_id,
            run_sample_key,
            sample_key,
            'qc.status',
            NULL,
            CASE
                WHEN sample_index % 29 = 0 THEN 'fail'
                WHEN sample_index % 11 = 0 THEN 'warn'
                ELSE 'pass'
            END
        FROM perf_run_samples
        """
    )


def _insert_sample_metric_json(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO sample_metric_json
        SELECT
            'multiqc_qc_metrics',
            run_id,
            run_sample_key,
            sample_key,
            'qc.flags',
            NULL,
            json_object(
                'adapter_content_warn', sample_index % 17 = 0,
                'duplication_warn', sample_index % 13 = 0,
                'low_complexity_warn', sample_index % 19 = 0
            )
        FROM perf_run_samples
        """
    )


def _insert_feature_value_numeric(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO feature_value_numeric
        SELECT
            'rna_expression',
            rs.run_id,
            rs.run_sample_key,
            rs.sample_key,
            g.feature_key,
            round(
                ((rs.sample_index * 37 + rs.run_index * 101 + g.feature_index * 17) % 20000) / 100.0
                + CASE WHEN g.feature_index < 512 AND rs.sample_role = 'tumor' THEN 25.0 ELSE 0.0 END,
                4
            ),
            'tpm',
            NULL
        FROM perf_run_samples rs
        CROSS JOIN perf_genes g
        """
    )


def _insert_feature_call(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO feature_call
        SELECT
            'copy_number',
            rs.run_id,
            rs.run_sample_key,
            rs.sample_key,
            g.feature_key,
            CASE (rs.sample_index + g.feature_index) % 5
                WHEN 0 THEN 'amplification'
                WHEN 1 THEN 'deep_deletion'
                WHEN 2 THEN 'gain'
                WHEN 3 THEN 'loss'
                ELSE 'neutral'
            END,
            CASE (rs.sample_index + g.feature_index) % 5
                WHEN 0 THEN 'Amplification'
                WHEN 1 THEN 'Deep deletion'
                WHEN 2 THEN 'Gain'
                WHEN 3 THEN 'Loss'
                ELSE 'Neutral'
            END,
            CASE (rs.sample_index + g.feature_index) % 5 WHEN 4 THEN 0 ELSE 1 END,
            ((rs.sample_index * 11 + g.feature_index * 7) % 1000) / 100.0,
            0.6 + ((rs.sample_index + g.feature_index) % 40) / 100.0,
            printf('cn-call:%s:%s', rs.run_sample_key, g.feature_key),
            NULL
        FROM perf_run_samples rs
        JOIN perf_genes g ON g.feature_index < ?
        """,
        [FEATURE_CALLS_PER_SAMPLE],
    )


def _insert_sample_interval_values(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO sample_interval_values
        SELECT
            'target_coverage',
            rs.run_id,
            rs.run_sample_key,
            rs.sample_key,
            i.interval_key,
            80 + ((rs.sample_index * 5 + i.interval_index * 3 + rs.run_index) % 250),
            'mean_depth',
            NULL
        FROM perf_run_samples rs
        JOIN perf_intervals i ON i.interval_index < ?
        """,
        [INTERVAL_VALUES_PER_SAMPLE],
    )


def _insert_copy_number_segments(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO copy_number_segments
        SELECT
            'copy_number',
            rs.run_id,
            rs.run_sample_key,
            rs.sample_key,
            'GRCh38',
            printf('%d', segment_index % 22 + 1),
            1000000 + segment_index * 1000000,
            1000000 + segment_index * 1000000 + 500000,
            100 + segment_index % 900,
            ((rs.sample_index + segment_index) % 21 - 10) / 10.0,
            greatest(0.0, 2.0 + ((rs.sample_index + segment_index) % 21 - 10) / 5.0),
            CASE WHEN (rs.sample_index + segment_index) % 7 = 0 THEN 0.0 ELSE 1.0 END,
            CASE
                WHEN ((rs.sample_index + segment_index) % 21 - 10) / 10.0 >= 0.7 THEN 'amplification'
                WHEN ((rs.sample_index + segment_index) % 21 - 10) / 10.0 <= -0.7 THEN 'deletion'
                ELSE 'neutral'
            END,
            NULL
        FROM perf_run_samples rs
        CROSS JOIN range(?) AS segment_range(segment_index)
        """,
        [COPY_NUMBER_SEGMENTS_PER_SAMPLE],
    )


def _insert_sample_variant_calls(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO sample_variant_calls
        SELECT
            'somatic_variants',
            rs.run_id,
            rs.run_sample_key,
            rs.sample_key,
            v.variant_key,
            CASE (rs.sample_index + v.variant_index) % 3
                WHEN 0 THEN '0/1'
                WHEN 1 THEN '1/1'
                ELSE '0/0'
            END,
            40 + ((rs.sample_index + v.variant_index) % 240),
            20 + ((rs.sample_index * 3 + v.variant_index) % 800) / 10.0,
            20 + ((rs.sample_index + v.variant_index) % 100),
            4 + ((rs.sample_index * 5 + v.variant_index) % 100),
            ((rs.sample_index * 11 + v.variant_index * 7) % 1000) / 1000.0,
            CASE WHEN (rs.sample_index + v.variant_index) % 23 = 0 THEN 'LowQual' ELSE 'PASS' END,
            json_object('caller', 'synthetic-mutect2', 'phase_set', (rs.sample_index + v.variant_index) % 50),
            NULL
        FROM perf_run_samples rs
        CROSS JOIN perf_variants v
        """
    )


def _insert_sample_structural_variant_calls(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    connection.execute(
        """
        INSERT INTO sample_structural_variant_calls
        SELECT
            'structural_variants',
            rs.run_id,
            rs.run_sample_key,
            rs.sample_key,
            sv.structural_variant_key,
            CASE WHEN (rs.sample_index + sv.sv_index) % 19 = 0 THEN 'filtered' ELSE 'called' END,
            CASE WHEN (rs.sample_index + sv.sv_index) % 3 = 0 THEN 'split_reads' ELSE 'paired_end' END,
            CASE WHEN sv.event_class = 'fusion' THEN 'junction_reads' ELSE NULL END,
            5 + ((rs.sample_index + sv.sv_index) % 120),
            (rs.sample_index + sv.sv_index) % 12,
            (rs.sample_index * 3 + sv.sv_index) % 80,
            (rs.sample_index * 5 + sv.sv_index) % 120,
            json_object('caller', 'synthetic-manta', 'event_class', sv.event_class),
            NULL
        FROM perf_run_samples rs
        CROSS JOIN perf_structural_variants sv
        """
    )


def _insert_timeline_events(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO timeline_events
        SELECT
            printf('event:%s:diagnosis', run_sample_key),
            subject_key,
            sample_key,
            run_sample_key,
            'diagnosis',
            CAST(TIMESTAMP '2023-01-01' + (sample_index % 365) * INTERVAL '1 day' AS TEXT),
            NULL,
            'datetime',
            'observed',
            json_object('cancer_type_index', sample_index % 5)
        FROM perf_run_samples
        UNION ALL
        SELECT
            printf('event:%s:collection', run_sample_key),
            subject_key,
            sample_key,
            run_sample_key,
            'sample_collection',
            CAST(TIMESTAMP '2024-01-01' + (sample_index % 365) * INTERVAL '1 day' AS TEXT),
            NULL,
            'datetime',
            'observed',
            json_object('sample_role', sample_role)
        FROM perf_run_samples
        """
    )


def _insert_profile_payloads(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO profile_payloads
        SELECT
            printf('payload:%s:%s', run_sample_key, payload_name),
            data_profile_key,
            run_id,
            run_sample_key,
            payload_name,
            payload_kind,
            'inline_metadata_only',
            NULL,
            NULL,
            schema_json,
            row_count,
            NULL,
            json_object(
                'sample_key', sample_key,
                'columns', columns_json,
                'rows', rows_json,
                'source_hash', printf('synthetic-%s-%s', run_sample_key, payload_name)
            )
        FROM perf_run_samples
        CROSS JOIN (
            VALUES
                (
                    'rna_top_expression_preview',
                    'table',
                    'rna_expression',
                    json_object('columns', ['feature_key', 'tpm']),
                    25,
                    ['feature_key', 'tpm'],
                    [
                        json_object('feature_key', 'gene:00001', 'tpm', 120.0),
                        json_object('feature_key', 'gene:00002', 'tpm', 98.5)
                    ]
                ),
                (
                    'multiqc_general_stats_preview',
                    'table',
                    'multiqc_qc_metrics',
                    json_object('columns', ['metric_key', 'value']),
                    ?,
                    ['metric_key', 'value'],
                    [
                        json_object('metric_key', 'qc.metric.01', 'value', 95.2),
                        json_object('metric_key', 'qc.metric.02', 'value', 12000000)
                    ]
                )
        ) AS payloads(
            payload_name,
            payload_kind,
            data_profile_key,
            schema_json,
            row_count,
            columns_json,
            rows_json
        )
        """,
        [QC_NUMERIC_METRIC_COUNT],
    )


def _insert_cohort_summaries(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO cohort_summaries
        SELECT
            'all_samples',
            'multiqc_qc_metrics',
            metric_key,
            NULL,
            count(*),
            avg(value),
            median(value),
            stddev(value),
            min(value),
            max(value),
            quantile_cont(value, 0.05),
            quantile_cont(value, 0.25),
            quantile_cont(value, 0.75),
            quantile_cont(value, 0.95)
        FROM sample_metric_numeric
        GROUP BY metric_key
        UNION ALL
        SELECT
            'all_samples',
            'rna_expression',
            NULL,
            feature_key,
            count(*),
            avg(value),
            median(value),
            stddev(value),
            min(value),
            max(value),
            quantile_cont(value, 0.05),
            quantile_cont(value, 0.25),
            quantile_cont(value, 0.75),
            quantile_cont(value, 0.95)
        FROM feature_value_numeric
        WHERE feature_key IN (SELECT feature_key FROM perf_genes WHERE feature_index < 200)
        GROUP BY feature_key
        """
    )


def _insert_tool_versions(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO tool_versions
        SELECT run_id, tool, version, NULL
        FROM perf_runs
        CROSS JOIN (
            VALUES
                ('fastqc', '0.12.1'),
                ('multiqc', '1.27'),
                ('star', '2.7.11b'),
                ('mutect2', '4.5.0.0'),
                ('manta', '1.6.0'),
                ('cnvkit', '0.9.10')
        ) AS tools(tool, version)
        """
    )


def _insert_data_sources(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO data_sources
        SELECT
            run_id,
            run_sample_key,
            sample_key,
            tool,
            module,
            printf('synthetic://%s/%s/%s', run_id, sample_key, module)
        FROM perf_run_samples
        CROSS JOIN (
            VALUES
                ('fastqc', 'general_stats'),
                ('star', 'alignment_summary'),
                ('mutect2', 'somatic_vcf'),
                ('manta', 'structural_variants'),
                ('cnvkit', 'copy_number')
        ) AS sources(tool, module)
        """
    )


def _refresh_derived_tables(store: DuckDBAnalyticsStore) -> None:
    print("refreshing gene_alteration_state and sample_profile_cache...")
    with store._connect() as connection:
        connection.begin()
        try:
            store._refresh_gene_alteration_state(connection, run_id=None)
            store._refresh_sample_profile_cache(connection, run_id=None)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _print_summary(store: DuckDBAnalyticsStore, db_path: Path) -> None:
    counts = store.row_counts()
    print(f"\ncreated {db_path}")
    print(f"database size: {store.database_size_bytes():,} bytes")
    for table in ANALYTICS_TABLES:
        print(f"{table}: {counts.get(table, 0):,}")


if __name__ == "__main__":
    main()
