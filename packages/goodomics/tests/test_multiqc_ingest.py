from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fixtures import write_multiqc_fixture
from goodomics.ingest.multiqc import ingest_multiqc, ingest_multiqc_runs
from goodomics.parsers.multiqc import (
    discover_multiqc_outputs,
    multiqc_upstream_run_id,
    parse_multiqc_bundle,
)
from goodomics.projects import DEFAULT_PROJECT_ID
from goodomics.storage.analytics_resolution import (
    resolve_analytics_batch_catalog_ids,
)
from goodomics.storage.duckdb import (
    DuckDBAnalyticsStore,
    delete_public_parquet,
    insert_public_parquet,
)
from goodomics.storage.sqlalchemy import (
    DataImportRecord,
    FileLinkRecord,
    FileRecord,
    RunRecord,
    RunRelationshipRecord,
    RunSampleRecord,
    SampleRecord,
    SQLModelGoodomicsStore,
    SubjectRecord,
)
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


def _scalar(row: tuple[Any, ...] | None) -> Any:
    assert row is not None
    return row[0]


def _sql_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _direct_catalog_maps(parsed: Any, *, run_id: str) -> dict[str, dict[str, int]]:
    sample_ids = sorted(parsed.sample_ids)
    upstream_run_ids = [
        multiqc_upstream_run_id(run_id, sample_id) for sample_id in sample_ids
    ]
    data_contract_ids = sorted(
        {
            record.data_contract_id
            for record in [*parsed.metrics, *parsed.payloads]
            if isinstance(record.data_contract_id, str)
        }
    )
    return {
        "data_contract_id": {
            data_contract_id: index
            for index, data_contract_id in enumerate(data_contract_ids, start=1)
        },
        "field_id": {
            field.field_id: index
            for index, field in enumerate(parsed.contract_fields, start=1)
        },
        "run_id": {
            label: index
            for index, label in enumerate([run_id, *upstream_run_ids], start=1)
        },
        "run_sample_id": {
            f"{multiqc_upstream_run_id(run_id, sample_id)}:{sample_id}": index
            for index, sample_id in enumerate(sample_ids, start=1)
        },
        "sample_id": {
            sample_id: index for index, sample_id in enumerate(sample_ids, start=1)
        },
    }


def _resolved_multiqc_batch(parsed: Any, *, run_id: str) -> Any:
    return resolve_analytics_batch_catalog_ids(
        parsed.to_batch(run_id=run_id),
        _direct_catalog_maps(parsed, run_id=run_id),
    )


def _run_pk(database_url: str, run_id: str) -> int:
    async def load() -> int:
        catalog_store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(catalog_store._get_engine()) as session:
            row = (
                await session.exec(select(RunRecord).where(RunRecord.run_id == run_id))
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def test_discover_multiqc_outputs(tmp_path: Path) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path)

    outputs = discover_multiqc_outputs(multiqc_dir)

    assert len(outputs) == 1
    assert outputs[0].report_html == multiqc_dir / "demo_multiqc_report.html"
    assert outputs[0].data_dir.name == "demo_multiqc_report_data"
    assert outputs[0].parquet_path == outputs[0].data_dir / "multiqc.parquet"


def test_parse_multiqc_bundle_requires_parquet(tmp_path: Path) -> None:
    empty_multiqc = tmp_path / "multiqc_data"
    empty_multiqc.mkdir()

    with pytest.raises(ValueError, match="No MultiQC parquet file"):
        parse_multiqc_bundle(empty_multiqc, run_id="run-1")


def test_parse_multiqc_bundle_infers_samples_and_source_observations(
    tmp_path: Path,
) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path / "results", sample_id="SRR3192396")

    parsed = parse_multiqc_bundle(multiqc_dir, run_id="run-1")

    assert len(parsed.sample_ids) == 1
    assert "SRR3192396" in parsed.sample_ids
    assert "SRR3192396 R1" not in parsed.sample_ids
    metric_ids = {metric.field_id for metric in parsed.metrics}
    assert "general_stats.fastqc_raw_percent_gc" in metric_ids
    assert "general_stats.salmon_percent_mapped" in metric_ids
    metrics_by_field = {metric.field_id: metric for metric in parsed.metrics}
    assert (
        metrics_by_field["general_stats.fastqc_raw_percent_gc"].data_contract_id
        == "fastqc:results"
    )
    assert {"fastqc:results", "salmon:results"} <= {
        contract.data_contract_id for contract in parsed.contracts
    }
    display_names = {
        field.field_id: field.display_name for field in parsed.contract_fields
    }
    assert display_names["general_stats.salmon_percent_mapped"] == "Percent mapped"
    assert display_names["general_stats.fastqc_raw_percent_gc"] == "Percent GC"
    srr_metrics = [
        metric
        for metric in parsed.metrics
        if metric.sample_id == "SRR3192396"
        and metric.field_id == "general_stats.fastqc_raw_percent_gc"
    ]
    assert {metric.source_observation_id for metric in srr_metrics} == {
        "multiqc:summary",
        "multiqc:r1",
    }
    assert {metric.run_id for metric in srr_metrics} == {"run-1:SRR3192396:analysis"}
    assert {metric.source_observation_label for metric in srr_metrics} == {
        "SRR3192396",
        "SRR3192396 R1",
    }
    assert parsed.payloads == []


