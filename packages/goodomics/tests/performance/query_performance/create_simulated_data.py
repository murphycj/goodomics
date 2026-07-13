"""Create a contract-aware synthetic catalog and analytical dataset.

The fixture intentionally uses the same public label write path as importers so
it exercises dimension resolution as well as the run-contract catalog model.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import duckdb
from goodomics.projects import (
    DEFAULT_PROJECT_ID,
    DEFAULT_PROJECT_NAME,
    analytics_path_for_project,
)
from goodomics.storage.database import DEFAULT_DATABASE_URL, sqlite_database_path
from goodomics.storage.duckdb import DuckDBAnalyticsStore, insert_public_select
from goodomics.storage.sqlalchemy import (
    AnalysisMethodRecord,
    AnalysisTypeRecord,
    DataContractAnalysisTypeRecord,
    DataContractFieldRecord,
    DataContractRecord,
    ProjectRecord,
    RunContractRecord,
    RunContractSampleRecord,
    RunRecord,
    RunSampleRecord,
    SampleRecord,
    SQLModelGoodomicsStore,
    SubjectRecord,
    get_record_by_field,
)
from sqlmodel.ext.asyncio.session import AsyncSession

DEFAULT_GOODOMICS_ROOT = Path(".goodomics")
DEFAULT_ANALYTICS_PATH = analytics_path_for_project(
    DEFAULT_GOODOMICS_ROOT,
    DEFAULT_PROJECT_ID,
)
GENE_COUNT = 20_000
QC_NUMERIC_METRIC_COUNT = 36


def main() -> None:
    args = _parse_args()
    _reset_database(DEFAULT_ANALYTICS_PATH)
    database_path = sqlite_database_path(DEFAULT_DATABASE_URL)
    if database_path is not None:
        _reset_database(database_path)

    # The fresh catalog assigns deterministic integer IDs. Analytical catalog
    # columns deliberately store those IDs rather than a second label mapping.
    asyncio.run(_write_catalog_database(args.runs, args.samples))
    store = DuckDBAnalyticsStore(DEFAULT_ANALYTICS_PATH)
    store.ensure_schema()
    with duckdb.connect(str(DEFAULT_ANALYTICS_PATH)) as connection:
        connection.execute("PRAGMA threads = 8")
        _create_staging_tables(connection, args.runs, args.samples)
        _load_analytics(connection)

    _print_summary(store)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create contract-aware synthetic data at the default paths used by "
            "`goodomics serve`. Inputs are run count and samples per run."
        )
    )
    parser.add_argument("runs", type=_positive_int)
    parser.add_argument("samples", type=_positive_int)
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


def _create_staging_tables(
    connection: duckdb.DuckDBPyConnection, runs: int, samples: int
) -> None:
    connection.execute(
        """
        CREATE TEMP TABLE perf_runs AS
        SELECT run_index, printf('run_%04d', run_index + 1) AS run_id
        FROM range(?) AS values(run_index)
        """,
        [runs],
    )
    connection.execute(
        """
        CREATE TEMP TABLE perf_samples AS
        SELECT
            r.run_index,
            r.run_id,
            sample_index,
            printf('S%05d', sample_index + 1) AS sample_id,
            printf('%s__S%05d', r.run_id, sample_index + 1) AS run_sample_id
        FROM perf_runs r
        CROSS JOIN range(?) AS values(sample_index)
        """,
        [samples],
    )


def _load_analytics(connection: duckdb.DuckDBPyConnection) -> None:
    print("loading synthetic features...")
    connection.execute(
        """
        INSERT INTO features
        SELECT
            printf('gene:%05d', feature_index + 1),
            printf('G%05d', feature_index + 1),
            'gene',
            printf('GENE%05d', feature_index + 1),
            printf('ENSG%011d', feature_index + 1),
            'ensembl',
            'GRCh38',
            json_object('synthetic_index', feature_index)
        FROM range(?) AS values(feature_index)
        """,
        [GENE_COUNT],
    )

    print("loading sample metrics...")
    metric_columns = (
        "data_contract_id",
        "run_contract_id",
        "run_id",
        "run_sample_id",
        "sample_id",
        "field_id",
        "source_observation_id",
        "source_observation_label",
        "source_observation_metadata_json",
        "value_type",
        "value_numeric",
    )
    insert_public_select(
        connection,
        "sample_metrics",
        metric_columns,
        """
        SELECT
            1 AS data_contract_id,
            run_index * 2 + 1 AS run_contract_id,
            run_index + 1 AS run_id,
            run_index * (SELECT count(DISTINCT sample_index) FROM perf_samples)
                + sample_index + 1 AS run_sample_id,
            sample_index + 1 AS sample_id,
            printf('qc.metric.%02d', metric_index + 1) AS field_id,
            run_sample_id AS source_observation_id,
            sample_id AS source_observation_label,
            '{}' AS source_observation_metadata_json,
            'numeric' AS value_type,
            40.0 + ((sample_index * 13 + metric_index + run_index) % 600) / 10.0
                AS value_numeric
        FROM perf_samples
        CROSS JOIN range(?) AS values(metric_index)
        """,
        [QC_NUMERIC_METRIC_COUNT],
    )

    print("loading expression values...")
    value_columns = (
        "data_contract_id",
        "run_contract_id",
        "run_id",
        "run_sample_id",
        "sample_id",
        "feature_id",
        "value",
    )
    insert_public_select(
        connection,
        "feature_value_numeric",
        value_columns,
        """
        SELECT
            2 AS data_contract_id,
            run_index * 2 + 2 AS run_contract_id,
            run_index + 1 AS run_id,
            run_index * (SELECT count(DISTINCT sample_index) FROM perf_samples)
                + sample_index + 1 AS run_sample_id,
            sample_index + 1 AS sample_id,
            printf('gene:%05d', feature_index + 1) AS feature_id,
            ln(1 + ((sample_index + 1) * (feature_index + 17) + run_index) % 100000)
                AS value
        FROM perf_samples
        CROSS JOIN range(?) AS values(feature_index)
        """,
        [GENE_COUNT],
    )


async def _write_catalog_database(runs: int, samples: int) -> None:
    print("writing contract-aware catalog...")
    store = SQLModelGoodomicsStore(DEFAULT_DATABASE_URL)
    await store.ensure_schema()
    await store.ensure_default_project()
    now = datetime.now(UTC)
    async with AsyncSession(store._get_engine()) as session:
        project = await get_record_by_field(
            session, ProjectRecord, ProjectRecord.project_id, DEFAULT_PROJECT_ID
        )
        if project is None or project.id is None:
            raise RuntimeError("Default project was not persisted")
        project.description = "Contract-aware synthetic query benchmark."

        analysis_type = AnalysisTypeRecord(
            analysis_type_id="generic_analysis",
            project_id=project.id,
            name="Generic analysis",
        )
        method = AnalysisMethodRecord(
            method_id="goodomics/query-performance-simulator",
            project_id=project.id,
            name="Goodomics query performance simulator",
            method_kind="benchmark",
        )
        session.add_all([analysis_type, method])
        await session.flush()
        if analysis_type.id is None or method.id is None:
            raise RuntimeError("Analysis catalogs were not persisted")

        contracts: list[DataContractRecord] = []
        for contract_id, name, data_type, primary_table in (
            (
                "synthetic_qc",
                "Synthetic QC metrics",
                "sample_metrics",
                "sample_metrics",
            ),
            (
                "synthetic_expression",
                "Synthetic gene expression",
                "feature_value_numeric",
                "feature_value_numeric",
            ),
        ):
            contract = DataContractRecord(
                data_contract_id=contract_id,
                project_id=project.id,
                name=name,
                data_type=data_type,
                value_type="numeric",
                entity_grain="sample",
                query_modes_json={"primary_table": primary_table},
                intrinsic_producer_families_json={"families": ["synthetic"]},
                last_profiled_at=now,
            )
            session.add(contract)
            contracts.append(contract)
        await session.flush()

        for contract in contracts:
            if contract.id is None:
                raise RuntimeError("Data contract was not persisted")
            session.add(
                DataContractAnalysisTypeRecord(
                    data_contract_id=contract.id,
                    analysis_type_id=analysis_type.id,
                )
            )
        session.add(
            DataContractFieldRecord(
                data_contract_id=cast(int, contracts[0].id),
                field_id="qc.metric.01",
                display_name="Synthetic QC metric",
                value_type="numeric",
                entity_scope="sample",
                primary_table="sample_metrics",
                physical_tables_json={"tables": ["sample_metrics"]},
                query_ref_json={"table": "sample_metrics", "field_id": "qc.metric.01"},
            )
        )

        subject_records: list[SubjectRecord] = []
        sample_records: list[SampleRecord] = []
        for sample_index in range(samples):
            subject = SubjectRecord(
                subject_id=f"SUBJ{sample_index + 1:05d}", project_id=project.id
            )
            session.add(subject)
            subject_records.append(subject)
        await session.flush()
        for sample_index, subject in enumerate(subject_records):
            sample = SampleRecord(
                sample_id=f"S{sample_index + 1:05d}",
                project_id=project.id,
                subject_id=subject.id,
                sample_name=f"Synthetic sample {sample_index + 1}",
            )
            session.add(sample)
            sample_records.append(sample)
        await session.flush()

        for run_index in range(runs):
            run_label = f"run_{run_index + 1:04d}"
            run = RunRecord(
                run_id=run_label,
                project_id=project.id,
                project=DEFAULT_PROJECT_NAME,
                name=f"Synthetic performance run {run_index + 1}",
                run_kind="query_performance_fixture",
                analysis_type_id=analysis_type.id,
                method_id=method.id,
                method_version="synthetic-v1",
                status="complete",
                ended_at=now,
                created_at=now,
            )
            session.add(run)
            await session.flush()
            if run.id is None:
                raise RuntimeError("Run was not persisted")

            run_samples: list[RunSampleRecord] = []
            for sample in sample_records:
                run_sample = RunSampleRecord(
                    run_sample_id=f"{run_label}__{sample.sample_id}",
                    run_id=run.id,
                    sample_id=cast(int, sample.id),
                    role="sample",
                )
                session.add(run_sample)
                run_samples.append(run_sample)
            await session.flush()

            for contract in contracts:
                run_contract = RunContractRecord(
                    run_contract_id=f"{run_label}:{contract.data_contract_id}",
                    run_id=run.id,
                    data_contract_id=cast(int, contract.id),
                    producer_method_id=method.id,
                    producer_version="synthetic-v1",
                    status="available",
                    ended_at=now,
                    created_at=now,
                )
                session.add(run_contract)
                await session.flush()
                run_contract_id = cast(int, run_contract.id)
                for run_sample in run_samples:
                    session.add(
                        RunContractSampleRecord(
                            run_contract_id=run_contract_id,
                            run_sample_id=cast(int, run_sample.id),
                            availability="observed",
                        )
                    )
        await session.commit()


def _print_summary(store: DuckDBAnalyticsStore) -> None:
    print(f"analytics database: {DEFAULT_ANALYTICS_PATH}")
    print(f"catalog database: {DEFAULT_DATABASE_URL}")
    with store._connect() as connection:
        for table in ("sample_metrics", "features", "feature_value_numeric"):
            row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
            if row is None:
                raise RuntimeError(f"Could not count synthetic table {table}")
            count = row[0]
            print(f"{table}: {count:,}")


if __name__ == "__main__":
    main()