def test_duckdb_store_round_trips_metrics_and_payloads(tmp_path: Path) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path / "results", sample_id="SRR3192396")
    parsed = parse_multiqc_bundle(multiqc_dir, run_id="run-1")
    store = DuckDBAnalyticsStore(tmp_path / "analytics.duckdb")

    store.write_batch(_resolved_multiqc_batch(parsed, run_id="run-1"))

    maps = _direct_catalog_maps(parsed, run_id="run-1")
    metrics = store.list_metric_values(maps["run_id"]["run-1:SRR3192396:analysis"])
    payloads = store.list_result_payloads(maps["run_id"]["run-1:SRR3192396:analysis"])
    mapped_percent_field_id = maps["field_id"]["general_stats.salmon_percent_mapped"]

    assert any(metric.field_id == mapped_percent_field_id for metric in metrics)
    assert payloads == []


def test_duckdb_store_keeps_json_looking_string_metrics_as_strings(
    tmp_path: Path,
) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path)
    parsed = parse_multiqc_bundle(multiqc_dir, run_id="run-1")
    store = DuckDBAnalyticsStore(tmp_path / "analytics.duckdb")

    parsed.sample_metric_string[0] = parsed.sample_metric_string[0].model_copy(
        update={"value_string": "[330, 612, 1140, 1989, 4614]"}
    )
    store.write_batch(_resolved_multiqc_batch(parsed, run_id="run-1"))

    metrics = store.list_metric_values(2)
    string_field_id = _direct_catalog_maps(parsed, run_id="run-1")["field_id"][
        parsed.sample_metric_string[0].field_id
    ]

    assert any(
        metric.value_string == "[330, 612, 1140, 1989, 4614]"
        for metric in metrics
        if metric.field_id == string_field_id
    )


def test_duckdb_store_inserts_non_integer_table_from_parquet(
    tmp_path: Path,
) -> None:
    store = DuckDBAnalyticsStore(tmp_path / "analytics.duckdb")
    store.ensure_schema()
    parquet_path = tmp_path / "features.parquet"

    with store._connect() as connection:
        connection.execute(f"""
            COPY (
                SELECT
                    'gene:tp53' AS feature_id,
                    'TP53' AS source_feature_id,
                    'gene' AS feature_type,
                    'TP53' AS symbol,
                    NULL AS stable_id,
                    NULL AS namespace,
                    NULL AS genome_build,
                    json_object() AS metadata_json
            ) TO {_sql_literal(parquet_path)} (FORMAT PARQUET)
            """)
        insert_public_parquet(
            connection,
            "features",
            (
                "feature_id",
                "source_feature_id",
                "feature_type",
                "symbol",
                "stable_id",
                "namespace",
                "genome_build",
                "metadata_json",
            ),
            parquet_path,
        )
        row = connection.execute(
            "SELECT symbol FROM features WHERE feature_id = ?",
            ["gene:tp53"],
        ).fetchone()

    assert _scalar(row) == "TP53"


def test_duckdb_store_replaces_integer_keyed_rows_from_parquet(
    tmp_path: Path,
) -> None:
    store = DuckDBAnalyticsStore(tmp_path / "analytics.duckdb")
    store.ensure_schema()
    first_path = tmp_path / "attrs-first.parquet"
    second_path = tmp_path / "attrs-second.parquet"
    columns = (
        "entity_scope",
        "entity_id",
        "field_id",
        "data_contract_id",
        "source_file_id",
        "value_type",
        "value_numeric",
        "value_string",
        "value_boolean",
        "value_datetime",
        "value_json",
    )

    with store._connect() as connection:
        for path, value in ((first_path, "old"), (second_path, "new")):
            connection.execute(f"""
                COPY (
                    SELECT
                        'sample' AS entity_scope,
                        'sample-1' AS entity_id,
                        'sample:status' AS field_id,
                        7::BIGINT AS data_contract_id,
                        NULL AS source_file_id,
                        'string' AS value_type,
                        NULL::DOUBLE AS value_numeric,
                        {value!r} AS value_string,
                        NULL::BOOLEAN AS value_boolean,
                        NULL::TIMESTAMP AS value_datetime,
                        NULL::JSON AS value_json
                ) TO {_sql_literal(path)} (FORMAT PARQUET)
                """)
        insert_public_parquet(connection, "entity_attributes", columns, first_path)
        delete_public_parquet(
            connection,
            "entity_attributes",
            ("entity_scope", "entity_id", "field_id", "data_contract_id"),
            second_path,
        )
        insert_public_parquet(
            connection,
            "entity_attributes",
            columns,
            second_path,
        )
        rows = connection.execute(
            "SELECT value_string FROM entity_attributes ORDER BY value_string"
        ).fetchall()

    assert rows == [("new",)]


def test_ingest_multiqc_creates_control_analytics_and_files(tmp_path: Path) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"

    result = ingest_multiqc(
        multiqc_dir,
        run_id="run-1",
        project="demo",
        analysis_type_id="rna_sequencing",
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )

    assert result.metrics_ingested > 0
    assert result.data_import_id == "run-1"
    assert result.files_stored == 4
    assert result.upstream_runs == 1
    assert result.run_relationships == 1
    assert analytics_path.exists()
    assert (file_root / "run-1" / "multiqc").exists()

    catalog_store = SQLModelGoodomicsStore(database_url)
    run = asyncio.run(catalog_store.get_run("run-1"))
    assert run is not None
    assert run.project == "demo"

    async def load_catalog() -> tuple[
        list[DataImportRecord],
        list[FileRecord],
        list[FileLinkRecord],
        list[RunRecord],
        list[RunSampleRecord],
        list[RunRelationshipRecord],
    ]:
        async with AsyncSession(catalog_store._get_engine()) as session:
            imports = (await session.exec(select(DataImportRecord))).all()
            files = (await session.exec(select(FileRecord))).all()
            runs = (await session.exec(select(RunRecord))).all()
            run_samples = (await session.exec(select(RunSampleRecord))).all()
            relationships = (await session.exec(select(RunRelationshipRecord))).all()
            run_row = (
                await session.exec(select(RunRecord).where(RunRecord.run_id == "run-1"))
            ).one()
            links = (
                await session.exec(
                    select(FileLinkRecord).where(FileLinkRecord.run_id == run_row.id)
                )
            ).all()
        return (
            list(imports),
            list(files),
            list(links),
            list(runs),
            list(run_samples),
            list(relationships),
        )

    imports, files, links, runs, run_samples, relationships = asyncio.run(
        load_catalog()
    )
    assert [data_import.data_import_id for data_import in imports] == ["run-1"]
    assert {run.run_id for run in runs} == {"run-1", "run-1:S1:analysis"}
    assert {run_sample.run_sample_id for run_sample in run_samples} == {
        "run-1:S1:analysis:S1"
    }
    assert len(relationships) == 1
    assert {file.file_role for file in files} == {
        "multiqc_data",
        "multiqc_log",
        "multiqc_parquet",
        "multiqc_report",
    }
    assert {link.file_id for link in links} == {file.id for file in files}
    assert {link.data_import_id for link in links} == {imports[0].id}


def test_ingest_multiqc_rnaseq_parquet_infers_upstream_runs(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"
    multiqc_dir = write_multiqc_fixture(tmp_path / "results", sample_id="SRR3192396")

    result = ingest_multiqc(
        multiqc_dir,
        run_id="rnaseq-report",
        project="demo",
        analysis_type_id="rna_sequencing",
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )

    assert result.upstream_runs == 1
    assert result.run_relationships == 1

    async def load_catalog() -> tuple[
        list[SubjectRecord],
        list[SampleRecord],
        list[RunRecord],
        list[RunSampleRecord],
        list[RunRelationshipRecord],
    ]:
        catalog_store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(catalog_store._get_engine()) as session:
            return (
                list((await session.exec(select(SubjectRecord))).all()),
                list((await session.exec(select(SampleRecord))).all()),
                list((await session.exec(select(RunRecord))).all()),
                list((await session.exec(select(RunSampleRecord))).all()),
                list((await session.exec(select(RunRelationshipRecord))).all()),
            )

    subjects, samples, runs, run_samples, relationships = asyncio.run(load_catalog())
    assert len(subjects) == 1
    assert len(samples) == 1
    assert len(runs) == 2
    assert len(run_samples) == 1
    assert len(relationships) == 1
    labels = {
        *{subject.subject_id for subject in subjects},
        *{sample.sample_id for sample in samples},
        *{run.run_id for run in runs},
        *{run_sample.run_sample_id for run_sample in run_samples},
    }
    assert "SRR3192396 R1" not in labels

    metrics = DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_url, "rnaseq-report:SRR3192396:analysis")
    )
    sample_pk = next(
        sample.id for sample in samples if sample.sample_id == "SRR3192396"
    )
    matching = [
        metric
        for metric in metrics
        if metric.source_observation_id
        in {"multiqc:summary", "multiqc:r1", "multiqc:r2"}
    ]
    assert {metric.sample_id for metric in matching} == {sample_pk}
    assert {metric.source_observation_id for metric in matching} >= {
        "multiqc:summary",
        "multiqc:r1",
    }


def test_ingest_multiqc_defaults_to_project_analytics_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    file_root = tmp_path / "state" / "files"

    result = ingest_multiqc(
        multiqc_dir,
        run_id="run-default-project",
        database_url=database_url,
        file_root=file_root,
    )

    expected_path = (
        Path(".goodomics") / "projects" / DEFAULT_PROJECT_ID / "analytics.duckdb"
    )
    assert result.analytics_path == expected_path
    assert (tmp_path / expected_path).exists()
    assert DuckDBAnalyticsStore(expected_path).list_metric_values(
        _run_pk(database_url, "run-default-project:S1:analysis")
    )


def test_ingest_multiqc_project_slug_uses_generated_project_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    file_root = tmp_path / "state" / "files"

    result = ingest_multiqc(
        multiqc_dir,
        run_id="run-project-slug",
        project="rnaseq-core",
        database_url=database_url,
        file_root=file_root,
    )

    catalog_store = SQLModelGoodomicsStore(database_url)
    run = asyncio.run(catalog_store.get_run("run-project-slug"))
    assert run is not None
    assert run.project_id is not None
    assert run.project_id.startswith("prj_")
    assert run.project_id != "rnaseq-core"
    assert result.analytics_path == (
        Path(".goodomics") / "projects" / run.project_id / "analytics.duckdb"
    )


def test_ingest_multiqc_runs_splits_parent_results_directory(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    write_multiqc_fixture(
        results_dir / "WT_REP1",
        sample_id="WT_REP1",
        report_prefix="WT_REP1",
    )
    write_multiqc_fixture(
        results_dir / "RAP1_IAA_30M_REP1",
        sample_id="RAP1_IAA_30M_REP1",
        report_prefix="RAP1_IAA_30M_REP1",
    )
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"

    results = ingest_multiqc_runs(
        results_dir,
        project="demo",
        analysis_type_id="rna_sequencing",
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )

    run_ids = {result.run_id for result in results}
    assert run_ids == {"RAP1_IAA_30M_REP1", "WT_REP1"}
    assert all(result.outputs_found == 1 for result in results)

    catalog_store = SQLModelGoodomicsStore(database_url)
    wt_run = asyncio.run(catalog_store.get_run("WT_REP1"))
    rap1_run = asyncio.run(catalog_store.get_run("RAP1_IAA_30M_REP1"))
    wt_upstream = asyncio.run(catalog_store.get_run("WT_REP1:WT_REP1:analysis"))
    rap1_upstream = asyncio.run(
        catalog_store.get_run("RAP1_IAA_30M_REP1:RAP1_IAA_30M_REP1:analysis")
    )
    assert wt_run is not None
    assert rap1_run is not None
    assert wt_upstream is not None
    assert rap1_upstream is not None
    assert "WT_REP1" in {sample.sample_id for sample in wt_upstream.samples}
    assert "RAP1_IAA_30M_REP1" in {sample.sample_id for sample in rap1_upstream.samples}
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_url, "WT_REP1:WT_REP1:analysis")
    )
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_url, "RAP1_IAA_30M_REP1:RAP1_IAA_30M_REP1:analysis")
    )
    assert (file_root / "WT_REP1" / "multiqc").exists()
    assert (file_root / "RAP1_IAA_30M_REP1" / "multiqc").exists()
